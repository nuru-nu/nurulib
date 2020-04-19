import os, time

import numpy as np  # type: ignore


def fmt_ns(ns):
    if ns > 10 * 1e9:
        return '{}s'.format(int(ns / 1e9))
    if ns > 10 * 1e6:
        return '{}m'.format(int(ns / 1e6))
    if ns > 10 * 1e3:
        return '{}µ'.format(int(ns / 1e3))
    return '{}n'.format(ns)


class Measurement:
    def __init__(self, times_n):
        a = np.array(times_n)
        self.n = len(a)
        self.mean_ns = int(a.mean())
        self.std_ns = int(a.std())

    def mean_std(self):
        return '{}±{}'.format(
            fmt_ns(self.mean_ns), fmt_ns(self.std_ns))

    def __str__(self):
        return 'Measurement({}, {})'.format(self.n, self.mean_std())

    def __repr__(self):
        return str(self)


class Timer:
    """Collect timing statistics about a repeated event."""
    def __init__(self, period_s=1, keep=1800):
        self.period_s = period_s
        self.keep = keep
        self.times_ns = []
        self.measurements = [None] * keep
        self.stats = []
        self.i = self.n = 0
        self.t0 = time.time()
        self.wasted_ns = 0

    def start(self):
        self.started = int(time.process_time() * 1e9)

    def stop(self):
        self.times_ns.append(int(time.process_time() * 1e9) - self.started)
        t = time.time()
        if t - self.t0 > self.period_s:
            ns = int(time.process_time() * 1e9)
            measurement = Measurement(self.times_ns)
            self.measurements[self.i % self.keep] = measurement
            self.i += 1
            self.times_ns = []
            self.t0 = t
            self.wasted_ns += int(time.process_time() * 1e9) - ns

    def measurement(self, ago=0):
        i = self.i - 1 - ago
        if i < 0:
            return None
        return self.measurements[i % self.keep]

    def __str__(self):
        return 'Timer({} - {}, ...)'.format(
            self.i, ', '.join([
                self.measurement(i).mean_std()
                for i in range(min(self.i, 10, self.keep))
            ]))

    def __repr__(self):
        return str(self)

    def measure(self, f):
        def wrapper(*k, **kw):
            self.start()
            ret = f(*k, **kw)
            self.stop()
            return ret
        return wrapper


timers = {}
log_file_path = log_period_s = log_t0 = None


def measure(name, period_s=1, keep=10):
    global timers
    if name not in timers:
        timers[name] = Timer(period_s=period_s, keep=keep)
    return timers[name].measure


def log_to_file(name, period_s):
    global log_file_path, log_period_s, log_t0
    log_file_path = os.path.join(
        os.path.dirname(__file__), '{}_perf.log', name)
    log_period_s = period_s
    log_t0 = time.time()


def stats():
    lt = time.localtime(time.time())
    s = '\n{}\n'.format(time.strftime('%Y-%m-%d %H:%M:%S', lt))
    wasted_ns = 0
    for name in sorted(timers):
        s += '{:20s} - {}\n'.format(name, str(timers[name]))
        wasted_ns += timers[name].wasted_ns
    s += '-> total wasted : {}\n'.format(fmt_ns(wasted_ns))
    return s


def maybe_log_to_file():
    global log_file_path, log_period_s, log_t0, timers
    t = time.time()
    if log_t0 - t > log_period_s:
        with open(log_file_path, 'a') as f:
            f.write(stats())


# @measure('t')
# def t():
#     time.sleep(0.1)
#
#
# for i in range(20):
#     t()
#
#
# print(stats())
