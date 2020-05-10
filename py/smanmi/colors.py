import colorsys

import numpy as np

from . import logic as L


# color signals
###############################################################################

class RGB(L.Signal):
    """A color defined by RGV, to be multiplied with activation."""

    def init(self, r, g, b):
        pass

    def call(self):
        return np.array([self.r, self.g, self.b])


class HSV(L.Signal):
    """A color defined by HSV, to be multiplied with activation."""

    def init(self, hue=1, saturation=1, value=1):
        pass

    def call(self):
        return np.array(colorsys.hsv_to_rgb(
            self.hue,
            self.saturation,
            self.value))


# palette signals
###############################################################################

class Palette(L.Signal):
    """Generates array of colors with precomputed interpolated palette."""

    def init(self, colors, n=256):
        xs = np.linspace(0, 1, n)
        self.lookup = np.array([
            np.interp(
                xs, [c.index for c in colors], [c.color[i] for c in colors])
            for i in range(3)
        ]).T

    def call(self, value):
        return self.lookup[(np.clip(value, 0, 1) * (self.n - 1)).astype(int)]


class InterpolPalette(L.Signal):
    """Interpolates between palettes based on control value valence."""

    def init(self, value, palettes):
        """Palettes is iterable of (value, palette)."""
        lvalue = None
        assert palettes
        self.ps = []
        for i, (value, palette) in enumerate(palettes):
            if lvalue is not None:
                assert lvalue < value, i
            if not isinstance(palette, Palette):
                palette = Palette(palette)
            self.ps.append((value, palette))
        self.vmin = self.ps[0][0]
        self.vmax = self.ps[-1][0]
        self.p0 = self.p1 = self.v0 = self.v1 = None

    def call(self, value):
        v = np.clip(self.value, self.vmin, self.vmax)
        if self.v0 is None or v < self.v0 or v > self.v1:
            for (self.v0, self.p0), (self.v1, self.p1) in zip(
                    self.ps[:-1], self.ps[1:]):
                if v > self.v0 and v <= self.v1:
                    break
        x = (v - self.v0) / (self.v1 - self.v0)
        return self.p0(value=value) * (1 - x) + self.p1(value=value) * x


class StatePalette(L.Signal):
    """Chooses a Palette based on `state.color`."""

    def init(self, default_palette, palettes_dict):
        self.default_palette_ = Palette(default_palette)
        self.palettes_dict_ = {
            name: Palette(palette)
            for name, palette in palettes_dict.items()
        }

    def call(self, value, state):
        return self.palettes_dict_.get(
            state.color,
            self.default_palette_
        )
