import pytest
import threading
import http.server
import functools
import os
import socket

def _find_free_port():
    """Find a free port to use for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP request handler that suppresses log messages."""
    def log_message(self, format, *args):
        pass  # Suppress logs

@pytest.fixture(scope="session")
def base_url():
    """Start an HTTP server serving the app and provide its base URL."""
    port = _find_free_port()
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    handler = functools.partial(QuietHandler, directory=root)
    server = http.server.HTTPServer(('127.0.0.1', port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
