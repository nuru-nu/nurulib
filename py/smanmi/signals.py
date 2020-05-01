"""Signals transform sound to scalars."""

# import aubio
import numpy as np

from . import logic as L, util


settings = None


def init(settings_):
    global settings
    settings = settings_


# state
###############################################################################

class Smoke(L.Signal):

    def init(self, threshold, pulse_secs, refactory_secs):
        self.t0 = 0

    def call(self, t, value):
        if t - self.t0 < self.pulse_secs:
            return 1
        if value < self.threshold:
            return 0
        if t - self.t0 > self.refactory_secs:
            self.t0 = t
            return 1


class InState(L.Signal):

    def init(self, state):
        pass

    def call(self, value, state):
        return value * (state.state == self.state)


class NotInState(L.Signal):

    def init(self, state):
        pass

    def call(self, value, state):
        return value * (state.state != self.state)


class RndPulse(L.Signal):

    def init(self, break_minmax):
        self.t0 = None
        self.wait_s = L.rnd(break_minmax)

    def call(self, t):
        if self.t0 is None:
            self.t0 = t
        if t - self.t0 >= self.wait_s:
            self.t0 = t
            self.wait_s = L.rnd(self.break_minmax)
            return 1.
        return 0.


class MidiPulse(L.Signal):

    def init(self, port_letter_octave):
        self.state = 0

    def call(self, midi):
        if midi == f'{self.port_letter_octave} on':
            self.state = 1
        if midi == f'{self.port_letter_octave} off':
            self.state = 0
        return self.state


class TriggerPulse(L.Signal):

    def init(self, state, secs):
        self.last_state = None
        self.last_t = 0

    def call(self, state, t):
        if state.state != self.last_state:
            self.last_state = state.state
            if state.state == self.state:
                self.last_t = t
        if t - self.last_t < self.secs:
            return 1.
        return 0.


class RndRamp(L.Signal):

    def init(self, break_minmax=[1, 60], duration_minmax=[2, 5],
             ramp_minmax=[1, 2],
             state='std'):
        self.t3 = -1

    def call(self, t, state):
        if t > self.t3:
            self.t0 = t + L.rnd(self.break_minmax)
            self.t1 = self.t0 + L.rnd(self.ramp_minmax)
            self.t2 = self.t1 + L.rnd(self.duration_minmax)
            self.t3 = self.t2 + L.rnd(self.ramp_minmax)
        if t < self.t0:
            return 0.
        if t < self.t1:
            return (t - self.t0) / (self.t1 - self.t0)
        if t < self.t2:
            return 1.
        return 1 - (t - self.t2) / (self.t3 - self.t2)


# features.wav
###############################################################################


# class Pitcher(L.Signal):
#     """Extracts pitch signal in Hz using `aubio`."""
#
#     def init(self, tolerance):
#         self.pitcher = aubio.pitch(
#             method='yinfft', buf_size=settings.buf_size,
#             hop_size=settings.hop_size, samplerate=settings.rate)
#         self.pitcher.set_unit('Hz')
#         self.pitcher.set_tolerance(tolerance)
#
#     def call(self, features):
#         wav = features.wav
#         pitch = self.pitcher(util.int16_to_float(wav[:settings.hop_size]))
#         assert len(pitch) == 1
#         return pitch[0]


class Louder(L.Signal):
    """Extracts loudness from averaged envelope."""

    def init(self, n):
        self.buf = np.zeros(n * settings.hop_size)
        self.i = 0

    def call(self, features):
        i0 = settings.hop_size * (self.i % self.n)
        self.buf[i0: i0 + settings.hop_size] = np.abs(
            features.wav[:settings.hop_size])
        self.i += 1
        return self.buf.mean()


class Max(L.Signal):
    """Max amplitude."""

    def call(self, features):
        return np.abs(features.wav).max()


class Overdrive(L.Signal):
    """Detects overdrive in signal."""

    def __init__(self, lim):
        super().__init__(lim=lim)

    def call(self, features):
        return np.abs(features.wav > self.lim).sum() / len(features.wav)

# features.logmel
###############################################################################


class WeightedAverage(L.Signal):

    def call(self, features):
        logmel = features.logmel
        assert list(logmel.shape) == [settings.num_mel_bins]
        return ((logmel - logmel.min()) * range(len(logmel))).mean()


class FreqBreadth(L.Signal):

    def init(self, threshold):
        pass

    def call(self, features):
        breadth = 0
        start = None
        for i, v in enumerate(list(features.logmel > self.threshold) + [0]):
            if v:
                if start is None:
                    start = i
            else:
                if start is not None:
                    breadth = max(breadth, i - start)
                    start = None
        return breadth


def hz2f(hz, n, rate=None):
    if rate is None:
        rate = settings.rate
    return hz * np.pi * n / rate


