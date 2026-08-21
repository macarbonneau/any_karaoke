import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke import assets  # noqa: E402
from any_karaoke.display_object import Logo  # noqa: E402


class TestAssetLookup(unittest.TestCase):
    def test_finds_the_logo_in_the_checkout(self):
        self.assertIsNotNone(assets.logo_path())
        self.assertTrue(os.path.isfile(assets.logo_path()))

    def test_finds_the_square_icon(self):
        self.assertTrue(assets.icon_path().endswith(assets.ICON_FILE))

    def test_unknown_asset_is_none_rather_than_an_error(self):
        self.assertIsNone(assets.asset_path("no_such_file.png"))

    def test_icon_falls_back_to_the_full_logo(self):
        with mock.patch.object(assets, "asset_path", side_effect=lambda n: None if n == assets.ICON_FILE else "full"):
            self.assertEqual(assets.icon_path(), "full")

    def test_everything_is_none_when_media_is_missing(self):
        with mock.patch.object(assets, "_SEARCH_PATHS", ()):
            self.assertIsNone(assets.logo_path())
            self.assertIsNone(assets.icon_path())


class TestLogoWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((1280, 720))

    def test_loads_the_artwork(self):
        self.assertTrue(Logo().available)

    def test_box_is_two_thirds_of_the_smaller_dimension(self):
        logo = Logo()
        self.assertEqual(logo.box_size(pygame.Surface((1280, 720))), int(720 * 2 / 3))
        # Portrait, so width is now the smaller side
        self.assertEqual(logo.box_size(pygame.Surface((600, 1200))), int(600 * 2 / 3))

    def test_scales_to_fit_that_box(self):
        logo = Logo()
        scaled = logo.scaled_to_box(logo.box_size(pygame.Surface((1280, 720))))
        self.assertLessEqual(max(scaled.get_size()), int(720 * 2 / 3))
        self.assertGreater(max(scaled.get_size()), int(720 * 2 / 3) - 2)

    def test_a_zero_box_gives_nothing(self):
        self.assertIsNone(Logo().scaled_to_box(0))

    def test_keeps_the_aspect_ratio(self):
        logo = Logo()
        source_ratio = logo.source.get_width() / logo.source.get_height()
        scaled = logo.scaled_to(200)
        self.assertAlmostEqual(scaled.get_width() / scaled.get_height(), source_ratio, places=1)

    def test_rescaling_is_cached_until_the_size_changes(self):
        logo = Logo()
        first = logo.scaled_to(200)
        self.assertIs(logo.scaled_to(200), first)
        self.assertIsNot(logo.scaled_to(300), first)

    def test_draws_something_on_screen(self):
        self.screen.fill((0, 0, 0))
        Logo().update_and_print(self.screen)
        painted = any(
            self.screen.get_at((x, y))[:3] != (0, 0, 0) for y in range(100, 400, 5) for x in range(400, 900, 5)
        )
        self.assertTrue(painted)

    def test_draws_nothing_and_does_not_raise_without_artwork(self):
        with mock.patch("any_karaoke.display_object.logo_path", return_value=None):
            logo = Logo()
        self.assertFalse(logo.available)
        self.screen.fill((0, 0, 0))
        logo.update_and_print(self.screen)
        self.assertEqual(self.screen.get_at((640, 260))[:3], (0, 0, 0))

    def test_zero_height_window_does_not_divide_by_zero(self):
        self.assertIsNone(Logo().scaled_to(0))


class TestPlayerIcon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((320, 240))

    def test_sets_the_window_icon(self):
        from any_karaoke.main import set_window_icon

        self.assertTrue(set_window_icon())

    def test_reports_failure_rather_than_raising_without_artwork(self):
        from any_karaoke import main

        with mock.patch.object(main, "icon_path", return_value=None):
            self.assertFalse(main.set_window_icon())


if __name__ == "__main__":
    unittest.main()
