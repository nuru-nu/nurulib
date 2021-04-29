import argparse
import glob
import socket
import time
import threading

import serial

from . import network
from . import util


# TODO: Make more stable (e.g. ignore decoding errors due to restart).
# TODO: Make work with multiple Arduinos (different signal names).

sensors = {
    "S" : "sonar",
    "P" : "pir"
}

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
    '--signal_name', type=str,
    help='Signal name.'
)
parser.add_argument(
    '--dev_glob', nargs='+', type=str, default='/dev/cu.usbmodem*',
    help='Glob to match device (alphabetically first match is used).'
)
args = parser.parse_args()
logger = util.createLogger('arduino')

running = True
def stop():
    global running
    running = False

def sensor_read(path):
    logger.info('Opening device %s', path)
    dev = serial.Serial(path, baudrate=args.baudrate, timeout=2.)
    logger.info(
        'Sending signals to port %d', args.signal_port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    failures = 0
    last_values = values = None
    def info_getter():
        nonlocal last_values
        return last_values
    stats = util.StreamingStats(logger)
    stats.catch_ctrlc(stop, info_getter)

    while running and failures < 10:
        values = None
        signal_name = None
        try:
            line = dev.readline().decode('utf8').strip('\n\r')
            signal_name = sensors[line[0]]
            if line:
                last_values = values = [int(value) for value in line[2:].split(',')]

            failures = 0
        except Exception as e:
            failures += 1
            print(f'Caught {e} ({failures}) - probably Arduino restarted.')
            time.sleep(1)
            continue
        if values and signal_name:
            # maxval = max(maxval, value)
            network.send(args.signal_port, {
                f'{signal_name}_{i}': value
                for i, value in enumerate(values)
            })
            if stats(signal_name):
                logger.info('Current values=%s', values)
    
    logger.info('\nClosing=%s', path)
    dev.close()

paths = sorted([p for path in args.dev_glob for p in glob.glob(path)])

logger.info(f'Found {len(paths)} devices at paths {paths}')

threads = []
for path in paths:
    threads.append(threading.Thread(target=sensor_read, args=(path,)))
    threads[-1].start()


