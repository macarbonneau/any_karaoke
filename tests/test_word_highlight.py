import json
import os
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import LyricsDisplay  # noqa: E402
from any_karaoke.game_config import (  # noqa: E402
    FONT_COLOR_CURRENT,
    FONT_COLOR_WORD_ACTIVE,
    FONT_COLOR_WORD_SUNG,
)
from any_karaoke.song_files import LYRICS_ALIGNMENT_FILE, SONG_INFO_FILE, pack_song  # noqa: E402
from any_karaoke.state_objects import choose_lyrics, find_line_at_time  # noqa: E402

ASR_LYRICS = [{"text": "Maybe thats a fact and more words here", "start": 0.0, "end": 8.0}]

REFERENCE_LINES = [
    {
        "index": 0,
        "verse": 0,
        "text": "Baby that's a fact",
        "start": 1.0,
        "end": 3.0,
        "words": [
            {"word": "Baby", "start": 1.0, "end": 1.5, "timing": "approximate"},
            {"word": "that's", "start": 1.5, "end": 2.0, "timing": "matched"},
            {"word": "a", "start": 2.0, "end": 2.5, "timing": "matched"},
            {"word": "fact", "start": 2.5, "end": 3.0, "timing": "matched"},
        ],
    }
]


def make_song(lines=REFERENCE_LINES, as_archive=False, song_lyrics=None):
    folder = tempfile.mkdtemp(prefix="song_")
    with open(os.path.join(folder, SONG_INFO_FILE), "w", encoding="utf-8") as handle:
        json.dump({"title": "T", "lyrics": ASR_LYRICS if song_lyrics is None else song_lyrics}, handle)
    if lines is not None:
        with open(os.path.join(folder, LYRICS_ALIGNMENT_FILE), "w", encoding="utf-8") as handle:
            json.dump({"source": "online", "line_count": len(lines), "lines": lines}, handle)
    for stem in ("music", "vocals"):
        with open(os.path.join(folder, stem + ".mp3"), "wb") as handle:
            handle.write(b"\0")

    if as_archive:
        return pack_song(folder, os.path.join(tempfile.mkdtemp(), "song.ak"))
    return folder


def info_for(path):
    from any_karaoke.song_files import read_song_info

    return read_song_info(path)


