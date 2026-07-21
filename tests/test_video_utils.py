import unittest

from shortsbot import video_utils


class TestCropFilter(unittest.TestCase):
    def test_wide_source_crops_width(self):
        vf = video_utils.build_crop_filter(1920, 1080)
        self.assertEqual(vf, "crop=608:1080:656:0,scale=1080:1920:flags=lanczos,setsar=1")

    def test_already_9x16_skips_crop(self):
        vf = video_utils.build_crop_filter(1080, 1920)
        self.assertNotIn("crop=", vf)
        self.assertIn("scale=1080:1920", vf)

    def test_narrow_source_crops_height(self):
        vf = video_utils.build_crop_filter(1000, 2500)
        self.assertTrue(vf.startswith("crop="))
        crop_part = vf.split(",")[0]
        _, dims = crop_part.split("=")
        w, h, x, y = (int(v) for v in dims.split(":"))
        self.assertEqual(w, 1000)
        self.assertEqual(x, 0)
        self.assertEqual(y, (2500 - h) // 2)


class TestSelectInterval(unittest.TestCase):
    def test_random_short_video_uses_whole_video(self):
        start, length = video_utils.select_interval(45.0, mode="random")
        self.assertEqual(start, 0.0)
        self.assertEqual(length, 45.0)

    def test_random_long_video_picks_60s_window(self):
        start, length = video_utils.select_interval(300.0, mode="random")
        self.assertEqual(length, 60.0)
        self.assertTrue(0 <= start <= 240.0)

    def test_manual_mode_clamps_to_60s(self):
        start, length = video_utils.select_interval(300.0, mode="manual", start=10.0, end=200.0)
        self.assertEqual(start, 10.0)
        self.assertEqual(length, 60.0)

    def test_manual_mode_requires_start(self):
        with self.assertRaises(video_utils.IntervalError):
            video_utils.select_interval(300.0, mode="manual")

    def test_manual_mode_rejects_start_past_duration(self):
        with self.assertRaises(video_utils.IntervalError):
            video_utils.select_interval(100.0, mode="manual", start=150.0)


class TestParseTimestamp(unittest.TestCase):
    def test_raw_seconds(self):
        self.assertEqual(video_utils.parse_timestamp("12.5"), 12.5)

    def test_mm_ss(self):
        self.assertEqual(video_utils.parse_timestamp("1:30"), 90.0)

    def test_hh_mm_ss(self):
        self.assertEqual(video_utils.parse_timestamp("1:01:30"), 3690.0)


if __name__ == "__main__":
    unittest.main()
