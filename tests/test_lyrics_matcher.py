import json
import os
import unittest

from any_karaoke.extractor import build_lyrics_alignment
from any_karaoke.lyrics_matcher import (
    comparison_tokens,
    fill_lyrics_timings,
    normalize_word,
    timed_words,
)

SAMPLE = os.path.join("karaoke_tracks", "$10 Cowboy")


def alignment(words, per_word=1.0, start=0.0):
    """One segment carrying evenly spaced timed words."""
    timed = []
    at = start
    for word in words:
        timed.append({"word": word, "start": round(at, 3), "end": round(at + per_word, 3)})
        at += per_word
    return {"segments": [{"start": start, "end": at, "text": " ".join(words), "words": timed}]}


def flat(filled):
    return [word for line in filled["lines"] for word in line["words"]]


class TestNormalize(unittest.TestCase):
    def test_lowercases_and_drops_punctuation(self):
        self.assertEqual(normalize_word("Cowboy,"), "cowboy")
        self.assertEqual(normalize_word("Baby!"), "baby")

    def test_keeps_internal_apostrophes(self):
        self.assertEqual(normalize_word("that's"), "that's")

    def test_empty_and_none(self):
        self.assertEqual(normalize_word(""), "")
        self.assertEqual(normalize_word(None), "")

    def test_punctuation_only_word(self):
        self.assertEqual(normalize_word("--"), "")


class TestComparisonTokens(unittest.TestCase):
    def test_splits_hyphenated_words_but_remembers_the_owner(self):
        keys, owners = comparison_tokens(["ten-dollar", "cowboy"])
        self.assertEqual(keys, ["ten", "dollar", "cowboy"])
        self.assertEqual(owners, [0, 0, 1])

    def test_drops_pieces_that_normalize_away(self):
        keys, owners = comparison_tokens(["...", "real"])
        self.assertEqual(keys, ["real"])
        self.assertEqual(owners, [1])


class TestTimedWords(unittest.TestCase):
    def test_flattens_segments(self):
        self.assertEqual(len(timed_words(alignment(["a", "b", "c"]))), 3)

    def test_skips_words_without_timings(self):
        result = {"segments": [{"words": [{"word": "a", "start": 1, "end": 2}, {"word": "1999"}]}]}
        self.assertEqual(len(timed_words(result)), 1)

    def test_handles_missing_input(self):
        self.assertEqual(timed_words(None), [])
        self.assertEqual(timed_words({}), [])


class TestExactMatch(unittest.TestCase):
    def setUp(self):
        self.scaffold = build_lyrics_alignment("one two\nthree four", "online")

    def test_identical_words_take_the_timings_directly(self):
        filled = fill_lyrics_timings(self.scaffold, alignment(["one", "two", "three", "four"]))
        self.assertEqual([w["start"] for w in flat(filled)], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(filled["timing"]["matched"], 4)
        self.assertEqual(filled["timing"]["coverage"], 1.0)

    def test_case_and_punctuation_still_match(self):
        filled = fill_lyrics_timings(self.scaffold, alignment(["One,", "TWO!", "three.", "Four"]))
        self.assertEqual(filled["timing"]["matched"], 4)

    def test_line_spans_wrap_their_words(self):
        filled = fill_lyrics_timings(self.scaffold, alignment(["one", "two", "three", "four"]))
        self.assertEqual((filled["lines"][0]["start"], filled["lines"][0]["end"]), (0.0, 2.0))
        self.assertEqual((filled["lines"][1]["start"], filled["lines"][1]["end"]), (2.0, 4.0))


class TestMisheardWords(unittest.TestCase):
    def test_a_substituted_word_keeps_its_slot(self):
        # The real case: the ASR heard "Maybe" where the lyrics say "Baby"
        scaffold = build_lyrics_alignment("Baby that's a fact", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["Maybe", "that's", "a", "fact"]))
        words = flat(filled)
        self.assertEqual(words[0]["start"], 0.0)
        self.assertEqual(words[0]["timing"], "approximate")
        self.assertEqual(words[1]["timing"], "matched")
        self.assertEqual(filled["timing"]["unmatched"], 0)

    def test_a_hyphenated_word_spans_both_spoken_words(self):
        scaffold = build_lyrics_alignment("ten-dollar cowboy", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["ten", "dollar", "cowboy"]))
        words = flat(filled)
        self.assertEqual((words[0]["start"], words[0]["end"]), (0.0, 2.0))
        self.assertEqual(words[1]["start"], 2.0)

    def test_extra_spoken_words_are_ignored(self):
        scaffold = build_lyrics_alignment("one two", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["one", "uh", "two"]))
        self.assertEqual(filled["timing"]["unmatched"], 0)
        self.assertEqual(flat(filled)[1]["start"], 2.0)


