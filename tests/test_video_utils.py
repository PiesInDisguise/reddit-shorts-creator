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


class TestFormatTimestamp(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(video_utils.format_timestamp(0), "00:00")

    def test_minutes_seconds(self):
        self.assertEqual(video_utils.format_timestamp(90), "01:30")

    def test_hours(self):
        self.assertEqual(video_utils.format_timestamp(3661), "1:01:01")

    def test_round_trips_with_parse_timestamp(self):
        formatted = video_utils.format_timestamp(125)
        self.assertEqual(video_utils.parse_timestamp(formatted), 125.0)


class TestSanitizeFilename(unittest.TestCase):
    def test_strips_reserved_chars_and_hyphenates_spaces(self):
        self.assertEqual(
            video_utils.sanitize_filename('My Video: "Best" Ever?'), "My-Video-Best-Ever"
        )

    def test_removes_chars_with_no_surrounding_space(self):
        self.assertEqual(
            video_utils.sanitize_filename("Weird/Name\\With*Chars<>|"), "WeirdNameWithChars"
        )

    def test_blank_input_falls_back(self):
        self.assertEqual(video_utils.sanitize_filename("   "), "video")

    def test_truncates_to_max_length(self):
        result = video_utils.sanitize_filename("x" * 200, max_length=80)
        self.assertLessEqual(len(result), 80)


class TestComputeGigaSampleIntervals(unittest.TestCase):
    def test_enough_room_no_overlap_spread_across_range(self):
        intervals = video_utils.compute_giga_sample_intervals(0, 600, count=5, clip_length=60)
        self.assertEqual(len(intervals), 5)
        for i, (s, e) in enumerate(intervals):
            self.assertAlmostEqual(e - s, 60)
            self.assertGreaterEqual(s, i * 120)
            self.assertLessEqual(e, (i + 1) * 120 + 1e-6)
        for (_, e1), (s2, _) in zip(intervals, intervals[1:]):
            self.assertLessEqual(e1, s2 + 1e-6)  # non-overlapping

    def test_not_enough_room_allows_overlap_but_still_spreads(self):
        intervals = video_utils.compute_giga_sample_intervals(0, 60, count=5, clip_length=30)
        self.assertEqual(len(intervals), 5)
        starts = [s for s, _ in intervals]
        self.assertEqual(starts, sorted(starts))  # spread monotonically
        self.assertTrue(
            any(e1 > s2 for (_, e1), (s2, _) in zip(intervals, intervals[1:]))
        )  # overlap happens
        for s, e in intervals:
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(e, 60)

    def test_rejects_clip_length_longer_than_range(self):
        with self.assertRaises(ValueError):
            video_utils.compute_giga_sample_intervals(0, 60, count=1, clip_length=90)

    def test_rejects_zero_count(self):
        with self.assertRaises(ValueError):
            video_utils.compute_giga_sample_intervals(0, 60, count=0, clip_length=10)


if __name__ == "__main__":
    unittest.main()
