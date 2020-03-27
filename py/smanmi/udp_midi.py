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
4. Run `python -m smanmi.udp_midi --midi_name='IAC Driver Bus 1' --send=C2

Note on testing the setup:

1. `python -m smanmi.udp_midi --midi_name='IAC Driver Bus 1' --port=7000`
2. `echo '{"midi": "C2"}' | nc -u 127.0.0.2 7000
"""

import argparse
import asyncio
import traceback

import rtmidi_python as rtmidi

from . import util


class Midi:

    def __init__(self, port_name, logger):
        """Initializes MIDI connection.

        Args:
          port_name: Can be number, complete port name, or partial name.
          logger: Logger for logging output.
        """
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
        logger.info(
            'Using port %s', self.midi_out.ports[port].decode('ascii'))
        self.midi_out.open_port(port)

    def send(self, note):
        letters = (
            'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'
        )
        # C2 == 48
        value = letters.index(note[:-1]) + int(note[-1]) * 12 + 24
        self.midi_out.send_message([0x90, value, 100])  # Note on
        self.midi_out.send_message([0x80, value, 100])  # Note off


class MidiProtocol:

    def __init__(self, midi, logger):
        self.midi = midi
        self.logger = logger

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        data = util.deserialize(data)
        midi = data.get('midi')
        if midi:
            self.logger.info('Sending %s', midi)
            self.midi.send(midi)


def exception_handler(self, loop, context):
    logger.error(
        'Caught exception: %r\n%s:\n%s\n',
        context['exception'], context['message'],
        ''.join(traceback.format_list(context['source_traceback'])))


parser = argparse.ArgumentParser(description='Bridges UDP to MIDI.')
parser.add_argument('--address', type=str, default='127.0.0.1',
                    help='IP address to listen at.')
parser.add_argument('--port', type=int, default=7000,
                    help='UDP port to listen at.')
parser.add_argument('--send', type=str, default=None,
                    help='Send single command instead of listening to UDP.')
parser.add_argument('--midi_name', type=str, default='0',
                    help='Midi port name to send commands to. If set to a '
                    'number then that is used as an index to the ports '
                    'enumerated by rtmidi.MidiOut().')
args = parser.parse_args()

logger = util.createLogger('udp_midi')
midi = Midi(args.midi_name, logger)

if args.send is None:
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    loop.set_exception_handler(exception_handler)
    logger.info('Listening on %s:%d', args.address, args.port)
    loop.run_until_complete(
        loop.create_datagram_endpoint(
            lambda: MidiProtocol(midi, logger),
            local_addr=(args.address, args.port)))
    loop.run_forever()
else:
    midi.send(args.send)
