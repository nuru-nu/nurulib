"""Forwards UDP signals & computes animations."""

import asyncio
import collections
import functools
import inspect
import os
import time
import traceback
import weakref

from aiohttp import web, WSMsgType, WSCloseCode

from smanmi import util


class ServerUdpProtocol(asyncio.DatagramProtocol):
    """Forwards connections_made and datagram_received."""

    def __init__(self, websocket_path, logger,
                 data_cb=lambda x: None, transport_cb=lambda x: None):
        super().__init__()
        self.websocket_path = websocket_path
        self.logger = logger
        self.data_cb = data_cb
        self.transport_cb = transport_cb

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.logger.info('udp_%s : connection_made peer=%s',
                         self.websocket_path, peername or '?')
        self.transport_cb(transport)

    def datagram_received(self, data, addr):
        self.data_cb(self.websocket_path, data)


UdpEndpoint = collections.namedtuple('UdpEndpoint', ('address', 'port'))


class UdpForwarding:
    """Specifies a [bi]directional UDP <-> websocket forwarding."""

    def __init__(self, websocket_path, in_udp, out_udp=None):
        assert isinstance(in_udp, UdpEndpoint)
        assert out_udp is None or isinstance(out_udp, UdpEndpoint)
        self.websocket_path = websocket_path
        self.in_udp = in_udp
        self.out_udp = out_udp
        self.in_callback = self.out_callback = None

    def with_callbacks(self, in_callback, out_callback=None):
        self.in_callback = in_callback
        self.out_callback = out_callback
        return self


PeriodicCallback = collections.namedtuple(
    'PeriodicCallback', ('websocket_path', 'callback', 'fps'))


