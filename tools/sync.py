"""Syncs files via ssh.

Synopsis:

python sync.py *.py arduino/plot_sonar/src/plot_sonar.ino mgcs:mgcs/


Note: Arduino file is NOT automagically compiled & sketched, you might want to

ssh mgcs 'cd mgcs/arduino/plot_sonar && /home/pi/.local/bin/ino build && /home/pi/.local/bin/ino upload'

"""

import argparse
import os
import time

import util


SYNC_COMMAND_FMT = 'scp {filename} {dst}'

parser = argparse.ArgumentParser('Poll file updates & sync via SSH.')
parser.add_argument('--ms', type=int, default=500,
                    help='How often to poll files.')
parser.add_argument('--flush', action='store_true',
                    help='Whether all files should be copied initially.')
parser.add_argument('files_and_dst', type=str, nargs='+',
                    help='Files to sync, last element is scp-style destination.')

args = parser.parse_args()
filenames, dst = args.files_and_dst[:-1], args.files_and_dst[-1]

logger = util.createLogger('sync')

mtimes = {
    filename: 0 if args.flush else int(os.stat(filename).st_mtime)
    for filename in filenames
}
logger.info('Starting syncing %s', filenames)
while True:
    time.sleep(args.ms / 1000.)
    for filename in filenames:
        mtime = int(os.stat(filename).st_mtime)
        if mtime <= mtimes[filename]:
            continue
        print(filename, mtime, mtimes[filename])
        logger.info('syncing %s...', filename)
        status = os.system(SYNC_COMMAND_FMT.format(
            filename=filename,
            dst=os.path.join(dst, os.path.dirname(filename))))
        if status != 0:
            logger.error('could not sync!')
        mtimes[filename] = mtime

