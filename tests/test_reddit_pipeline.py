import unittest

from shortsbot import reddit_pipeline


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
