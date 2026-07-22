import unittest

from shortsbot import captions
from shortsbot.tts_client import _alignment_from_words


class TestAlignmentFromWords(unittest.TestCase):
    def test_expands_words_into_characters_with_shared_timing(self):
        words = [
            {"word": "hi", "start": 0.0, "end": 0.4},
            {"word": "there", "start": 0.5, "end": 1.0},
        ]
        alignment = _alignment_from_words(words)
        self.assertEqual("".join(alignment.characters), "hi there")
        # every char of "hi" shares that word's start/end
        self.assertEqual(alignment.start_times[0], 0.0)
        self.assertEqual(alignment.end_times[1], 0.4)
        # the space between them doesn't need meaningful timing of its own
        self.assertEqual(alignment.characters[2], " ")

    def test_round_trips_through_words_from_alignment(self):
        words = [
            {"word": "hi", "start": 0.0, "end": 0.4},
            {"word": "there", "start": 0.5, "end": 1.0},
            {"word": "friend", "start": 1.1, "end": 1.6},
        ]
        alignment = _alignment_from_words(words)
        parsed = captions.words_from_alignment(alignment)
        self.assertEqual([w.text for w in parsed], ["hi", "there", "friend"])
        self.assertAlmostEqual(parsed[0].start, 0.0)
        self.assertAlmostEqual(parsed[0].end, 0.4)
        self.assertAlmostEqual(parsed[1].start, 0.5)
        self.assertAlmostEqual(parsed[2].end, 1.6)

    def test_single_word(self):
        words = [{"word": "solo", "start": 0.1, "end": 0.3}]
        alignment = _alignment_from_words(words)
        self.assertEqual("".join(alignment.characters), "solo")


if __name__ == "__main__":
    unittest.main()
