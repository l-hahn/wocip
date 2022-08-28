import network
import socket
import _thread
from time import sleep
from collections import deque
from uasyncio import Event
import re


class MicroProxy:
    wait_symbols = {
        0: "-",
        1: "\\",
        2: "|",
        3: "/"
    }
    def __init__(
            self, n_threads_max = 2, buf_byte_size=1024, client_timeout=10):
        self._n_threads = 0
        self._n_threads_max = n_threads_max
        self._buf_byte_size = buf_byte_size
        self._client_timeout = client_timeout

        self._thread_events = []
        self._job_queue = deque((), 1024)
        self._threads_lock = _thread.allocate_lock()
        self._max_lock = _thread.allocate_lock()
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
        self._socket_listen = socket.socket(
            socket.AF_INET,
            (
                socket.SOCK_STREAM
                if self._proxy_type == "TCP"
                else
                socket.SOCK_DGRAM
            )
        )
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
            _thread.start_new_thread(
                self._listener_thread,(self._listener_event,)
            )

            self._is_listening = True

    def stop(self):
        if self._is_listening:
            self._listener_event.set()
            ctr = 0
            while self._listener_event.is_set():
                print(
                    (
                        "Waiting for listener thread to finish... "
                        f"{MicroProxy.wait_symbols[ctr%4]}\r"
                    ),
                    end=""
                )
                ctr += 1
                sleep(0.5)
            else:
                print("Listener thread finished closing safely.")
            self.rescale(0)
            self._socket_listen.close()
            del self._socket_listen
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

    def _spin_up(self, thread_cnt_new):
        self._threads_lock.acquire()
        
        new_thread_events = [
            Event()
            for _ in range(thread_cnt_new)
        ]
        self._thread_events.extend(new_thread_events)

        for idx, event in enumerate(new_thread_events):
            _thread.start_new_thread(
                self._worker_thread, (
                    #thread_idx is 1 based; 0 is master.
                    event, self._n_threads+idx+1
                )
            )
        self._n_threads = len(self._thread_events)

        self._threads_lock.release()

    def _spin_down(self, thread_cnt_del):
        self._threads_lock.acquire()
        remaining = self._n_threads - thread_cnt_del

        thread_events_stop = self._thread_events[remaining:]
        self._thread_events = self._thread_events[:remaining]
        for event in thread_events_stop:
            event.set()
        
        ctr = 0
        while any(
            event.is_set()
            for event in thread_events_stop
        ):
            print(
                (
                    "Wait for worker threads to finish... "
                    f"{MicroProxy.wait_symbols[ctr%4]}\r"
                ),
                end=""
            )
            ctr += 1
            sleep(0.5)
        else:
            print("Worker threads finished spinning down safely.")
        for idx in range(len(thread_events_stop)-1, -1, -1):
            del thread_events_stop[idx]
        del thread_events_stop

        self._threads_lock.release()


    def _listener_thread(self, event):
        while not event.is_set():
            conn, addr = self._socket_listen.accept()
            self._job_queue.append((addr, conn))
        # clear event to indicate it stopped at spindown task
        event.clear()

    def _worker_thread(self, event, thread_id):
        print(f"Worker thread {thread_id}: starting.")
        socket_client_thread = socket.socket(
            socket.AF_INET,
            (
                socket.SOCK_STREAM
                if self._proxy_type == "TCP"
                else
                socket.SOCK_DGRAM
            )
        )
        socket_client_thread.settimeout(self._client_timeout)
        while not event.is_set():
            if len(self._job_queue) > 0:
                try:
                    addr, conn = self._job_queue.popleft()
                except:
                    # Maybe another thread was faster inbetween.
                    # If so, simply continue
                    continue
                print(
                    f"Worker thread {thread_id}:",
                    f"handling connection of '{addr}'"
                )
                request = conn.recv(self._buf_byte_size)
                protocol, host_domain, port = MicroProxy.proxy_forward_filter(
                    request
                )
                print(
                    f"Worker thread {thread_id}: ",
                    f"{protocol}://{host_domain}:{port}"
                )
                socket_client_thread.connect(host_domain, port)
                socket_client_thread.sendall(request)
                has_response = False
                while not has_response:
                    response = socket_client_thread.recv(self._buf_byte_size)
                    if len(response) > 0:
                        has_response = True
                        conn.send(response)
            else:
                sleep(0.1)
        print(f"Worker thread {thread_id}: finished safely and shutting down.")
        # clear event to indicate it stopped at spindown task
        event.clear()

    def proxy_forward_filter(request):
        header = request.split('\n')[0]
        url = header.split()[1]

        protocol = re.findall('(\w+)://', url)[0]
        host_domain = re.findall('://([\w\-\.]+)', url)
        ports = re.findall('://[\w\-\.]+:(\d+)', url)
        port = ports[0] if len(ports) > 0 else 443 if protocol == "https" else 80

        return (protocol, host_domain, port)


def connect_wlan(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        info_str = (
            
        )
        print(
            "waiting for connection...",
            f"{MicroProxy.wait_symbols[max_wait%4]}\r",
            end=""
        )
        sleep(1)
    if wlan.status() != 3:
        raise RuntimeError('network connection failed')
    else:
        status = wlan.ifconfig()
        print(f'conntected, ip = {status[0]}')
    return wlan

def main():
    ssid = 'Lars-WLAN'
    password = '0243LHBS18021909'
    wlan = connect_wlan(ssid, password)

    mitm = MicroProxy(n_threads_max=1)
    mitm.listen(addr='0.0.0.0', port=8080)

    for idx in range(100):
        print("Do proxy stuff")
        sleep(1)

if __name__ == "__main__":
    main()