"""UDP MIDI bridge.

Note on OS X (tested on 10.14.6):

1. Open Audio MIDI Setup
2. Menu : Window -> Show MIDI Studio
3. Double click on 'IAC Driver'
4. Enable 'Device is Online' with ports 'Bus 1'
5. List MIDI ports by starting program `python -m smanmi.midi`

Note on Ableton Live:

1. Preferences : Link MIDI : MIDI Port 'IAC Driver (Bus 1)' enable 'Remote'
2. Click on 'MIDI' (top left button)
3. Agitate UI element to connect
4. Run `python -m smanmi.midi --send='0: C2 on'
       `python -m smanmi.midi --send='0: C2 off'

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
from typing import List
from typing import Optional

import rtmidi_python as rtmidi

from . import util


class Note(collections.namedtuple('Note', 'port letter octave')):
    """Represents a MIDI note on a specific port."""

    RE = re.compile(r'(?P<port>\d+): (?P<letter>[A-G]#?)(?P<octave>-?\d+)')
    LETTERS = (
        'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'
    )

    def __new__(cls, port: int, letter: str, octave: int):
        assert port >= 0, port
        assert letter in cls.LETTERS, letter
        assert octave >= -2 and octave <= 8, octave
        return super().__new__(cls, port, letter, octave)

    def __str__(self):
        return f'{self.port}: {self.letter}{self.octave}'

    @property
    def value(self) -> int:
        return (
            24
            + self.octave * 12
            + self.LETTERS.index(self.letter)
        )

    @classmethod
    def parse(cls, s: str) -> Note:
        m = cls.RE.match(s)
        if not m:
            return None
        return cls(
            int(m.group('port')), m.group('letter'), int(m.group('octave')))

    @classmethod
    def from_value(cls, port: int, value: int) -> Note:
        letter = cls.LETTERS[value % 12]
        octave = value // 12 - 2
        return cls(port, letter, octave)


class Controller(collections.namedtuple('Controller', 'port number value')):
    """Represents a continuous MIDI controller value."""

    RE = re.compile(r'(?P<port>\d+): X(?P<number>\d+)=(?P<value>\d+)')

    def __new__(cls, port: int, number: int, value: int):
        assert port >= 0, port
        assert number >= 0 and number <= 119, number
        assert value >= 0 and value <= 127
        return super().__new__(cls, port, number, value)

    def __str__(self):
        return f'{self.port}: X{self.number}={self.value}'

    @classmethod
    def parse(cls, s: str) -> Controller:
        m = cls.RE.match(s)
        if not m:
            return None
        print(m.groups())
        return cls(
            int(m.group('port')), int(m.group('number')), int(m.group('value'))
        )


# TODO clean up this mess !
class Command(collections.namedtuple('Command', 'note command controller')):
    """Represents a MIDI command."""

    COMMANDS = (
        'on', 'off'
    )

    def __new__(cls, port: int, note: Optional[Note] = None,
                command: Optional[str] = None,
                controller: Optional[Controller] = None):
        if note:
            assert command in cls.COMMANDS, command
            assert not controller, controller
            assert port == note.port, (port, note.port)
            return super().__new__(cls, note, command, None)
        assert controller, controller
        assert port == controller.port, (port, controller.port)
        return super().__new__(cls, None, None, controller)

    def __str__(self):
        if self.note:
            return f'{str(self.note)} {self.command}'
        else:
            return str(self.controller)

    @property
    def bytes(self) -> List[int]:
        if self.controller:
            return [0xA0, self.controller.number, self.controller.value]
        if self.command == 'on':
            return [0x90, self.note.value, 100]
        if self.command == 'off':
            return [0x80, self.note.value, 100]

    @classmethod
    def parse(cls, s: str) -> Note:
        controller = Controller.parse(s)
        if controller:
            return cls(port=controller.port, controller=controller)
        idx = s.rindex(' ')
        if idx < 0:
            return None
        note = Note.parse(s[:idx])
        if note is None:
            return None
        cmd = s[idx + 1:]
        if cmd not in cls.COMMANDS:
            return None
        return cls(port=note.port, note=note, command=cmd)

    @classmethod
    def from_bytes(cls, port: int, message: List[int]) -> Command:
        if message[0] == 0xA0:
            return cls(port, controller=Controller(port, *message[1:]))
        note = Note.from_value(port, message[1])
        if message[0] == 0x90:
            return cls(port=note.port, note=note, command='on')
        if message[0] == 0x80:
            return cls(port=note.port, note=note, command='off')


class Midi:

    def __init__(self, logger, echo=False):
        """Initializes MIDI connection.

        Args:
          logger: Logger for logging output.
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

        midi = rtmidi.MidiIn(b'smanmi')
        self.midi_ins = []
        for port, name in enumerate(midi.ports):
            midi_in = rtmidi.MidiIn(b'smanmi')
            midi_in.callback = functools.partial(self.callback, port)
            midi_in.open_port(port)
            self.midi_ins.append(midi_in)
            logger.info(
                'MIDI input port #%d : "%s"', port, name.decode('ascii'))

    def send(self, command: Command):
        self.sent.add(command)
        self.midi_outs[command.note.port].send_message(command.bytes)

    def callback(self, port, message, timestamp):
        command = Command.from_bytes(port, message)
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
