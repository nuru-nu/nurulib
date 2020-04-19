from matplotlib import pyplot as plt
import numpy as np

from audioset import mel_features


def mel_to_hertz(frequencies_mel):
    """Convert frequencies from mel scale to Hz using HTK formula.

    Args:
      frequencies_mel: Scalar or np.array of frequencies in mel.

    Returns:
      Object of same size as frequencies_mel containing corresponding values
      on the Hz scale.
      """
    return mel_features._MEL_BREAK_FREQUENCY_HERTZ * (
        np.exp(frequencies_mel / mel_features._MEL_HIGH_FREQUENCY_Q) - 1.0)


def plot_logmel(logmel, rate, hop_size, lower_edge_hertz, upper_edge_hertz,
                ax=None, hzmax=None, **matshow_kw):
    mels = np.linspace(
        mel_features.hertz_to_mel(lower_edge_hertz),
        mel_features.hertz_to_mel(upper_edge_hertz),
        logmel.shape[1] + 2)[1:-1]
    hertzs = mel_to_hertz(mels)
    if ax is None:
        plt.figure(figsize=(12, 4))
        ax = plt.subplot(111)
    if hzmax:
        maxidx = (hertzs > hzmax).argmax() - 1
        logmel = logmel[:, :maxidx]
    ax.matshow(logmel.T, cmap='jet', **matshow_kw)
    ax.set_xticklabels([
        '%.1f' % (frame * hop_size / rate)
        for frame in ax.get_xticks()
    ])
    ax.set_yticklabels([
        '{:,}'.format(f < len(hertzs) and int(hertzs[int(f)]))
        #str(f)
        for f in ax.get_yticks()
    ])
    ax.set_xlabel('t [s]')
    ax.set_ylabel('f [Hz]')
    return mels, hertzs
