import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import PlayStopButton  # noqa: E402
from any_karaoke.game_config import BUTTON_HEIGHT, BUTTON_WIDTH  # noqa: E402


class ButtonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((800, 600))

    def setUp(self):
        self.playing = False
        self.button = PlayStopButton(lambda: self.playing)
        self.button.layout(100, 400)


class TestLayoutAndHits(ButtonTestCase):
    def test_is_centred_on_the_given_x(self):
        self.assertEqual(self.button.rect.centerx, 100)
        self.assertEqual(self.button.rect.top, 400)
        self.assertEqual(self.button.rect.size, (BUTTON_WIDTH, BUTTON_HEIGHT))

    def test_hit_inside_and_outside(self):
        self.assertTrue(self.button.hit(self.button.rect.center))
        self.assertFalse(self.button.hit((0, 0)))

    def test_cannot_be_hit_before_it_is_laid_out(self):
        fresh = PlayStopButton(lambda: False)
        self.assertFalse(fresh.hit((0, 0)))
        self.assertFalse(fresh.hit((100, 400)))


class TestIconState(ButtonTestCase):
    def test_shows_play_when_nothing_is_loaded(self):
        self.assertFalse(self.button.showing_stop)

    def test_shows_stop_while_a_song_is_loaded(self):
        self.playing = True
        self.assertTrue(self.button.showing_stop)

    def test_icon_follows_the_callable_rather_than_a_stale_copy(self):
        self.assertFalse(self.button.showing_stop)
        self.playing = True
        self.assertTrue(self.button.showing_stop)
        self.playing = False
        self.assertFalse(self.button.showing_stop)


class TestDrawing(ButtonTestCase):
    def render(self, mouse=(0, 0)):
        self.screen.fill((0, 0, 0))
        with mock.patch("pygame.mouse.get_pos", return_value=mouse):
            self.button.update_and_print(self.screen)

    def coloured_pixels(self):
        found = 0
        for y in range(self.button.rect.top, self.button.rect.bottom):
            for x in range(self.button.rect.left, self.button.rect.right):
                pixel = self.screen.get_at((x, y))[:3]
                if pixel[1] > 100 or pixel[0] > 100:
                    found += 1
        return found

    def test_draws_in_both_states(self):
        self.render()
        play_pixels = self.coloured_pixels()
        self.playing = True
        self.render()
        stop_pixels = self.coloured_pixels()
        self.assertGreater(play_pixels, 0)
        self.assertGreater(stop_pixels, 0)

    def test_stop_square_covers_more_area_than_the_play_triangle(self):
        # A triangle is half the area of its bounding box, so this catches a swapped icon
        self.render()
        play_pixels = self.coloured_pixels()
        self.playing = True
        self.render()
        self.assertGreater(self.coloured_pixels(), play_pixels)

    def test_hover_brightens_it(self):
        self.render(mouse=(0, 0))
        idle = self.coloured_pixels()
        self.render(mouse=self.button.rect.center)
        self.assertGreater(self.coloured_pixels(), idle)


if __name__ == "__main__":
    unittest.main()
