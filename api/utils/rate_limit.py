import time

class RateLimiter:
    def __init__(self, max_requests=20, window_seconds=60):
        self._store = {}
        self._max = max_requests
        self._window = window_seconds

    def is_limited(self, ip):
        """Returns True if the IP has exceeded the rate limit."""
        now = time.time()
        if ip not in self._store:
            self._store[ip] = []
        self._store[ip] = [t for t in self._store[ip] if now - t < self._window]
        if len(self._store[ip]) >= self._max:
            return True
        self._store[ip].append(now)
        return False

    def get_client_ip(self, handler):
        """Extract client IP from request headers."""
        ip = handler.headers.get('X-Forwarded-For',
            handler.client_address[0] if handler.client_address else 'unknown')
        if isinstance(ip, str) and ',' in ip:
            ip = ip.split(',')[0].strip()
        return ip
