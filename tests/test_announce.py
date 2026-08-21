import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import Announce  # noqa: E402


class AnnounceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.announce = Announce()


class TestFitting(AnnounceTestCase):
    def rendered_width(self, text):
        size = self.announce.fitted_font_size(text, self.screen)
        return self.announce._font(size).size(text)[0]

    def test_text_fits_the_width_budget(self):
        budget = self.screen.get_width() * self.announce.width_ratio
        for text in ("A", "Short", "$10 Cowboy", "A Fairly Long Song Title Indeed", "x" * 120):
            self.assertLessEqual(self.rendered_width(text), budget + 2, text)

    def test_text_fits_the_height_budget(self):
        budget = self.screen.get_height() * self.announce.height_ratio
        for text in ("A", "$10 Cowboy", "x" * 120):
            size = self.announce.fitted_font_size(text, self.screen)
            self.assertLessEqual(self.announce._font(size).size(text)[1], budget + 2, text)

    def test_a_short_title_gets_a_bigger_font_than_a_long_one(self):
        short = self.announce.fitted_font_size("Hey", self.screen)
        long_one = self.announce.fitted_font_size("A Very Long Song Title That Goes On", self.screen)
        self.assertGreater(short, long_one)

    def test_a_wider_window_allows_a_bigger_font(self):
        narrow = self.announce.fitted_font_size("$10 Cowboy", pygame.Surface((640, 480)))
        wide = self.announce.fitted_font_size("$10 Cowboy", pygame.Surface((2560, 1440)))
        self.assertGreater(wide, narrow)

    def test_never_goes_below_the_minimum(self):
        size = self.announce.fitted_font_size("y" * 4000, pygame.Surface((200, 100)))
        self.assertGreaterEqual(size, Announce.MIN_FONT_SIZE)


class TestFontCache(AnnounceTestCase):
    def test_same_size_reuses_the_font_object(self):
        self.assertIs(self.announce._font(64), self.announce._font(64))

    def test_different_sizes_are_distinct(self):
        self.assertIsNot(self.announce._font(64), self.announce._font(65))


class TestDrawing(AnnounceTestCase):
    def test_empty_text_draws_nothing(self):
        self.screen.fill((0, 0, 0))
        self.announce.update_and_print(self.screen, "")
        self.announce.update_and_print(self.screen, None)
        self.assertEqual(self.screen.get_at((640, 360))[:3], (0, 0, 0))

    def test_text_lands_on_screen(self):
        self.screen.fill((0, 0, 0))
        self.announce.update_and_print(self.screen, "$10 Cowboy", color=(255, 0, 0))
        painted = any(self.screen.get_at((x, y))[0] > 100 for y in range(300, 420, 4) for x in range(300, 980, 4))
        self.assertTrue(painted)

    def test_draws_titles_of_wildly_different_lengths(self):
        for text in ("A", "$10 Cowboy", "An Extremely Long Song Title " * 4):
            self.screen.fill((0, 0, 0))
            self.announce.update_and_print(self.screen, text)


if __name__ == "__main__":
    unittest.main()
