"""UDP utility for recording/playback.

Usage:

python -m nurulib.udp --record_port=1234 --file=data.ndjson
python -m nurulib.udp --playback_port=1234 --file=data.ndjson
"""

import argparse
import asyncio
import os
import time
import traceback

from . import util


parser = argparse.ArgumentParser(description='UDP utility')
parser.add_argument('--address', type=str, default='127.0.0.1')
parser.add_argument('--record_port', type=int, default=None)
parser.add_argument('--playback_port', type=int, default=None)
parser.add_argument('--file', type=str, default=None)
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--timestamp_key', type=str, default='__t')
parser.add_argument('--noloop', action='store_true')


class UdpReceiver:

    def __init__(self, udp_tool):
        self.udp_tool = udp_tool

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        data = util.deserialize(data)
        self.udp_tool.data_received(data)


class UdpSender(asyncio.DatagramProtocol):

    def __init__(self, udp_tool):
        self.udp_tool = udp_tool

    def connection_made(self, transport):
        self.udp_tool.register_transport(transport)


class UdpTool:

    def __init__(self, args):
        assert args.file
        assert bool(args.record_port) != bool(args.playback_port)

        self.logger = util.createLogger('udp')
        self.stats = util.StreamingStats(self.logger)
        self.stats.catch_ctrlc(self.stop)
        self.args = args
        self.transport = None

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))

    async def send_loop(self):
        while self.running:
            with open(self.args.file) as f:
                if not self.running:
                    break
                lt = None
                for line in f:
                    d = util.deserialize(line.encode('utf8'))
                    t = d.pop(self.args.timestamp_key)
                    if lt is None:
                        lt = t
                    dt = t - lt
                    lt = t
                    await asyncio.sleep(dt)
                    if not self.transport:
                        self.logger.warning(
                            'Waiting for transport, skipping frmae...')
                        continue
                    self.transport.sendto(util.serialize(d))
                    self.stats('data_sent', line)
            if self.args.noloop:
                break
        self.stop()

    def register_transport(self, transport):
        if self.transport is not None:
            self.logger.warning('Reregistering transport')
        self.transport = transport

    def data_received(self, data):
        data[self.args.timestamp_key] = time.time()
        line = util.serialize(data).decode('utf8') + '\n'
        self.file.write(line)
        self.stats('data_received', line)

    def stop(self):
        self.running = False
        asyncio.get_event_loop().stop()

    def start(self):

        self.running = True
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)
        if self.args.record_port:
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: UdpReceiver(self),
                local_addr=(self.args.address, self.args.record_port)))
            task = None
            assert self.args.overwrite or not os.path.exists(self.args.file)
            self.file = open(self.args.file, 'w')
        if self.args.playback_port:
            task = loop.create_task(self.send_loop())
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: UdpSender(self),
                remote_addr=(self.args.address, self.args.playback_port)))
        try:
            loop.run_forever()
        finally:
            self.logger.info('SHUTTING DOWN...')
            self.running = False
            if task:
                loop.run_until_complete(task)
        loop.close()


UdpTool(parser.parse_args()).start()
