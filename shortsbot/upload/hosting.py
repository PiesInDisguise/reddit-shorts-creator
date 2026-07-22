import contextlib
import http.server
import socket
import threading
from functools import partial
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def temporary_public_url(file_path: Path, ngrok_auth_token: str = ""):
    """Serve file_path over a temporary public HTTPS URL via a local HTTP
    server tunneled through ngrok -- Instagram's Graph API needs a public URL
    for the video, not a direct file upload. Requires `pyngrok` (see
    requirements-upload.txt) and, for a stable/longer-lived tunnel, an
    NGROK_AUTH_TOKEN (free account)."""
    try:
        from pyngrok import ngrok
    except ImportError as exc:
        raise RuntimeError(
            "pyngrok is not installed. Run: pip install -r requirements-upload.txt"
        ) from exc

    if ngrok_auth_token:
        ngrok.set_auth_token(ngrok_auth_token)

    port = _free_port()
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(file_path.parent))
    server = http.server.ThreadingHTTPServer(("localhost", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    tunnel = ngrok.connect(port, "http")
    public_base = tunnel.public_url.replace("http://", "https://")

    try:
        yield f"{public_base}/{file_path.name}"
    finally:
        ngrok.disconnect(tunnel.public_url)
        server.shutdown()
        server.server_close()
