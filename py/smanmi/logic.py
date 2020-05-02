"""Building blocs for signals etc.

Synoposis:

  import signals as S

  class A(S.Signal):
    def init(mult):
        pass
    def call(self, value):
        return value * self.mult

  class B(S.Signal):
    def call(self, in1, in2):
        return dict(value=in1 + in2)

  runner = S.SignalRunner(dict(a=A(mult=3, b=B())), ['in1', 'in2'])
  values = runner(in1=1, in2=2)
  print(values['a'])
"""

import functools
import inspect
import random

# utils
###############################################################################


def rnd(minmax):
    return minmax[0] + random.random() * (
        minmax[1] - minmax[0])


class MissingInputsException(Exception):
    """Thrown if signal inputs cannot be satisfied."""
    pass


# Base classes
###############################################################################


def is_signal(x):
    # WTF ?! this fails with `return isinstance(x, Signal):`
    return hasattr(x, 'call') or isinstance(x, SignalChain)


class D:
    """Helper class for attribute access to dictionary."""
    def __init__(self, **kw):
        self.kw = kw

    def __dir__(self):
        return self.kw.keys()

    def __getattr__(self, key):
        return getattr(self, 'kw')[key]

    def __repr__(self):
        return repr(self.kw)


class Signal:
    """Provides |, wants, params.

    A Signal subclass provides
    - `init(self, param1, param2=0, ...)` that can provide additional
      initialization logic
    - `call(self, signal1, signal2, ...)` that returns either a dictionary,
      or a single value that will be converted to `dict(value=value)`.

    Every signal is called with `**signals` as arguments and the calculated
    signals will be added to the signal dictionary that is forwarded to any
    chained classes (see `SignalChain`).

    Every parameter can be a `Signal` itself in which case it will be compouted
    before the function `call()` is executed and the result will be made
    available as an attribute like a non-`Signal` parameter.


    Note the following special attributes
    - `wants` : signals needed for computation - used by `SignalRunner`
    - `callkws` : part of `wants` that is needed as params for `call()`
    - `params` : names of parameters (for `repr()` display)
    - `signalparams` : dictionary of signals from which to compute params
    """

    def __init__(self, *args, **params):
        self.callkws = set(inspect.getfullargspec(self.call).args[1:])
        self.wants = set(self.callkws)
        self.params = params.keys()
        if hasattr(self, 'init'):
            names = inspect.getfullargspec(self.init).args[1:]
            defaults = inspect.getfullargspec(self.init).defaults
            defaults = defaults if defaults else []
            d = dict(zip(names[::-1], defaults[::-1]))
            d.update(**params)
            params = d
            if args:
                params.update(zip(names, args))
            self.init(**params)
        self.signalparams = {}
        for k, v in params.items():
            assert not hasattr(self, k), 'hasattr({}, {})'.format(
                self.__class__.__name__, k)
            setattr(self, k, v)
            if is_signal(v):
                self.signalparams[k] = v
                self.wants = self.wants.union(v.wants)

    def __or__(self, other):
        return SignalChain(self, other)

    def __mul__(self, other):
        return SignalMult(self, other)

    def __add__(self, other):
        return SignalAdd(self, other)

    def __call__(self, **allkw):
        for k, v in self.signalparams.items():
            setattr(self, k, v(**allkw))
        missing = set(self.wants).difference(allkw.keys())
        if missing:
            raise MissingInputsException(
                f'Signal {self!r} is missing inputs {missing}')
        kw = {k: allkw[k] for k in self.callkws}
        return self.call(**kw)

    def __repr__(self):
        return '{}({})'.format(
            self.__class__.__name__,
            ','.join([
                '{}={}'.format(p, self.signalparams.get(p, getattr(self, p)))
                for p in self.params
            ]))


class SignalLast(Signal):
    """Provides lastin, lastout."""

    def __call__(self, **allkw):
        kw = {k: allkw[k] for k in self.wants}
        if not hasattr(self, 'lastin'):
            self.lastin = self.lastout = D(**kw)
        lastin = D(**kw)
        value = super().__call__(**allkw)
        self.lastin = lastin
        self.lastout = D(value=value)
        return value


