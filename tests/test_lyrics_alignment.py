import os
import unittest

from any_karaoke.extractor import build_lyrics_alignment

REAL_LYRICS = os.path.join("karaoke_tracks", "$10 Cowboy", "online_lyrics.txt")

TWO_VERSES = "First line\nSecond line\n\nThird line\nFourth line\n"


class TestStructure(unittest.TestCase):
    def test_reports_the_source_and_count(self):
        result = build_lyrics_alignment(TWO_VERSES, "online")
        self.assertEqual(result["source"], "online")
        self.assertEqual(result["line_count"], 4)
        self.assertEqual(len(result["lines"]), 4)

    def test_indices_are_contiguous_from_zero(self):
        lines = build_lyrics_alignment(TWO_VERSES, "pasted")["lines"]
        self.assertEqual([line["index"] for line in lines], [0, 1, 2, 3])

    def test_every_timing_slot_is_blank(self):
        for line in build_lyrics_alignment(TWO_VERSES, "online")["lines"]:
            self.assertIsNone(line["start"])
            self.assertIsNone(line["end"])
            for word in line["words"]:
                self.assertIsNone(word["start"])
                self.assertIsNone(word["end"])

    def test_text_is_stripped(self):
        lines = build_lyrics_alignment("   padded line   \n", "online")["lines"]
        self.assertEqual(lines[0]["text"], "padded line")


class TestVerses(unittest.TestCase):
    def test_blank_line_starts_a_new_verse(self):
        lines = build_lyrics_alignment(TWO_VERSES, "online")["lines"]
        self.assertEqual([line["verse"] for line in lines], [0, 0, 1, 1])

    def test_several_blank_lines_count_as_one_break(self):
        lines = build_lyrics_alignment("a\n\n\n\nb\n", "online")["lines"]
        self.assertEqual([line["verse"] for line in lines], [0, 1])

    def test_leading_blank_lines_do_not_shift_the_first_verse(self):
        lines = build_lyrics_alignment("\n\n\nfirst\n", "online")["lines"]
        self.assertEqual(lines[0]["verse"], 0)

    def test_trailing_blank_lines_add_no_verse(self):
        lines = build_lyrics_alignment("only\n\n\n", "online")["lines"]
        self.assertEqual([line["verse"] for line in lines], [0])

    def test_whitespace_only_lines_count_as_blank(self):
        lines = build_lyrics_alignment("a\n   \t \nb\n", "online")["lines"]
        self.assertEqual([line["verse"] for line in lines], [0, 1])


class TestLineEndings(unittest.TestCase):
    def test_crlf_and_lf_give_the_same_result(self):
        # api.lyrics.ovh returns CRLF
        crlf = build_lyrics_alignment(TWO_VERSES.replace("\n", "\r\n"), "online")
        self.assertEqual(crlf, build_lyrics_alignment(TWO_VERSES, "online"))

    def test_bare_cr_is_handled(self):
        result = build_lyrics_alignment("a\rb\r", "online")
        self.assertEqual(result["line_count"], 2)


class TestWords(unittest.TestCase):
    def test_splits_on_whitespace(self):
        words = build_lyrics_alignment("one two three", "online")["lines"][0]["words"]
        self.assertEqual([w["word"] for w in words], ["one", "two", "three"])

    def test_punctuation_stays_attached(self):
        # The matcher can normalise; dropping characters here would lose information
        words = build_lyrics_alignment("I'm a ten-dollar cowboy, baby!", "online")["lines"][0]["words"]
        self.assertEqual([w["word"] for w in words], ["I'm", "a", "ten-dollar", "cowboy,", "baby!"])

    def test_runs_of_spaces_do_not_make_empty_words(self):
        words = build_lyrics_alignment("one    two", "online")["lines"][0]["words"]
        self.assertEqual(len(words), 2)


class TestEmptyInput(unittest.TestCase):
    def test_empty_string(self):
        result = build_lyrics_alignment("", "online")
        self.assertEqual(result["line_count"], 0)
        self.assertEqual(result["lines"], [])

    def test_none(self):
        self.assertEqual(build_lyrics_alignment(None, "online")["line_count"], 0)

    def test_only_whitespace(self):
        self.assertEqual(build_lyrics_alignment("  \n\n \t \n", "online")["line_count"], 0)


@unittest.skipUnless(os.path.isfile(REAL_LYRICS), "sample lyrics not present")
class TestAgainstRealLyrics(unittest.TestCase):
    def setUp(self):
        with open(REAL_LYRICS, encoding="utf-8") as handle:
            self.result = build_lyrics_alignment(handle.read(), "online")

    def test_line_and_verse_counts(self):
        self.assertEqual(self.result["line_count"], 42)
        self.assertEqual(self.result["lines"][-1]["verse"] + 1, 10)

    def test_keeps_the_spelling_the_asr_got_wrong(self):
        texts = [line["text"] for line in self.result["lines"]]
        self.assertIn("Baby that's a fact", texts)  # the ASR heard "Maybe that's a fact"

    def test_word_count_is_close_to_the_timed_words(self):
        # 205 words carry timings in alignment_result.json, so a matcher has a real chance
        words = sum(len(line["words"]) for line in self.result["lines"])
        self.assertGreater(words, 150)
        self.assertLess(words, 260)


if __name__ == "__main__":
    unittest.main()