class TestChooseLyrics(unittest.TestCase):
    def test_prefers_the_reference_lyrics_over_the_transcription(self):
        for as_archive in (False, True):
            path = make_song(as_archive=as_archive)
            lyrics = choose_lyrics(path, info_for(path))
            self.assertEqual(lyrics[0]["text"], "Baby that's a fact", as_archive)

    def test_falls_back_when_there_is_no_alignment_file(self):
        path = make_song(lines=None)
        self.assertEqual(choose_lyrics(path, info_for(path)), ASR_LYRICS)

    def test_falls_back_when_no_line_got_a_timing(self):
        untimed = [dict(REFERENCE_LINES[0], start=None, end=None)]
        path = make_song(lines=untimed)
        self.assertEqual(choose_lyrics(path, info_for(path)), ASR_LYRICS)

    def test_drops_only_the_lines_that_missed_out(self):
        mixed = [REFERENCE_LINES[0], {"text": "no timing", "start": None, "end": None, "words": []}]
        path = make_song(lines=mixed)
        lyrics = choose_lyrics(path, info_for(path))
        self.assertEqual(len(lyrics), 1)
        self.assertEqual(lyrics[0]["text"], "Baby that's a fact")

    def test_a_corrupt_alignment_file_falls_back(self):
        folder = make_song()
        with open(os.path.join(folder, LYRICS_ALIGNMENT_FILE), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(choose_lyrics(folder, info_for(folder)), ASR_LYRICS)

    def test_word_timings_come_through(self):
        path = make_song()
        line = choose_lyrics(path, info_for(path))[0]
        self.assertEqual(len(line["words"]), 4)

    def test_the_lookup_helpers_still_work_on_reference_lines(self):
        path = make_song()
        lyrics = choose_lyrics(path, info_for(path))
        self.assertEqual(find_line_at_time(lyrics, 2.2)["text"], "Baby that's a fact")
        self.assertIsNone(find_line_at_time(lyrics, 9.0))


class DisplayTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.display = LyricsDisplay()
        self.words = REFERENCE_LINES[0]["words"]


class TestWordColor(DisplayTestCase):
    def test_before_the_line_every_word_is_upcoming(self):
        self.assertTrue(all(self.display.word_color(w, 0.5) == FONT_COLOR_CURRENT for w in self.words))

    def test_the_word_being_sung_is_picked_out(self):
        self.assertEqual(self.display.word_color(self.words[1], 1.7), FONT_COLOR_WORD_ACTIVE)

    def test_words_already_sung_switch_colour(self):
        self.assertEqual(self.display.word_color(self.words[0], 2.7), FONT_COLOR_WORD_SUNG)

    def test_after_the_line_every_word_is_sung(self):
        self.assertTrue(all(self.display.word_color(w, 5.0) == FONT_COLOR_WORD_SUNG for w in self.words))

    def test_the_fill_only_moves_forwards(self):
        # Once a word turns sung it must not go back to upcoming as the song plays on
        seen_sung = 0
        for stamp in [x / 10 for x in range(0, 60)]:
            sung = sum(1 for w in self.words if self.display.word_color(w, stamp) == FONT_COLOR_WORD_SUNG)
            self.assertGreaterEqual(sung, seen_sung)
            seen_sung = sung

    def test_a_word_without_timings_stays_neutral(self):
        self.assertEqual(self.display.word_color({"word": "x"}, 1.0), FONT_COLOR_CURRENT)

    def test_exactly_one_word_is_active_at_a_time(self):
        for stamp in (1.2, 1.7, 2.2, 2.7):
            active = [w for w in self.words if self.display.word_color(w, stamp) == FONT_COLOR_WORD_ACTIVE]
            self.assertEqual(len(active), 1, stamp)


class TestWrapWords(DisplayTestCase):
    def test_a_short_line_stays_on_one_row(self):
        self.assertEqual(len(self.display.wrap_words(self.words, 2000)), 1)

    def test_a_long_line_is_split_but_keeps_every_word(self):
        many = [{"word": f"word{i}", "start": i, "end": i + 1} for i in range(40)]
        rows = self.display.wrap_words(many, 600)
        self.assertGreater(len(rows), 1)
        self.assertEqual([w["word"] for row in rows for w in row], [w["word"] for w in many])

    def test_rows_fit_the_width(self):
        many = [{"word": f"word{i}", "start": i, "end": i + 1} for i in range(40)]
        for row in self.display.wrap_words(many, 600):
            text = " ".join(w["word"] for w in row)
            if len(row) > 1:
                self.assertLessEqual(self.display.measure_width(text), 600)

    def test_no_words(self):
        self.assertEqual(self.display.wrap_words([], 600), [])


class TestRendering(DisplayTestCase):
    def paint(self, stamp, words=None):
        self.screen.fill((0, 0, 0))
        self.display.update_and_print(
            self.screen,
            "Baby that's a fact",
            ["earlier line"],
            ["later line"],
            current_words=self.words if words is None else words,
            time_stamp=stamp,
        )

    def count(self, colour):
        found = 0
        for y in range(0, 720, 2):
            for x in range(0, 1280, 4):
                if self.screen.get_at((x, y))[:3] == colour:
                    found += 1
        return found

    def test_the_sung_colour_grows_as_the_line_plays(self):
        self.paint(1.2)
        early = self.count(FONT_COLOR_WORD_SUNG)
        self.paint(2.9)
        self.assertGreater(self.count(FONT_COLOR_WORD_SUNG), early)

    def test_nothing_is_sung_before_the_line_starts(self):
        self.paint(0.1)
        self.assertEqual(self.count(FONT_COLOR_WORD_SUNG), 0)

    def test_the_active_word_is_on_screen_mid_line(self):
        self.paint(1.7)
        self.assertGreater(self.count(FONT_COLOR_WORD_ACTIVE), 0)

    def test_falls_back_to_a_plain_line_without_word_timings(self):
        self.paint(1.7, words=[])
        self.assertEqual(self.count(FONT_COLOR_WORD_ACTIVE), 0)
        self.assertGreater(self.count(FONT_COLOR_CURRENT), 0)

    def test_renders_with_no_current_line(self):
        self.screen.fill((0, 0, 0))
        self.display.update_and_print(self.screen, None, [], ["later"], current_words=None, time_stamp=1.0)

    def test_old_call_signature_still_works(self):
        self.screen.fill((0, 0, 0))
        self.display.update_and_print(self.screen, "a line", ["past"], ["next"])


if __name__ == "__main__":
    unittest.main()
