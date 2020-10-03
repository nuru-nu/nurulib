"""UDP MIDI bridge.

Note on OS X (tested on 10.14.6):

1. Open Audio MIDI Setup
2. Menu : Window -> Show MIDI Studio
3. Double click on 'IAC Driver'
4. Enable 'Device is Online' with ports 'Bus 1'
5. List MIDI ports by starting program `python -m smanmi.midi`

Note on Ableton Live:

1. Settings : Link MIDI : MIDI Port 'Input: IAC Driver (Bus 1)' enable 'Remote'
2. Click on 'MIDI' (top right button)
3. Agitate UI element to connect
4. Run `python -m smanmi.midi --send='0: C2 on'
       `python -m smanmi.midi --send='0: C2 off'
5. Settings : Link MIDI : Midi Port 'Output: IAC Driver (Bus 1)' enable 'Track'
   then instruments can be redirected to 'MIDI To'

Note on testing the setup:

1. `python -m smanmi.midi --cmd_port=7000`
2. `echo '{"midi": "0: C2 On"}' | nc -u 127.0.0.2 7000
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import functools
import re
import traceback
from typing import Sequence

import rtmidi_python as rtmidi

from . import util


class Command:
    """Represents a MIDI command.

    This class is hashable and uniquely identified by the string that was
    used to initialize it. Currently supported formats:
    
    - Note: '1: C#2 on' -> kind='note', name='1: C#2', value='on'
    - Controller: '3: X1=23' -> kind='controller', name='3: X1', value=23

    This scheme makes it easy to identify things by their "name" which is a
    combination of the channel and the actual MIDI note/controller name.
    """

    NOTE_RE = re.compile(
        r'(?P<channel>\d+): '
        r'(?P<letter>[A-G]#?)(?P<octave>-?\d+) (?P<value>\w+)')
    LETTERS = (
        'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'
    )

    CONTROLLER_RE = re.compile(
        r'(?P<channel>\d+): X(?P<number>\d+)=(?P<value>\d+)')

    def __init__(self, s: str):
        self.s = s
        m = self.NOTE_RE.match(s)
        if m:
            return self._parse_note(**m.groupdict())
        m = self.CONTROLLER_RE.match(s)
        if m:
            return self._parse_controller(**m.groupdict())
        raise ValueError(f'Could not parse MIDI Command: {s}')

    def _parse_note(self, channel, letter, octave, value):
        self.kind = 'note'
        channel = int(channel)
        assert 1 <= channel <= 16, channel
        self.channel = channel
        octave = int(octave)
        assert -2 <= octave <= 8, octave
        self._halftone = (
            24
            + int(octave) * 12
            + self.LETTERS.index(letter)
        )
        self.name = f'{channel}: {letter}{octave}'
        assert value in ('on', 'off'), value
        self.value = value
        if value == 'on':
            self.bytes = (
                0x90 + self.channel - 1,
                self._halftone,
                100,
            )
        if value == 'off':
            self.bytes = (
                0x80 + self.channel - 1,
                self._halftone,
                100,
            )

    def _parse_controller(self, channel, number, value):
        self.kind = 'controller'
        channel = int(channel)
        assert 1 <= channel <= 16, channel
        self.channel = channel
        value = int(value)
        number = int(number)
        self.name = f'{channel}: X{number}'
        self.value = value
        self.bytes = (
            0xA0 + channel - 1,
            number,
            value,
        )

    def __str__(self) -> str:
        return self.s

    def __repr__(self) -> str:
        return f'Command("{self}")"'

    def __eq__(self, other: object) -> bool:
        return self.s == other.s  # type: ignore

    def __hash__(self) -> int:
        return hash(self.s)

    @classmethod
    def from_bytes(cls, bytes: Sequence[int]) -> 'Command':
        """Parses from `.bytes` for raises ValueError."""
        if len(bytes) == 3:
            channel = (bytes[0] & 0xF) + 1
            if bytes[0] >> 4 in (8, 9):
                octave = (bytes[1] // 12) - 2
                note = cls.LETTERS[bytes[1] % 12]
                command = 'on' if bytes[0] >> 4 == 9 else 'off'
                return cls(f'{channel}: {note}{octave} {command}')
            elif bytes[0] >> 4 == 0xA:
                return cls(f'{channel}: X{bytes[1]}={bytes[2]}')
        raise ValueError(f'Cannot parse MIDI bytes : {bytes}')


class Midi:

    def __init__(self, logger, echo=False):
        """Initializes MIDI connection.

        Args:
          logger: Logger for logging output.
          echo: Whether signals sent to MIDI out should be echo-ed in MIDI in
        """
        self.logger = logger
        self.echo = echo
        self.sent = set()
        self.listeners = set()

        midi = rtmidi.MidiOut(b'smanmi')
        self.midi_outs = []
        for port, name in enumerate(midi.ports):
            midi_out = rtmidi.MidiOut(b'smanmi')
            midi_out.open_port(port)
            self.midi_outs.append(midi_out)
            logger.info(
                'MIDI output port #%d : "%s"', port, name.decode('ascii'))
        assert self.midi_outs, 'No output ports, check module pydoc!'
        if len(self.midi_outs) > 1:
            logger.warning('Sending MIDI signals to >1 output ports!')

        midi = rtmidi.MidiIn(b'smanmi')
        self.midi_ins = []
        for port, name in enumerate(midi.ports):
            midi_in = rtmidi.MidiIn(b'smanmi')
            midi_in.callback = functools.partial(self.callback, port)
            midi_in.open_port(port)
            self.midi_ins.append(midi_in)
            logger.info(
                'MIDI input port #%d : "%s"', port, name.decode('ascii'))
        assert self.midi_ins, 'No input ports, check module pydoc!'

    def send(self, command: Command):
        self.sent.add(command)
        for midi_out in self.midi_outs:
            midi_out.send_message(command.bytes)

    def callback(self, port, message, timestamp):
        command = Command.from_bytes(message)
        if command in self.sent:
            self.sent.remove(command)
            if not self.echo:
                return
        if not command:
            self.logger.info('Ignoring message %s', message)
            return
        self.logger.info('Received %s', command)
        for listener in self.listeners:
            listener(command)

    def add_listener(self, listener):
        self.listeners.add(listener)


class UdpInbound:

    def __init__(self, midi_forwarder, logger):
        self.midi_forwarder = midi_forwarder
        self.logger = logger

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.midi_forwarder.datagram_received(data)

class UdpOutbound(asyncio.DatagramProtocol):

    def __init__(self, midi_forwarder):
        self.midi_forwarder = midi_forwarder

    def connection_made(self, transport):
        self.midi_forwarder.register_transport(transport)


def signal2midi(data, logger):
    if 'midi' in data:
        command = Command.parse(data['midi'])
        if command:
            return (command,)
        else:
            logger.warning('Cannot parse midi command: %s', data['midi'])
    return ()


def midi2signal(command, logger):
    return (dict(midi=str(command)),)


class MidiForwarder:

    def __init__(self, midi, cmd_address_port, signal_address_port, logger):
        self.cmd_address, self.cmd_port = cmd_address_port
        self.signal_address, self.signal_port = signal_address_port
        self.logger = logger
        self.midi = midi
        self.midi.add_listener(self.got_midi)
        self.transport = None
        self.signal2midis = {signal2midi}
        self.midi2signals = {midi2signal}

    def start(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)
        if self.cmd_port:
            self.logger.info(
                'Listening on %s:%d', self.cmd_address, self.cmd_port)
            loop.run_until_complete(
                loop.create_datagram_endpoint(
                    lambda: UdpInbound(self, self.logger),
                    local_addr=(self.cmd_address, self.cmd_port)))
        if self.signal_port:
            self.logger.info(
                'Sending UDP to %s:%d', self.signal_address, self.signal_port)
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: UdpOutbound(self),
                remote_addr=(self.signal_address, self.signal_port)))
        loop.run_forever()

    def register_transport(self, transport):
        if self.transport is not None:
            self.logger.warning('Reregistering transport')
        self.transport = transport

    def datagram_received(self, data):
        data = util.deserialize(data)
        for signal2midi in self.signal2midis:
            for command in signal2midi(data, self.logger):
                self.logger.info('Sending %s', command)
                self.midi.send(command)

    def got_midi(self, command):
        for midi2signal in self.midi2signals:
            for data in midi2signal(command, self.logger):
                self.transport.sendto(util.serialize(data))

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bridges UDP to MIDI.')

    parser.add_argument('--cmd_address', type=str, default='127.0.0.1',
                        help='IP address to listen at.')
    parser.add_argument('--cmd_port', type=int, default=0,
                        help='UDP cmd_port to listen at for commands.')

    parser.add_argument('--signal_address', type=str, default='127.0.0.1',
                        help='IP address to send UDP packets to.')
    parser.add_argument('--signal_port', type=int, default=0,
                        help='UDP signal_port to forwarad MIDI signals to.')

    parser.add_argument('--send', type=str, default=None,
                        help='Send single command.')

    logger = util.createLogger('midi')
    args = parser.parse_args()

    midi = Midi(logger)

    if args.send:
        midi.send(args.send)

    if args.cmd_port or args.signal_port:
        forwarder = MidiForwarder(
            midi=midi,
            cmd_address_port=(args.cmd_address, args.cmd_port),
            signal_address_port=(args.signal_address, args.signal_port),
            logger=logger,
        )
        forwarder.start()
