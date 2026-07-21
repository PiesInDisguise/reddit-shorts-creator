import unittest

from shortsbot import reddit_pipeline


class TestTruncateToSentence(unittest.TestCase):
    def test_no_truncation_needed(self):
        text = "One sentence here. Another one too."
        self.assertEqual(reddit_pipeline._truncate_to_sentence(text, 100), text)

    def test_cuts_at_last_full_sentence(self):
        text = "First sentence ends here. Second sentence ends here too. Third one is cut off"
        # budget lands partway into the third sentence
        max_words = len("First sentence ends here. Second sentence ends here too. Third".split())
        result = reddit_pipeline._truncate_to_sentence(text, max_words)
        self.assertEqual(result, "First sentence ends here. Second sentence ends here too.")

    def test_hard_cut_when_no_sentence_boundary_in_range(self):
        text = "This is one very long sentence with no punctuation at all until the very end period"
        result = reddit_pipeline._truncate_to_sentence(text, 5)
        self.assertEqual(result, "This is one very long")


class TestPrepareBodyForBudget(unittest.TestCase):
    def test_short_body_stays_normal_speed_untruncated(self):
        text = "Just a short sentence."
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=60.0)
        self.assertEqual(speed, 1.0)
        self.assertEqual(out_text, text)

    def test_moderately_long_body_speeds_up_within_cap(self):
        # ~2.5 words/sec baseline -> 200 words needs 80s naturally
        text = " ".join(["word"] * 200)
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=70.0)
        self.assertAlmostEqual(speed, 80.0 / 70.0, places=3)
        self.assertLessEqual(speed, reddit_pipeline.MAX_TOTAL_SPEED)
        self.assertEqual(out_text, text)  # fits within the cap, no truncation

    def test_extremely_long_body_caps_speed_and_truncates(self):
        # 500 words at 2.5 wps = 200s naturally -- way more than any reasonable
        # budget even at MAX_TOTAL_SPEED, so this must truncate.
        sentences = [f"Sentence number {i} is right here." for i in range(80)]
        text = " ".join(sentences)
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=60.0)
        self.assertEqual(speed, reddit_pipeline.MAX_TOTAL_SPEED)
        self.assertLess(len(out_text.split()), len(text.split()))
        self.assertTrue(out_text.rstrip().endswith("."))


if __name__ == "__main__":
    unittest.main()
