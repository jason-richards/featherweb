try:
    import socket
    import select
    import errno
    import sys
except:
    import usocket as socket
    import uselect as select
    import uerrno as errno


class FeatherWeb(object):
    m_Address = None
    m_Port = 80
    m_MaxQ = 5
    m_Routes = []


    def __init__(self, addr='0.0.0.0', port=80, maxQ=5, insecureReuse=False):
        self.m_Address = addr
        self.m_Port = port
        self.m_MaxQ = maxQ
        self.m_InsecureReuse = insecureReuse


    def route(self, url, **kwargs):
        def _route(f):
            self.m_Routes.append((url, f, kwargs))
            return f
        return _route


    def run(self, timeout=5, callback=None, **kwargs):
        """ Run the request server forever.  If provided, a callback is fired with kwargs on the timeout interval.
            Returning False from timeout callback shall cause the request server to exit."""

        address = socket.getaddrinfo(self.m_Address, self.m_Port)[0][-1]
        l_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.m_InsecureReuse:
            l_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l_Socket.bind(address)
        l_Socket.listen(self.m_MaxQ)
        l_Socket.setblocking(True)
        l_Socket.settimeout(timeout)

        sockfd = l_Socket.makefile('rb')
        try:
            sockfd = sockfd.fileno()
        except:
            pass
        poller = select.poll()
        poller.register(sockfd, select.POLLIN)

        running = True
        while running:
            try:
                events = poller.poll(timeout*1000)
                if not events and callback:
                    running = callback(**kwargs)
                    continue

                for fd, event in events:
                    if event & select.POLLHUP or event & select.POLLERR:
                        poller.unregister(sockfd)
                        raise Exception ("POLLHUP/POLLERR")

                    if fd is not sockfd or not event & select.POLLIN:
                        continue

                    client, address = l_Socket.accept()
                    client.settimeout(timeout)

                    try:
                        clientfd = client.makefile('rwb', 0)

                        response = HTTPRequest(client, clientfd.readline())

                        # This may be dangerous for the ESP8266.  Request headers may be extensively large - a simple
                        # Request with lots of HTTP headers could cause OOM crash. Request headers may be 8-16KB!
                        while True:
                            line = clientfd.readline()
                            if not line or line == b'\r\n':
                                break
                            k, v = line.split(b":", 1)
                            response.headers[k] = v.strip()

                        found = False
                        for e in self.m_Routes:
                            pattern = e[0]
                            handler = e[1]

                            if response.path.split('?', 1)[0] == pattern:
                                found = True
                                break

                        if not found:
                            raise Exception("Not Found")

                        handler(response)

                    except KeyboardInterrupt:
                        running = False

                    except Exception as e:
                        if e.args[0] != errno.ETIMEDOUT:
                            client.sendall('HTTP/1.0 404 NA\r\n\r\n'.encode('utf-8'))

                    finally:
                        clientfd.close()
                        client.close()

            except KeyboardInterrupt:
                running = False

        poller.unregister(sockfd)
        try:
            sockfd.close()
        except:
            pass
        l_Socket.close()


HTTPStatusCodes = {
    200 : 'OK',
    201 : 'Created',
    202 : 'Accepted',
    203 : 'Non-Authoritative Information',
    204 : 'No Content',
    205 : 'Reset Content',
    206 : 'Partial Content',
    300 : 'Multiple Choices',
    301 : 'Moved Permanently',
    302 : 'Found',
    303 : 'See Other',
    304 : 'Not Modified',
    305 : 'Use Proxy',
    306 : '(Unused)',
    307 : 'Temporary Redirect',
    400 : 'Bad Request',
    401 : 'Unauthorized',
    402 : 'Payment Required',
    403 : 'Forbidden',
    404 : 'Not Found',
    405 : 'Method Not Allowed',
    406 : 'Not Acceptable',
    407 : 'Proxy Authentication Required',
    408 : 'Request Timeout',
    409 : 'Conflict',
    410 : 'Gone',
    411 : 'Length Required',
    412 : 'Precondition Failed',
    413 : 'Request Entity Too Large',
    414 : 'Request-URI Too Long',
    415 : 'Unsupported Media Type',
    416 : 'Requested Range Not Satisfiable',
    417 : 'Expectation Failed',
    500 : 'Internal Server Error',
    501 : 'Not Implemented',
    502 : 'Bad Gateway',
    503 : 'Service Unavailable',
    504 : 'Gateway Timeout',
    505 : 'HTTP Version Not Supported'
}

class HTTPRequest():
    method = None
    path = None
    proto = None
    headers = {}

    def __init__(self, client, request, headers={}):
        """ Utility object for HTTP request responses. """
        self.client = client
        self.method, self.path, self.proto = request.decode().split()
        self.headers = headers

    def __headers(self, status, content_type, headers):
        self.client.sendall(("HTTP/1.1 %d %s\r\n" % (status, HTTPStatusCodes[status] if status in HTTPStatusCodes else "NA")).encode('utf-8'))
        self.client.sendall("Content-Type: ".encode('utf-8'))
        self.client.sendall(content_type.encode('utf-8'))
        if not headers:
            self.client.sendall("\r\n\r\n".encode('utf-8'))
        else:
            self.client.sendall("\r\n".encode('utf-8'))
            if isinstance(headers, bytes):
                self.client.sendall(headers)
            elif isinstance(headers, str):
                self.client.sendall(headers.encode('utf-8'))
            else:
                for k, v in self.items():
                    self.client.sendall(k.encode('utf-8'))
                    self.client.sendall(": ".encode('utf-8'))
                    self.client.sendall(v.encode('utf-8'))
                    self.client.sendall("\r\n".encode('utf-8'))
            self.client.sendall("\r\n".encode('utf-8'))

    def send(self, response='', status=200, content_type="text/html; charset=utf-8", headers=None):
        """ Send a textual response. """
        self.__headers(status, content_type, headers)
        self.client.sendall(response.encode('utf-8') if isinstance(response, str) else response)

    def sendfile(self, filename, chunksize=128, status=200, content_type="text/html; charset=utf-8", headers=None):
        """ Send a file in response, one chunk at a time.  Caller handles exceptions. """
        with open(filename, 'rb') as f:
            self.__headers(status, content_type, headers)
            while True:
                data = f.read(chunksize)
                if not data:
                    break
                self.client.sendall(data)