class FreqBand(L.Signal):
    """Frequency band with cosine slope. Values not normalized."""

    def init(self, hzmin, hzmax, hzslope=1, n=None):
        if n is None:
            n = settings.num_mel_bins
        fmin, fmax, df = hz2f(hzmin, n), hz2f(hzmax, n), hz2f(hzslope, n)
        self.kernel = np.array([
            self.f01((f + df - fmin) / df) * self.f01((fmax + df - f) / df)
            for f in range(n)
        ])
        self.kernel /= self.kernel.sum()

    def call(self, features):
        return (self.kernel * features.logmel).sum()

    def f01(self, x):
        return (1 + np.cos((np.clip(x, 0, 1) - 1) * np.pi)) / 2

# value -> value
###############################################################################


class Noop(L.Signal):
    def init(self, dt=0):
        self.logger = util.PrintEvery(dt)

    def call(self, value):
        self.logger('Noop: value={}'.format(value))
        return value


class SinT(L.Signal):
    """Sine wave."""

    def init(self, hz):
        self.last_t = 0
        self.last_wt = 0

    def call(self, t):
        dt = t - self.last_t
        self.last_t += dt
        self.last_wt += 2 * np.pi * self.hz * dt
        return np.sin(self.last_wt)


class Saw(L.Signal):
    """Sawtooth wave."""

    def init(self, hz, dt):
        pass

    def call(self, t):
        return ((t + self.dt) * self.hz) % 1


class Lin(L.Signal):
    """Linear transformation of scalar signal."""

    def init(self, shift=0, mult=1, mod=None):
        pass

    def call(self, value):
        value = self.mult * value + self.shift
        if self.mod:
            value = value % self.mod
        return value


class Limiter(L.SignalLast):
    """Ignores (keeps latest) values outside [minv..maxv]."""

    def init(self, minv=0.0, maxv=1.0):
        pass

    def call(self, value):
        if value > self.maxv or value < self.minv:
            return self.lastout.value
        return value


class MovingAverage(L.Signal):

    def init(self, n=None, secs=None):
        assert n or secs and not (n and secs)
        if secs:
            n = int(secs // settings.hop_secs)
        self.buf = np.zeros(n)
        self.i = 0

    def call(self, value):
        if self.n == 0:
            return value
        self.buf[self.i % len(self.buf)] = value
        self.i += 1
        return self.buf.mean()


class Exponential(L.SignalLast):
    """Exponential smoothing (alpha=0 disables)."""

    def init(self, alpha):
        pass

    def call(self, value):
        return self.lastout.value + (
            value - self.lastout.value) * (1 - self.alpha)


class Median(L.Signal):
    """To be used with e.g. a ML detector."""

    def init(self, n, threshold):
        self.buf = np.zeros(n, dtype='float32')
        self.i = 0

    def call(self, value):
        self.buf[self.i % len(self.buf)] = value
        self.i += 1
        x = np.median(self.buf)
        if self.threshold:
            x = 1. * (x > self.threshold)
        return x


class Hamming(L.Signal):

    def init(self, n):
        self.w = np.hamming(n)
        self.w /= self.w.sum()
        self.buf = np.zeros(n)

    def call(self, value):
        self.buf[0] = value
        self.buf = np.roll(self.buf, shift=1)
        return (self.buf * self.w).sum()


class Clip(L.Signal):

    def __init__(self, amin=0, amax=1):
        super().__init__(amin=amin, amax=amax)

    def call(self, value):
        return np.clip(value, self.amin, self.amax)


class ClipToMaxOfMin(L.Signal):
    """Clips a signal relative to the max of the min."""

    def init(self, min_s=1, amin=0, amax=1):
        self.buf = np.zeros(int(min_s * settings.rate / settings.hop_size))
        self.i = 0
        self.max = 1e-6

    def call(self, value):
        self.buf[self.i] = value
        self.i = (self.i + 1) % len(self.buf)
        self.max = max(self.max, self.buf.min())
        return np.clip(value / self.max * self.amax, self.amin, self.amax)

    def __repr__(self):
        return super().__repr__() + '={:.2f}'.format(self.max)


class Ramp(L.SignalLast):

    def init(self, up_s, down_s):
        """`up_s` is dvalue/ds when going up (the larger the faster)."""
        pass

    def call(self, t, value):
        dt = t - self.lastout.t
        if value > self.lastout.value:
            return np.clip(self.lastout.value + dt * self.up_s, 0, 1)
        elif value < self.lastout.value:
            return np.clip(self.lastout.value - dt * self.down_s, 0, 1)
        return value


class Hyst(L.SignalLast):

    def init(self, up_th, down_th):
        pass

    def call(self, t, value):
        if self.lastout.value > 0:
            return 1 * (value >= self.down_th)
        else:
            return 1 * (value >= self.up_th)


class Tocos(L.Signal):

    def call(self, value, t):
        return (1 + np.cos((value - 1) * np.pi)) / 2


class Thr(L.Signal):

    def init(self, th):
        pass

    def call(self, value, t):
        return 1 * (value >= self.th)


class Exp(L.Signal):

    def init(self, alpha):
        pass

    def call(self, value):
        return value ** self.alpha
