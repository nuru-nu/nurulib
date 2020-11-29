import colorsys

import numpy as np

from . import logic as L
from . import palette as P


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
