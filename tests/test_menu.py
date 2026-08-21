import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.game_config import MENU_BAR_HEIGHT  # noqa: E402
from any_karaoke.menu import Menu, MenuBar, MenuItem  # noqa: E402


def key_event(key, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod)


def click(pos):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)


class MenuTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((800, 600))

    def setUp(self):
        self.fired = []
        self.enabled = True
        self.items = [
            MenuItem("Open", lambda: self.fired.append("open"), pygame.K_o, pygame.KMOD_CTRL, "Ctrl+O"),
            MenuItem("Quit", lambda: self.fired.append("quit"), pygame.K_q, pygame.KMOD_CTRL, "Ctrl+Q"),
        ]
        self.playback = [
            MenuItem(
                "Pause",
                lambda: self.fired.append("pause"),
                pygame.K_SPACE,
                shortcut_text="Space",
                enabled=lambda: self.enabled,
            ),
        ]
        self.bar = MenuBar([Menu("File", self.items), Menu("Playback", self.playback)])
        self.bar._layout_titles()


class TestShortcutMatching(MenuTestCase):
    def test_ctrl_shortcut_matches(self):
        self.assertTrue(self.items[0].matches(key_event(pygame.K_o, pygame.KMOD_CTRL)))

    def test_bare_key_does_not_match_a_ctrl_shortcut(self):
        self.assertFalse(self.items[0].matches(key_event(pygame.K_o)))

    def test_wrong_key_does_not_match(self):
        self.assertFalse(self.items[0].matches(key_event(pygame.K_p, pygame.KMOD_CTRL)))

    def test_bare_shortcut_matches_without_modifiers(self):
        self.assertTrue(self.playback[0].matches(key_event(pygame.K_SPACE)))

    def test_bare_shortcut_ignored_while_ctrl_is_held(self):
        # Otherwise Ctrl+Space would trigger pause
        self.assertFalse(self.playback[0].matches(key_event(pygame.K_SPACE, pygame.KMOD_CTRL)))

    def test_item_without_a_shortcut_never_matches(self):
        self.assertFalse(MenuItem("info", None).matches(key_event(pygame.K_a)))


class TestKeyboardDispatch(MenuTestCase):
    def test_bar_runs_the_matching_action(self):
        self.assertTrue(self.bar.handle_event(key_event(pygame.K_q, pygame.KMOD_CTRL)))
        self.assertEqual(self.fired, ["quit"])

    def test_unknown_key_is_not_consumed(self):
        self.assertFalse(self.bar.handle_event(key_event(pygame.K_z)))
        self.assertEqual(self.fired, [])

    def test_disabled_item_does_not_fire(self):
        self.enabled = False
        self.bar.handle_event(key_event(pygame.K_SPACE))
        self.assertEqual(self.fired, [])

    def test_escape_closes_an_open_menu(self):
        self.bar.handle_event(click((10, 10)))
        self.assertTrue(self.bar.is_open())
        self.assertTrue(self.bar.handle_event(key_event(pygame.K_ESCAPE)))
        self.assertFalse(self.bar.is_open())


class TestHitTesting(MenuTestCase):
    def test_title_at_finds_each_menu(self):
        self.assertEqual(self.bar.title_at((10, 10)), 0)
        second = self.bar._title_rects[1]
        self.assertEqual(self.bar.title_at((second.centerx, second.centery)), 1)

    def test_title_at_below_the_bar_is_nothing(self):
        self.assertIsNone(self.bar.title_at((10, MENU_BAR_HEIGHT + 40)))

    def test_clicking_a_title_opens_and_closes_it(self):
        self.bar.handle_event(click((10, 10)))
        self.assertEqual(self.bar.open_index, 0)
        self.bar.handle_event(click((10, 10)))
        self.assertFalse(self.bar.is_open())

    def test_clicking_an_item_runs_it_and_closes(self):
        self.bar.handle_event(click((10, 10)))
        item_rect = self.bar._item_rects[1]
        self.bar.handle_event(click(item_rect.center))
        self.assertEqual(self.fired, ["quit"])
        self.assertFalse(self.bar.is_open())

    def test_clicking_away_closes_without_firing(self):
        self.bar.handle_event(click((10, 10)))
        self.bar.handle_event(click((400, 400)))
        self.assertFalse(self.bar.is_open())
        self.assertEqual(self.fired, [])

    def test_sliding_onto_another_title_switches_menus(self):
        self.bar.handle_event(click((10, 10)))
        second = self.bar._title_rects[1]
        self.bar.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=second.center))
        self.assertEqual(self.bar.open_index, 1)


class TestVisibility(MenuTestCase):
    def test_hidden_in_the_middle_of_the_window(self):
        self.assertFalse(self.bar.is_visible((400, 300), 800))

    def test_shown_in_the_top_strip(self):
        self.assertTrue(self.bar.is_visible((400, MENU_BAR_HEIGHT - 2), 800))

    def test_hidden_just_below_the_strip(self):
        self.assertFalse(self.bar.is_visible((400, MENU_BAR_HEIGHT + 2), 800))

    def test_stays_visible_over_an_open_dropdown(self):
        self.bar.handle_event(click((10, 10)))
        panel = self.bar._panel_rect
        # Well below the bar, but inside the dropdown
        self.assertGreater(panel.centery, MENU_BAR_HEIGHT)
        self.assertTrue(self.bar.is_visible(panel.center, 800))


class TestLabels(MenuTestCase):
    def test_callable_label_is_resolved(self):
        value = [1]
        item = MenuItem(lambda: f"offset {value[0]}", None)
        self.assertEqual(item.label_text(), "offset 1")
        value[0] = 2
        self.assertEqual(item.label_text(), "offset 2")

    def test_plain_label_passes_through(self):
        self.assertEqual(MenuItem("Quit", None).label_text(), "Quit")


if __name__ == "__main__":
    unittest.main()
