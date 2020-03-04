"""Integrates sensor signals & outputs signals asynchronously."""

import asyncio, json, os, time, traceback

from . import util


class SignalinProtocol(asyncio.DatagramProtocol):
    """Forwards datagrams from an UDP port to the integrator."""

    def __init__(self, integrator):
        self.integrator = integrator

    def datagram_received(self, data, addr):
        del addr
        self.integrator.datagram_received(data)


class SignalsProtocol(asyncio.DatagramProtocol):
    """Forwards UDP connections to the integrator for sending data to UDP."""

    def __init__(self, integrator):
        self.integrator = integrator

    def connection_made(self, transport):
        self.integrator.connection_made(transport)


class Integrator:

    """Integrates `signalin` to produce `signals`.

    The integrator receives `signalin` on (multiple) input port(s) async and
    emits `signals` to (multiple) destination port(s) at a regular frequency.

    Client classes must overwrite the following two methods:

    - `integrate()` : what to do with new `signalin`
    - `compute()` : returns a `signal` dictionary to be sent
    """

    def __init__(self, logger, fps, address, signalin_ports, signals_ports,
                 recordings_path):
        """Initializes the integrator -- call `start()` to start.

        Args (non exhaustive):
          fps : At what frequency `compute()` should be called. Can be set to
              zero in which case `self.event.set()` triggers the computation.
              If set to another value then zero then every call to
              `self.event.set()` will result in the fps timer being reset.
        """
        self.logger = logger
        self.fps = fps
        self.address = address
        self.signalin_ports = signalin_ports
        self.signals_ports = signals_ports
        self.recordings_path = recordings_path

        self.stats = util.StreamingStats(logger)
        self.stats.catch_ctrlc(self.stop)
        self.loop = None
        self.running = False
        self.transports = []
        self.recording_f = None
        self.event = asyncio.Event()

    def integrate(self, signalin):
        raise NotImplementedError()

    def compute(self):
        raise NotImplementedError()

    def record_start(self, name):
        path = os.path.join(
            self.recordings_path, f'{util.now_fmt()}_{name}.ndjson')
        self.logger.info('Start recording : %s', path)
        self.recording_f = open(path, 'a')

    def record_stop(self):
        self.logger.info('Stop recording')
        self.recording_f.close()
        self.recording_f = None
        self.running = False

    def record_maybe(self, signalin):
        if self.recording_f:
            self.recording_f.write(json.dumps(dict(
                t=time.time(), **signalin)) + '\n')

    def datagram_received(self, data):
        try:
            self.stats('signalin', data)
            signalin = json.loads(data.decode('utf8'))
            self.record_maybe(signalin)
            self.integrate(signalin)
        except Exception as e:
            self.logger.error('datagram_received ERROR: %s', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def connection_made(self, transport):
        self.transports.append(transport)

    async def sending_loop(self):
        self.t = time.time()
        try:
            while self.running:
                if self.fps:
                    dt = 1 / self.fps - (time.time() - self.t)
                    try:
                        await asyncio.wait_for(self.event.wait(), max(0, dt))
                    except asyncio.TimeoutError:
                        pass
                else:
                    await self.event.wait()
                self.event.clear()
                self.t = time.time()
                signals = self.compute()
                for transport in self.transports:
                    if transport.is_closing():
                        self.logger.info('transport closing')
                        continue
                    msg = json.dumps(util.pythonize(signals)).encode('utf8')
                    transport.sendto(msg)
                self.stats('signals', msg)
        except Exception as e:
            self.logger.error('sending_loop ERROR: %s', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def stop(self):
        if self.loop is not None:
            self.loop.stop()
        self.running = False

    def exception_handler(self, loop, context):
        msg = context.get('exception', context['message'])
        self.logger.error('caught exception: %s', msg)

    def start(self):
        self.loop = loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)

        for signalin_port in self.signalin_ports:
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: SignalinProtocol(self),
                local_addr=('127.0.0.1', signalin_port)))
        for signals_port in self.signals_ports:
            loop.run_until_complete(loop.create_datagram_endpoint(
                lambda: SignalsProtocol(self),
                remote_addr=(self.address, signals_port)))

        self.running = True
        sending_task = loop.create_task(self.sending_loop())

        self.logger.info('run_forever()')
        try:
            loop.run_forever()
        finally:
            self.logger.info('shutting down..')
            loop.run_until_complete(sending_task)
            self.logger.info('done')
            loop.close()
            self.loop = None
