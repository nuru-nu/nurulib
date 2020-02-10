from matplotlib import pyplot as plt
import numpy as np


def plot_logmel(logmel, ax=None, rate=settings.rate, hzmax=None,
                hop_secs=settings.hop_secs, **matshow_kw):
    f2hz = rate / logmel.shape[1] / np.pi
    if ax is None:
        plt.figure(figsize=(12, 4))
        ax = plt.subplot(111)
    if hzmax:
        logmel = logmel[:, :int(hzmax / f2hz)]
    ax.matshow(logmel.T, cmap='jet', **matshow_kw)
    ax.set_xticklabels([
        '%.1f' % (frame * hop_secs)
        for frame in ax.get_xticks()
    ])
    ax.set_yticklabels([
        '{:,}'.format(int(f * f2hz))
        for f in ax.get_yticks()
    ])
    ax.set_xlabel('t [s]')
    ax.set_ylabel('f [Hz]')

