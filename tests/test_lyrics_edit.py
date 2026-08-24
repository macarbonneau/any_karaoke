import os
import tempfile
import unittest
import zipfile
from unittest import mock

from any_karaoke.extractor import build_lyrics_alignment
from any_karaoke.lyrics_edit import (
    CORRECTED_LYRICS_FILE,
    apply_corrected_lyrics,
    describe_timing,
    force_align_lines,
    lyrics_text_from_scaffold,
    read_editable_lyrics,
    song_language,
    summarise_timings,
)
from any_karaoke.lyrics_matcher import fill_lyrics_timings
from any_karaoke.song_files import (
    is_song,
    list_entries,
    pack_song,
    read_lyrics_alignment,
    unpack_song,
)
from tests.song_fixtures import ALIGNMENT, LYRIC_TEXT, build_song


class TestTextRoundTrip(unittest.TestCase):
    def test_scaffold_back_to_the_text_it_came_from(self):
        scaffold = build_lyrics_alignment(LYRIC_TEXT, "online")
        self.assertEqual(lyrics_text_from_scaffold(scaffold), LYRIC_TEXT)

    def test_verse_breaks_survive(self):
        text = "a\n\nb\n\nc"
        self.assertEqual(lyrics_text_from_scaffold(build_lyrics_alignment(text, "online")), text)

    def test_repeated_blank_lines_collapse_to_one(self):
        scaffold = build_lyrics_alignment("a\n\n\n\nb", "online")
        self.assertEqual(lyrics_text_from_scaffold(scaffold), "a\n\nb")

    def test_empty_and_missing(self):
        self.assertEqual(lyrics_text_from_scaffold(None), "")
        self.assertEqual(lyrics_text_from_scaffold({}), "")
        self.assertEqual(lyrics_text_from_scaffold({"lines": []}), "")


class TestReadEditableLyrics(unittest.TestCase):
    def test_prefers_the_scaffold(self):
        song = build_song(extras={"online_lyrics.txt": "SHOULD NOT BE USED"})
        self.assertEqual(read_editable_lyrics(song), LYRIC_TEXT)

    def test_falls_back_to_the_stored_text(self):
        song = build_song(with_scaffold=False, extras={"online_lyrics.txt": "from the internet"})
        self.assertEqual(read_editable_lyrics(song), "from the internet")

    def test_prefers_corrected_over_online(self):
        song = build_song(
            with_scaffold=False,
            extras={"online_lyrics.txt": "online", CORRECTED_LYRICS_FILE: "corrected"},
        )
        self.assertEqual(read_editable_lyrics(song), "corrected")

    def test_empty_when_the_song_has_no_lyrics_at_all(self):
        self.assertEqual(read_editable_lyrics(build_song(with_scaffold=False)), "")


