import random
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from shortsbot import autopicker, used_posts
from shortsbot.reddit_client import RedditPost


def _post(post_id, word_count, title_words=2):
    body_words = max(word_count - title_words, 0)
    return RedditPost(
        subreddit="copypasta",
        author="someone",
        title=" ".join(["t"] * title_words),
        body=" ".join(["w"] * body_words),
        over_18=False,
        post_id=post_id,
        icon_path=None,
    )


def _post_text(post_id, title, body=""):
    return RedditPost(
        subreddit="copypasta",
        author="someone",
        title=title,
        body=body,
        over_18=False,
        post_id=post_id,
        icon_path=None,
    )


class TestEstimateTooLong(unittest.TestCase):
    def test_just_under_threshold_is_not_too_long(self):
        # threshold is TARGET_SECONDS * MAX_SPEEDUP * WORDS_PER_SECOND words
        limit = int(autopicker.TARGET_SECONDS * autopicker.MAX_SPEEDUP * autopicker.WORDS_PER_SECOND)
        post = _post("short", limit - 5)
        self.assertFalse(autopicker.estimate_too_long(post))

    def test_well_over_threshold_is_too_long(self):
        limit = int(autopicker.TARGET_SECONDS * autopicker.MAX_SPEEDUP * autopicker.WORDS_PER_SECOND)
        post = _post("long", limit + 500)
        self.assertTrue(autopicker.estimate_too_long(post))


class TestContainsSlur(unittest.TestCase):
    def test_detects_slur_in_title(self):
        post = _post_text("s1", "No future for this nigga")
        self.assertTrue(autopicker.contains_slur(post))

    def test_detects_slur_in_body(self):
        post = _post_text("s2", "A normal title", body="he called me a chink")
        self.assertTrue(autopicker.contains_slur(post))

    def test_is_case_insensitive(self):
        post = _post_text("s3", "NIGGER did this")
        self.assertTrue(autopicker.contains_slur(post))

    def test_clean_post_is_not_flagged(self):
        post = _post_text("s4", "My neighbor's raccoon got into the trash again")
        self.assertFalse(autopicker.contains_slur(post))


class TestPoolOrder(unittest.TestCase):
    def test_weights_passed_to_rng(self):
        rng = mock.Mock(wraps=random.Random(0))
        autopicker._pool_order(rng)
        rng.choices.assert_called_once()
        _, kwargs = rng.choices.call_args
        self.assertEqual(kwargs["weights"], [0.30, 0.40, 0.30])

    def test_fallback_order_is_remaining_pools_by_weight(self):
        rng = random.Random(0)
        rng.choices = lambda pools, weights, k: ["day"]
        order = autopicker._pool_order(rng)
        self.assertEqual(order, ["day", "week", "year"])

        rng.choices = lambda pools, weights, k: ["year"]
        order = autopicker._pool_order(rng)
        self.assertEqual(order, ["year", "week", "day"])


class TestPickPost(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.used_posts_path = d / "used_posts.json"
        self.icon_cache_dir = d / "icons"

    def test_first_usable_candidate_wins(self):
        pools = {
            "day": [_post("d1", 10)],
            "week": [],
            "year": [],
        }

        def fetch_fn(subreddit, pool, token, icon_dir, max_items):
            return pools[pool]

        rng = random.Random(0)
        rng.choices = lambda p, weights, k: ["day"]

        result = autopicker.pick_post(
            "copypasta", "token", self.icon_cache_dir,
            used_posts_path=self.used_posts_path, rng=rng, fetch_fn=fetch_fn,
        )
        self.assertEqual(result.post_id, "d1")

    def test_exhausted_pool_falls_through_to_next(self):
        limit = int(autopicker.TARGET_SECONDS * autopicker.MAX_SPEEDUP * autopicker.WORDS_PER_SECOND)
        pools = {
            "day": [_post("too_long", limit + 500)],
            "week": [_post("w1", 10)],
            "year": [],
        }

        def fetch_fn(subreddit, pool, token, icon_dir, max_items):
            return pools[pool]

        rng = random.Random(0)
        rng.choices = lambda p, weights, k: ["day"]

        result = autopicker.pick_post(
            "copypasta", "token", self.icon_cache_dir,
            used_posts_path=self.used_posts_path, rng=rng, fetch_fn=fetch_fn,
        )
        self.assertEqual(result.post_id, "w1")

    def test_all_pools_exhausted_returns_none(self):
        def fetch_fn(subreddit, pool, token, icon_dir, max_items):
            return []

        rng = random.Random(0)
        rng.choices = lambda p, weights, k: ["day"]

        result = autopicker.pick_post(
            "copypasta", "token", self.icon_cache_dir,
            used_posts_path=self.used_posts_path, rng=rng, fetch_fn=fetch_fn,
        )
        self.assertIsNone(result)

    def test_slur_post_is_skipped(self):
        pools = {
            "day": [_post_text("bad", "No future for this nigga"), _post("d2", 10)],
            "week": [],
            "year": [],
        }

        def fetch_fn(subreddit, pool, token, icon_dir, max_items):
            return pools[pool]

        rng = random.Random(0)
        rng.choices = lambda p, weights, k: ["day"]

        result = autopicker.pick_post(
            "copypasta", "token", self.icon_cache_dir,
            used_posts_path=self.used_posts_path, rng=rng, fetch_fn=fetch_fn,
        )
        self.assertEqual(result.post_id, "d2")

    def test_used_post_is_skipped(self):
        used_posts.mark_used("d1", self.used_posts_path)
        pools = {
            "day": [_post("d1", 10), _post("d2", 10)],
            "week": [],
            "year": [],
        }

        def fetch_fn(subreddit, pool, token, icon_dir, max_items):
            return pools[pool]

        rng = random.Random(0)
        rng.choices = lambda p, weights, k: ["day"]

        result = autopicker.pick_post(
            "copypasta", "token", self.icon_cache_dir,
            used_posts_path=self.used_posts_path, rng=rng, fetch_fn=fetch_fn,
        )
        self.assertEqual(result.post_id, "d2")


if __name__ == "__main__":
    unittest.main()
