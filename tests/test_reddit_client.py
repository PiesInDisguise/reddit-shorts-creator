import unittest
from unittest.mock import MagicMock, patch

from shortsbot import reddit_client


def _mock_response(json_data=None, content=b"", status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    resp.text = text
    return resp


class TestFetchPost(unittest.TestCase):
    def test_parses_text_post_and_icon(self):
        dataset_items = [
            {
                "id": "t3_abc123",
                "parsedId": "abc123",
                "title": "A test title",
                "body": "A test body with some words in it.",
                "username": "some_user",
                "communityName": "r/AskReddit",
                "parsedCommunityName": "AskReddit",
                "contentType": "text",
                "dataType": "post",
                "imageUrls": ["https://styles.redditmedia.com/icon.png?width=96"],
            }
        ]

        def fake_post(url, params=None, json=None, timeout=None):
            self.assertEqual(url, reddit_client.RUN_SYNC_URL)
            self.assertEqual(params, {"token": "fake-token"})
            return _mock_response(json_data=dataset_items)

        def fake_get(url, timeout=None):
            self.assertIn("styles.redditmedia.com", url)
            return _mock_response(content=b"fake-icon-bytes")

        with patch("shortsbot.reddit_client.requests.post", side_effect=fake_post), \
             patch("shortsbot.reddit_client.requests.get", side_effect=fake_get):
            post = reddit_client.fetch_post(
                "https://www.reddit.com/r/AskReddit/comments/abc123/a_test_title/",
                apify_api_token="fake-token",
                icon_cache_dir=self._tmp_dir(),
            )

        self.assertEqual(post.subreddit, "AskReddit")
        self.assertEqual(post.author, "some_user")
        self.assertEqual(post.title, "A test title")
        self.assertEqual(post.body, "A test body with some words in it.")
        self.assertEqual(post.post_id, "abc123")
        self.assertIsNotNone(post.icon_path)
        self.assertTrue(post.icon_path.exists())
        self.assertEqual(post.icon_path.read_bytes(), b"fake-icon-bytes")

    def test_non_text_post_skips_icon(self):
        dataset_items = [
            {
                "id": "t3_vid123",
                "parsedId": "vid123",
                "title": "A video post",
                "body": "",
                "username": "some_user",
                "parsedCommunityName": "pasta",
                "contentType": "video",
                "dataType": "post",
                "videoUrls": ["https://packaged-media.redd.it/whatever.mp4"],
            }
        ]

        with patch(
            "shortsbot.reddit_client.requests.post",
            return_value=_mock_response(json_data=dataset_items),
        ):
            post = reddit_client.fetch_post(
                "https://www.reddit.com/r/pasta/comments/vid123/x/",
                apify_api_token="fake-token",
                icon_cache_dir=self._tmp_dir(),
            )

        self.assertIsNone(post.icon_path)
        self.assertEqual(post.body, "")

    def test_empty_results_raises(self):
        with patch(
            "shortsbot.reddit_client.requests.post",
            return_value=_mock_response(json_data=[]),
        ):
            with self.assertRaises(reddit_client.RedditError):
                reddit_client.fetch_post(
                    "https://www.reddit.com/r/x/comments/abc/x/",
                    apify_api_token="fake-token",
                    icon_cache_dir=self._tmp_dir(),
                )

    def test_missing_token_raises(self):
        with self.assertRaises(reddit_client.RedditError):
            reddit_client.fetch_post(
                "https://www.reddit.com/r/x/comments/abc/x/",
                apify_api_token="",
                icon_cache_dir=self._tmp_dir(),
            )

    def _tmp_dir(self):
        import shutil
        import tempfile
        from pathlib import Path

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        return d


if __name__ == "__main__":
    unittest.main()
