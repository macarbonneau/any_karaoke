import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import LyricsDisplay  # noqa: E402
from any_karaoke.game_config import BACK_COLOR, LYRICS_MIN_FONT_SIZE  # noqa: E402

LINES = [
    "Baby that's a fact",
    "I got some inhibitions",
    "That might be holding me back",
]


def surface(width, height):
    return pygame.Surface((width, height))


class LyricsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((100, 100))

    def setUp(self):
        self.display = LyricsDisplay()


class TestFontScaling(LyricsTestCase):
    def test_a_taller_window_gets_a_bigger_font(self):
        small = self.display.font_size_for(surface(1280, 720))
        large = self.display.font_size_for(surface(1920, 1080))
        self.assertGreater(large, small)

    def test_scales_roughly_with_height(self):
        single = self.display.font_size_for(surface(1280, 720))
        double = self.display.font_size_for(surface(2560, 1440))
        self.assertAlmostEqual(double / single, 2.0, delta=0.15)

    def test_width_caps_the_font_on_a_narrow_window(self):
        # Height alone would give a big font that wrapped every line into pieces
        tall_and_narrow = self.display.font_size_for(surface(500, 900))
        by_height_alone = int(900 * self.display.height_ratio)
        self.assertLess(tall_and_narrow, by_height_alone)

    def test_never_smaller_than_the_floor(self):
        self.assertGreaterEqual(self.display.font_size_for(surface(1, 1)), LYRICS_MIN_FONT_SIZE)

    def test_fonts_are_cached_per_size(self):
        first = self.display._font(48)
        self.assertIs(self.display._font(48), first)
        self.assertIsNot(self.display._font(49), first)

    def test_using_a_screen_swaps_the_live_font(self):
        self.display.use_font_for(surface(800, 600))
        small = self.display.measure_width("cowboy")
        self.display.use_font_for(surface(2560, 1440))
        self.assertGreater(self.display.measure_width("cowboy"), small)


class TestMargins(LyricsTestCase):
    def test_leaves_a_margin_on_each_side(self):
        width = 1280
        usable = self.display.text_width_for(surface(width, 720))
        self.assertLess(usable, width)
        self.assertAlmostEqual((width - usable) / 2 / width, self.display.margin_ratio, places=2)

    def test_the_margin_grows_with_the_window(self):
        narrow = 800 - self.display.text_width_for(surface(800, 600))
        wide = 1920 - self.display.text_width_for(surface(1920, 1080))
        self.assertGreater(wide, narrow)

    def test_wrapping_respects_the_margin_not_the_window_edge(self):
        screen = surface(900, 600)
        usable = self.display.text_width_for(screen)
        self.display.use_font_for(screen)

        # A line that would fit the raw window but not the usable width must be split
        line = "x" * 400
        for piece in self.display.split_line_to_fit_in_screen(screen, line):
            self.assertLessEqual(self.display.measure_width(piece), usable)

    def test_nothing_is_painted_inside_the_margin(self):
        for width, height in ((800, 600), (1280, 720), (1920, 1080)):
            screen = pygame.Surface((width, height))
            screen.fill(BACK_COLOR)
            self.display.update_and_print(screen, LINES[0], [LINES[1]], [LINES[2]])

            margin = (width - self.display.text_width_for(screen)) // 2
            for x in (0, margin // 2, max(0, margin - 3)):
                column = [screen.get_at((x, y))[:3] for y in range(0, height, 3)]
                self.assertTrue(all(pixel == BACK_COLOR for pixel in column), f"{width}x{height} at x={x}")

    def test_long_lines_still_fit_after_scaling(self):
        for width, height in ((640, 480), (1280, 720), (2560, 1440)):
            screen = surface(width, height)
            self.display.use_font_for(screen)
            usable = self.display.text_width_for(screen)
            pieces = self.display.split_line_to_fit_in_screen(screen, "That might be holding me back" * 3)
            for piece in pieces:
                self.assertLessEqual(self.display.measure_width(piece), usable, f"{width}x{height}")


class TestRenderingAtEverySize(LyricsTestCase):
    def test_draws_without_error_across_window_sizes(self):
        for width, height in ((320, 240), (800, 600), (1920, 1080), (3440, 1440), (500, 2000)):
            screen = pygame.Surface((width, height))
            screen.fill(BACK_COLOR)
            self.display.update_and_print(screen, LINES[0], [LINES[1]], [LINES[2]])

    def test_bigger_window_paints_more_ink(self):
        def ink(width, height):
            screen = pygame.Surface((width, height))
            screen.fill(BACK_COLOR)
            self.display.update_and_print(screen, LINES[0], [LINES[1]], [LINES[2]])
            return sum(
                1 for y in range(0, height, 2) for x in range(0, width, 2) if screen.get_at((x, y))[:3] != BACK_COLOR
            )

        self.assertGreater(ink(1920, 1080), ink(800, 600))


if __name__ == "__main__":
    unittest.main()