class TestApplyCorrectedLyrics(unittest.TestCase):
    def setUp(self):
        self.song = build_song()

    def test_the_song_is_still_playable_afterwards(self):
        apply_corrected_lyrics(self.song, "one two three\nfour five")
        self.assertTrue(is_song(self.song))
        self.assertTrue(zipfile.is_zipfile(self.song))

    def test_the_stems_and_other_entries_survive(self):
        before = set(list_entries(self.song))
        apply_corrected_lyrics(self.song, LYRIC_TEXT)
        after = set(list_entries(self.song))
        self.assertTrue(before <= after)
        self.assertIn("music.mp3", after)
        self.assertIn("alignment_result.json", after)

    def test_records_the_correction(self):
        apply_corrected_lyrics(self.song, "brand new words")
        scaffold = read_lyrics_alignment(self.song)
        self.assertEqual(scaffold["source"], "corrected")
        self.assertEqual(scaffold["lines"][0]["text"], "brand new words")
        self.assertIn(CORRECTED_LYRICS_FILE, list_entries(self.song))

    def test_the_corrected_text_reopens_in_the_editor(self):
        apply_corrected_lyrics(self.song, "alpha bravo\n\ncharlie")
        self.assertEqual(read_editable_lyrics(self.song), "alpha bravo\n\ncharlie")

    def test_a_matching_correction_stays_fully_timed(self):
        summary = apply_corrected_lyrics(self.song, LYRIC_TEXT)
        self.assertEqual(summary["coverage"], 1.0)
        self.assertEqual(summary["unmatched"], 0)

    def test_fixing_one_word_keeps_the_rest_matched(self):
        summary = apply_corrected_lyrics(self.song, LYRIC_TEXT.replace("three", "tree"))
        self.assertEqual(summary["coverage"], 1.0)
        self.assertGreater(summary["matched"], summary["approximate"])

    def test_unrelated_lyrics_are_visible_in_the_summary(self):
        good = apply_corrected_lyrics(self.song, LYRIC_TEXT)
        bad = apply_corrected_lyrics(self.song, "nothing like the song at all\nnot a single word shared")
        self.assertLess(bad["matched"], good["matched"])

    def test_leaves_no_partial_file_behind(self):
        apply_corrected_lyrics(self.song, LYRIC_TEXT)
        self.assertFalse(os.path.exists(self.song + ".partial"))

    def test_a_failure_leaves_the_original_alone(self):
        before = read_editable_lyrics(self.song)
        with mock.patch("any_karaoke.lyrics_edit.pack_song", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                apply_corrected_lyrics(self.song, "half written")
        self.assertTrue(is_song(self.song))
        self.assertEqual(read_editable_lyrics(self.song), before)

    def test_no_staging_directory_is_left_behind(self):
        import glob

        pattern = os.path.join(tempfile.gettempdir(), "any_karaoke_edit_*")
        before = set(glob.glob(pattern))
        apply_corrected_lyrics(self.song, LYRIC_TEXT)
        self.assertEqual(set(glob.glob(pattern)) - before, set())


class TestForceAlign(unittest.TestCase):
    def setUp(self):
        self.lines = fill_lyrics_timings(build_lyrics_alignment("one two\nthree four", "online"), ALIGNMENT)["lines"]

    def fake_whisperx(self, segments):
        module = mock.MagicMock()
        module.load_audio.return_value = "audio"
        module.align.return_value = {"segments": segments}
        return module

    def run_align(self, segments):
        module = self.fake_whisperx(segments)
        models = mock.MagicMock()
        models.align.return_value = ("model", "meta")
        models.device = "cpu"
        with mock.patch.dict("sys.modules", {"whisperx": module}):
            return force_align_lines(self.lines, "vocals.mp3", "en", models=models)

    def test_words_come_back_marked_aligned(self):
        lines = self.run_align(
            [
                {"words": [{"word": "one", "start": 10.0, "end": 10.5}, {"word": "two", "start": 10.6, "end": 11.0}]},
                {"words": [{"word": "three", "start": 12.0, "end": 12.5}]},
            ]
        )
        self.assertTrue(all(w["timing"] == "aligned" for w in lines[0]["words"]))
        self.assertEqual(lines[0]["start"], 10.0)
        self.assertEqual(lines[0]["end"], 11.0)

    def test_a_line_the_aligner_skips_keeps_its_matched_timings(self):
        before = dict(self.lines[1])
        lines = self.run_align([{"words": [{"word": "one", "start": 10.0, "end": 10.5}]}, {"words": []}])
        self.assertEqual(lines[1]["start"], before["start"])
        self.assertEqual(lines[1]["end"], before["end"])

    def test_a_short_result_does_not_lose_the_rest(self):
        # The aligner returned one segment for two lines
        lines = self.run_align([{"words": [{"word": "one", "start": 10.0, "end": 10.5}]}])
        self.assertEqual(len(lines), 2)
        self.assertIsNotNone(lines[1]["start"])

    def test_words_without_timings_are_dropped(self):
        lines = self.run_align(
            [{"words": [{"word": "one", "start": 10.0, "end": 10.5}, {"word": "2", "start": None, "end": None}]}]
        )
        self.assertEqual([w["word"] for w in lines[0]["words"]], ["one"])

    def test_untimed_lines_are_not_sent_to_the_aligner(self):
        self.lines[0]["start"] = None
        self.lines[0]["end"] = None
        module = self.fake_whisperx([{"words": [{"word": "three", "start": 1.0, "end": 2.0}]}])
        models = mock.MagicMock()
        models.align.return_value = ("model", "meta")
        models.device = "cpu"
        with mock.patch.dict("sys.modules", {"whisperx": module}):
            force_align_lines(self.lines, "vocals.mp3", "en", models=models)
        sent = module.align.call_args.args[0]
        self.assertEqual(len(sent), 1)


class TestSummary(unittest.TestCase):
    def test_counts_each_kind(self):
        lines = [
            {"words": [{"start": 0, "end": 1, "timing": "aligned"}, {"start": 1, "end": 2, "timing": "matched"}]},
            {"words": [{"start": None, "end": None, "timing": None}]},
        ]
        summary = summarise_timings(lines)
        self.assertEqual(summary["aligned"], 1)
        self.assertEqual(summary["matched"], 1)
        self.assertEqual(summary["unmatched"], 1)
        self.assertAlmostEqual(summary["coverage"], 2 / 3, places=3)

    def test_no_words_at_all(self):
        self.assertEqual(summarise_timings([])["coverage"], 0.0)

    def test_describe_reads_naturally(self):
        text = describe_timing({"aligned": 202, "coverage": 1.0})
        self.assertIn("202 aligned", text)
        self.assertIn("100%", text)

    def test_describe_without_a_summary(self):
        self.assertEqual(describe_timing(None), "no timings")


class TestSongLanguage(unittest.TestCase):
    def test_reads_the_detected_language(self):
        staging = unpack_song(build_song(), tempfile.mkdtemp())
        self.assertEqual(song_language(staging), "fr")

    def test_defaults_to_english_without_an_asr_result(self):
        self.assertEqual(song_language(tempfile.mkdtemp()), "en")


class TestUnpackSong(unittest.TestCase):
    def test_every_entry_comes_out(self):
        song = build_song()
        dest = unpack_song(song, tempfile.mkdtemp())
        self.assertEqual(sorted(os.listdir(dest)), sorted(list_entries(song)))

    def test_round_trips_through_pack(self):
        song = build_song()
        repacked = pack_song(unpack_song(song, tempfile.mkdtemp()), os.path.join(tempfile.mkdtemp(), "again.ak"))
        self.assertEqual(list_entries(song), list_entries(repacked))


if __name__ == "__main__":
    unittest.main()
