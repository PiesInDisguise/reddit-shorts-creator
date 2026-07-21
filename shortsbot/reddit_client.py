from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

# trudax/reddit-scraper-lite: fetches Reddit posts via Apify's own (residential)
# proxy infrastructure. Reddit hard-blocks anonymous/unauthenticated scraping of
# its public JSON endpoints at the network/fingerprint level from most hosts, so
# going direct is not viable; this is the pragmatic, paid-per-result workaround.
ACTOR_ID = "oAuCIx3ItNrs2okjQ"
RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


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


def fetch_post(url: str, apify_api_token: str, icon_cache_dir: Path) -> RedditPost:
    if not apify_api_token:
        raise RedditError(
            "APIFY_API_TOKEN is not set. This tool fetches Reddit posts via the Apify "
            "'Reddit Scraper Lite' actor, since Reddit blocks anonymous scraping directly. "
            "Get a token from https://console.apify.com/settings/integrations and set "
            "APIFY_API_TOKEN in your .env."
        )

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

    item = items[0]
    if item.get("dataType") != "post":
        raise RedditError(
            f"Expected a Reddit post URL, got a '{item.get('dataType')}' result for: {url}"
        )

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
        title=item.get("title", ""),
        body=item.get("body", "") or "",
        over_18=False,  # not exposed at the post level by this actor
        post_id=post_id,
        icon_path=icon_path,
    )


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
