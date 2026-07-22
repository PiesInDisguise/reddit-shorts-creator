import base64
import unittest
from unittest.mock import MagicMock, patch

from shortsbot import tts_client


def _mock_response(json_data=None, status_code=200, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


class TestSynthesize(unittest.TestCase):
    def test_writes_audio_and_returns_alignment(self):
        audio_bytes = b"fake-mp3-bytes"
        response_json = {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "alignment": {
                "characters": ["h", "i"],
                "character_start_times_seconds": [0.0, 0.1],
                "character_end_times_seconds": [0.1, 0.2],
            },
        }

        def fake_post(url, headers=None, json=None, timeout=None):
            self.assertIn("/text-to-speech/voice123/with-timestamps", url)
            self.assertEqual(headers["xi-api-key"], "fake-key")
            self.assertEqual(json["text"], "hi")
            return _mock_response(json_data=response_json)

        with patch("shortsbot.tts_client.requests.post", side_effect=fake_post):
            out_path = self._tmp_path()
            alignment = tts_client.synthesize("hi", "voice123", "fake-key", out_path)

        self.assertEqual(out_path.read_bytes(), audio_bytes)
        self.assertEqual(alignment.characters, ["h", "i"])
        self.assertEqual(alignment.start_times, [0.0, 0.1])
        self.assertEqual(alignment.end_times, [0.1, 0.2])

    def test_empty_text_raises(self):
        with self.assertRaises(tts_client.TTSError):
            tts_client.synthesize("   ", "voice123", "fake-key", self._tmp_path())

    def test_non_200_response_raises(self):
        with patch(
            "shortsbot.tts_client.requests.post",
            return_value=_mock_response(status_code=401, text="unauthorized"),
        ):
            with self.assertRaises(tts_client.TTSError):
                tts_client.synthesize("hi", "voice123", "bad-key", self._tmp_path())

    def _tmp_path(self):
        import shutil
        import tempfile
        from pathlib import Path

        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        return d / "out.mp3"


if __name__ == "__main__":
    unittest.main()
