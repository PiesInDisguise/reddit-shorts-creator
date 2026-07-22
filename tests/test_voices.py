import shutil
import tempfile
import unittest
from pathlib import Path

from shortsbot import voices


class TestVoices(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(d, ignore_errors=True))
        self.path = d / "voices.json"

    def test_load_seeds_defaults_when_missing(self):
        result = voices.load_voices(self.path)
        self.assertEqual(result, voices.DEFAULT_VOICES)
        self.assertTrue(self.path.exists())  # defaults get persisted on first load

    def test_add_voice_appends_and_persists(self):
        voices.load_voices(self.path)
        updated = voices.add_voice("NEWVOICEID123", self.path)
        self.assertIn("NEWVOICEID123", updated)
        reloaded = voices.load_voices(self.path)
        self.assertIn("NEWVOICEID123", reloaded)

    def test_add_voice_does_not_duplicate(self):
        voices.load_voices(self.path)
        first = voices.add_voice("DUPLICATE", self.path)
        second = voices.add_voice("DUPLICATE", self.path)
        self.assertEqual(first, second)
        self.assertEqual(second.count("DUPLICATE"), 1)

    def test_add_voice_ignores_blank_input(self):
        before = voices.load_voices(self.path)
        after = voices.add_voice("   ", self.path)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
