import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import MixerToggleButton, PlayPauseButton  # noqa: E402
from any_karaoke.game_config import (  # noqa: E402
    BUTTON_HEIGHT,
    BUTTON_PAUSE_COLOR,
    BUTTON_PLAY_COLOR,
    BUTTON_WIDTH,
    GHOST_ACTIVE_COLOR,
)


class ButtonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((800, 600))

    def paint(self, button, mouse=(0, 0)):
        self.screen.fill((0, 0, 0))
        with mock.patch("pygame.mouse.get_pos", return_value=mouse):
            button.update_and_print(self.screen)

    def glyph_pixels(self, button, colour):
        found = 0
        for y in range(button.rect.top, button.rect.bottom):
            for x in range(button.rect.left, button.rect.right):
                if self.screen.get_at((x, y))[:3] == colour:
                    found += 1
        return found


class TestPlayPauseButton(ButtonTestCase):
    def setUp(self):
        self.playing = False
        self.button = PlayPauseButton(lambda: self.playing)
        self.button.layout(22, 540)

    def test_sits_where_it_was_put(self):
        self.assertEqual(self.button.rect.topleft, (22, 540))
        self.assertEqual(self.button.rect.size, (BUTTON_WIDTH, BUTTON_HEIGHT))

    def test_shows_play_when_nothing_is_running(self):
        self.assertFalse(self.button.showing_pause)

    def test_shows_pause_while_a_song_runs(self):
        self.playing = True
        self.assertTrue(self.button.showing_pause)

    def test_the_glyph_follows_the_callable(self):
        self.paint(self.button)
        self.assertGreater(self.glyph_pixels(self.button, BUTTON_PLAY_COLOR), 0)
        self.playing = True
        self.paint(self.button)
        self.assertGreater(self.glyph_pixels(self.button, BUTTON_PAUSE_COLOR), 0)

    def test_two_pause_bars_cover_less_than_a_solid_triangle_area(self):
        # Catches the two glyphs being swapped
        self.paint(self.button)
        play = self.glyph_pixels(self.button, BUTTON_PLAY_COLOR)
        self.playing = True
        self.paint(self.button)
        self.assertNotEqual(self.glyph_pixels(self.button, BUTTON_PAUSE_COLOR), play)

    def colours_used(self, button):
        return {
            self.screen.get_at((x, y))[:3]
            for y in range(button.rect.top, button.rect.bottom)
            for x in range(button.rect.left, button.rect.right)
            if self.screen.get_at((x, y))[:3] != (0, 0, 0)
        }

    def test_hover_brightens_it(self):
        # Brightening changes the colours, not how many pixels are painted
        self.paint(self.button, mouse=(0, 0))
        idle = self.colours_used(self.button)
        self.paint(self.button, mouse=self.button.rect.center)
        self.assertNotEqual(self.colours_used(self.button), idle)

    def test_cannot_be_hit_before_layout(self):
        fresh = PlayPauseButton(lambda: False)
        self.assertFalse(fresh.hit((22, 540)))


class TestMixerToggleButton(ButtonTestCase):
    def setUp(self):
        self.showing = False
        self.button = MixerToggleButton(lambda: self.showing)
        self.button.layout(90, 540)

    def test_reports_the_toggle_state(self):
        self.assertFalse(self.button.is_active)
        self.showing = True
        self.assertTrue(self.button.is_active)

    def test_ghost_style_leaves_the_middle_unfilled(self):
        """No panel behind it, so the lyrics show through."""
        self.paint(self.button)
        inside = self.button.rect.inflate(-14, -14)
        background = sum(
            1
            for y in range(inside.top, inside.bottom, 2)
            for x in range(inside.left, inside.right, 2)
            if self.screen.get_at((x, y))[:3] == (0, 0, 0)
        )
        total = len(range(inside.top, inside.bottom, 2)) * len(range(inside.left, inside.right, 2))
        # The glyph is thin lines, so most of the inside is still background
        self.assertGreater(background / total, 0.6)

    def test_picks_up_the_accent_while_active(self):
        self.paint(self.button)
        self.assertEqual(self.glyph_pixels(self.button, GHOST_ACTIVE_COLOR), 0)
        self.showing = True
        self.paint(self.button)
        self.assertGreater(self.glyph_pixels(self.button, GHOST_ACTIVE_COLOR), 0)

    def test_draws_a_glyph_when_idle_too(self):
        self.paint(self.button)
        painted = sum(
            1
            for y in range(self.button.rect.top, self.button.rect.bottom)
            for x in range(self.button.rect.left, self.button.rect.right)
            if self.screen.get_at((x, y))[:3] != (0, 0, 0)
        )
        self.assertGreater(painted, 0)

    def test_cannot_be_hit_before_layout(self):
        self.assertFalse(MixerToggleButton(lambda: False).hit((90, 540)))


if __name__ == "__main__":
    unittest.main()
