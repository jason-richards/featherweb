import usocket as socket
import uselect as select


class FeatherWeb(object):
    m_Socket = None
    m_Routes = []


    def __init__(self, addr='0.0.0.0', port=80, maxQ=5):
        address = socket.getaddrinfo(addr, port)[0][-1]
        self.m_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.m_Socket.bind(address)
        self.m_Socket.listen(maxQ)
        self.m_Socket.setblocking(True)


    def __del__(self):
        self.m_Socket.close()


    def route(self, url, **kwargs):
        def _route(f):
            self.m_Routes.append((url, f, kwargs))
            return f
        return _route


    def run(self, timeout=5, callback=None, **kwargs):
        """ Run the request server forever.  If provided, a callback is fired with kwargs on the timeout interval.
            Returning False from timeout callback shall cause the request server to exit."""

        self.m_Socket.settimeout(timeout)

        poller = select.poll()
        poller.register(self.m_Socket, select.POLLIN)

        while True:
            events = poller.poll(timeout*1000)
            if not events and callback:
                if not callback(**kwargs):
                    break
                continue

            for fd, event in events:
                if event & select.POLLHUP or event & select.POLLERR:
                    poller.unregister(self.m_Socket)
                    raise Exception ("POLLHUP/POLLERR")

                if id(fd) is not id(self.m_Socket) or not event & select.POLLIN:
                    continue

                client, address = self.m_Socket.accept()

                try:
                    f = client.makefile('rwb', 0)

                    response = HTTPRequest(client, f.readline())

                    # This may be dangerous for the ESP8266.  Request headers may be extensively large - a simple
                    # Request with lots of HTTP headers could cause OOM crash. Request headers may be 8-16KB!
                    while True:
                        line = f.readline()
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
                        raise

                    handler(response)

                except Exception as e:
                    client.sendall('HTTP/1.0 404 NA\r\n\r\n')

                finally:
                    client.close()

        poller.unregister(self.m_Socket)

        
class HTTPRequest():

    def __init__(self, client, request, content_type="text/html; charset=utf-8", status="200", headers={}):
        """ Utility object for HTTP request responses. """
        self.client = client
        self.method, self.path, self.proto = request.decode().split()
        self.content_type = content_type
        self.status = status
        self.headers = headers


    def __headers(self):
        self.client.sendall("HTTP/1.0 %s OK\r\n" % self.status)
        self.client.sendall("Content-Type: ")
        self.client.sendall(self.content_type)
        if not self.headers:
            self.client.sendall("\r\n\r\n")
        else:
            self.client.sendall("\r\n")
            if isinstance(self.headers, bytes) or isinstance(self.headers, str):
                self.client.sendall(self.headers)
            else:
                for k, v in self.headers.items():
                    self.client.sendall(k)
                    self.client.sendall(": ")
                    self.client.sendall(v)
                    self.client.sendall("\r\n")
            self.client.sendall("\r\n")


    def send(self, response):
        """ Send a textual response. """
        self.__headers()
        self.client.sendall(response)


    def sendfile(self, filename, chunksize=128):
        """ Send a file in response, one chunk at a time.  Caller handles exceptions. """
        with open(filename, 'rb') as f:
            self.__headers()
            while True:
                data = f.read(chunksize)
                if not data:
                    break
                self.client.sendall(data)
