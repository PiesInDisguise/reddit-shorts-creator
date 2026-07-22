import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import requests

# trudax/reddit-scraper-lite: fetches Reddit posts via Apify's own (residential)
# proxy infrastructure. Reddit hard-blocks anonymous/unauthenticated scraping of
# its public JSON endpoints at the network/fingerprint level from most hosts, so
# going direct is not viable; this is the pragmatic, paid-per-result workaround.
ACTOR_ID = "oAuCIx3ItNrs2okjQ"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


class RedditError(RuntimeError):
    pass


_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_CTA_PHRASES = {
    "view in app", "view poll", "view image", "view video",
    "continue this thread", "read more", "view on reddit",
}


def _strip_reddit_artifacts(text: str) -> str:
    """Reddit injects UI navigation prompts into some post bodies -- e.g. a
    trailing "[View in app](...)" markdown link on posts with app-only
    embedded media -- which TTS otherwise narrates literally. Strip those out
    here so they never reach the narration step."""

    def _replace_link(match: re.Match) -> str:
        label = match.group(1).strip()
        return "" if not label or label.lower() in _CTA_PHRASES else label

    text = _MD_LINK_RE.sub(_replace_link, text)
    text = _BARE_URL_RE.sub("", text)
    lines = [ln for ln in text.splitlines() if ln.strip().lower() not in _CTA_PHRASES]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass
class RedditPost:
    subreddit: str
    author: str
    title: str
    body: str
    over_18: bool
    post_id: str
    icon_path: Optional[Path]


def _parse_post_item(item: dict, icon_cache_dir: Path) -> Optional[RedditPost]:
    """Convert one Apify dataset item into a RedditPost, or None if it isn't a
    post (e.g. a 'community' item)."""
    if item.get("dataType") != "post":
        return None

    subreddit = item.get("parsedCommunityName") or item.get("communityName", "").removeprefix("r/")
    post_id = item.get("parsedId") or item.get("id", "").removeprefix("t3_")

    # The community icon rides along as a fallback thumbnail image only on
    # text posts; video/link/image posts carry their own media there instead.
    icon_path = None
    if item.get("contentType") == "text":
        image_urls = item.get("imageUrls") or []
        if image_urls:
            icon_path = _download_icon(image_urls[0], subreddit, icon_cache_dir)

    return RedditPost(
        subreddit=subreddit,
        author=item.get("username", "unknown"),
        title=_strip_reddit_artifacts(item.get("title", "")),
        body=_strip_reddit_artifacts(item.get("body", "") or ""),
        over_18=False,  # not exposed at the post level by this actor
        post_id=post_id,
        icon_path=icon_path,
    )


def _require_token(apify_api_token: str) -> None:
    if not apify_api_token:
        raise RedditError(
            "APIFY_API_TOKEN is not set. This tool fetches Reddit posts via the Apify "
            "'Reddit Scraper Lite' actor, since Reddit blocks anonymous scraping directly. "
            "Get a token from https://console.apify.com/settings/integrations and set "
            "APIFY_API_TOKEN in your .env."
        )


def fetch_post(url: str, apify_api_token: str, icon_cache_dir: Path) -> RedditPost:
    _require_token(apify_api_token)

    payload = {
        "startUrls": [{"url": url}],
        "skipComments": True,
        "includeMediaLinks": True,
        "maxItems": 1,
    }
    resp = requests.post(
        RUN_SYNC_URL, params={"token": apify_api_token}, json=payload, timeout=180
    )
    if resp.status_code >= 400:
        raise RedditError(f"Apify request failed ({resp.status_code}): {resp.text[:500]}")

    items = resp.json()
    if not items:
        raise RedditError(
            f"Apify returned no results for: {url}. Check the URL is a valid Reddit post link."
        )

    post = _parse_post_item(items[0], icon_cache_dir)
    if post is None:
        raise RedditError(
            f"Expected a Reddit post URL, got a '{items[0].get('dataType')}' result for: {url}"
        )
    return post


def fetch_top_posts(
    subreddit: str,
    time_filter: str,
    apify_api_token: str,
    icon_cache_dir: Path,
    max_items: int = 15,
) -> List[RedditPost]:
    """Fetch the top `max_items` posts from a subreddit's "top" listing for a
    given time_filter ("day"/"week"/"month"/"year"/"all"), ranked best-first."""
    _require_token(apify_api_token)

    payload = {
        "startUrls": [{"url": f"https://www.reddit.com/r/{subreddit}/top/?t={time_filter}"}],
        "skipComments": True,
        "includeMediaLinks": True,
        "maxItems": max_items,
    }
    resp = requests.post(
        RUN_SYNC_URL, params={"token": apify_api_token}, json=payload, timeout=180
    )
    if resp.status_code >= 400:
        raise RedditError(f"Apify request failed ({resp.status_code}): {resp.text[:500]}")

    items = resp.json()
    posts = [_parse_post_item(item, icon_cache_dir) for item in items]
    return [p for p in posts if p is not None]


def _download_icon(icon_url: str, subreddit: str, icon_cache_dir: Path) -> Optional[Path]:
    icon_cache_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg"
    name_part = icon_url.split("?")[0].rsplit("/", 1)[-1]
    if "." in name_part:
        ext = "." + name_part.rsplit(".", 1)[-1]
    icon_path = icon_cache_dir / f"{subreddit.lower()}{ext}"

    if icon_path.exists():
        return icon_path

    # This is Reddit's static media CDN, not the API -- a plain GET works fine.
    resp = requests.get(icon_url, timeout=15)
    if resp.status_code != 200:
        return None
    icon_path.write_bytes(resp.content)
    return icon_path
