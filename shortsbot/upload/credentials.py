from pathlib import Path

from .base import NotConfiguredError

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


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
