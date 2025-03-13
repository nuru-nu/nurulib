import json

import numpy as np
import PIL
import tensorflow as tf

from . import logic as L


class WithPrevious:
    """Extends features with scaled averaged copy."""

    def __init__(self, n, d):
        self.n = n
        self.d = d
        self.buf = np.zeros((self.n, self.d), dtype='float32')
        self.i = 0

    def __call__(self, logmel):
        x = logmel
        if self.d != len(logmel):
            x = np.array(
                PIL.Image.fromarray(x.reshape((1, -1))).resize((self.d, 1)))[0]
        self.buf[self.i % self.n, :] = x
        self.i += 1
        return np.concatenate([logmel, self.buf.mean(axis=0)])


class KerasDetector(L.Signal):
    """Transforms logmel to keras model scalar output."""

    PREPROCESSORS = {
        'none': lambda x: x,
        'wp_5_5': WithPrevious(n=5, d=5),
        'wp_10_10': WithPrevious(n=10, d=10),
        'wp_20_20': WithPrevious(n=20, d=20),
        'wp_20_50': WithPrevious(n=20, d=50),
    }

    def init(self, model, model_path):
        preprocessor = json.load(open(os.path.join(model_path,
            model + '_conf.json')))['preprocessor']
        self._model = tf.keras.models.load_model(
            os.path.join(get_model_path, model + '.h5'))
        self._preprocessor = self.PREPROCESSORS[preprocessor]
        self.lastv = self.lastlm = None

    def call(self, features):
        if not (features.logmel == self.lastlm).all():
            self.lastlm = features.logmel
            batch = np.array([self._preprocessor(features.logmel)])
            self.lastv = self._model.predict(batch)[0, 1]
        return self.lastv
