import random
import re
from pathlib import Path
from typing import Callable, List, Optional

from . import reddit_client, used_posts
from .reddit_client import RedditPost

POOL_WEIGHTS = {"day": 0.30, "week": 0.40, "year": 0.30}
WORDS_PER_SECOND = 2.5
MAX_SPEEDUP = 1.4
TARGET_SECONDS = 90.0  # independent of reddit_pipeline.BUDGET_SECONDS -- deliberately
# separate: this is a quality gate for what the autonomous picker considers usable,
# not a change to the pipeline's own (uncapped) speed-up behavior for manual/user-
# supplied posts.

# Auto-published content is public immediately with no human review, so posts
# using a racial slur (in the title or body) are hard-blocked regardless of
# how well they'd otherwise fit the time budget.
_SLUR_PATTERN = re.compile(
    r"\b("
    r"nigger|niggers|nigga|niggas|niggah|niggahs|"
    r"chink|chinks|spic|spics|kike|kikes|"
    r"wetback|wetbacks|gook|gooks|coon|coons|beaner|beaners"
    r")\b",
    re.IGNORECASE,
)


def contains_slur(post: RedditPost) -> bool:
    return bool(_SLUR_PATTERN.search(post.title) or _SLUR_PATTERN.search(post.body))


def estimate_too_long(post: RedditPost) -> bool:
    word_count = len((post.title + " " + post.body).split())
    return word_count / WORDS_PER_SECOND > TARGET_SECONDS * MAX_SPEEDUP


def _pool_order(rng: random.Random) -> List[str]:
    pools = list(POOL_WEIGHTS.keys())
    weights = list(POOL_WEIGHTS.values())
    first = rng.choices(pools, weights=weights, k=1)[0]
    rest = sorted((p for p in pools if p != first), key=lambda p: -POOL_WEIGHTS[p])
    return [first] + rest


def pick_post(
    subreddit: str,
    apify_api_token: str,
    icon_cache_dir: Path,
    used_posts_path: Optional[Path] = None,
    max_items_per_pool: int = 15,
    rng: Optional[random.Random] = None,
    fetch_fn: Callable[..., List[RedditPost]] = reddit_client.fetch_top_posts,
) -> Optional[RedditPost]:
    """Pick the next post to auto-generate: choose a time-window pool by weighted
    random draw (day 30% / week 40% / year 30%), then return the first candidate
    in that pool that hasn't been used before, isn't too long to narrate nicely,
    and doesn't contain a racial slur. Falls back to the other pools (in weight
    order) if the chosen one has nothing usable; returns None if all three
    pools are exhausted."""
    rng = rng or random.Random()

    for pool in _pool_order(rng):
        candidates = fetch_fn(subreddit, pool, apify_api_token, icon_cache_dir, max_items_per_pool)
        for candidate in candidates:
            if used_posts.is_used(candidate.post_id, used_posts_path):
                continue
            if estimate_too_long(candidate):
                continue
            if contains_slur(candidate):
                continue
            return candidate

    return None
