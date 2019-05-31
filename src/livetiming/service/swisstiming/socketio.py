from socketIO_client import SocketIO, parsers
from socketIO_client.transports import *

import requests

ENGINEIO_PROTOCOL = 3


class StrippedWSTransport(AbstractTransport):
    def __init__(self, http_session, is_secure, url, engineIO_session=None):
        super(StrippedWSTransport, self).__init__(
            http_session, is_secure, url, engineIO_session)
        params = dict(http_session.params, **{
            'EIO': ENGINEIO_PROTOCOL, 'transport': 'websocket'})
        request = http_session.prepare_request(requests.Request('GET', url))
        kw = {'header': ['%s: %s' % x for x in request.headers.items()]}

        if engineIO_session:
            kw['timeout'] = self._timeout = engineIO_session.ping_timeout

        ws_url = '%s://%s/?%s' % (
            'wss' if is_secure else 'ws', url, format_query(params))
        http_scheme = 'https' if is_secure else 'http'
        if http_scheme in http_session.proxies:  # Use the correct proxy
            proxy_url_pack = parse_url(http_session.proxies[http_scheme])
            kw['http_proxy_host'] = proxy_url_pack.hostname
            kw['http_proxy_port'] = proxy_url_pack.port
            if proxy_url_pack.username:
                kw['http_proxy_auth'] = (
                    proxy_url_pack.username, proxy_url_pack.password)
        if http_session.verify:
            if http_session.cert:  # Specify certificate path on disk
                if isinstance(http_session.cert, six.string_types):
                    kw['ca_certs'] = http_session.cert
                else:
                    kw['ca_certs'] = http_session.cert[0]
        else:  # Do not verify the SSL certificate
            kw['sslopt'] = {'cert_reqs': ssl.CERT_NONE}
        try:
            self._connection = create_connection(ws_url, **kw)
        except Exception as e:
            raise ConnectionError(e)

    def recv_packet(self):
        try:
            packet_text = self._connection.recv()
        except WebSocketTimeoutException as e:
            raise TimeoutError('recv timed out (%s)' % e)
        except SSLError as e:
            raise ConnectionError('recv disconnected by SSL (%s)' % e)
        except WebSocketConnectionClosedException as e:
            raise ConnectionError('recv disconnected (%s)' % e)
        except SocketError as e:
            raise ConnectionError('recv disconnected (%s)' % e)
        if not isinstance(packet_text, six.binary_type):
            packet_text = packet_text.encode('utf-8')
        engineIO_packet_type, engineIO_packet_data = parse_packet_text(
            packet_text)
        yield engineIO_packet_type, engineIO_packet_data

    def send_packet(self, engineIO_packet_type, engineIO_packet_data=''):
        packet = format_packet_text(engineIO_packet_type, engineIO_packet_data)
        try:
            self._connection.send(packet)
        except WebSocketTimeoutException as e:
            raise TimeoutError('send timed out (%s)' % e)
        except (SocketError, WebSocketConnectionClosedException) as e:
            raise ConnectionError('send disconnected (%s)' % e)

    def set_timeout(self, seconds=None):
        self._connection.settimeout(seconds or self._timeout)


class WebsocketOnlySocketIO(SocketIO):
    def _get_engineIO_session(self):
        warning_screen = self._yield_warning_screen()
        for elapsed_time in warning_screen:
            transport = StrippedWSTransport(
                self._http_session, self._is_secure, self._url)
            try:
                engineIO_packet_type, engineIO_packet_data = next(
                    transport.recv_packet())
                break
            except (TimeoutError, ConnectionError) as e:
                if not self._wait_for_connection:
                    raise
                warning = Exception(
                    '[engine.io waiting for connection] %s' % e)
                warning_screen.throw(warning)
        assert engineIO_packet_type == 0  # engineIO_packet_type == open
        return parsers.parse_engineIO_session(engineIO_packet_data)

    def _negotiate_transport(self):
        self.transport_name = 'websocket'
        self._transport_instance = self._get_transport('websocket')
        try:
            transport = self._get_transport('websocket')
            transport.send_packet(2, 'probe')
            for packet_type, packet_data in transport.recv_packet():
                if packet_type == 3 and packet_data == b'probe':
                    transport.send_packet(5, '')
                    self._transport_instance = transport
                    self.transport_name = 'websocket'
                else:
                    self._warn('unexpected engine.io packet')
        except Exception:
            pass
        self._debug('[engine.io transport selected] %s', self.transport_name)

    def _get_transport(self, transport_name):
        SelectedTransport = {
            'websocket': StrippedWSTransport,
        }[transport_name]
        return SelectedTransport(
            self._http_session, self._is_secure, self._url,
            self._engineIO_session)
