import unittest
from unittest.mock import MagicMock, patch

from shortsbot import reddit_client


def _mock_response(json_data=None, content=b"", status_code=200, url=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    resp.url = url
    resp.raise_for_status = MagicMock()
    return resp


class TestExtractSubAndId(unittest.TestCase):
    def test_extracts_from_full_comments_url(self):
        sub, post_id = reddit_client._extract_sub_and_id(
            "https://www.reddit.com/r/AskReddit/comments/abc123/some_title/"
        )
        self.assertEqual(sub, "AskReddit")
        self.assertEqual(post_id, "abc123")

    def test_raises_on_unparseable_url(self):
        with self.assertRaises(reddit_client.RedditError):
            reddit_client._extract_sub_and_id("https://example.com/not-a-reddit-link")


class TestFetchPost(unittest.TestCase):
    def test_parses_post_and_icon_fields(self):
        post_json = [
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "subreddit": "AskReddit",
                                "author": "some_user",
                                "title": "A test title",
                                "selftext": "A test body with some words in it.",
                                "over_18": False,
                                "id": "abc123",
                            }
                        }
                    ]
                }
            }
        ]
        about_json = {
            "data": {
                "community_icon": "https://example.com/icon.png?width=256&amp;height=256",
            }
        }

        def fake_get(url, headers=None, timeout=None, allow_redirects=None):
            if url.endswith("comments/abc123.json"):
                return _mock_response(json_data=post_json)
            if url.endswith("about.json"):
                return _mock_response(json_data=about_json)
            if "icon.png" in url:
                return _mock_response(content=b"fake-png-bytes")
            raise AssertionError(f"Unexpected URL requested: {url}")

        with patch("shortsbot.reddit_client.requests.get", side_effect=fake_get):
            post = reddit_client.fetch_post(
                "https://www.reddit.com/r/AskReddit/comments/abc123/a_test_title/",
                user_agent="shortsbot/0.1 by u/test",
                icon_cache_dir=self._tmp_icon_dir(),
            )

        self.assertEqual(post.subreddit, "AskReddit")
        self.assertEqual(post.author, "some_user")
        self.assertEqual(post.title, "A test title")
        self.assertEqual(post.body, "A test body with some words in it.")
        self.assertFalse(post.over_18)
        self.assertIsNotNone(post.icon_path)
        self.assertTrue(post.icon_path.exists())
        self.assertEqual(post.icon_path.read_bytes(), b"fake-png-bytes")

    def _tmp_icon_dir(self):
        import shutil
        import tempfile
        from pathlib import Path

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        return d

    def test_missing_user_agent_raises(self):
        with self.assertRaises(reddit_client.RedditError):
            reddit_client.fetch_post("https://www.reddit.com/r/x/comments/abc/x/", "", None)


if __name__ == "__main__":
    unittest.main()
