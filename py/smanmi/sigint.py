"""Ctrl-C handling for outputting data and gracefully shutting down."""

import signal
import sys
import time


ctrlc_handlers = set()
ctrlc2_handlers = set()
ctrlc_t0 = 0
original_handler = signal.getsignal(signal.SIGINT)


def register_ctrlc_handler(handler):
    ctrlc_handlers.add(handler)


def register_ctrlc2_handler(handler):
    ctrlc2_handlers.add(handler)


def sigint_handler(*_):
    global ctrlc_t0
    t = time.time()
    if t - ctrlc_t0 < 1.0:
        print('\n\n### caught 2x CTRL-C ###\n\n', file=sys.stderr)
        handlers = ctrlc2_handlers
    else:
        print('\n# caught CTRL-C #\n', file=sys.stderr)
        handlers = ctrlc_handlers
    ctrlc_t0 = t
    for handler in handlers:
        handler()
    if not handlers:
        print('=> no handlers registered : default action\n', file=sys.stderr)
        original_handler()


signal.signal(signal.SIGINT, sigint_handler)
