import collections, colorsys

import numpy as np

from . import logic as L


# color
###############################################################################

class RGB(L.Signal):
    def init(self, r, g, b):
        pass

    def call(self):
        return [self.r, self.g, self.b]

class HSV(L.Signal):
    def init(self, hue=1, saturation=1, value=1):
        pass

    def call(self):
        return colorsys.hsv_to_rgb(
            self.hue,
            self.saturation,
            self.value)

# palette
###############################################################################


class Palette:
    """Generates array of colors with precomputed interpolated palette."""

    def __init__(self, colors, n=256):
        self.n = n
        xs = np.linspace(0, 1, n)
        self.lookup = np.array([
            np.interp(
                xs, [c.index for c in colors], [c.color[i] for c in colors])
            for i in range(3)
        ]).T

    def __call__(self, values):
        return self.lookup[(np.clip(values, 0, 1) * (self.n - 1)).astype(int)]


class StatePalette(L.Signal):
    def init(self, default_palette, palettes_dict):
        pass

    def call(self, state):
        return self.palettes_dict.get(
            state.color,
            self.default_palette
        )


class StateColorPalette(L.Signal):
    def init(self, default_palette, palettes_dict):
        pass

    def call(self, value, state):
        return self.palettes_dict.get(
            state.color,
            self.default_palette
        )(value)


class ColorPalette(L.Signal):
    def init(self, colors, n=256):
        xs = np.linspace(0, 1, n)
        self.lookup = np.array([
            np.interp(
                xs, [c.index for c in colors], [c.color[i] for c in colors])
            for i in range(3)
        ]).T

    def call(self, value):
        return self.lookup[
            (np.clip(value, 0, 1) * (self.n - 1)).astype(int), :]


# TODO make this work with SimpleSignal
class RedToPalette(L.Signal):
    """Converts the red channel of a (legacy) animation to a color palette."""

    # (just subclassing for the __or__ operator)

    def __init__(self, colors):
        if not hasattr(colors, '__call__'):
            colors = ColorPalette(colors)
        self.color_palette = colors

    def __call__(self, value, **kw):
        red_values = value[:, 0]
        colors = self.color_palette(value=red_values)['value']
        return dict(value=colors)


# parse palettes
###############################################################################

ColorPoint = collections.namedtuple('ColorPoint', ['index', 'color'])

def parse_colors_co_scss(scss):
    """Copy'n'paste color.co's SCSS palettes."""
    rgbs = [
        [float(v) / 256
         for v in line[line.index('(') + 1:line.index(')')].split(', ')[:3]]
        for line in scss.split('\n')
        if line
    ]
    return [
        ColorPoint(i / len(rgbs), rgb)
        for i, rgb in enumerate(rgbs)
    ]


def hex_to_tuple(s):
    """Converts #FFFFFF (or #FFF) to (1, 1, 1)."""
    if s[0] == '#':
        s = s[1:]
    if len(s) == 3:
        return tuple((
            0x10 * int(c, 0x10) / 256
            for c in s
        ))
    elif len(s) == 6:
        return tuple((
            int(s[i * 2: (i + 1) * 2], 0x10) / 256
            for i in range(len(s) // 2)
        ))
    else:
        raise ValueError('invalid hex: {}'.format(s))


def parse_colors_hex(indexes_and_hexes):
    return [
        ColorPoint(index, hex_to_tuple(hex_s))
        for index, hex_s in indexes_and_hexes
    ]

