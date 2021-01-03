"""Signals transform sound to scalars."""

import re
from typing import Optional, Tuple

# import aubio
import numpy as np
from scipy import stats

from . import logic as L
from . import util

# pylint: disable=no-member


settings = None


def init(settings_):
    global settings
    settings = settings_


# state
###############################################################################

class ActionLatch(L.Signal):
    """Keeps last from a choice of actions with prefix."""

    def init(self, regex, value=None, converter=lambda x: x):
        self._regex = re.compile(regex)

    def call(self, action):
        if action:
            m = self._regex.match(action)
            if m:
                self.value = self.converter(m.group(1))
        return self.value


class InState(L.Signal):
    """Evaluates to 1 iff in specified state."""

    def init(self, state):
        pass

    def call(self, value, state):
        return value * (state.state == self.state)


class NotInState(L.Signal):
    """Evaluates to 1 iff NOT in specified state."""

    def init(self, state):
        pass

    def call(self, value, state):
        return value * (state.state != self.state)


# pulses, ramps
###############################################################################


class TransientPulse(L.Signal):
    """Creates a pulse based on a transient on/off signal."""

    def init(self, transient_name: str, signal_name: str):
        self.state = 0

    def call(self, **signals):
        transient = signals.get(self.transient_name)
        if transient == f'{self.signal_name} on':
            self.state = 1
        elif transient == f'{self.signal_name} off':
            self.state = 0
        return self.state


class RandomPulse(L.Signal):
    """Creates a random pulse train with poisson distribution."""

    def init(self, hz=1, duration=0.1):
        self.last_t = self.dt = 0

    def call(self, t):
        dt = t - self.last_t
        if dt > self.dt:
            self.last_t = t
            self.dt = stats.expon(scale=1 / self.hz).rvs() + self.duration
        if dt < self.duration:
            return 1
        return 0


class RefractoryPulse(L.Signal):
    """Triggers a pulse with a refractory period."""

    def init(self, threshold, pulse_secs, refractory_secs):
        self.t0 = 0

    def call(self, t, value):
        if t - self.t0 < self.pulse_secs:
            return 1
        if value < self.threshold:
            return 0
        if t - self.t0 > self.refractory_secs:
            self.t0 = t
            return 1


class TriggerPulse(L.Signal):
    """Creates a 1-pulse of duration `secs` when `state` is entered."""

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
    """Creates random ramps with duration, break, ramp in (min, max)."""

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


# Consider using crepe instead of aubio:
# https://github.com/marl/crepe

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


class FreqBreadth(L.Signal):
    """Measures max - min freq where logmel > threshold."""

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


class FreqBand(L.Signal):
    """Frequency band with cosine slope. Values not normalized."""

    def init(self, fmin, fmax, df=1, n=None):
        if n is None:
            n = settings.num_mel_bins

        self.kernel = np.array([
            self.f01((f + df - fmin) / df) * self.f01((fmax + df - f) / df)
            for f in range(n)
        ])
        self.kernel /= self.kernel.sum()

    def call(self, features):
        return (self.kernel * features.logmel).sum()

    def f01(self, x):
        return (1 + np.cos((np.clip(x, 0, 1) - 1) * np.pi)) / 2


# generators
###############################################################################

class Const(L.Signal):
    """Simply returns a constant value."""

    def init(self, value):
        pass

    def call(self):
        return self.value


class Saw(L.Signal):
    """Sawtooth wave.

    Note : Use with `| S.Tocos()` to generate smooth waves.

    Note : Mostly superseeded by S.Const() | S.Int() nowadays ...
    """

    def init(self, hz):
        self.value = self.lt = 0

    def call(self, t):
        dt = t - self.lt
        self.lt = t
        self.value += dt * self.hz
        return self.value % 1


# kinect
###############################################################################

class KinectDistance(L.Signal):
    """Returns array of distances."""

    def call(self, people):
        return [
            (p['cm'][0] ** 2 + p['cm'][1] ** 2) ** .5
            for p in people
            if 'cm' in p
        ]


# utils
###############################################################################


class Print(L.Signal):
    """Prints if not none."""

    def init(self, message, signal):
        pass

    def call(self):
        if self.signal is not None:
            print(self.message, self.signal)

class T(L.Signal):
    """Returns transposed."""

    def call(self, value):
        return value.T


class Length(L.Signal):
    """Returns length of array"""

    def init(self):
        pass

    def call(self, value):
        return len(value)


class With(L.Signal):
    def init(self, value):
        pass
    def call(self, value):
        return list(value) + [self.value]

class Min(L.Signal):
    """Returns minimum value of array, or default."""

    def init(self, default=None):
        pass

    def call(self, value):
        return min(value) if value else self.default


class ElementAt(L.Signal):
    """Returns the idx-th element from a list signal."""

    def init(self, idx):
        pass

    def call(self, value):
        return value[self.idx]


