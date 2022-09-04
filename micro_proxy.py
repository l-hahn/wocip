import socket
import ssl
from time import sleep
from queue import Queue
from threading import Thread, Event, Lock


class MicroProxy:
    wait_symbols = "-\|/"
    def __init__(
            self, n_threads_max = 2, buf_byte_size=4096, client_timeout=0.5):
        self._n_threads = 0
        self._n_threads_max = n_threads_max
        self._buf_byte_size = buf_byte_size
        self._client_timeout = client_timeout

        self._thread_events = []
        self._threads = []
        self._job_queue = Queue()
        self._threads_lock = Lock()
        self._max_lock = Lock()
        self._listener_event = Event()
        self._is_listening = False

    def set_max_thread_count(self, n_threads_max):
        self._max_lock.acquire()
        self._n_threads_max = n_threads_max
        if self._n_threads > self._n_threads_max:
            self.rescale(self._n_threads_max)
        self._max_lock.release()

    def max_thread_count(self):
        return self._n_threads_max

    def thread_count(self):
        return self._n_threads

    def _get_socket(self):
        return socket.socket(
            socket.AF_INET,
            (
                socket.SOCK_STREAM
                if self._proxy_type == "TCP"
                else
                socket.SOCK_DGRAM
            )
        )

    def _set_listener(self):
        # Check what kind of socket is needed to
        # bind onto.
        # Take the first possible socket and the
        # required IP info for binding.
        self._addr_listen = socket.getaddrinfo(
            self._addr, self._port
        )[0][-1]

        if hasattr(self, '_socket_listen') and self._socket_listen is not None:
            self.stop()
        self._socket_listen = self._get_socket()
        self._socket_listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def listen(self, addr, port, proxy_type="TCP", backlog=0):
        if not self._is_listening:
            self._addr = addr
            self._port = port
            self._proxy_type = "UDP" if not proxy_type == "TCP" else proxy_type

            self._set_listener()

            self._socket_listen.bind(self._addr_listen)
            self._socket_listen.listen(backlog)

            self.rescale(self._n_threads_max)
            self._listen_thread = Thread(
                target=self._listener_thread, args=(self._listener_event,)
            )
            self._listen_thread.start()
            print(f"init done for serving on {self._addr_listen}")
            self._is_listening = True

    def stop(self):
        if self._is_listening:
            self._listener_event.set()
            ctr = 0
            while self._listen_thread.is_alive():
                print(
                    (
                        "Waiting for listener thread to finish... "
                        f"{MicroProxy.wait_symbols[ctr%len(MicroProxy.wait_symbols)]}\r"
                    ),
                    end=""
                )
                ctr += 1
                sleep(0.5)
            else:
                print("Listener thread finished closing safely.")
            self.rescale(0)
            self._socket_listen.close()
            del self._listen_thread
            self._is_listening = False

    def rescale(self, n_threads):
        new_n_threads = min(
            (
                n_threads
                if isinstance(n_threads, int) and max(-1,n_threads) >= 0
                else
                self._n_threads
            ), self._n_threads_max
        )
        old_n_threads = self._n_threads
        if self._n_threads < new_n_threads:
            self._spin_up(new_n_threads - self._n_threads)
        elif self._n_threads > new_n_threads:
            self._spin_down(self._n_threads - new_n_threads)
        if new_n_threads != old_n_threads:
            print(
                "Changed worker thread size "
                f"from {old_n_threads} to {new_n_threads}."
            )

    def join(self):
        if self._is_listening:
            self._listen_thread.join()

    def _spin_up(self, thread_cnt_new):
        self._threads_lock.acquire()

        new_thread_events = [
            Event()
            for _ in range(thread_cnt_new)
        ]
        self._thread_events.extend(new_thread_events)

        new_threads = [
            Thread(target=self._worker_thread, args=(event,))
            for event in new_thread_events
        ]
        self._threads.extend(new_threads)
        self._n_threads = len(self._threads)

        for thread in new_threads:
            thread.start()

        self._threads_lock.release()

    def _spin_down(self, thread_cnt_del):
        self._threads_lock.acquire()
        remaining = self._n_threads - thread_cnt_del

        thread_events_stop = self._thread_events[remaining:]
        threads_stop = self._threads[remaining:]
        self._thread_events = self._thread_events[:remaining]
        self._threads = self._threads[:remaining]
        for event in thread_events_stop:
            event.set()

        ctr = 0
        while any(
            thread.is_alive()
            for thread in threads_stop
        ):
            print(
                (
                    "Wait for worker threads to finish... "
                    f"{MicroProxy.wait_symbols[ctr%len(MicroProxy.wait_symbols)]}\r"
                ),
                end=""
            )
            ctr += 1
            sleep(0.5)
        else:
            print("Worker threads finished spinning down safely.")
        for idx in range(len(thread_events_stop)-1, -1, -1):
            del thread_events_stop[idx]
            del threads_stop[idx]
        del thread_events_stop
        del threads_stop

        self._threads_lock.release()


    def _listener_thread(self, event):
        while not event.is_set():
            conn, addr = self._socket_listen.accept()
            self._job_queue.put((addr, conn))
        # clear event to indicate it stopped at spindown task
        event.clear()

    def init_tunnle(request, sock_in, sock_out, host, port):
        if request.startswith(b"CONNECT"):
            try:
                sock_out.connect((host,port))
                sock_in.sendall(b"HTTP/1.1 200 established\r\n\r\n")
            except Exception as e:
                print("Cannot initiate HTTPS connection:", e)     
        return sock_out, sock_in

    def receive_data(sock, buf_byte):
        data = b""
        is_complete = False
        while not is_complete:
            try:
                part_data = sock.recv(buf_byte)
                if len(part_data) > 0:
                    data += part_data
                else:
                    is_complete = True
            except socket.timeout:
                is_complete = True
        return data

    def _sendrecv(self, sock_in, sock_out):
        init_data = MicroProxy.receive_data(sock_in, self._buf_byte_size)
        protocol, host_domain, port = MicroProxy.proxy_forward_filter(init_data.decode())
        if protocol == "https" or port == 443:
            sock_out, sock_in = MicroProxy.init_tunnle(init_data, sock_in, sock_out, host_domain, port)
            #initial request is CONNECT and handled by init_tunnle
            is_init = False
        else:
            sock_out.connect((host_domain,port))
            is_init = True
        is_last_request = len(init_data) == 0

        while not is_last_request:
            if is_init:
                request = init_data
                is_init = False
            else:
                request = MicroProxy.receive_data(sock_in, self._buf_byte_size)
            if len(request) > 0:
                sock_out.sendall(request)
                response = MicroProxy.receive_data(sock_out, self._buf_byte_size)
                if len(response) > 0:
                    sock_in.sendall(response)
            else:
                is_last_request = True

    def _worker_thread(self, event):
        while not event.is_set():
            if not self._job_queue.empty():
                addr, conn = self._job_queue.get()

                conn.settimeout(self._client_timeout)
                socket_client_thread = self._get_socket()
                socket_client_thread.settimeout(self._client_timeout)
                try:
                    self._sendrecv(conn, socket_client_thread)
                except Exception as e:
                    print("ERROR occured in Thread: ", e)
                conn.close()
                socket_client_thread.close()
            else:
                sleep(0.1)
        # clear event to indicate it stopped at spindown task
        event.clear()

    def proxy_forward_filter(request):
        header = request.split('\n')[0]
        url = header.split()[1]
        port = 80
        protocol = None
        has_port = False
        has_protocol = False

        if url.startswith("http"):
            protocol, host_part = url.split('://')
            has_protocol = True
        else:
            host_part = url

        if ":" in host_part:
            splitter = host_part.split(':')
            host_domain = splitter[0]
            port = int(splitter[1])
            has_port = True
        elif "/" in host_part:
            host_domain = host_part.split('/')[0]

        if not has_protocol and has_port:
            if port == 443:
                protocol = "https"
            else:
                protocol = "http"
        if not has_port:
            if protocol == "https":
                port = 443
            else:
                port = 80
        return (protocol, host_domain, port)

def main():
    mitm = MicroProxy(n_threads_max=10)
    mitm.listen(addr='0.0.0.0', port=8080)


if __name__ == "__main__":
    main()
