import unittest
from pathlib import Path

from shortsbot.upload.instagram_upload import InstagramUploader
from shortsbot.upload.tiktok_upload import PRIVACY_MAP, TikTokUploader


class TestTikTokDryRun(unittest.TestCase):
    def setUp(self):
        self.uploader = TikTokUploader(
            client_key="",
            client_secret="",
            token_file=Path("unused.json"),
            redirect_uri="http://localhost:8081/callback",
        )

    def test_dry_run_never_hits_network_or_requires_credentials(self):
        result = self.uploader.upload(
            Path(__file__), title="Test title", tags=["one", "two"], dry_run=True
        )
        self.assertTrue(result.dry_run)
        self.assertIsNone(result.video_id)

    def test_dry_run_maps_privacy_and_appends_hashtags(self):
        result = self.uploader.upload(
            Path(__file__), title="Test title", tags=["one", "two"], privacy="public", dry_run=True
        )
        self.assertEqual(result.payload["post_info"]["privacy_level"], "PUBLIC_TO_EVERYONE")
        self.assertIn("#one", result.payload["post_info"]["title"])
        self.assertIn("#two", result.payload["post_info"]["title"])

    def test_privacy_map_has_no_unlisted_gap(self):
        for level in ("public", "unlisted", "private"):
            self.assertIn(level, PRIVACY_MAP)


class TestInstagramDryRun(unittest.TestCase):
    def setUp(self):
        self.uploader = InstagramUploader(access_token="", ig_user_id="", ngrok_auth_token="")

    def test_dry_run_never_hits_network_or_requires_credentials(self):
        result = self.uploader.upload(
            Path(__file__), title="Test title", description="body", tags=["x"], dry_run=True
        )
        self.assertTrue(result.dry_run)
        self.assertIsNone(result.video_id)
        self.assertIn("#x", result.payload["caption"])
        self.assertIn("body", result.payload["caption"])


if __name__ == "__main__":
    unittest.main()
