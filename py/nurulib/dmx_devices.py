import array, collections

import numpy as np


class DmxDevice:
    """Defines a property -> channel mapping (0 based)."""

    def __init__(self):
        self.init_data()
        assert type(self.data) == collections.OrderedDict

    def init_data(self):
        self.data = collections.OrderedDict()

    def __dir__(self):
        return self.data.keys()

    def __getattr__(self, k):
        return self.data[k]

    def __setattr__(self, k, v):
        if k == 'data':
            return super().__setattr__(k, v)
        assert k in self.data
        self.data[k] = v

    def values(self):
        return list(self.data.values())

    def __len__(self):
        return len(self.data)


class FroggyLight(DmxDevice):
    def init_data(self):
        self.data = collections.OrderedDict([
            ('dimmer', 0),
            ('strobe', 0),
            ('red', 0),
            ('green', 0),
            ('blue', 0),
            #  pan : 0=148: 0
            #        37=184: pi/2
            #        72=221: pi
            #        109=255: 3pi/2
            ('pan', 0),
            #  tilt: 38: 0
            #        86: pi/4
            #        133: pi/2
            #        191: 3pi/4
            #        229: pi
            ('tilt', 0),
            ('speed', 0),
        ])


class StageLight(DmxDevice):
    def init_data(self):
        self.data = collections.OrderedDict([
            ('intensity', 0),
            ('red', 0),
            ('green', 0),
            ('blue', 0),
        ])


class ZBeam(DmxDevice):
    def init_data(self):
        self.data = collections.OrderedDict([
            ('volume', 0),
        ])


class DmxController:
    """Maps multiple DmxDevice to a controller."""

    def __init__(self, wrapper):
        """Reqiures a ola.ClientWrapper instance as argument."""
        self.devices = []
        self.universes = []
        self.channel_offsets = []
        self.universe_sizes = {}
        self.wrapper = wrapper
        self.client = self.wrapper.Client()
        self.lastas = {}

    def add_device(self, device, universe, channel_offset=0):
        self.devices.append(device)
        self.universes.append(universe)
        self.channel_offsets.append(channel_offset)
        self.universe_sizes[universe] = max(
            self.universe_sizes.get(universe, 0), channel_offset + len(device)
        )

    def pad_universe_size(self, universe_size):
        return int(np.ceil(universe_size / 16) * 16)

    def values(self):
        values = {
            universe: np.zeros(
                self.pad_universe_size(universe_size), dtype=np.uint8)
            for universe, universe_size in self.universe_sizes.items()
        }
        for device, universe, offset in zip(
            self.devices,
            self.universes,
            self.channel_offsets
        ):
            values[universe][
                offset: offset + len(device)] = device.values()
        return values

    def update(self):
        for universe, values in self.values().items():
            a = array.array('B', map(int, values))
            if self.lastas.get(universe) == a:
                continue
            self.client.SendDmx(universe, a, lambda state: self.wrapper.Stop())
            # this should work with DMXEnttecPro
            # self.client.set_channel(universe, a)
            # self.client.submit() 