
import collections
import datetime
import json
import logging
import os
import socket
import sys
import time
import traceback

import numpy as np  # type: ignore

from . import logic as L
from . import sigint


FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOGDIR = './logs'


# Will be set when `createLogger()` is called the first time.
logger: logging.Logger = logging.getLogger()


class Colorize:
    # https://stackoverflow.com/questions/4842424
    ANSI_RESET = '\033[0m'
    ANSI_MAP = {
        logging.INFO: '\033[1m',  # bold
        logging.WARNING: '\033[33m',  # yellow
        logging.ERROR: '\033[91m',  # bright red
        logging.FATAL: '\033[30;101m',  # black on bright red
    }

    def __init__(self, formatter):
        self.formatter = formatter

    def format(self, record):
        return ''.join([
            self.ANSI_MAP.get(record.levelno, self.ANSI_RESET),
            self.formatter.format(record),
            self.ANSI_RESET
        ])

    def __getattr__(self, name):
        return getattr(self.formatter, name)


def createLogger(name, stderr=True, logfile=True, colored=True, debug=True):  # noqa: N802, E501
    """Also updates module's `logger` to newly initialized logger."""
    global logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    formatter = logging.Formatter(FORMAT)
    if stderr:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(Colorize(formatter) if colored else formatter)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    if logfile:
        path = os.path.join(LOGDIR, name + '.log')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = logging.FileHandler(path)
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
    return logger


class NoLogger:
    def info(*args, **kw):
        pass

    def warn(*args, **kw):
        pass

    def warning(*args, **kw):
        pass

    def debug(*args, **kw):
        pass

    def error(*args, **kw):
        pass


class XtermScale(object):

    def __init__(self, f, n):
        def hex2tuple(color):
            return (int(color[:2], 16) / 255.,
                    int(color[2:4], 16) / 255.,
                    int(color[4:], 16) / 255.)
        colors = [
            hex2tuple(color)
            for color in json.load(open('colors.json'))
        ]

        def colordist(c1, c2):
            # https://en.wikipedia.org/wiki/Color_difference
            return sum([((a - b)**2) for a, b in zip(c1, c2)]) ** .5

        def closest(c):
            return min([(colordist(c, color), i)
                        for i, color in enumerate(colors)])[1]

        self.scale = [
            closest(f(1. * i / (n - 1))[:3])
            for i in range(n)
        ]

    def __call__(self, x):
        i = int(len(self.scale) * min(1, max(0, x)))
        return self.scale[min(i, len(self.scale) - 1)]


def int16_to_float(a):
    if a.dtype.name == 'int16':
        a = (a / 32768.0).astype(np.float32)
    return a


def float_to_int16(a):
    if not a.dtype.name == 'int16':
        a = (a * 32768.0).astype('int16')
    return a


serializers = {}


def register_serializer(name):
    """Registers [de]serializer `cls` for signal with `name`.

    Deerialization is performed via single constructor argument and
    serialization is performed by callint `repr()` on the instance.
    """
    def wrapped(cls):
        serializers[name] = cls
        return cls
    return wrapped


def pythonize(d):
    """Transforms numpy arrays, float32, int64 to native Python dtypes."""
    if isinstance(d, dict):
        return {pythonize(k): pythonize(v) for k, v in d.items()}
    if isinstance(d, np.ndarray) or isinstance(d, list):
        return [pythonize(v) for v in d]
    if isinstance(d, np.float32):
        return float(d)
    if isinstance(d, np.int64):
        return int(d)
    if isinstance(d, collections.abc.KeysView):
        return list(d)
    return d


def serialize(signals, indent=None):
    """Serializes `signals` to UTF8, also serializing "state" etc."""
    return json.dumps(pythonize({
        name: repr(sig) if name in serializers else sig
        for name, sig in signals.items()
    }), indent=indent).encode('utf8')


def deserialize(msg):
    """Does the opposite of `serialize()`."""
    if isinstance(msg, bytes):
        msg = msg.decode('utf8')
    signals = json.loads(msg)
    return {
        name: serializers.get(name, lambda x: x)(sig)
        for name, sig in signals.items()
    }


class Streamer:
    """Access array in buf_size-sized chunks hop_size apart."""

    def __init__(self, data, buf_size, hop_size):
        self.i = 0
        self.data = data
        self.buf_size = buf_size
        self.hop_size = hop_size

    def __iter__(self):
        return self

    def __next__(self):
        if self.i >= len(self.data):
            raise StopIteration
        ret = self.data[self.i:self.i + self.buf_size]
        self.i += self.hop_size
        if len(ret) < self.buf_size:
            ret = np.pad(ret, [(0, self.buf_size - len(ret))], mode='constant')
        return ret


def apply_effect(wav, effect, hop_size):
    """Applies `effect()` to `wav`, hop by hop."""
    ret = np.zeros(len(wav), dtype=wav.dtype)
    i1 = 0
    for buf in Streamer(wav, hop_size=hop_size, buf_size=hop_size):
        i2 = i1 + len(buf)
        ret[i1: i2] = effect(buf)
        i1 = i2
    return ret


