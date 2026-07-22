import time
from pathlib import Path
from typing import List, Optional

import requests

from .base import NotConfiguredError, Uploader, UploadError, UploadResult
from .hosting import temporary_public_url

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


class InstagramUploader(Uploader):
    """Instagram Graph API Reels publishing. Needs a Business/Creator IG
    account linked to a Facebook Page and a long-lived access token with the
    instagram_content_publish permission (Meta App Review required for use
    beyond your own linked test account). The Graph API requires a public
    URL for the video rather than a direct upload, so this spins up a
    temporary ngrok tunnel to the local file for the duration of the call --
    see hosting.py."""

    platform_name = "instagram"

    def __init__(self, access_token: str, ig_user_id: str, ngrok_auth_token: str = ""):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.ngrok_auth_token = ngrok_auth_token

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy: str = "private",
        dry_run: bool = False,
    ) -> UploadResult:
        caption = title
        if description:
            caption += "\n\n" + description
        if tags:
            caption += " " + " ".join(f"#{t.lstrip('#')}" for t in tags)

        payload = {"media_type": "REELS", "caption": caption}

        if dry_run:
            return UploadResult(
                platform=self.platform_name, video_id=None, url=None, dry_run=True, payload=payload
            )

        if not self.access_token or not self.ig_user_id:
            raise NotConfiguredError(
                "IG_ACCESS_TOKEN/IG_BUSINESS_ACCOUNT_ID are not set. Needs a Business/Creator "
                "IG account linked to a Facebook Page, and a long-lived access token with the "
                "instagram_content_publish permission."
            )

        # Instagram's privacy follows the account's own setting, not a per-post
        # API field -- `privacy` is accepted for interface consistency but has
        # no effect here.
        with temporary_public_url(video_path, self.ngrok_auth_token) as video_url:
            create_resp = requests.post(
                f"{GRAPH_API_BASE}/{self.ig_user_id}/media",
                data={
                    "access_token": self.access_token,
                    "video_url": video_url,
                    "media_type": "REELS",
                    "caption": caption,
                },
                timeout=30,
            )
            if create_resp.status_code != 200:
                raise UploadError(f"Instagram media creation failed: {create_resp.text}")
            creation_id = create_resp.json()["id"]

            status = self._wait_until_ready(creation_id)
            if status != "FINISHED":
                raise UploadError(
                    f"Instagram media processing did not finish (status={status}, "
                    f"creation_id={creation_id})."
                )

        publish_resp = requests.post(
            f"{GRAPH_API_BASE}/{self.ig_user_id}/media_publish",
            data={"access_token": self.access_token, "creation_id": creation_id},
            timeout=30,
        )
        if publish_resp.status_code != 200:
            raise UploadError(f"Instagram publish failed: {publish_resp.text}")
        media_id = publish_resp.json()["id"]

        url = None
        permalink_resp = requests.get(
            f"{GRAPH_API_BASE}/{media_id}",
            params={"fields": "permalink", "access_token": self.access_token},
            timeout=30,
        )
        if permalink_resp.status_code == 200:
            url = permalink_resp.json().get("permalink")

        return UploadResult(
            platform=self.platform_name, video_id=media_id, url=url, dry_run=False, payload=payload
        )

    def _wait_until_ready(self, creation_id: str, timeout: float = 180, interval: float = 5) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.get(
                f"{GRAPH_API_BASE}/{creation_id}",
                params={"fields": "status_code", "access_token": self.access_token},
                timeout=30,
            )
            if resp.status_code == 200:
                status = resp.json().get("status_code")
                if status in ("FINISHED", "ERROR", "EXPIRED"):
                    return status
            time.sleep(interval)
        return "TIMEOUT"
