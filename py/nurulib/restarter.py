"""Restarts programs & reports status."""

import signal, subprocess, sys, time

from . import network, util

waits_i = 0
waits_secs = [2, 4, 10, 10, 10, 60]
waits_reset_secs = 60

logger = util.createLogger('restarter')

argv = list(sys.argv[1:])


def execute_fc(argv):
    process = subprocess.Popen(
        # argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    out_iter = iter(process.stdout.readline, '')
    # err_iter = iter(process.stderr.readline, '')
    for output in out_iter:
        print(output, end='')
        if (
        'detached' in output or
        'Fadecandy: Access denied' in output):
            logger.info('KILLING fcserver')
            process.kill()
            break


stats = 'initial'
name = 'restarter_{}'.format(' '.join(argv[1:]))
status_sender = network.StatusSender(name, logger=logger)

signal.signal(signal.SIGINT, signal.SIG_IGN)
counter = 0
times_log = []
waits_log = []
while True:
    status_sender.send(stats)
    started = time.time()
    if './fcserver' in argv:
        logger.info('starting fadecandy {}'.format(argv))
        execute_fc(argv)
    else:
        logger.info('starting {}'.format(argv))
        subprocess.run(argv)
    stopped = time.time()
    times_log.append(int(stopped - started))
    counter += 1
    if stopped - started > waits_reset_secs:
        waits_i = 0
    wait = waits_secs[min(waits_i, len(waits_secs) - 1)]
    waits_log.append(wait)
    waits_i += 1
    logger.info('stopped, waiting {} seconds'.format(wait))
    time.sleep(wait)
    stats = 'counter={} times_log={} waits_log={}'.format(
        counter, times_log, waits_log
    )
