import shutil
import tempfile
import unittest
from pathlib import Path

from shortsbot import uploaded_videos


class TestUploadedVideos(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.path = d / "uploaded_videos.json"

    def test_load_seeds_empty_dict_when_missing(self):
        result = uploaded_videos.load_uploaded_videos(self.path)
        self.assertEqual(result, {})
        self.assertTrue(self.path.exists())

    def test_record_upload_persists_and_is_retrievable(self):
        uploaded_videos.record_upload(
            "some_short.mp4", "youtube", "abc123", "https://youtube.com/shorts/abc123", self.path
        )
        info = uploaded_videos.get_upload_info("some_short.mp4", self.path)
        self.assertEqual(info["platform"], "youtube")
        self.assertEqual(info["video_id"], "abc123")
        self.assertEqual(info["url"], "https://youtube.com/shorts/abc123")

    def test_get_upload_info_missing_returns_none(self):
        self.assertIsNone(uploaded_videos.get_upload_info("nope.mp4", self.path))

    def test_remove_upload_deletes_entry(self):
        uploaded_videos.record_upload("a.mp4", "youtube", "id1", "url1", self.path)
        uploaded_videos.remove_upload("a.mp4", self.path)
        self.assertIsNone(uploaded_videos.get_upload_info("a.mp4", self.path))

    def test_remove_upload_missing_is_a_noop(self):
        uploaded_videos.remove_upload("never-existed.mp4", self.path)
        self.assertEqual(uploaded_videos.load_uploaded_videos(self.path), {})


if __name__ == "__main__":
    unittest.main()
