"""In-process pub/sub. The HTTP server turns each subscriber queue into an SSE stream."""
import queue
import threading


class Bus:
    def __init__(self):
        self.subs = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.subs.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subs:
                self.subs.remove(q)

    def publish(self, kind, **data):
        msg = dict(kind=kind, **data)
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:  # slow client: drop, it re-syncs from /api/state
                pass