class Noop(L.Signal):
    """Does not modify a signal, but can print it every dt seconds."""

    def init(self, dt=0):
        self.logger = util.PrintEvery(dt)

    def call(self, value):
        self.logger('Noop: value={}'.format(value))
        return value


class Overridable(L.Signal):
    """Overrides signal if non null."""

    def init(self, signal, override):
        pass

    def call(self):
        if self.override is not None:
            return self.override
        return self.signal


# value transformation
###############################################################################


def linear(x):
    return np.clip(x, 0, 1)


def sinramp(x):
    return np.sin(np.clip(x, 0, 1) * np.pi / 2)


class F(L.Signal):
    """Applies a function to a signal."""

    def init(self, f=linear):
        pass

    def call(self, value):
        return self.f(value)


class Lin(L.Signal):
    """Linear transformation of scalar signal : x => x * mult + shift."""

    def init(self, shift=0, mult=1, mod=None):
        pass

    def call(self, value):
        value = self.mult * value + self.shift
        if self.mod:
            value = value % self.mod
        return value


class From(L.Signal):
    """Transforms from `src` to 0..1"""

    def init(self, src_min, src_max):
        pass

    def call(self, value):
        return (value - self.src_min) / (self.src_max - self.src_min)


class To(L.Signal):
    """Transforms from 0..1 to `dst`"""

    def init(self, dst_min, dst_max):
        pass

    def call(self, value):
        return value * (self.dst_max - self.dst_min) + self.dst_min


class Thr(L.Signal):
    """Returns 1-signal if above threshold."""

    def init(self, th):
        pass

    def call(self, value, t):
        return 1 * (value >= self.th)


class Hyst(L.SignalLast):

    def init(self, up_th, down_th):
        pass

    def call(self, t, value):
        if self.lastout.value > 0:
            return 1 * (value >= self.down_th)
        else:
            return 1 * (value >= self.up_th)


class Tocos(L.Signal):
    """Maps 0..1 with cosine smoothing."""

    def call(self, value):
        return (1 + np.cos((value - 1) * np.pi)) / 2


class Exp(L.Signal):
    """Exponentiates the signal."""

    def init(self, alpha):
        pass

    def call(self, value):
        return value ** self.alpha


class Norm(L.Signal):
    """Divides signal by maximal value."""

    def call(self, value):
        m = value.max()
        if m:
            value /= m
        return value


class Mod(L.Signal):
    """Returns the value module some base."""

    def init(self, base):
        pass

    def call(self, value):
        return value % self.base


class Clip(L.Signal):
    """Clamps a value between min/max."""

    def init(self, min: int = 0, max: int = 1):
        pass

    def call(self, value):
        return np.clip(value, self.min, self.max)


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


class Apply(L.Signal):
    """Applies a signal, for use with |-chaining."""

    def init(self, signal):
        pass

    def call(self, value):
        return self.signal(value=value)


class Dict(L.Signal):
    """Returns a value from a dictionary."""

    def init(self, name, dictionary):
        pass

    def call(self):
        return self.dictionary[self.name]


class F(L.Signal):
    """Calculates a function on previous signal with optional parameters."""

    def init(self, f, p1=None):
        pass

    def call(self, value):
        if self.p1 is None:
            return self.f(value)
        return self.f(value, self.p1)


# value transformation in time
###############################################################################

class Int(L.Signal):
    """Integrates the signal."""

    def init(self,
             slope: float = 1,
             mod: Optional[int] = None):
        self.t = self.value = 0

    def call(self, value, t):
        if self.t:
            self.value += value * (t - self.t)
        if self.mod:
            self.value %= self.mod
        self.t = t
        return self.value


class RateLimit(L.Signal):
    """Limits dvalue/dt."""

    def init(self, limit):
        self.last_value = self.last_t = None

    def call(self, value, t):
        if self.last_value is None:
            dt = rate = 0
        else:
            dt = (t - self.last_t)
            rate = 0 if dt == 0 else (value - self.last_value) / dt
            if rate >= 0:
                rate = min(rate, self.limit)
            else:
                rate = max(rate, -self.limit)
            value = self.last_value + rate * dt
        self.last_t = t
        self.last_value = value
        return value

class MovingAverage(L.Signal):
    """Keeps a moving average over `n` samples or `secs` seconds."""

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
    """Exponential follower."""

    def init(self, alpha):
        pass

    def call(self, value):
        return self.lastout.value + (
            value - self.lastout.value) * (1 - self.alpha)


class Median(L.Signal):
    """Returns 1-value if median of last n samples is > threshold."""

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
    """Applies a hamming over `n` samples."""

    def init(self, n):
        self.w = np.hamming(n)
        self.w /= self.w.sum()
        self.buf = np.zeros(n)

    def call(self, value):
        self.buf[0] = value
        self.buf = np.roll(self.buf, shift=1)
        return (self.buf * self.w).sum()


class ClampSlope(L.SignalLast):
    """Follows signal with maximum dvalue/dt."""

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