class Server:
    """Forwards UDP & periodic output to websockets. Also serves static."""

    def __init__(self, static_dir, logger, index_html='index.html'):
        self.static_dir = static_dir
        self.logger = logger
        self.stats = util.StreamingStats(logger)
        self.index_html = index_html
        self.stats.catch_ctrlc(self.stop)
        self.udp_forwardings = {}
        self.periodic_callbacks = {}
        # keeps last data received via UDP
        self.udp_data = {}
        # (elements are WeakSet)
        self.websockets = {}
        self.transports = {}
        self.routes = []
        self.key_counter = util.KeyCounter()

    def forward_udp(self, udp_forwarding):
        assert udp_forwarding.websocket_path not in self.udp_forwardings
        assert udp_forwarding.websocket_path not in self.periodic_callbacks
        self.udp_forwardings[udp_forwarding.websocket_path] = udp_forwarding

    def run_periodically(self, periodic_callback):
        assert periodic_callback.websocket_path not in self.udp_forwardings
        assert periodic_callback.websocket_path not in self.periodic_callbacks
        self.periodic_callbacks[
            periodic_callback.websocket_path] = periodic_callback

    async def websocket_handler(self, websocket_path, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.websockets[websocket_path].add(ws)
        try:
            await self.websocket_loop(websocket_path, ws)
        finally:
            self.websockets[websocket_path].discard(ws)
            return ws

    def call_create_task(self, function_or_coroutine, *args, **kwargs):
        if inspect.iscoroutinefunction(function_or_coroutine):
            asyncio.get_event_loop().create_task(
                function_or_coroutine(*args, **kwargs))
        else:
            function_or_coroutine(*args, **kwargs)

    def log_signals(self, websocket_path, msg):
        data = util.deserialize(msg)
        self.key_counter(data)
        data2 = {}
        for k, v in data.items():
            if self.key_counter.counts[k] < 5:
                data2[k] = v
            elif self.key_counter.counts[k] == 5:
                self.logger.warning('Temporarily ignoring too frequent: %s', k)
        if not data2:
            return False
        self.logger.info('%s, received signal: %s', websocket_path, data2)
        return True

    async def websocket_loop(self, websocket_path, ws):
        async for msg in ws:
            try:
                if msg.type == WSMsgType.TEXT:
                    should_log = self.log_signals(websocket_path, msg.data)
                    udp_forwarding = self.udp_forwardings.get(websocket_path)
                    if udp_forwarding and udp_forwarding.out_udp:
                        for transport in self.transports[websocket_path]:
                            if not transport.is_closing():
                                if should_log:
                                    self.logger.info(
                                        'sending to %s', udp_forwarding.out_udp)
                                transport.sendto(msg.data.encode('utf8'))
                    if udp_forwarding and udp_forwarding.out_callback:
                        self.call_create_task(
                            udp_forwarding.out_callback, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    self.logger.warning(
                        'signals ws closed with exception %s', ws.exception())
                else:
                    self.logger.debug('msg.type=%s', msg.type)
        except Exception as e:
            self.logger.error('uncaught exception : %s', e)
            self.logger.warning(traceback.format_exc())

    async def index(self, request):
        return web.FileResponse(os.path.join(self.static_dir, self.index_html))

    def init_app(self):
        self.app = web.Application()
        self.routes.append(web.get('/', self.index))
        for websocket_path in self.periodic_callbacks:
            self.websockets[websocket_path] = weakref.WeakSet()
            self.routes.append(web.get(
                websocket_path,
                functools.partial(self.websocket_handler, websocket_path)))
        for websocket_path in self.udp_forwardings:
            self.websockets[websocket_path] = weakref.WeakSet()
            self.transports[websocket_path] = weakref.WeakSet()
            self.routes.append(web.get(
                websocket_path,
                functools.partial(self.websocket_handler, websocket_path)))
        static_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'static')
        self.routes.append(web.static('/smanmi', static_path, name='smanmi'))
        self.routes.append(web.static('/', self.static_dir, name='static'))
        self.app.add_routes(self.routes)
        self.runner = web.AppRunner(self.app)

    async def start(self, address, port):
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, address, port)
        await self.site.start()

    def stop(self):
        self.running = False
        asyncio.get_event_loop().stop()

    async def safe_send_bytes(self, name, ws, data):
        try:
            await ws.send_bytes(data)
        except BrokenPipeError:
            self.logger.warning('broken pipe : %s', name)
        except ConnectionResetError:
            self.logger.warning('connection reset : %s', name)
        except Exception as e:
            self.logger.warning('other exception "%s" : %s',
                                e.__class__.__name__, name)

    def received_udp(self, websocket_path, data):
        self.stats('udp_in_{}'.format(websocket_path), data)
        udp_forwarding = self.udp_forwardings[websocket_path]
        if udp_forwarding.in_callback:
            self.call_create_task(udp_forwarding.in_callback, data)
        for ws in self.websockets[websocket_path]:
            asyncio.ensure_future(self.safe_send_bytes(
                websocket_path, ws, data))

    async def periodic_loop(self, periodic_callback):
        t0 = time.time()
        try:
            while self.running:
                dt = 1 / periodic_callback.fps - (time.time() - t0)
                await asyncio.sleep(max(0, dt))
                t0 = time.time()
                data = periodic_callback.callback()
                if data is None:
                    continue
                self.stats(
                    'periodic_{}'.format(periodic_callback.websocket_path),
                    data)
                try:
                    for ws in self.websockets[periodic_callback.websocket_path]:
                        await self.safe_send_bytes(
                            periodic_callback.websocket_path, ws, data)
                except RuntimeError as e:
                    if 'Set changed size during iteration' in str(e):
                        self.logger.info('Set changed size during iteration')
                    else:
                        raise e
        except Exception as e:
            self.logger.error('periodic_loop ERROR: %r', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def exception_handler(self, loop, context):
        msg = context.get('exception', context['message'])
        self.logger.error('caught exception: %s', msg)

    def run(self, udp_address='127.0.0.1', address='localhost', port=8080):
        self.init_app()

        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)

        loop.run_until_complete(self.start(address, port))

        #? status websocket

        for websocket_path, udp_forwarding in self.udp_forwardings.items():
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: ServerUdpProtocol(
                    websocket_path, self.logger, data_cb=self.received_udp),
                local_addr=udp_forwarding.in_udp))
            if not udp_forwarding.out_udp:
                continue
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: ServerUdpProtocol(
                    websocket_path, self.logger,
                    transport_cb=lambda transport: self.transports[
                        websocket_path].add(transport)),
                remote_addr=udp_forwarding.out_udp))

        self.running = True
        periodic_tasks = {}
        for websocket_path in self.periodic_callbacks:
            periodic_tasks[websocket_path] = loop.create_task(
                self.periodic_loop(self.periodic_callbacks[websocket_path]))

        self.logger.info('started server on http://%s:%d', address, port)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            print()
        finally:
            self.logger.info('SHUTTING DOWN...')
            self.running = False
            for task in periodic_tasks.values():
                loop.run_until_complete(task)
            for wss in self.websockets.values():
                for ws in list(wss):
                    loop.run_until_complete(ws.close(
                        code=WSCloseCode.GOING_AWAY,
                        message='Server shutdown'))
            loop.run_until_complete(self.runner.cleanup())

            loop.close()
