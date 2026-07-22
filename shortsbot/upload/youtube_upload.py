from pathlib import Path
from typing import List, Optional

from .base import Uploader, UploadResult
from .credentials import get_youtube_client

PRIVACY_MAP = {"public": "public", "private": "private", "unlisted": "unlisted"}


class YouTubeUploader(Uploader):
    platform_name = "youtube"

    def __init__(self, client_secrets_file: Path, token_file: Path):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file

    def upload(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy: str = "private",
        dry_run: bool = False,
    ) -> UploadResult:
        if "#shorts" not in description.lower():
            description = f"{description}\n\n#Shorts".strip()

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or [],
            },
            "status": {"privacyStatus": PRIVACY_MAP.get(privacy, "private")},
        }

        if dry_run:
            return UploadResult(
                platform=self.platform_name,
                video_id=None,
                url=None,
                dry_run=True,
                payload={"body": body, "video_path": str(video_path)},
            )

        from googleapiclient.http import MediaFileUpload

        youtube = get_youtube_client(self.client_secrets_file, self.token_file)
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()

        video_id = response["id"]
        return UploadResult(
            platform=self.platform_name,
            video_id=video_id,
            url=f"https://youtube.com/shorts/{video_id}",
            dry_run=False,
            payload=body,
        )

    def delete(self, video_id: str) -> None:
        youtube = get_youtube_client(self.client_secrets_file, self.token_file)
        youtube.videos().delete(id=video_id).execute()
