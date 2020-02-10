"""Audio dataBASE - handle audio files and transforms in memory.

Transformed audio is cached in settings.abase_cache_dir.

Synposis:
  abase = ABase()
  abase.df.head()
"""

import collections, hashlib, os, pickle, random, struct, time

import pandas
import scipy.io.wavfile

from . import audio, util


settings = None
def init(settings_):
    global settings
    settings = settings_


def rand_stable(s):
    """Returns a random value 0..1 based on hash(s)."""
    return struct.unpack(
        '<L', hashlib.md5(s.encode('utf8')).digest()[:4])[0] / 2.0**32


def load_wav(path):
    sr, data = scipy.io.wavfile.read(path)
    data = util.int16_to_float(data)
    if sr == settings.rate:
        return data
    else:
        print('ignoring "{}" : rate {}!={}'.format(
            path, sr, settings.rate))


class ValueByColumn:
    """Makes dataframe's row's values autocomplete-accessible by their col."""

    def __init__(self, row):
        self.row = row

    def __dir__(self):
        return list(self.row.keys())

    def __getitem__(self, col):
        return self.row[col]

    def __getattr__(self, col):
        if col == 'wav' and self.row[col] is None:
            return load_wav(self.row['path'])
        return self.row[col]

    def play(self, start=0, stop=None, plot=False):
        wav = self.wav[int(settings.rate * start):]
        if stop:
            wav = wav[:int(settings.rate * (stop - start))]
        audio.playback(wav)

    def __repr__(self):
        if settings.is_interactive:
            from IPython.display import Audio, display
            from matplotlib import pyplot as plt
            fig, axs = plt.subplots(2, 1, figsize=(12, 8))
            axs[0].plot(self.wav)
            util.plot_logmel(self.row['logmel'], ax=axs[1])
            plt.show()
            display(Audio(filename=self.row['path']))
        return '{}(path={})'.format(self.__class__.__name__,
                                    self.row['path'])


class RowByIndex:
    """Makes dataframe's rows autocomplete-accessible by their index."""

    def __init__(self, df):
        self.df = df

    def __dir__(self):
        return list(self.df.index)

    def __getattr__(self, idx):
        return ValueByColumn(self.df.loc[idx])


