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
    '--baudrate', type=int, default=9600,
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
dev = serial.Serial(path, baudrate=9600, timeout=2.)
logger.info(
    'Sending signals "%s" to port %d', args.signal_name, args.signal_port)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

running = True
stats = util.StreamingStats(logger)
def stop():
    global running
    running = False
stats.catch_ctrlc(stop)

failures = 0
while failures < 10:
    try:
        line = dev.readline().decode('utf8').strip('\n\r')
        failures = 0
    except serial.serialutil.SerialException:
        failures += 1
        print(f'Caught SerialException ({failures}) - probably Arduino restarted.')
        time.sleep(1)
        continue
    except UnicodeDecodeError:
        failures += 1
        print('Caught UnicodeDecodeError ({failures}) - probably Arduino restarted.')
        time.sleep(1)
        continue
    if line:
        value = int(line)
        network.send(args.signal_port, {
            args.signal_name: min(1, value / 100),
        })
        if stats(args.signal_name):
            logger.info('Current value=%d', value)
print()
print('closing...')
dev.close()
