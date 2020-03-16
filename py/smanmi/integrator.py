"""Integrates sensor signals & outputs signals asynchronously.

There are two flows of information:

- signals : flowing from sensors to integrator, and being forwarded to
  effectors (fadecandy, monitor, dmx, ...) - these signals are received async
  and at regular intervals (or when specific signals are received) the output
  signals are computed and sent to all specified output ports

- commands : flowing from monitor back to sensors - whenever a messag arrives
  it is immediately forwarded to all output ports
"""

import asyncio, time, traceback

from . import util


class SignalinProtocol(asyncio.DatagramProtocol):
    """Forwards datagrams from an UDP port to the integrator."""

    def __init__(self, integrator, group):
        self.integrator = integrator
        self.group = group

    def datagram_received(self, data, addr):
        del addr
        self.integrator.datagram_received(self.group, data)


class UdpOutProtocol(asyncio.DatagramProtocol):
    """Forwards UDP connections to the integrator for sending data to UDP."""

    def __init__(self, integrator, group):
        self.integrator = integrator
        self.group = group

    def connection_made(self, transport):
        self.integrator.connection_made(self.group, transport)


class Integrator:

    """Integrates `signalin` to produce `signals`.

    Client classes must overwrite the `__call__()` method that computes the
    output signals from the input signals.

    Note that `self.signals` will only be updated with new signals retured by
    `__call__()`, and old signals are kept until overridden.

    Client classes can also override the following methods:

    - `should_send_now(signals)` : called with the currently received input
      signals. will immediately send output signals if this method returns
      `True`, otherwise will wait until next `fps` is reached
    """

    def __init__(self, logger, fps, address,
                 sig_in_ports, sig_out_ports,
                 cmd_in_ports, cmd_out_ports):
        """Initializes the integrator -- call `start()` to start.

        Args (non exhaustive):
          fps : At what frequency `__call__()` should be called *at least*.
              Every time new signals are recived, the function
              `should_send_now()` is called, and if that method returns `True`,
              then signals are sent immediately. Setting `fps=0` results in
              sending signals only based on `should_send_now()`.
          address : all outgoing UDP packets will be sent to this address
        """
        self.logger = logger
        self.fps = fps
        self.address = address
        self.sig_in_ports = sig_in_ports
        self.sig_out_ports = sig_out_ports
        self.cmd_in_ports = cmd_in_ports
        self.cmd_out_ports = cmd_out_ports

        self.stats = util.StreamingStats(logger)
        self.stats.catch_ctrlc(self.stop)
        self.loop = None
        self.running = False
        self.transports = dict(sig=[], cmd=[])
        self.event = asyncio.Event()

    def should_send_now(self, signals):
        return False

    def datagram_received(self, group, data):
        try:
            if group == 'cmd':
                self.sendto('cmd', data)
                return
            assert group == 'sig', group
            self.stats('sig_in', data)
            signals = util.deserialize(data)
            self.signals.update(signals)
            if self.should_send_now(signals):
                self.event.set()
        except Exception as e:
            self.logger.error('datagram_received ERROR: %s', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def connection_made(self, group, transport):
        self.transports[group].append(transport)

    def sendto(self, group, msg):
        for transport in self.transports[group]:
            if transport.is_closing():
                self.logger.info('transport %s closing', group)
                continue
            transport.sendto(msg)

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
                self.signals['t'] = self.t = time.time()
                signals = self()
                if signals:
                    self.signals.update(signals)
                    msg = util.serialize(self.signals)
                    self.sendto('sig', msg)
                    self.stats('sig_out', msg)
        except Exception as e:
            self.logger.error('sending_loop ERROR: %r', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def stop(self):
        if self.loop is not None:
            self.loop.stop()
        self.running = False

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))

    def start(self):
        self.loop = loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)

        for group, ports in (
                ('sig', self.sig_in_ports),
                ('cmd', self.cmd_in_ports)):
            for port in ports:
                loop.run_until_complete(loop.create_datagram_endpoint(
                    lambda: SignalinProtocol(self, group),
                    local_addr=('127.0.0.1', port)))
        for group, ports in (
                ('sig', self.sig_out_ports),
                ('cmd', self.cmd_out_ports)):
            for port in ports:
                loop.run_until_complete(loop.create_datagram_endpoint(
                    lambda: UdpOutProtocol(self, group),
                    remote_addr=(self.address, port)))

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
