"""UDP MIDI bridge.

Note on OS X (tested on 10.14.6):

1. Open Audio MIDI Setup
2. Menu : Window -> Show MIDI Studio
3. Double click on 'IAC Driver'
4. Enable 'Device is Online' with ports 'Bus 1'
5. Start this program with --midi_name='IAC Driver Bus 1'

Note on Ableton Live:

1. Preferences : Link MIDI : MIDI Port 'IAC Driver' enable 'Remote'
2. Click on 'MIDI' (top left button)
3. Agitate UI element to connewct
4. Run `python -m smanmi.midi --midi_name='IAC Driver Bus 1' --send='C2 on'
       `python -m smanmi.midi --midi_name='IAC Driver Bus 1' --send='C2 off'

Note on testing the setup:

1. `python -m smanmi.midi --midi_name='IAC Driver Bus 1' --cmd_port=7000`
2. `echo '{"midi": "C2"}' | nc -u 127.0.0.2 7000
"""

import argparse
import asyncio
import re
import traceback

import rtmidi_python as rtmidi

from . import util


class Midi:

    COMMAND = re.compile(
        r'(?P<letter>[A-G]#?)(?P<octave>-?\d+) (?P<command>.*)')

    def __init__(self, port_name, logger):
        """Initializes MIDI connection.

        Args:
          port_name: Can be number, complete port name, or partial name.
          logger: Logger for logging output.
        """
        self.logger = logger
        self.midi_out = rtmidi.MidiOut(b'nuru')
        port = None
        try:
            port = int(port_name)
        except ValueError:
            for i, name in enumerate(self.midi_out.ports):
                if port_name == name.decode('ascii'):
                    port = i
                    break
            if port is None:
                for i, name in enumerate(self.midi_out.ports):
                    if port_name in name.decode('ascii'):
                        port = i
                    break
        if port is None:
            raise ValueError(f'Could not find port_name={port_name}')
        self.logger.info(
            'Using port %s', self.midi_out.ports[port].decode('ascii'))
        self.midi_out.open_port(port)

    def send(self, command):
        m = Midi.COMMAND.match(command)
        if m is None:
            self.logger.warning('Could not parse command: %s', command)
            return
        letters = (
            'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'
        )
        # C2 == 48
        value = (
            24
            + int(m.group('octave')) * 12
            + letters.index(m.group('letter'))
        )
        if m.group('command') == 'on':
            self.midi_out.send_message([0x90, value, 100])
        elif m.group('command') == 'off':
            self.midi_out.send_message([0x80, value, 100])
        else:
            self.logger.warn('Did not understand command: %s', command)


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


class MidiForwarder:

    def __init__(self, address, cmd_port, logger, midi_name):
        self.address = address
        self.cmd_port = cmd_port
        self.logger = logger
        self.midi = Midi(midi_name, logger)

    def start(self):
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)
        self.logger.info('Listening on %s:%d', self.address, self.cmd_port)
        loop.run_until_complete(
            loop.create_datagram_endpoint(
                lambda: MidiProtocol(self.midi, self.logger),
                local_addr=(self.address, self.cmd_port)))
        loop.run_forever()

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))


parser = argparse.ArgumentParser(description='Bridges UDP to MIDI.')
parser.add_argument('--address', type=str, default='127.0.0.1',
                    help='IP address to listen at.')
parser.add_argument('--cmd_port', type=int, default=7000,
                    help='UDP cmd_port to listen at for commands.')
parser.add_argument('--send', type=str, default=None,
                    help='Send single command instead of listening to UDP.')
parser.add_argument('--midi_name', type=str, default='0',
                    help='Midi port name to send commands to. If set to a '
                    'number then that is used as an index to the ports '
                    'enumerated by rtmidi.MidiOut().')

if __name__ == '__main__':
    logger = util.createLogger('midi')
    args = parser.parse_args()

    if args.send is None:
        forwarder = MidiForwarder(
            address=args.address,
            cmd_port=args.cmd_port,
            midi_name=args.midi_name,
            logger=logger,
        )
        forwarder.start()
    else:
        midi = Midi(args.midi_name, logger)
        midi.send(args.send)
