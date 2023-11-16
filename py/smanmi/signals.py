"""Signals transform sound to scalars."""

import glob
import random
import re
from typing import Optional, Tuple

# import aubio
import numpy as np
from scipy import stats

from . import logic as L
from . import util
import time

# pylint: disable=no-member


settings = None


def init(settings_):
    global settings
    settings = settings_


# state
###############################################################################

class ActionLatch(L.Signal):
    """Keeps value from action by regex.
    
    Usage:
      sigs = {'mode': ActionLatch('set_mode=(.*)', N.mode)}
    """

    def init(self, regex, sig=None, converter=lambda x: x):
        self._regex = re.compile(regex)
        self.value = None
        # print('ActionLatch', self.value)

    def call(self, action):
        if self.value is None:
            if self.sig is not None:
                # print(self.regex, 'None', '->', self.sig)
                self.value = self.sig
        if action:
            m = self._regex.match(action)
            if m:
                # print('->', m.group(1))
                self.value = self.converter(m.group(1))
        return self.value


class InState(L.Signal):
    """Evaluates to 1 iff in specified state."""

    def init(self, state):
        pass

    def call(self, value, state):
        if not hasattr(state, 'state'):
            return 0
        return value * (state.state == self.state)


class NotInState(L.Signal):
    """Evaluates to 1 iff NOT in specified state."""

    def init(self, state):
        pass

    def call(self, value, state):
        return value * (state.state != self.state)


# pulses, ramps
###############################################################################

class ActionOnOff(L.Signal):
    """Generates 1 after action_on until action_off."""

    def init(self, action_on, action_off):
        self.state = 0

    def call(self, action):
        if action == self.action_on:
            self.state = 1
        elif action == self.action_off:
            self.state = 0
        return self.state


class Ramps(L.Signal):
    """Ramps a signal up and down based on 0/1 input signal."""

    def init(self, slope_on, slope_off):
        self.value = 0
        self.lt = None

    def call(self, value, t, action):
        if self.lt is None:
            self.lt = t
            return self.value
        dt = t - self.lt
        self.lt = t

        if value:
            self.value += dt * self.slope_on
        else:
            self.value -= dt * self.slope_off
        self.value = np.clip(self.value, 0, 1)
        return self.value


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


class RndWalk(L.Signal):
    """"Creates random walk (often used with MovingAverage)."""

    def init(self, k):
        self.value = 0.5
        self.dv = 0
        self.rddv = 1 / k
        self.i = 0

    def call(self, t):
        self.dv += (random.random() - 0.5) * self.rddv
        self.i += 1
        while self.value + self.dv > 1.0:
            self.dv -= self.rddv
        while self.value + self.dv < 0.0:
            self.dv += self.rddv
        self.dv *= 0.9
        self.value += self.dv
        return self.value


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

class KinectLike(L.Signal):
    """ Returns the likes per person """

    def init(self, r_z2, dl_dt):
        self.likes = {}
        self.lt = None
    
    def call(self, people, t):
        if not self.lt:
            self.lt = t
        dt = t - self.lt

        likes = {}
        for person in people:
            like = self.likes.get(str(person['id']), 0)  # Note: JSON has always string keys!
            d = np.linalg.norm(person['cm'][:2])
            like += np.clip(self.dl_dt*dt, 0, 3)
            if d < self.r_z2 and like < 1:
                like =0
            likes[str(person['id'])] = like


        self.likes = likes

        self.lt = t

        return self.likes
            

class KinectDistance(L.Signal):
    """Returns array of distances."""

    def call(self, people):
        return [
            (p['cm'][0] ** 2 + p['cm'][1] ** 2) ** .5
            for p in people
            if 'cm' in p
        ]

class ConnectionMeter(L.Signal):
    def init(self, decay_rate, acceptance_rate):
        self.connection_val = 0
        # self.decay_rate = decay_rate
        # self.acceptance_rate = acceptance_rate
        self.prev_t = time.time()

    def call(self, people):

        dt_s = time.time() - self.prev_t

        distances_m = [
            (p['cm'][0] ** 2 + p['cm'][1] ** 2) ** .5
            for p in people
            if 'cm' in p
        ]

        self.connection_val += self.acceptance_rate * sum(distances_m) * dt_s
        if len(distances_m) == 0:
            self.connection_val -= self.decay_rate * dt_s

        self.connection_val = np.clip(self.connection_val, 0, 1)

        self.prev_t = time.time()

        return self.connection_val

class KinectMovement(L.Signal):
    """Quantifies overall movement."""

    def init(self, avg):
        self.cms = {}

    def call(self, t, people):
        seen = set()
        for person in people:
            seen.add(person['id'])
            cms = self.cms.get(person['id'], [])
            self.cms[person['id']] = [person['cm']] + cms[:2 * self.avg - 1]
            # util.printn(self, 20, person['id'], person['cm'])
        self.cms = {
            k: v for k, v in self.cms.items() if k in seen
        }
        dsum = 0
        for cms in self.cms.values():
            if len(cms) == 2 * self.avg:
                cm1 = np.array(cms[:self.avg]).mean(axis=0)
                cm2 = np.array(cms[self.avg:]).mean(axis=0)
                dsum += np.linalg.norm(cm1 - cm2)
                # util.printn(self, 20, '', cm1, '\n', cm2, cm1 - cm2, np.linalg.norm(cm1 - cm2))
        # util.printn(self, 20, dsum)
        return dsum


