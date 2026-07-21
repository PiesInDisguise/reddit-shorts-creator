from pathlib import Path
from typing import List, Optional

from .base import NotConfiguredError, Uploader, UploadResult


class InstagramUploader(Uploader):
    """Stub: Instagram's Graph API needs the video to be reachable via a public
    URL (not a direct file upload) plus a Business/Creator IG account linked to
    a Facebook Page. Not wired up yet — needs a hosting decision (cloud bucket
    with signed URL vs. a local tunnel like ngrok) and a Meta App Review for
    the instagram_content_publish permission before this can go live."""

    platform_name = "instagram"

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
            "Instagram upload is not implemented yet: it needs a public URL for the "
            "video file (cloud bucket or local tunnel), a Business/Creator IG account "
            "linked to a Facebook Page, and Meta App Review for instagram_content_publish. "
            "Post the finished file manually for now."
        )
