import unittest

from any_karaoke.state_objects import find_lyrics_at_time, find_next_lines, find_past_lines

LYRICS = [
    {"text": " line one ", "start": 0.0, "end": 1.0},
    {"text": "line two", "start": 1.0, "end": 2.0},
    {"text": "line three", "start": 2.0, "end": 3.0},
    {"text": "line four", "start": 3.0, "end": 4.0},
    {"text": "line five", "start": 4.0, "end": 5.0},
]


class TestFindLyricsAtTime(unittest.TestCase):
    def test_returns_stripped_current_line(self):
        self.assertEqual(find_lyrics_at_time(LYRICS, 0.5), "line one")

    def test_boundaries_are_inclusive(self):
        self.assertEqual(find_lyrics_at_time(LYRICS, 2.0), "line two")

    def test_returns_none_after_the_last_line(self):
        self.assertIsNone(find_lyrics_at_time(LYRICS, 99.0))

    def test_empty_lyrics(self):
        self.assertIsNone(find_lyrics_at_time([], 1.0))


class TestFindNextLines(unittest.TestCase):
    def test_returns_upcoming_lines_in_order(self):
        self.assertEqual(find_next_lines(LYRICS, 2.5, nb_lines=2), ["line four", "line five"])

    def test_respects_the_line_limit(self):
        self.assertEqual(len(find_next_lines(LYRICS, 0.0, nb_lines=3)), 3)

    def test_empty_at_the_end_of_the_song(self):
        self.assertEqual(find_next_lines(LYRICS, 99.0, nb_lines=3), [])


class TestFindPastLines(unittest.TestCase):
    def test_returns_lines_already_finished(self):
        self.assertEqual(find_past_lines(LYRICS, 2.5), ["line one", "line two"])

    def test_keeps_the_most_recent_lines_not_the_oldest(self):
        # Regression: the limit used to drop the newest lines and keep the song intro
        self.assertEqual(find_past_lines(LYRICS, 4.5, nb_lines=2), ["line three", "line four"])

    def test_no_limit_returns_everything(self):
        self.assertEqual(len(find_past_lines(LYRICS, 4.5)), 4)

    def test_empty_at_the_start_of_the_song(self):
        self.assertEqual(find_past_lines(LYRICS, 0.0, nb_lines=5), [])


if __name__ == "__main__":
    unittest.main()
