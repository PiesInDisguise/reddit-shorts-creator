from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class UploadResult:
    platform: str
    video_id: Optional[str]
    url: Optional[str]
    dry_run: bool
    payload: dict


class Uploader(ABC):
    platform_name = "base"

    @abstractmethod
    def upload(
        self,
        video_path: Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy: str = "private",
        dry_run: bool = False,
    ) -> UploadResult:
        raise NotImplementedError


class NotConfiguredError(RuntimeError):
    """Credentials/config for this platform haven't been set up yet."""


class UploadError(RuntimeError):
    """Credentials were present but the upload itself failed (API error)."""
