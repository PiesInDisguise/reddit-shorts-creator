import time
from pathlib import Path
from typing import List, Optional

import requests

from .base import NotConfiguredError, Uploader, UploadError, UploadResult
from .credentials import get_tiktok_access_token

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# TikTok has no "unlisted" concept; FOLLOWER_OF_CREATOR is the closest
# less-than-fully-public option.
PRIVACY_MAP = {
    "public": "PUBLIC_TO_EVERYONE",
    "unlisted": "FOLLOWER_OF_CREATOR",
    "private": "SELF_ONLY",
}

CHUNK_SIZE = 10 * 1024 * 1024  # 10MB


class TikTokUploader(Uploader):
    """TikTok Content Posting API (direct post, FILE_UPLOAD source). Note:
    unaudited apps are restricted by TikTok to SELF_ONLY privacy and/or
    posting to the creator's draft inbox rather than direct publish --
    that's a TikTok-side app review requirement, not something this code
    can work around."""

    platform_name = "tiktok"

    def __init__(self, client_key: str, client_secret: str, token_file: Path, redirect_uri: str):
        self.client_key = client_key
        self.client_secret = client_secret
        self.token_file = token_file
        self.redirect_uri = redirect_uri

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
        if tags:
            caption += " " + " ".join(f"#{t.lstrip('#')}" for t in tags)

        video_size = video_path.stat().st_size
        total_chunk_count = max(1, (video_size + CHUNK_SIZE - 1) // CHUNK_SIZE)
        chunk_size = CHUNK_SIZE if total_chunk_count > 1 else video_size

        payload = {
            "post_info": {
                "title": caption,
                "privacy_level": PRIVACY_MAP.get(privacy, "SELF_ONLY"),
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": chunk_size,
                "total_chunk_count": total_chunk_count,
            },
        }

        if dry_run:
            return UploadResult(
                platform=self.platform_name, video_id=None, url=None, dry_run=True, payload=payload
            )

        access_token = get_tiktok_access_token(
            self.client_key, self.client_secret, self.token_file, self.redirect_uri
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        init_resp = requests.post(INIT_URL, headers=headers, json=payload, timeout=30)
        init_data = init_resp.json() if init_resp.content else {}
        if init_resp.status_code != 200 or init_data.get("error", {}).get("code") not in (
            "ok",
            None,
        ):
            raise UploadError(f"TikTok publish init failed: {init_resp.status_code} {init_resp.text}")

        publish_id = init_data["data"]["publish_id"]
        upload_url = init_data["data"]["upload_url"]

        video_bytes = video_path.read_bytes()
        for i in range(total_chunk_count):
            start = i * chunk_size
            end = min(start + chunk_size, video_size) - 1
            chunk = video_bytes[start : end + 1]
            put_resp = requests.put(
                upload_url,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{video_size}",
                    "Content-Type": "video/mp4",
                },
                data=chunk,
                timeout=120,
            )
            if put_resp.status_code not in (200, 201):
                raise UploadError(
                    f"TikTok chunk {i + 1}/{total_chunk_count} upload failed: "
                    f"{put_resp.status_code} {put_resp.text}"
                )

        status = self._poll_status(publish_id, headers)
        if status == "FAILED":
            raise UploadError(f"TikTok reported the post failed processing (publish_id={publish_id}).")

        return UploadResult(
            platform=self.platform_name,
            video_id=publish_id,
            url=None,  # TikTok's API doesn't return a direct post URL synchronously
            dry_run=False,
            payload={"status": status},
        )

    def _poll_status(self, publish_id: str, headers: dict, timeout: float = 120, interval: float = 5) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            resp = requests.post(
                STATUS_URL, headers=headers, json={"publish_id": publish_id}, timeout=30
            )
            if resp.status_code == 200:
                status = resp.json().get("data", {}).get("status")
                if status in ("PUBLISH_COMPLETE", "FAILED"):
                    return status
            time.sleep(interval)
        return "TIMEOUT"
