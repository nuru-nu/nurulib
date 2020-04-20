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

import argparse
import asyncio
import functools
import re
import traceback

import rtmidi_python as rtmidi

from . import util


class Midi:

    COMMAND = re.compile(
        r'(?P<port>\d+): (?P<letter>[A-G]#?)(?P<octave>-?\d+) (?P<command>.*)')
    LETTERS = (
        'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'
    )

    def __init__(self, logger):
        """Initializes MIDI connection.

        Args:
          logger: Logger for logging output.
        """
        self.logger = logger
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

    def send(self, s):
        m = Midi.COMMAND.match(s)
        if m is None:
            self.logger.warning('Could not parse command: %s', s)
            return
        port = int(m.group('port'))
        # C2 == 48
        value = (
            24
            + int(m.group('octave')) * 12
            + self.LETTERS.index(m.group('letter'))
        )
        if m.group('command') == 'on':
            self.midi_outs[port].send_message([0x90, value, 100])
        elif m.group('command') == 'off':
            self.midi_outs[port].send_message([0x80, value, 100])
        else:
            self.logger.warning('Did not understand command: %s', s)

    def callback(self, port, message, timestamp):
        if message[0] == 0x80:
            command = 'off'
        elif message[0] == 0x90:
            command = 'on'
        else:
            self.logger.debug('Ignoring message %s', message)
            return
        value = message[1]
        letter = self.LETTERS[value % 12]
        octave = value // 12 - 2
        s = f'{port}: {letter}{octave} {command}'
        for listener in self.listeners:
            listener(s)

    def add_listener(self, listener):
        self.listeners.add(listener)


class MidiProtocol:

    def __init__(self, midi, logger):
        self.midi = midi
        self.logger = logger

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        data = util.deserialize(data)
        command = data.get('midi')
        if command is not None:
            self.logger.info('Sending %s', command)
            self.midi.send(command)


class UdpProtocol(asyncio.DatagramProtocol):

    def __init__(self, midi_forwarder):
        self.midi_forwarder = midi_forwarder

    def connection_made(self, transport):
        self.midi_forwarder.register_transport(transport)


class MidiForwarder:

    def __init__(self, midi, cmd_address_port, signal_address_port, logger):
        self.cmd_address, self.cmd_port = cmd_address_port
        self.signal_address, self.signal_port = signal_address_port
        self.logger = logger
        self.midi = midi
        self.midi.add_listener(self.send)
        self.transport = None

    def start(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)
        if self.cmd_port:
            self.logger.info(
                'Listening on %s:%d', self.cmd_address, self.cmd_port)
            loop.run_until_complete(
                loop.create_datagram_endpoint(
                    lambda: MidiProtocol(self.midi, self.logger),
                    local_addr=(self.cmd_address, self.cmd_port)))
        if self.signal_port:
            self.logger.info(
                'Sending UDP to %s:%d', self.signal_address, self.signal_port)
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: UdpProtocol(self),
                remote_addr=(self.signal_address, self.signal_port)))
        loop.run_forever()

    def register_transport(self, transport):
        if self.transport is not None:
            self.logger.warning('Reregistering transport')
        self.transport = transport

    def send(self, command):
        msg = util.serialize(dict(midi=command))
        self.transport.sendto(msg)

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))


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

if __name__ == '__main__':
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
