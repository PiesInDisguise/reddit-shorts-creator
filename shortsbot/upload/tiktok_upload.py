from pathlib import Path
from typing import List, Optional

from .base import NotConfiguredError, Uploader, UploadResult


class TikTokUploader(Uploader):
    """Stub: TikTok's Content Posting API requires an app-review-approved
    developer app for direct publish; unaudited apps are restricted to pushing
    to the creator's private draft inbox for manual confirmation in-app. Not
    wired up yet — build this out once API access is sorted."""

    platform_name = "tiktok"

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy: str = "private",
        dry_run: bool = False,
    ) -> UploadResult:
        payload = {
            "video_path": str(video_path),
            "title": title,
            "description": description,
            "tags": tags or [],
            "privacy": privacy,
        }
        if dry_run:
            return UploadResult(
                platform=self.platform_name, video_id=None, url=None, dry_run=True, payload=payload
            )
        raise NotConfiguredError(
            "TikTok upload is not implemented yet: it needs a TikTok Developer app "
            "with Content Posting API access (app review required for direct publish; "
            "unaudited apps can only push to the creator's draft inbox). "
            "Post the finished file manually for now."
        )
