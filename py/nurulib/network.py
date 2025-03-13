import io, json, socket, time

from . import perf, settings, util


logger = util.NoLogger()
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send(port, data, address=settings.address, sock=sock):
    msg = util.serialize(data)
    sock.sendto(msg + b'\n', (address, port))


class SignalinSender:
    """Sends messages to integrator's signalin port."""

    def __init__(self, signalin_port, logger):
        self.signalin_port = signalin_port
        self.logger = logger
        self.signalin_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, d, address):
        self.logger.info('sending {} to {}'.format(d, address))
        msg = json.dumps(d).encode('utf8')
        self.signalin_sock.sendto(msg, (address, self.signalin_port))


class StatusSender:
    """Sends changes and periodic confirmations of updates."""

    def __init__(self, name, logger, repeat_secs=10):
        self.name = name
        self.repeat_secs = repeat_secs
        self.logger = logger
        self.status_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_status = None
        self.last_t = 0

    def send(self, status, log_send=False):
        assert isinstance(status, str), '{} should be string'.format(status)
        t = time.time()
        if self.last_status == status and t - self.last_t < self.repeat_secs:
            return
        self.last_status = status
        self.last_t = t
        d = dict(
            name=self.name,
            status=status,
            t=t,
            ip=get_ip(),
        )
        if log_send:
            self.logger.debug('sending {}'.format(d))
        msg = json.dumps(d).encode('utf8')
        status_address = (settings.address, settings.status_port)
        try:
            self.status_sock.sendto(msg, status_address)
        except socket.gaierror as e:
            logger.error('Could not send GAI error : {}'.format(e))
        except socket.error as e:
            logger.error('Could not send socket error : {}'.format(e))


def create_udp_socket(port, address, timeout=0):
    """Creates a UDP socket.

    Args:
      port: port to listen on
      address: address to listen on
      timeout: setting `None` makes the socket blocking, otherwise every call
          to `recvfrom()` will wait up to `timeout` seconds
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    # sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.bind((address, port))
    return sock


@perf.measure('get_json_and_address')
def get_json_and_address(sock, max_size=4096):
    try:
        data, address = sock.recvfrom(max_size)
    except socket.timeout:
        return None, None
    except io.BlockingIOError:
        return None, None
    try:
        data = util.deserialize(data)
        return data, address
    except json.JSONDecodeError as e:
        logger.warning('Could not decode {!r} : {}'.format(data, e))
        return None, None


def get_json(sock, data, max_size=4096):
    newdata, _ = get_json_and_address(sock, max_size=max_size)
    if newdata:
        return newdata
    return data


def get_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except socket.gaierror:
        return 'get_ip:gaierror'
