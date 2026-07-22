import json
from pathlib import Path
from typing import List, Optional

USED_POSTS_FILE = Path("used_posts.json")


def load_used_posts(path: Optional[Path] = None) -> List[str]:
    path = path or USED_POSTS_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    save_used_posts([], path)
    return []


def save_used_posts(post_ids: List[str], path: Optional[Path] = None) -> None:
    path = path or USED_POSTS_FILE
    path.write_text(json.dumps(post_ids, indent=2))


def mark_used(post_id: str, path: Optional[Path] = None) -> List[str]:
    used = load_used_posts(path)
    if post_id and post_id not in used:
        used.append(post_id)
        save_used_posts(used, path)
    return used


def is_used(post_id: str, path: Optional[Path] = None) -> bool:
    return post_id in load_used_posts(path)