def get_signals(wav, signals, hop_secs, wav2features):
    """Iterates through `wav` and computes values for `signals`."""
    runner = L.SignalRunner(signals, ('features', 't', 'signalin', 'state'))
    values = collections.defaultdict(lambda: [])
    t = 0
    for buf in Streamer(wav):
        feats = wav2features(buf)
        sigs = runner(features=feats, t=t, signalin={})
        for name, value in sigs.items():
            values[name].append(value)
        t += hop_secs
    return dict(**values)


class RollingBuffer:
    def __init__(self, buf_size):
        self.buf = np.zeros(buf_size, dtype=np.float32)

    # TODO only roll() once.
    def __call__(self, buf):
        if len(self.buf) and len(buf):
            self.buf = np.roll(self.buf, shift=-len(buf))
            self.buf[-(len(buf)):] = buf


def phi_theta_samples(n):
    phi_samples = np.random.uniform(size=n) * 2 * np.pi
    theta = np.linspace(0, np.pi / 2, 200)
    pdf = np.sin(theta)
    cdf = pdf.cumsum()
    cdf /= cdf[-1]
    u = np.random.uniform(size=n)
    theta_samples = np.searchsorted(cdf, u) / len(cdf) * (np.pi / 2)
    return phi_samples, theta_samples


class PrintEvery:
    def __init__(self, dt):
        self.dt = dt
        self.t0 = 0

    def __call__(self, msg):
        if self.dt > 0 and time.time() - self.t0 > self.dt:
            self.t0 = time.time()
            print(msg)


_print_every = {}
def print_every(name, msg, dt=5):
    if name not in _print_every:
        _print_every[name] = PrintEvery(dt)
    _print_every[name](msg)


def except_kill(func):
    """Kills the program if any exception is encountered."""
    def wrapper(*args, **kw):
        try:
            return func(*args, **kw)
        except:  # NOQA
            print('#### EXITING ####')
            traceback.print_exception(*sys.exc_info())
            os._exit(-999)
    return wrapper


def machine_name():
    return socket.gethostname()


class Timetracer:
    """Traces time [ms] in text file."""

    def __init__(self, name, timetraces_dir, flush_secs=5):
        path = '{}/{}/{}.txt'.format(
            timetraces_dir, machine_name(), name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, 'w')
        self.t0 = int(time.time() * 1e3)
        self.flush_secs = flush_secs

    def __call__(self):
        t = int(time.time() * 1e3)
        self.f.write('{}\n'.format(t))
        if t - self.t0 > self.flush_secs * 1e3:
            self.f.flush()
            self.t0 = t


class StreamingStats:
    """Helper class to periodically show stats."""

    def __init__(self, logger, hz=0.01, delay0=1.0):
        self.logger = logger
        self.t0 = time.time() - 1 / hz + delay0
        self.total = {}
        self.totaltotal = {}
        self.n = {}
        self.hz = hz
        self.info_getter = None

    def catch_ctrlc(self, shutdown_callback, info_getter=None):
        sigint.register_ctrlc_handler(self.dump)
        sigint.register_ctrlc2_handler(shutdown_callback)
        self.info_getter = info_getter

    def sigint_handler(self, *_):
        print()
        self.dump_reset()

    def dump(self):
        """Dumps stats to logger.info()."""
        dt = time.time() - self.t0
        for name in sorted(self.total):
            self.logger.debug(
                'stats[%s] : %.1f fps %.1f kps (sum %.1fM) -- %s',
                name, self.n[name] / dt, self.total[name] / dt / 1e3,
                self.totaltotal[name] / 1e6,
                self.info_getter() if self.info_getter else '')

    def dump_reset(self):
        self.dump()
        self.t0 = time.time()
        for name in self.n:
            self.n[name] = self.total[name] = 0

    def __call__(self, name, s=None):
        """"Adds `s` to stats and calls dump() every 1/hz seconds."""
        if name not in self.n:
            self.n[name] = self.total[name] = self.totaltotal[name] = 0
        self.n[name] += 1
        if s is not None:
            self.total[name] += len(s)
            self.totaltotal[name] += len(s)
        dt = time.time() - self.t0
        if dt * self.hz >= 1:
            self.dump_reset()
            return True
        return False


def pad_fadecandy(values):
    """Adds 4 zero RGBs after every 60 values."""
    zeros = np.zeros((4, 3), 'uint8')
    return np.concatenate([
        np.concatenate([
            values[i0: i0 + 60],
            zeros
        ])
        for i0 in range(0, values.shape[0], 60)
    ])


def now():
    return datetime.datetime.now().strftime('%Y%m%d_%H%M%S')


class KeyCounter:
    """Counts occurences of data keys in sliding window."""

    def __init__(self, secs=1):
        self.secs = secs
        self.counts = collections.defaultdict(int)
        self.events = collections.deque()

    def __call__(self, data):
        if not isinstance(data, dict):
            data = deserialize(data)
        t = time.time()
        for key in data:
            self.counts[key] += 1
            self.events.append((t, key))
        while self.events and self.events[0][0] < t - self.secs:
            _, key = self.events.popleft()
            self.counts[key] -= 1


def print_exc(fun):
    """Useful when executing code async."""
    def wrapped():
        try:
            fun()
        except Exception as e:
            import traceback
            logger.error('uncaught exception : %s', e)
            logger.warning(traceback.format_exc())
    return wrapped