class Constant(Signal):
    """Simply returns a constant value."""

    def init(self, value):
        pass

    def call(self):
        return self.value


class SignalChain(Signal):

    def __init__(self, sig1, sig2):
        self.wants = sig1.wants.union(sig2.wants.difference(('value',)))
        self.sig1 = sig1
        self.sig2 = sig2
        nsigs1 = sig1.nsigs if isinstance(sig1, SignalChain) else 1
        nsigs2 = sig2.nsigs if isinstance(sig2, SignalChain) else 1
        self.nsigs = nsigs1 + nsigs2

    def recurse(self):
        for sig in (self.sig1, self.sig2):
            if isinstance(sig, SignalChain):
                for sigsig in sig.recurse():
                    yield sigsig
                continue
            yield sig

    def __call__(self, **kw):
        return self.sig2(value=self.sig1(**kw), **{
            k: v for k, v in kw.items() if k != 'value'})

    def __repr__(self):
        return ' | '.join([repr(self.sig1), repr(self.sig2)])


class SignalMult(SignalChain):
    """Multiplies signals, tries to be smart about shapes."""

    def __init__(self, sig1, sig2):
        super().__init__(sig1, sig2)
        self.wants = set(sig1.wants).union(sig2.wants)

    def __call__(self, **kw):
        value1 = self.sig1(**kw)
        value2 = self.sig2(**kw)
        if value1.shape == value2.shape:
            return value1 * value2
        if value1.shape == () or value2.shape == ():
            return value1 * value2
        # Handy hack for animations.
        assert len(value1.shape) == 1, value1.shape
        assert len(value2.shape) == 1, value2.shape
        a = value1 if len(value1) < len(value2) else value2
        b = value2 if len(value1) < len(value2) else value1
        return a.reshape((1, -1)) * b.reshape((-1, 1))

    def __repr__(self):
        return ' * '.join([repr(self.sig1), repr(self.sig2)])


class SignalAdd(SignalChain):

    def __init__(self, sig1, sig2):
        super().__init__(sig1, sig2)
        self.wants = set(sig1.wants).union(sig2.wants)

    def __call__(self, **kw):
        value1 = self.sig1(**kw)
        value2 = self.sig2(**kw)
        return value1 + value2

    def __repr__(self):
        return ' + '.join([repr(self.sig1), repr(self.sig2)])


# Basic signals
###############################################################################

class Named(Signal):

    def __init__(self, name, default=None):
        # Overwrite so we can specify positional arguments
        super().__init__(name=name)
        self.callkws = set((name,))
        self.wants = set(self.callkws)
        self.default = default

    def call(self, **kw):
        return kw.get(self.name, self.default)


# SignalRunner
###############################################################################

def make_order(signals, provided):
    """Returns ordered keys of `signals` satisfying their wants."""
    ordered = []
    provided = set(provided)
    names = set(signals.keys())
    while names:
        done = set()
        for name in names:
            signal = signals[name]
            if len(provided.intersection(signal.wants)) == len(signal.wants):
                done.add(name)
        if not done:
            raise MissingInputsException(
                'Given {}, could not satisfy ANY of {}'.format(
                    provided,
                    ', '.join([
                        '{}->{}'.format(signals[name], signals[name].wants)
                        for name in names
                    ])
                ))
        names = names.difference(done)
        provided = provided.union(done)
        ordered += list(done)
    return ordered


class SignalRunner:
    """Runs signals DAG."""

    def __init__(self, signals):
        """Constructs the SignalRunner.

        Args:
          signals: Dictionary mapping signal name to `L.Signal`
        """
        self.signals = signals
        self.provided = functools.reduce(
            lambda acc, sig: acc.union(sig.wants), signals.values(), set()
        ).difference((
            name for name, signal in signals.items()
            if name not in signal.wants
        ))
        self.ordered = make_order(signals, self.provided)

    def __call__(self, **kw):
        """Computes output signals from input signals.

        Note that input signals are copied onto output signals, but can be
        overriden if an output signal has the same name.
        """
        values = dict(**kw)
        missing = self.provided.difference(values.keys())
        if missing:
            raise MissingInputsException(f'Missing provided : {missing}')
        for name in self.ordered:
            values[name] = self.signals[name](**values)
        return values