class TestInterpolation(unittest.TestCase):
    def test_a_word_the_aligner_missed_is_interpolated_between_anchors(self):
        scaffold = build_lyrics_alignment("alpha bravo charlie", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["alpha", "charlie"]))
        words = flat(filled)
        self.assertEqual(words[1]["timing"], "interpolated")
        self.assertGreaterEqual(words[1]["start"], words[0]["end"])
        self.assertLessEqual(words[1]["end"], words[2]["start"] + 1e-9)
        self.assertEqual(filled["timing"]["interpolated"], 1)

    def test_a_run_of_missing_words_is_shared_out(self):
        scaffold = build_lyrics_alignment("alpha one two three bravo", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["alpha", "bravo"], per_word=1.0))
        middle = flat(filled)[1:4]
        self.assertTrue(all(w["timing"] == "interpolated" for w in middle))
        starts = [w["start"] for w in middle]
        self.assertEqual(starts, sorted(starts))

    def test_unmatched_words_at_the_start_still_get_a_time(self):
        scaffold = build_lyrics_alignment("intro alpha", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["alpha"], start=5.0))
        self.assertIsNotNone(flat(filled)[0]["start"])
        self.assertEqual(filled["timing"]["unmatched"], 0)

    def test_unmatched_words_at_the_end_still_get_a_time(self):
        scaffold = build_lyrics_alignment("alpha outro", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["alpha"]))
        self.assertIsNotNone(flat(filled)[1]["start"])

    def test_nothing_matches_at_all(self):
        scaffold = build_lyrics_alignment("totally different words", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["nothing", "alike", "here"]))
        # Same length, so they pair off positionally rather than being left blank
        self.assertEqual(filled["timing"]["unmatched"], 0)


class TestOrdering(unittest.TestCase):
    def test_timeline_never_goes_backwards(self):
        scaffold = build_lyrics_alignment("one two three four five", "online")
        out_of_order = alignment(["one", "two", "three", "four", "five"])
        out_of_order["segments"][0]["words"][2]["start"] = 0.1  # a stray early match
        filled = fill_lyrics_timings(scaffold, out_of_order)
        starts = [w["start"] for w in flat(filled)]
        self.assertEqual(starts, sorted(starts))

    def test_every_word_ends_no_earlier_than_it_starts(self):
        scaffold = build_lyrics_alignment("one two three", "online")
        filled = fill_lyrics_timings(scaffold, alignment(["one", "three"]))
        for word in flat(filled):
            self.assertGreaterEqual(word["end"], word["start"])


class TestDegenerateInput(unittest.TestCase):
    def test_no_timed_words_leaves_everything_blank(self):
        scaffold = build_lyrics_alignment("one two", "online")
        filled = fill_lyrics_timings(scaffold, {"segments": []})
        self.assertEqual(
            filled["timing"], {"matched": 0, "approximate": 0, "interpolated": 0, "unmatched": 2, "coverage": 0.0}
        )
        self.assertIsNone(flat(filled)[0]["start"])

    def test_empty_scaffold(self):
        filled = fill_lyrics_timings(build_lyrics_alignment("", "online"), alignment(["a"]))
        self.assertEqual(filled["lines"], [])
        self.assertEqual(filled["timing"]["coverage"], 0.0)

    def test_none_inputs(self):
        self.assertEqual(fill_lyrics_timings(None, None)["timing"]["coverage"], 0.0)

    def test_the_input_scaffold_is_not_mutated(self):
        scaffold = build_lyrics_alignment("one two", "online")
        fill_lyrics_timings(scaffold, alignment(["one", "two"]))
        self.assertIsNone(scaffold["lines"][0]["words"][0]["start"])

    def test_source_and_line_count_survive(self):
        scaffold = build_lyrics_alignment("one\ntwo", "pasted")
        filled = fill_lyrics_timings(scaffold, alignment(["one", "two"]))
        self.assertEqual(filled["source"], "pasted")
        self.assertEqual(filled["line_count"], 2)


@unittest.skipUnless(os.path.isdir(SAMPLE), "sample song not present")
class TestAgainstTheRealSong(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(SAMPLE, "online_lyrics.txt"), encoding="utf-8") as handle:
            scaffold = build_lyrics_alignment(handle.read(), "online")
        with open(os.path.join(SAMPLE, "alignment_result.json"), encoding="utf-8") as handle:
            cls.filled = fill_lyrics_timings(scaffold, json.load(handle))

    def test_every_word_gets_a_time(self):
        self.assertEqual(self.filled["timing"]["unmatched"], 0)
        self.assertEqual(self.filled["timing"]["coverage"], 1.0)

    def test_most_words_match_exactly(self):
        summary = self.filled["timing"]
        self.assertGreater(summary["matched"], summary["approximate"] + summary["interpolated"])

    def test_every_line_gets_a_span(self):
        self.assertTrue(all(line["start"] is not None for line in self.filled["lines"]))

    def test_lines_run_in_order(self):
        starts = [line["start"] for line in self.filled["lines"]]
        self.assertEqual(starts, sorted(starts))

    def test_timings_stay_inside_the_song(self):
        starts = [line["start"] for line in self.filled["lines"]]
        ends = [line["end"] for line in self.filled["lines"]]
        self.assertGreaterEqual(min(starts), 0.0)
        self.assertLess(max(ends), 216.0)  # the track is 215.5s

    def test_the_misheard_line_keeps_the_correct_words(self):
        line = next(x for x in self.filled["lines"] if "Baby that's a fact" in x["text"])
        self.assertIsNotNone(line["start"])
        self.assertEqual([w["word"] for w in line["words"]], ["Baby", "that's", "a", "fact"])


if __name__ == "__main__":
    unittest.main()
