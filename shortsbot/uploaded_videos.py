import json
from pathlib import Path
from typing import Dict, Optional

UPLOADED_VIDEOS_FILE = Path("uploaded_videos.json")


def load_uploaded_videos(path: Optional[Path] = None) -> Dict[str, dict]:
    path = path or UPLOADED_VIDEOS_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    save_uploaded_videos({}, path)
    return {}


def save_uploaded_videos(data: Dict[str, dict], path: Optional[Path] = None) -> None:
    path = path or UPLOADED_VIDEOS_FILE
    path.write_text(json.dumps(data, indent=2))


def record_upload(
    filename: str, platform: str, video_id: str, url: str, path: Optional[Path] = None
) -> None:
    """Record which platform/video_id a generated short's file (by name, not
    full path -- output/ is a flat directory and callers run from varying
    cwds/relative paths) was uploaded as, so it can later be deleted remotely
    from the GUI's Library tab."""
    data = load_uploaded_videos(path)
    data[filename] = {"platform": platform, "video_id": video_id, "url": url}
    save_uploaded_videos(data, path)


def get_upload_info(filename: str, path: Optional[Path] = None) -> Optional[dict]:
    return load_uploaded_videos(path).get(filename)


def remove_upload(filename: str, path: Optional[Path] = None) -> None:
    data = load_uploaded_videos(path)
    if filename in data:
        del data[filename]
        save_uploaded_videos(data, path)
