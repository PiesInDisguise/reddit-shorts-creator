import unittest

from shortsbot import reddit_pipeline


class TestPrepareBodyForBudget(unittest.TestCase):
    def test_short_body_stays_normal_speed(self):
        text = "Just a short sentence."
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=60.0)
        self.assertEqual(speed, 1.0)
        self.assertEqual(out_text, text)

    def test_moderately_long_body_speeds_up(self):
        # ~2.5 words/sec baseline -> 200 words needs 80s naturally
        text = " ".join(["word"] * 200)
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=70.0)
        self.assertAlmostEqual(speed, 80.0 / 70.0, places=3)
        self.assertEqual(out_text, text)  # never truncated

    def test_extremely_long_body_speeds_up_without_limit_or_truncation(self):
        # Way more than fits even at a brisk pace -- must still speed up (not
        # truncate) to fit, however fast that requires.
        text = " ".join(["word"] * 1000)  # 400s naturally at 2.5 wps
        speed, out_text = reddit_pipeline._prepare_body_for_budget(text, remaining_budget=60.0)
        self.assertAlmostEqual(speed, 400.0 / 60.0, places=3)
        self.assertEqual(out_text, text)  # full text preserved, no truncation


class TestAtempoChain(unittest.TestCase):
    def test_single_stage_within_range(self):
        self.assertEqual(reddit_pipeline._atempo_chain(1.35), "atempo=1.350000")

    def test_chains_multiple_stages_beyond_single_filter_limit(self):
        chain = reddit_pipeline._atempo_chain(3.0)
        stages = [float(s.split("=")[1]) for s in chain.split(",")]
        self.assertTrue(all(0.5 <= s <= 2.0 for s in stages))
        product = 1.0
        for s in stages:
            product *= s
        self.assertAlmostEqual(product, 3.0, places=3)


if __name__ == "__main__":
    unittest.main()
