import html
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

COMMENT_URL_RE = re.compile(r"/r/(?P<sub>[^/]+)/comments/(?P<id>[a-z0-9]+)", re.IGNORECASE)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
OAUTH_BASE_URL = "https://oauth.reddit.com"

# Module-level token cache: Reddit's client_credentials tokens last ~1 hour and
# are safe to reuse across calls within a process (this is a personal CLI/GUI
# tool, not a multi-tenant service).
_token_cache = {"access_token": None, "expires_at": 0.0}


class RedditError(RuntimeError):
    pass


@dataclass
class RedditPost:
    subreddit: str
    author: str
    title: str
    body: str
    over_18: bool
    post_id: str
    icon_path: Optional[Path]


def _get_access_token(client_id: str, client_secret: str, user_agent: str) -> str:
    now = time.time()
    if _token_cache["access_token"] and now < _token_cache["expires_at"]:
        return _token_cache["access_token"]

    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": user_agent},
        timeout=15,
    )
    if resp.status_code != 200:
        raise RedditError(
            f"Failed to get a Reddit OAuth token ({resp.status_code}): {resp.text}. "
            "Double-check REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET in your .env."
        )
    data = resp.json()
    token = data["access_token"]
    # Refresh a little early to avoid racing the actual expiry.
    _token_cache["access_token"] = token
    _token_cache["expires_at"] = now + data.get("expires_in", 3600) - 60
    return token


def _resolve_url(url: str, user_agent: str) -> str:
    if "redd.it" in url or COMMENT_URL_RE.search(url) is None:
        resp = requests.get(
            url, headers={"User-Agent": user_agent}, allow_redirects=True, timeout=15
        )
        resp.raise_for_status()
        url = resp.url
    return url


def _extract_sub_and_id(url: str) -> tuple:
    match = COMMENT_URL_RE.search(url)
    if not match:
        raise RedditError(f"Could not parse a subreddit/post id out of: {url}")
    return match.group("sub"), match.group("id")


def fetch_post(
    url: str,
    user_agent: str,
    icon_cache_dir: Path,
    client_id: str = "",
    client_secret: str = "",
) -> RedditPost:
    if not user_agent:
        raise RedditError(
            "A REDDIT_USER_AGENT is required (Reddit requires one on every request, "
            "including OAuth API calls). Set it in your .env file."
        )
    if not client_id or not client_secret:
        raise RedditError(
            "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are required. Reddit blocks anonymous "
            "access to its public JSON endpoints from most networks now, so this tool "
            "authenticates via Reddit's OAuth API instead. Create a free 'script' app at "
            "https://www.reddit.com/prefs/apps and put its client id/secret in .env."
        )

    token = _get_access_token(client_id, client_secret, user_agent)
    headers = {"User-Agent": user_agent, "Authorization": f"Bearer {token}"}

    resolved_url = _resolve_url(url, user_agent)
    subreddit, post_id = _extract_sub_and_id(resolved_url)

    post_resp = requests.get(
        f"{OAUTH_BASE_URL}/r/{subreddit}/comments/{post_id}.json",
        headers=headers,
        timeout=15,
    )
    post_resp.raise_for_status()
    post_data = post_resp.json()[0]["data"]["children"][0]["data"]

    about_resp = requests.get(
        f"{OAUTH_BASE_URL}/r/{subreddit}/about.json",
        headers=headers,
        timeout=15,
    )
    about_resp.raise_for_status()
    about_data = about_resp.json()["data"]

    icon_path = _fetch_icon(about_data, subreddit, headers, icon_cache_dir)

    return RedditPost(
        subreddit=post_data.get("subreddit", subreddit),
        author=post_data.get("author", "unknown"),
        title=post_data.get("title", ""),
        body=post_data.get("selftext", "") or "",
        over_18=bool(post_data.get("over_18", False)),
        post_id=post_data.get("id", post_id),
        icon_path=icon_path,
    )


def _fetch_icon(
    about_data: dict, subreddit: str, headers: dict, icon_cache_dir: Path
) -> Optional[Path]:
    icon_url = about_data.get("community_icon") or about_data.get("icon_img")
    if not icon_url:
        return None
    icon_url = html.unescape(icon_url)
    if not icon_url:
        return None

    icon_cache_dir.mkdir(parents=True, exist_ok=True)
    ext = ".png"
    if "." in icon_url.split("?")[0].rsplit("/", 1)[-1]:
        ext = "." + icon_url.split("?")[0].rsplit(".", 1)[-1]
    icon_path = icon_cache_dir / f"{subreddit.lower()}{ext}"

    if icon_path.exists():
        return icon_path

    # Icon URLs point at Reddit's media CDN (styles.redditmedia.com), a
    # different host from the API, so this plain (non-OAuth) GET is fine.
    resp = requests.get(icon_url, headers={"User-Agent": headers["User-Agent"]}, timeout=15)
    if resp.status_code != 200:
        return None
    icon_path.write_bytes(resp.content)
    return icon_path
