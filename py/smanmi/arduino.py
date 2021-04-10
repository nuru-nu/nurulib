import argparse
import glob
import socket
import time

import serial

from . import network
from . import util


# TODO: Make more stable (e.g. ignore decoding errors due to restart).
# TODO: Make work with multiple Arduinos (different signal names).


parser = argparse.ArgumentParser(description='Reads data from Arduino.')
parser.add_argument(
    '--signal_port', type=int, required=True,
    help='What port to send signal to.'
)
parser.add_argument(
    '--baudrate', type=int, default=57600,
    help='What baudrate to use.'
)
parser.add_argument(
    '--signal_name', type=str, required=True,
    help='Signal name.'
)
parser.add_argument(
    '--dev_glob', type=str, default='/dev/cu.usbmodem*',
    help='Glob to match device (alphabetically first match is used).'
)
args = parser.parse_args()
logger = util.createLogger('arduino')
path = sorted(glob.glob(args.dev_glob))[0]
logger.info('Opening device %s', path)
dev = serial.Serial(path, baudrate=args.baudrate, timeout=2.)
logger.info(
    'Sending signals "%s" to port %d', args.signal_name, args.signal_port)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

running = True
failures = 0
last_values = values = None

def info_getter():
    global last_values
    return last_values
def stop():
    global running
    running = False
stats = util.StreamingStats(logger)
stats.catch_ctrlc(stop, info_getter)

while running and failures < 10:
    values = None
    try:
        line = dev.readline().decode('utf8').strip('\n\r')
        if line:
            last_values = values = [int(value) for value in line.split(',')]
        failures = 0
    except Exception as e:
        failures += 1
        print(f'Caught {e} ({failures}) - probably Arduino restarted.')
        time.sleep(1)
        continue
    if values:
        # maxval = max(maxval, value)
        network.send(args.signal_port, {
            f'{args.signal_name}_{i}': value
            for i, value in enumerate(values)
        })
        if stats(args.signal_name):
            logger.info('Current values=%s', values)
print()
print('closing...')
dev.close()
