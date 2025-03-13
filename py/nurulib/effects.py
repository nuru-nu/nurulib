
import random, time

import numpy as np
import scipy, scipy.io.wavfile

from . import perf, util


# TODO: Rewrite these as logic.Signal?


settings = None
def init(settings_):
    global settings
    settings = settings_


class Effector:
    """Composes effects and handles channels."""
    def __init__(self, rate, effects):
        buf_size = int(rate * settings.buf_secs)
        self.effects = effects
        self.bufs = [
            util.RollingBuffer(buf_size) for _ in range(len(effects))
            if buf_size
        ]

    @perf.measure('effector')
    def __call__(self, input_data, signals):
        # (not checking this anymore with streaming interface)
        # assert len(input_data) == settings.buf_secs, (
        #     'Expected input_data={}!={}'.format(
        #         settings.buf_secs, len(input_data)))
        input_data = util.int16_to_float(input_data)

        output_datas = [
            effect(input_data, signals)
            for effect in self.effects
        ]
        for buf, output_data in zip(self.bufs, output_datas):
            buf(output_data)
        return output_datas


class Effect:
    def __or__(self, other):
        return ChainedEffect(self, other)


# TODO merge with A.Mixer ?
class Mixer:
    """Mixes effects by state.state with some interpolation."""

    def __init__(self, default_effect, effect_by_state):
        self.default_effect = default_effect
        self.effect_by_state = effect_by_state
        self.t0 = 0
        self.dt = 1
        self.current = self.last = 'std'

    def get(self, state, buf, signals):
        effect = self.effect_by_state.get(state, self.default_effect)
        return effect(buf, signals)

    def __call__(self, buf, signals):
        state = signals['state'].state
        t = signals['t']
        if state != self.current:
            self.last = self.current
            self.current = state
            self.t0 = t
        out = self.get(state, buf, signals)
        if t - self.t0 < self.dt:
            lastbuf = self.get(self.last, buf, signals)
            v = (t - self.t0) / self.dt
            out = v * buf + (1 - v) * lastbuf
        return out


class Recording(Effect):
    """Plays a recording from signalin[name]."""

    def __init__(self, name):
        self.name = name
        self.i = 0
        self.buf = None

        t0 = time.time()
        self.data = {}
        for name, path in settings.get_recordings().items():
            sr, data = scipy.io.wavfile.read(path)
            if sr != settings.rate:
                # We only support input rate.
                print('IGNORING {} {}!={}'.format(
                    name, sr, settings.rate))
                continue
            if data.dtype != settings.dtype_np:
                print('IGNORING {} {}!={}'.format(
                    name, data.dtype.name, settings.dtype_np.name))
                continue
            self.data[name] = util.int16_to_float(data)
        print('Loaded {} recordings in {:.3f}ms'.format(
            len(self.data), time.time() - t0))

    def __call__(self, buf, signals):
        recording = signals.get('signalin', {}).get(self.name)
        if recording:
            self.i = 0
            self.buf = self.data[recording]
            signals['state'].play(recording)
            print('playing {}...'.format(recording))
        if self.buf is not None:
            if self.i + len(buf) <= len(self.buf):
                buf = self.buf[self.i: self.i + len(buf)]
                self.i += len(buf)
            else:
                self.buf = None
                signals['state'].play(None)
        return buf


class ChainedEffect(Effect):
    def __init__(self, effect1, effect2):
        self.effect1 = effect1
        self.effect2 = effect2

    def __call__(self, buf, signals):
        return self.effect2(self.effect1(buf, signals), signals)


class Echo(Effect):
    def __init__(self, delay_s=0.2, coeff=0.7):
        self.delay_s = delay_s
        self.delay_n = int(delay_s / settings.hop_secs)
        self.coeff = coeff
        self.bufs = np.zeros((self.delay_n, settings.buf_secs))
        self.i = 0

    def __call__(self, buf, signals):
        buf = buf[:settings.buf_secs]
        n = self.bufs.shape[0]
        delayed = self.bufs[self.i % n].copy()
        self.bufs[self.i % n] = buf + delayed * self.coeff
        ret = self.bufs[self.i % n]
        self.i += 1
        return ret


