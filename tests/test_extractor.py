import unittest

import os
import tempfile

from any_karaoke.extractor import build_lyrics, sanitize_for_path, song_file_for

ASR_RESULT = {
    "language": "en",
    "segments": [
        {"text": " rough timing ", "start": 0.0, "end": 4.0},
    ],
}

ALIGN_RESULT = {
    "segments": [
        {
            "text": "rough timing",
            "start": 0.12,
            "end": 3.87,
            "words": [
                {"word": "rough", "start": 0.12, "end": 1.0},
                {"word": "timing", "start": 1.2, "end": 3.87},
                {"word": "1999", "start": None, "end": None},
            ],
        }
    ]
}


class TestSanitizeForPath(unittest.TestCase):
    def test_replaces_invalid_characters(self):
        self.assertEqual(sanitize_for_path("AC/DC: Back?"), "AC_DC_ Back_")

    def test_strips_trailing_dots_and_spaces(self):
        self.assertEqual(sanitize_for_path("Song Title. "), "Song Title")

    def test_falls_back_when_nothing_is_left(self):
        self.assertEqual(sanitize_for_path("..."), "untitled")


class TestSongFileFor(unittest.TestCase):
    def test_targets_an_ak_file_not_a_folder(self):
        target = song_file_for(os.path.join(tempfile.mkdtemp(), "missing.mp3"), r"D:\library")
        self.assertTrue(target.endswith(".ak"))
        self.assertEqual(os.path.dirname(target), r"D:\library")

    def test_falls_back_when_the_source_does_not_exist(self):
        target = song_file_for("no_such_file.mp3", "library")
        self.assertTrue(target.endswith(".ak"))
        self.assertIn("untitled", target)


class TestBuildLyrics(unittest.TestCase):
    def test_prefers_aligned_timings_over_asr_timings(self):
        # Regression: the aligned result used to be written to disk then ignored
        lyrics = build_lyrics(ASR_RESULT, ALIGN_RESULT)
        self.assertEqual(lyrics[0]["start"], 0.12)
        self.assertEqual(lyrics[0]["end"], 3.87)

    def test_keeps_word_level_timings(self):
        lyrics = build_lyrics(ASR_RESULT, ALIGN_RESULT)
        self.assertEqual([w["word"] for w in lyrics[0]["words"]], ["rough", "timing"])

    def test_falls_back_to_asr_when_alignment_is_missing(self):
        lyrics = build_lyrics(ASR_RESULT, None)
        self.assertEqual(lyrics, [{"text": "rough timing", "start": 0.0, "end": 4.0}])

    def test_falls_back_when_alignment_is_empty(self):
        lyrics = build_lyrics(ASR_RESULT, {"segments": []})
        self.assertEqual(lyrics[0]["start"], 0.0)

    def test_skips_segments_without_timings(self):
        lyrics = build_lyrics({"segments": [{"text": "no timing", "start": None, "end": None}]}, None)
        self.assertEqual(lyrics, [])

    def test_no_results_at_all(self):
        self.assertEqual(build_lyrics(None, None), [])


if __name__ == "__main__":
    unittest.main()
