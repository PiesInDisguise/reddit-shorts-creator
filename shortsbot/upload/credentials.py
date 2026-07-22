import json
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

from .base import NotConfiguredError

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_SCOPES = "video.publish"


def get_youtube_client(client_secrets_file: Path, token_file: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise NotConfiguredError(
            "YouTube upload dependencies are not installed. Run: "
            "pip install -r requirements-upload.txt"
        ) from exc

    if not client_secrets_file.exists():
        raise NotConfiguredError(
            f"YouTube client secrets file not found at {client_secrets_file}. "
            "Create an OAuth client (Desktop app) in Google Cloud Console, enable the "
            "YouTube Data API v3, and download the client secret JSON to that path."
        )

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), YOUTUBE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_file), YOUTUBE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def _run_local_callback_server(port: int) -> str:
    """Block until the OAuth redirect hits http://localhost:{port}/..., then
    return the 'code' query param from it."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            result["code"] = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Authorized -- you can close this tab.</body></html>")

        def log_message(self, *args):
            pass

    server = HTTPServer(("localhost", port), Handler)
    server.handle_request()  # blocks for exactly one request, then returns
    return result.get("code")


def _save_tiktok_token(token_file: Path, token_response: dict) -> None:
    token_file.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": token_response["access_token"],
        "refresh_token": token_response.get("refresh_token"),
        "expires_at": time.time() + token_response.get("expires_in", 3600),
    }
    token_file.write_text(json.dumps(data))


def get_tiktok_access_token(
    client_key: str, client_secret: str, token_file: Path, redirect_uri: str
) -> str:
    """Return a valid TikTok access token, refreshing a cached one or running
    the interactive browser authorization flow (one-time, then cached) if
    needed."""
    if not client_key or not client_secret:
        raise NotConfiguredError(
            "TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET are not set. Create an app at "
            "https://developers.tiktok.com with Content Posting API access."
        )

    if token_file.exists():
        cached = json.loads(token_file.read_text())
        if cached.get("expires_at", 0) > time.time() + 60:
            return cached["access_token"]
        if cached.get("refresh_token"):
            resp = requests.post(
                TIKTOK_TOKEN_URL,
                data={
                    "client_key": client_key,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": cached["refresh_token"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.status_code == 200:
                token_response = resp.json()
                _save_tiktok_token(token_file, token_response)
                return token_response["access_token"]

    # No valid/refreshable cached token -- run the one-time browser authorization flow.
    port = int(urllib.parse.urlparse(redirect_uri).port or 8081)
    params = {
        "client_key": client_key,
        "scope": TIKTOK_SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": "shortsbot",
    }
    auth_url = f"{TIKTOK_AUTH_URL}?{urllib.parse.urlencode(params)}"
    webbrowser.open(auth_url)
    code = _run_local_callback_server(port)
    if not code:
        raise NotConfiguredError(
            "TikTok authorization did not return a code (redirect URI must match your "
            f"app's registered redirect URI exactly: {redirect_uri})."
        )

    resp = requests.post(
        TIKTOK_TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise NotConfiguredError(f"TikTok token exchange failed: {resp.text}")
    token_response = resp.json()
    _save_tiktok_token(token_file, token_response)
    return token_response["access_token"]