class Delay(Effect):
    def __init__(self, delay_s=0.2):
        self.delay_s = delay_s
        self.delay_n = int(delay_s / settings.hop_secs)
        self.bufs = np.zeros((self.delay_n, settings.buf_secs))
        self.i = 0

    def __call__(self, buf, signals):
        buf = buf[:settings.buf_secs]
        n = self.bufs.shape[0]
        delayed = self.bufs[self.i % n].copy()
        self.bufs[self.i % n] = buf
        ret = delayed
        self.i += 1
        return ret


class Passthrough(Effect):
    def __call__(self, buf, signals):
        return buf


class Silence(Effect):
    def __init__(self):
        self.buf = np.zeros(0)

    def __call__(self, buf, signals):
        if len(self.buf) != len(buf):
            self.buf = np.zeros(buf.shape)
        return self.buf


class SilenceOrPlaying(Silence):

    def __call__(self, buf, signals):
        if signals['state'].playing:
            return buf
        return super().__call__(buf, signals)


class Sinusoidal(Effect):
    def __init__(self, hz, A=0.2, rate=None):
        if rate is None: rate = settings.out1_rate
        T = int(rate / hz)
        n = int(np.ceil(settings.buf_secs * rate / T))
        self.buf = A * np.sin(np.linspace(0, n * 2 * np.pi, n * T))

    def __call__(self, buf, signals):
        self.buf = np.roll(self.buf, shift=-len(buf))
        return self.buf[:len(buf)].copy()


class Square(Sinusoidal):
    def __init__(self, hz, A=0.2, rate=None):
        super().__init__(hz, A, rate)
        self.buf = 2 * A * (self.buf > 0) - A

    def __call__(self, buf, signals):
        self.buf = np.roll(self.buf, shift=-len(buf))
        return self.buf[:len(buf)]


class SigAmp:
    def __init__(self, signal_name):
        self.signal_name = signal_name

    def __call__(self, buf, signals):
        return buf * np.clip(signals.get(self.signal_name, 0), 0, 1)


class Compressor(Effect):
    def __init__(self, factor):
        self.factor = factor

    def __call__(self, data, signals=None):
        # TODO interpol
        return np.arctan(data * self.factor) / np.pi * 2


class Linear(Effect):
    def __init__(self, mult=1, shift=0):
        self.shift = shift
        self.mult = mult

    def __call__(self, data, signals=None):
        return (data + self.shift) * self.mult


class Iir(Effect):
    def __init__(self, b, a):
        self.b = b
        self.a = a
        self.zi = scipy.signal.lfiltic(b, a, [])

    def __call__(self, data, signals=None):
        data, self.zi = scipy.signal.lfilter(self.b, self.a, data, zi=self.zi)
        return data


class Notch(Iir):
    def __init__(self, hz, Q, rate=None):
        if rate is None: rate = settings.out1_rate
        super().__init__(*scipy.signal.iirnotch(hz, Q, rate))


class LowPass(Iir):
    def __init__(self, hz, order, rate=None):
        if rate is None: rate = settings.out1_rate
        b, a = scipy.signal.butter(order, hz, btype='low', fs=rate)
        super().__init__(b, a)


class HighPass(Iir):
    def __init__(self, hz, order, rate=None):
        if rate is None: rate = settings.out1_rate
        b, a = scipy.signal.butter(order, hz, btype='high', fs=rate)
        super().__init__(b, a)


class BandPass(Iir):
    def __init__(self, hz1, hz2, order, rate=None):
        if rate is None: rate = settings.out1_rate
        b, a = scipy.signal.butter(
            order, [hz1, hz2], btype='band', fs=rate)
        super().__init__(b, a)


