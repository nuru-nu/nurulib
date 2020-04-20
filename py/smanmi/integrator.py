"""Integrates sensor signals & outputs signals asynchronously.

There are two flows of information:

- signals : flowing from sensors to integrator, and being forwarded to
  effectors (fadecandy, monitor, dmx, ...) - these signals are received async
  and at regular intervals (or when specific signals are received) the output
  signals are computed and sent to all specified output ports

- commands : flowing from monitor back to sensors - whenever a messag arrives
  it is immediately forwarded to all output ports
"""

import asyncio, traceback

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


class IntegrationServer:

    """Async server for distribution of signals and commands.

    Both signals and commads are received from multiple ports and sent to
    multiple ports/addresses.

    Commands are sent as is, whenever they arrive.

    Signals are forwarded to registered listeners (`onreceive()`) which should
    in turn call `send()` when "enough" signals are accumulated.
    """

    def __init__(self, logger, address,
                 sig_in_ports, sig_out_ports,
                 cmd_in_ports, cmd_out_ports):
        """Initializes the serverr -- call `start()` to start.

        Args (non exhaustive):
          sig_in_ports: list of ports (or address,port tuples) to receive
              signal packages from
          sig_out_ports: list of ports (or address,port tuples) to send
              signal packages to
          cmd_in_ports: list of ports (or address,port tuples) to receive
              command packages from
          cmd_out_ports: list of ports (or address,port tuples) to send
              command packages to
          address : default address for UDP packets
        """
        self.logger = logger
        self.address = address
        self.sig_in_ports = sig_in_ports
        self.sig_out_ports = sig_out_ports
        self.cmd_in_ports = cmd_in_ports
        self.cmd_out_ports = cmd_out_ports

        self.stats = util.StreamingStats(logger)
        self.stats.catch_ctrlc(self.stop)
        self.loop = None
        self.transports = dict(sig=[], cmd=[])
        self.event = asyncio.Event()
        self.onreceive_listeners = set()

    def onreceive(self, listener):
        self.onreceive_listeners.add(listener)

    def datagram_received(self, group, data):
        try:
            if group == 'cmd':
                self.sendto('cmd', data)
                return
            assert group == 'sig', group
            self.stats(f'sig_in', data)
            signals = util.deserialize(data)
            for listener in self.onreceive_listeners:
                listener(signals)
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

    def send(self, signals):
        try:
            msg = util.serialize(signals)
            self.sendto('sig', msg)
            self.stats('sig_out', msg)
        except Exception as e:
            self.logger.error('sending_loop ERROR: %r', e)
            self.logger.warning(traceback.format_exc())
            self.stop()

    def stop(self):
        if self.loop is not None:
            self.loop.stop()

    def exception_handler(self, loop, context):
        self.logger.error(
            'Caught exception: %r\n%s:\n%s\n',
            context['exception'], context['message'],
            ''.join(traceback.format_list(context['source_traceback'])))

    def start(self):
        self.loop = loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.set_exception_handler(self.exception_handler)

        def address_port(port_or_tuple):
            if isinstance(port_or_tuple, int):
                return self.address, port_or_tuple
            return port_or_tuple

        for group, ports in (
                ('sig', self.sig_in_ports),
                ('cmd', self.cmd_in_ports)):
            for port_or_tuple in ports:
                address, port = address_port(port_or_tuple)
                loop.run_until_complete(loop.create_datagram_endpoint(
                    lambda: SignalinProtocol(self, group),
                    local_addr=(address, port)))
        for group, ports in (
                ('sig', self.sig_out_ports),
                ('cmd', self.cmd_out_ports)):
            for port_or_tuple in ports:
                address, port = address_port(port_or_tuple)
                loop.run_until_complete(loop.create_datagram_endpoint(
                    lambda: UdpOutProtocol(self, group),
                    remote_addr=(address, port)))

        self.logger.info('run_forever()')
        try:
            loop.run_forever()
        finally:
            self.logger.info('shutting down..')
            self.logger.info('done')
            loop.close()
            self.loop = None