class KinectFix(L.Signal):
    """Cleans up Kinect signal."""

    def init(self, phantoms, dphi, people_aug=()):
        self.min_dist = 0.4
        self.people_proposals = []
        self.persist_t = 5

    def update_proposals(self, people_aug):
        for p_aug in people_aug:
            for p_prop in self.people_proposals:
                if np.linalg.norm(
                    np.array(p_prop['cm'][:2]) - np.array(p_aug['cm'][:2])
                ) < self.min_dist:
                    p_prop["pres_t"] += 1
                    p_prop["away_t"] = 0
                    p_prop["eval"] = True
                    p_prop['cm'] = p_aug['cm']
                    break
            else:
                person = p_aug
                person["away_t"] = 0
                person["pres_t"] = 0
                person["eval"] = True
                if len(self.people_proposals) == 0:
                    person["id"] = -1
                else:
                    person["id"] = min([p["id"] for p in self.people_proposals]) - 1
                self.people_proposals.append(person)            

        for person in self.people_proposals:
            if person["eval"] == False:
                person["away_t"] += 1
                
        # Remove where lost tracking
        self.people_proposals = [
            person
            for person in self.people_proposals
            if person["away_t"] < self.persist_t
        ]

    def merge_people(self, people):
        for p_prop in self.people_proposals:
            if p_prop["pres_t"] > self.persist_t:
                people.append(p_prop)
        return people

    def call(self, value, kinect_alg):
        # Rotates from ui slider
        def fix(person):
            d = dict(**person)
            x, y, z = d['cm']
            dphi = self.dphi / 360 * 2 * np.pi
            x, y = np.array([x, y]) @ np.array([
                [np.cos(dphi), -np.sin(dphi)],
                [np.sin(dphi),  np.cos(dphi)],
            ])
            d['cm'] = [x, y, z]
            return d

        # Removes doubles
        def reduce_seg_people(people):
            red_people = []
            for person in people:
                if any([
                        np.linalg.norm(np.array(person['cm'][:2]) -  np.array(red_person['cm'][:2])) < self.min_dist 
                        for red_person in red_people
                        ]):
                    continue
                red_people.append(person)
            return red_people

        # Remove phantoms and apply fix
        people_orig = [
            fix(p_orig)
            for p_orig in value
            if not np.any([
                np.allclose(sorted(p_orig['cm']), sorted(phantom))
                for phantom in self.phantoms
            ])
        ]

        if kinect_alg == 'yolo':
            fixed_people = [
                fix(p_orig)
                for p_orig in value
            ]
            return fixed_people

        if kinect_alg == 'nite':
            return people_orig

        # Remove doubles and apply fix
        people_aug = [
            fix(p_aug) 
            for p_aug in reduce_seg_people(self.people_aug) 
            if p_aug['cm_depth'] != 0
        ]
        
        if kinect_alg == 'merged':
            # Remove orig from aug
            people_aug = [
                p_aug
                for p_aug in people_aug
                if not any([
                    np.linalg.norm(np.array(p_orig['cm'][:2]) - np.array(p_aug['cm'][:2])) < self.min_dist 
                    for p_orig in people_orig
                ])
            ]

        self.update_proposals(people_aug)

        for person in self.people_proposals:
            person['eval'] = False

        if kinect_alg == 'merged':
            return self.merge_people(people_orig)
        elif kinect_alg == 'algo':
            return self.people_proposals
        else:
            return []



# sensors
###############################################################################

class Sonar(L.Signal):
    """Intelligently maps sonar signal to 0..1"""

    def init(self, sig, max_dist=40):
        self.value = 0

    def call(self):
        if self.sig:
            self.value = max(0, min(1, 1 - self.sig / self.max_dist))
        return self.value


# utils
###############################################################################


class Dt(L.Signal):
    """Simply keeps delta to last `t`."""

    def init(self):
        self.lt = 0

    def call(self, t):
        if not self.lt: self.lt = t
        dt = t - self.lt
        self.lt = t
        return max(0, dt)

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


def sinramp2(x):
    return (np.sin(np.clip(x, 0, 1) * np.pi - np.pi / 2) + 1) / 2


def gauss_std(x, std=1):
    g = stats.norm(0, std).pdf
    return g(x) / g(0)


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

    def init(self, dst_min, dst_max, clip=False):
        pass

    def call(self, value):
        value = value * (self.dst_max - self.dst_min) + self.dst_min
        if self.clip:
            value = np.clip(value, 0, 1)
        return value


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
    """Maps 0..1 with cosine smoothing (0 -> 1 -> 0)."""

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
        return value / m if m else value


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


def fexp(x, gamma=1):
    """Use S.From(max, min) | S.F(S.fexp) | S.To(0, dst)."""
    return (np.exp(x * gamma) - 1) / np.exp(gamma)


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

    def init(self, limit, down_limit=None):
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
                limit = self.down_limit
                if limit is None:
                    limit = self.limit
                rate = max(rate, -limit)
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
    """Exponential follower (alpha=1 to disable; .1 is a good value)."""

    def init(self, alpha=1):
        pass

    def call(self, t, value):
        return self.lastout.value + (value - self.lastout.value) * self.alpha


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
