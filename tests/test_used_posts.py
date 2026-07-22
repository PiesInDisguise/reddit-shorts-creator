import shutil
import tempfile
import unittest
from pathlib import Path

from shortsbot import used_posts


class TestUsedPosts(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.path = d / "used_posts.json"

    def test_load_seeds_empty_list_when_missing(self):
        result = used_posts.load_used_posts(self.path)
        self.assertEqual(result, [])
        self.assertTrue(self.path.exists())

    def test_mark_used_appends_and_persists(self):
        used_posts.load_used_posts(self.path)
        updated = used_posts.mark_used("abc123", self.path)
        self.assertIn("abc123", updated)
        reloaded = used_posts.load_used_posts(self.path)
        self.assertIn("abc123", reloaded)

    def test_mark_used_does_not_duplicate(self):
        used_posts.load_used_posts(self.path)
        first = used_posts.mark_used("dup", self.path)
        second = used_posts.mark_used("dup", self.path)
        self.assertEqual(first, second)
        self.assertEqual(second.count("dup"), 1)

    def test_is_used_true_and_false(self):
        used_posts.load_used_posts(self.path)
        used_posts.mark_used("known", self.path)
        self.assertTrue(used_posts.is_used("known", self.path))
        self.assertFalse(used_posts.is_used("unknown", self.path))


if __name__ == "__main__":
    unittest.main()