class ABase:

    def __init__(self, load_wav=False, df=None, queries=(), **kwargs):
        os.makedirs(settings.abase_cache_dir, exist_ok=True)
        self.queries = queries
        if df is None:
            self.reload(load_wav=load_wav, **kwargs)
        else:
            self.df = df
            self.df.is_copy = False

    def reload(self, load_wav=False, **kwargs):
        self.df = self.make_df(settings.get_recordings().values(), **kwargs)
        if load_wav:
            for name in self.df.index:
                if self.df.loc[name, 'wav'] is None:
                    self.df.at[name, 'wav'] = self.wav(name)
        for query in self.queries:
            self.df = self.df.query(query)
        self.data = RowByIndex(self.df)

    def name(self, path):
        return os.path.basename(path)[:-4]

    def make_df(self, paths, reverse=False, load_wav=True):
        """Mainly parses path name info into dataframe."""
        df = collections.OrderedDict((
            ('path', []),
            ('dirname', []),
            ('name', []),
            # o : semi sung a/o (POS)
            # ohoch, otief (POS)
            # t : spoken words (NEG)
            # m : music (NEG)
            # i : i rather than o
            ('what', []),
            ('w', []),
            ('who', []),
            ('series_i', []),
            # 1..5 : 1st session
            # s2 : 2nd session
            ('inseries', []),
            ('rand', []),
            ('rand_stable', []),
            # original format
            ('wav', []),
        ))
        more = []
        series_i = 0
        nowseries = None
        for path in sorted(paths, reverse=reverse):
            dirname = os.path.dirname(path)
            name = self.name(path)
            parts = name.split('_')
            what = parts[0]
            who = None
            if len(parts) > 1:
                who = parts[1]

            inseries = None
            if len(parts) > 2:
                inseries = parts[-1]
                if nowseries != tuple(parts[:-1]):
                    nowseries = tuple(parts[:-1])
                    series_i += 1
            kws = []
            for kw in kws:
                if not kw:
                    continue
                if kw not in df:
                    df[kw] = [False] * len(df['name'])
                    more.append(kw)

            for m in more:
                df[m].append(m in kws)
            df['path'].append(path)
            df['dirname'].append(dirname)
            df['name'].append(name)
            df['what'].append(what)
            df['w'].append(what[:1])
            df['who'].append(who)
            df['series_i'].append(series_i)
            df['inseries'].append(inseries)
            df['rand'].append(random.random())
            df['rand_stable'].append(rand_stable(path))
            df['wav'].append(None)

        df = pandas.DataFrame(df).set_index('name')
        df['name'] = df.index
        return df

    def query(self, query):
        queries = tuple(list(self.queries) + [query])
        return ABase(df=self.df.query(query), queries=queries)

    def __str__(self):
        return ('{class_}(n={n}, series={series}, what={what}, '
                'who={whos})').format(
            class_=self.__class__.__name__,
            n=len(self.df),
            series=len(self.df.series_i.dropna().unique()),
            what='|'.join(['%s:%d' % (k, v)
                           for k, v in self.df.what.value_counts().items()]),
            whos='|'.join(['%s:%d' % (k, v)
                           for k, v in self.df.who.value_counts().items()]),
        )

    def __repr__(self):
        return self.__str__()

    def wav(self, name):
        return load_wav(self.df.loc[name, 'path'])

    def transform(self, col, transformer, progress_secs=5., write=True):
        data, index = [], []
        transformed = 0
        t0 = time.time()
        for name, row in self.df.iterrows():
            if col in row and row[col] is not None:
                d = row[col]
            else:
                d = transformer(row)
                transformed += 1
            data.append(d)
            index.append(name)
            if name == self.df.index[-1] or (
                    progress_secs > 0 and time.time() - t0 > progress_secs):
                print('Updated {}/{} ({:.1f}%)'.format(
                    transformed, len(self.df),
                    100. * transformed / len(self.df)))
                t0 = time.time()
        cache = os.path.join(settings.abase_cache_dir,
                             '{}.pickle'.format(col))
        data = pandas.Series(data=data, index=index)
        if write:
            with open(cache, 'wb') as f:
                pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)
        print('{} : {:.2f}M ({:.1f}s)'.format(
            cache, os.stat(cache).st_size / 1024. / 1024, time.time() - t0))
        self.df.loc[:, col] = data

    def load(self, cols, notexists_ok=True):
        """Loads columns from cache (`cols` can be singel col name or list)."""
        if isinstance(cols, str):
            cols = [cols]
        for col in cols:
            cache_path = os.path.join(settings.abase_cache_dir,
                                      '{}.pickle'.format(col))
            if notexists_ok and not os.path.exists(cache_path):
                print('cannot load non-existing "{}"'.format(col))
                continue
            with open(cache_path, 'rb') as f:
                s = pickle.load(f)
                self.df.loc[:, col] = s
            print('loaded %d/%d (%.2f%%)' % (
                len(s), len(self.df), 100. * len(s) / len(self.df)))

    def clear(self, cols):
        """Clears column(s) from dataframe -- opposite of load()."""
        if isinstance(cols, str):
            cols = [cols]
        for col in cols:
            if col in self.df.columns:
                del self.df[col]

    def play(self, name, start=0, stop=None, plot=False):
        wav = self.wav(name)[int(settings.rate * start):]
        if stop:
            wav = wav[:int(settings.rate * (stop - start))]
        audio.playback(wav)

    def sample(self, n=1):
        if n == 1:
            name = self.df.sample(n=1).index[0]
            return name
        return self.df.sample(n=n).index
