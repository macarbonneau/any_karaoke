import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.display_object import VolumeSlider, brighten  # noqa: E402
from any_karaoke.game_config import SLIDER_HIT_WIDTH, SLIDER_TRACK_WIDTH  # noqa: E402


class SliderTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((800, 600))

    def setUp(self):
        self.slider = VolumeSlider("music", 0.5, 0.5)
        self.slider.layout(self.screen)


class TestLayout(SliderTestCase):
    def test_grab_area_is_wider_than_the_drawn_track(self):
        # The track is slim so it does not cover the lyrics, but it still has to be grabbable
        self.assertEqual(self.slider.track_rect.width, SLIDER_TRACK_WIDTH)
        self.assertGreaterEqual(self.slider.hit_rect.width, SLIDER_HIT_WIDTH)
        self.assertGreater(self.slider.hit_rect.width, self.slider.track_rect.width)

    def test_grab_area_is_centred_on_the_track(self):
        self.assertEqual(self.slider.hit_rect.centerx, self.slider.track_rect.centerx)

    def test_rects_are_empty_before_the_first_layout(self):
        fresh = VolumeSlider("music", 0.5, 0.5)
        self.assertEqual(fresh.hit_rect, pygame.Rect(0, 0, 0, 0))
        self.assertIsNone(fresh.update_drag((10, 10), True))

    def test_outline_rect_still_exposes_the_grab_area(self):
        self.assertEqual(self.slider.outline_rect, self.slider.hit_rect)

    def test_layout_follows_the_window_size(self):
        bigger = pygame.Surface((1600, 1200))
        self.slider.layout(bigger)
        self.assertEqual(self.slider.track_rect.centerx, 800)


class TestValueMapping(SliderTestCase):
    def test_top_of_the_track_is_full(self):
        track = self.slider.track_rect
        self.slider.update_drag((track.centerx, track.top), True)
        self.assertEqual(self.slider.slider_value, 100)

    def test_bottom_of_the_track_is_silent(self):
        track = self.slider.track_rect
        self.slider.update_drag((track.centerx, track.bottom), True)
        self.assertEqual(self.slider.slider_value, 0)
        self.assertTrue(self.slider.muted)

    def test_middle_is_about_half(self):
        track = self.slider.track_rect
        self.slider.update_drag((track.centerx, track.centery), True)
        self.assertAlmostEqual(self.slider.slider_value, 50, delta=1)

    def test_volume_is_the_percentage_over_100(self):
        self.slider.set_percent(40)
        self.assertAlmostEqual(self.slider.volume, 0.4)

    def test_values_are_clamped(self):
        self.assertEqual(self.slider.set_percent(500), 1.0)
        self.assertEqual(self.slider.set_percent(-20), 0.0)


class TestDragCapture(SliderTestCase):
    def test_press_outside_the_grab_area_does_nothing(self):
        self.assertIsNone(self.slider.update_drag((5, 5), True))
        self.assertFalse(self.slider.dragging)

    def test_press_inside_starts_a_drag(self):
        self.slider.update_drag(self.slider.hit_rect.center, True)
        self.assertTrue(self.slider.dragging)

    def test_drag_continues_when_the_mouse_leaves_the_track(self):
        track = self.slider.track_rect
        self.slider.update_drag(track.center, True)
        # Far to the side, the way a real drag wanders
        self.slider.update_drag((track.centerx + 400, track.top), True)
        self.assertEqual(self.slider.slider_value, 100)

    def test_releasing_ends_the_drag(self):
        self.slider.update_drag(self.slider.hit_rect.center, True)
        self.assertIsNone(self.slider.update_drag(self.slider.hit_rect.center, False))
        self.assertFalse(self.slider.dragging)

    def test_a_new_press_away_from_the_slider_does_not_resume(self):
        self.slider.update_drag(self.slider.hit_rect.center, True)
        self.slider.update_drag(self.slider.hit_rect.center, False)
        self.assertIsNone(self.slider.update_drag((5, 5), True))

    def test_drag_beyond_the_ends_is_clamped(self):
        track = self.slider.track_rect
        self.slider.update_drag(track.center, True)
        self.slider.update_drag((track.centerx, track.top - 500), True)
        self.assertEqual(self.slider.slider_value, 100)
        self.slider.update_drag((track.centerx, track.bottom + 500), True)
        self.assertEqual(self.slider.slider_value, 0)


class TestDrawing(SliderTestCase):
    def render(self, value):
        self.screen.fill((0, 0, 0))
        self.slider.set_percent(value)
        self.slider.update_and_print(self.screen)

    def test_draws_at_every_level_without_error(self):
        for value in (0, 1, 3, 25, 50, 99, 100):
            self.render(value)

    def test_accent_is_visible_when_loud_and_absent_when_silent(self):
        accent = self.slider.accent
        self.render(100)
        loud = self.count_accent_pixels(accent)
        self.render(0)
        silent = self.count_accent_pixels(accent)
        self.assertGreater(loud, 0)
        self.assertEqual(silent, 0)

    def test_more_fill_at_a_higher_level(self):
        accent = self.slider.accent
        self.render(25)
        quiet = self.count_accent_pixels(accent)
        self.render(75)
        loud = self.count_accent_pixels(accent)
        self.assertGreater(loud, quiet)

    def count_accent_pixels(self, accent):
        track = self.slider.track_rect
        found = 0
        for y in range(track.top, track.bottom, 4):
            if self.screen.get_at((track.centerx, y))[:3] == accent:
                found += 1
        return found

    def test_a_tiny_level_still_draws_inside_the_track(self):
        self.render(2)
        track = self.slider.track_rect
        self.assertLessEqual(self.slider.track_rect.bottom, track.bottom)


class TestBrighten(unittest.TestCase):
    def test_scales_channels(self):
        self.assertEqual(brighten((100, 50, 25), 2), (200, 100, 50))

    def test_clamps_at_255(self):
        self.assertEqual(brighten((200, 200, 200), 5), (255, 255, 255))

    def test_drops_any_alpha(self):
        self.assertEqual(len(brighten((10, 20, 30, 40), 1)), 3)


if __name__ == "__main__":
    unittest.main()