class RndSub(Effect):
    """Randomly plays subsamples from provided sample."""

    def __init__(self, wav, sample_minmax, break_minmax,
                 ramp_minmax=(0.5, 0.5), rate=None):
        if rate is None: rate = settings.out1_rate
        self.rate = rate
        self.wav = wav
        self.sample_minmax = sample_minmax
        self.break_minmax = break_minmax
        self.ramp_minmax = ramp_minmax
        self.zeros = np.zeros(settings.buf_secs)
        self.state = 'on'
        self.next()

    def next(self):
        self.state = dict(on='off', off='on')[self.state]
        self.left = self.rnd_n(dict(
            on=self.sample_minmax, off=self.break_minmax)[self.state])
        if self.state == 'on':
            self.win = scipy.hamming(2 * self.rnd_n(self.ramp_minmax))
            self.wav_i = self.wav_i0 = self.rnd_n([
                0, len(self.wav) / self.rate - self.sample_minmax[1]])

    def rnd_n(self, minmax):
        secs = minmax[0] + random.random() * (minmax[1] - minmax[0])
        return int(self.rate * secs)

    def __call__(self, buf, signals):
        n = len(buf)
        if self.state == 'off':
            buf = self.zeros
        else:
            buf = self.wav[self.wav_i: self.wav_i + n]
            dwav = self.wav_i - self.wav_i0
            if dwav < len(self.win) // 2:
                buf = np.array(buf)
                m = min(n, len(self.win) // 2 - dwav)
                buf[:m] *= self.win[dwav:][:m]
            elif self.left < len(self.win) // 2:
                buf = np.array(buf)
                m = min(self.left, n)
                buf[:m] *= self.win[-self.left:][:m]
                buf[m:] *= 0
            self.wav_i += n
        self.left -= len(buf)
        if self.left < 0:
            self.next()
        return buf


class RndPlay(Effect):

    def __init__(self, wav, signal, rate=None):
        if rate is None: rate = settings.out1_rate
        self.rate = rate
        self.wav = wav
        self.signal = signal
        self.i = None
        self.zeros = np.zeros(0)

    def get_zeros(self, buf):
        if len(self.zeros) != len(buf):
            self.zeros = np.zeros(buf.shape)
        return self.zeros

    def __call__(self, buf, signals):
        n = len(buf)
        value = signals.get(self.signal, 0)
        if value == 0:
            self.i = None
            return self.get_zeros(buf)
        if self.i is None:
            self.i = int(self.rate * random.random() * (
                len(self.wav) / self.rate))
        if self.i + n > len(self.wav):
            left = n - (len(self.wav) - self.i)
            buf = np.concatenate([self.wav[self.i:], self.wav[:left]])
            self.i = left
        else:
            buf = self.wav[self.i: self.i + n]
            self.i += n
        if value < 1:
            buf = buf * value
        return buf


class Loop(Effect):

    def __init__(self, wav):
        self.wav = wav
        self.i = 0

    def __call__(self, buf, signals):
        n = len(buf)
        buf = self.wav[self.i: self.i + n]
        self.i = (self.i + n) % len(self.wav)
        if len(buf) < n:
            print(len(buf), self.i, n - len(buf))
            buf = np.concatenate(
                buf, self.wav[self.i - (n - len(buf)): self.i])
        return buf


class Amplitude(Effect):

    def __init__(self, signal):
        self.signal = signal
        self.value = 0

    def __call__(self, buf, signals):
        value = np.clip(0, 1, signals.get(self.signal, 0))
        self.value += 0.5 * (value - self.value)
        return buf * self.value


class RandomLoop(Effect):

    def __init__(self, wavs):
        self.wavs = wavs
        self.i = 0

    def __call__(self, buf, signals):
        wav = self.wavs[int(signals['state'].rnd) % len(self.wavs)]
        n = len(buf)
        if self.i > len(wav):
            self.i = 0
        buf = wav[self.i: self.i + n]
        self.i = (self.i + n) % len(wav)
        if len(buf) < n:
            diff = n - len(buf)
            buf = np.concatenate([buf, np.zeros(diff)])
        return buf


class PlayPart(Effect):
    """One shot player triggered by signal>0."""

    def __init__(self, signal, wav, rate, start_secs=0, length=None):
        self.signal = signal
        self.wav = wav
        self.i0 = int(rate * start_secs)
        if length is None:
            self.i1 = len(wav)
        else:
            self.i1 = int(rate * (start_secs + length))
        self.i = None

    def __call__(self, buf, signals):
        if self.i > self.i1:
            self.i = None
        if self.i is None:
            value = signals.get(self.signal)
            if not value:
                return buf
            self.i = self.i0
        i = self.i
        self.i += len(buf)
        return self.wav[i: i + len(buf)]
