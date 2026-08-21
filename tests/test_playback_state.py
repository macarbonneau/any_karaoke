import json
import os
import struct
import tempfile
import time
import unittest
import wave
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from any_karaoke.main import PlayerApp  # noqa: E402
from any_karaoke.song_files import pack_song  # noqa: E402
from any_karaoke.state_objects import NotStartedState, StateObject, find_lyrics_at_time  # noqa: E402

LYRICS = [
    {"text": "first", "start": 1.0, "end": 2.0},
    {"text": "second", "start": 3.0, "end": 4.0},
]


def make_staging(seconds=1, title="Test Song", song_info=None):
    """The loose files that get packed into a song."""
    folder = tempfile.mkdtemp(prefix="staging_")
    for stem in ("music", "vocals"):
        with wave.open(os.path.join(folder, stem + ".wav"), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"".join(struct.pack("<h", 0) for _ in range(22050 * seconds)))

    if song_info is None:
        song_info = {"title": title, "artist": "A", "album": "B", "duration": 10, "lyrics": LYRICS}
    with open(os.path.join(folder, "any_karaoke_file.json"), "w", encoding="utf-8") as f:
        json.dump(song_info, f)
    return folder


def make_song(seconds=1, title="Test Song", song_info=None, file_name=None):
    """A playable .ak song."""
    folder = make_staging(seconds=seconds, title=title, song_info=song_info)
    name = (file_name or title) + ".ak"
    return pack_song(folder, os.path.join(tempfile.mkdtemp(prefix="library_"), name))


def seek(song, stamp):
    """Move a playing song to a point on its timeline.

    update_and_print recomputes time_elapsed from the clock, so setting that attribute
    directly does nothing: the clock is what has to move.
    """
    song.start_time = time.time() - stamp
    song.paused = False
    song.paused_total = 0.0
    song.paused_since = 0.0


class TestPauseClock(unittest.TestCase):
    """The lyric clock must freeze on pause, not just the audio."""

    def setUp(self):
        self.now = 1000.0
        patcher = mock.patch("any_karaoke.state_objects.time.time", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = StateObject({})

    def test_elapsed_advances_normally(self):
        self.now += 5
        self.assertAlmostEqual(self.state.current_elapsed(), 5)

    def test_elapsed_freezes_while_paused(self):
        self.now += 5
        self.state.pause()
        self.now += 100
        self.assertAlmostEqual(self.state.current_elapsed(), 5)

    def test_elapsed_resumes_from_where_it_stopped(self):
        self.now += 5
        self.state.pause()
        self.now += 100
        self.state.resume()
        self.now += 2
        self.assertAlmostEqual(self.state.current_elapsed(), 7)

    def test_repeated_pauses_accumulate(self):
        for _ in range(3):
            self.now += 1
            self.state.pause()
            self.now += 10
            self.state.resume()
        self.assertAlmostEqual(self.state.current_elapsed(), 3)

    def test_toggle_reports_the_new_state(self):
        self.assertTrue(self.state.toggle_pause())
        self.assertFalse(self.state.toggle_pause())

    def test_double_pause_does_not_lose_time(self):
        self.now += 5
        self.state.pause()
        self.state.pause()
        self.now += 10
        self.state.resume()
        self.assertAlmostEqual(self.state.current_elapsed(), 5)


class PlayerAppTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = make_song()

    def setUp(self):
        self.app = PlayerApp(folder_picker=lambda: None)
        self.addCleanup(pygame.quit)


class TestPlayerActions(PlayerAppTestCase):
    def test_starts_with_no_song(self):
        self.assertFalse(self.app.has_song())

    def test_load_song_switches_state_and_toasts_the_title(self):
        self.assertTrue(self.app.load_song(self.song))
        self.assertTrue(self.app.has_song())
        self.assertEqual(self.app.toast.message, "Test Song")

    def test_load_rejects_a_folder_that_is_not_a_song(self):
        self.assertFalse(self.app.load_song(tempfile.mkdtemp()))
        self.assertFalse(self.app.has_song())

    def test_stop_returns_to_the_waiting_state(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        self.assertFalse(self.app.has_song())

    def test_stopped_song_does_not_restart_itself_on_the_next_frame(self):
        self.app.load_song(self.song)
        song = self.app.game_state
        song.update_and_print(self.app.screen)
        song.stop()
        song.update_and_print(self.app.screen)
        self.assertFalse(song.playing)

    def test_quit_clears_running(self):
        self.app.quit()
        self.assertFalse(self.app.running)

    def test_the_transport_does_nothing_useful_without_a_song(self):
        # With nothing loaded and the picker returning None, there is nothing to pause
        self.app.toggle_play_pause()
        self.assertFalse(self.app.is_paused())
        self.assertFalse(self.app.has_song())

    def test_pause_toggles_with_a_song_loaded(self):
        self.app.load_song(self.song)
        self.app.toggle_play_pause()
        self.assertTrue(self.app.is_paused())
        self.app.toggle_play_pause()
        self.assertFalse(self.app.is_paused())

    def test_pausing_before_the_first_frame_survives_playback_starting(self):
        # Regression: the first update starts the song and calls reset_timer, which used to
        # clear the paused flag set a moment earlier
        self.app.load_song(self.song)
        self.app.toggle_play_pause()
        self.assertTrue(self.app.is_paused())

        self.app.game_state.update_and_print(self.app.screen)
        self.assertTrue(self.app.is_paused())
        self.assertTrue(self.app.game_state.playing)

    def test_clock_stays_frozen_across_frames_while_paused(self):
        self.app.load_song(self.song)
        song = self.app.game_state
        song.update_and_print(self.app.screen)
        self.app.toggle_play_pause()
        song.update_and_print(self.app.screen)
        frozen = song.time_elapsed

        # Real delay, so an unfrozen clock would move by an unmistakable amount
        time.sleep(0.05)
        song.update_and_print(self.app.screen)
        self.assertEqual(song.time_elapsed, frozen)

        self.app.toggle_play_pause()
        time.sleep(0.05)
        song.update_and_print(self.app.screen)
        self.assertGreater(song.time_elapsed, frozen)

    def test_restart_resets_the_clock(self):
        self.app.load_song(self.song)
        song = self.app.game_state
        song.update_and_print(self.app.screen)
        song.time_elapsed = 42
        self.app.restart_song()
        self.assertEqual(song.time_elapsed, 0)
        self.assertFalse(song.stopped)


class TestVocalsToggle(PlayerAppTestCase):
    def test_mute_then_restore_returns_the_previous_percentage(self):
        self.app.slider_vocals.set_percent(65)
        self.app.toggle_vocals()
        self.assertEqual(self.app.slider_vocals.slider_value, 0)
        self.assertFalse(self.app.vocals_audible())

        self.app.toggle_vocals()
        self.assertEqual(self.app.slider_vocals.slider_value, 65)
        self.assertTrue(self.app.vocals_audible())

    def test_unmuting_without_a_stored_value_falls_back(self):
        self.app.slider_vocals.set_percent(0)
        self.app.vocals_percent_before_mute = None
        self.app.toggle_vocals()
        self.assertGreater(self.app.slider_vocals.slider_value, 0)

    def test_dragging_the_slider_clears_the_stored_value(self):
        self.app.show_mixer = True
        self.app.toggle_vocals()
        self.app.slider_vocals.update_and_print(self.app.screen)
        rect = self.app.slider_vocals.hit_rect
        with (
            mock.patch("pygame.mouse.get_pressed", return_value=(True, False, False)),
            mock.patch("pygame.mouse.get_pos", return_value=rect.center),
        ):
            self.app.update_sliders()
        self.assertIsNone(self.app.vocals_percent_before_mute)


class TestLyricsNudge(PlayerAppTestCase):
    def test_nudging_shifts_which_line_is_current(self):
        self.app.load_song(self.song)
        song = self.app.game_state
        song.time_elapsed = 2.5
        self.assertIsNone(find_lyrics_at_time(song.lyrics, song.lyrics_time))

        # Pulling the lyrics 0.6s earlier brings the 3.0s line into view
        song.nudge_lyrics(0.6)
        self.assertEqual(find_lyrics_at_time(song.lyrics, song.lyrics_time), "second")

    def test_earlier_and_later_cancel_out(self):
        self.app.load_song(self.song)
        self.app.nudge_lyrics_earlier()
        self.app.nudge_lyrics_later()
        self.assertAlmostEqual(self.app.game_state.lyrics_offset, 0.0)

    def test_offset_label_tracks_the_value(self):
        self.app.load_song(self.song)
        self.app.nudge_lyrics_earlier()
        self.assertIn("+0.10", self.app.lyrics_offset_label())

    def test_offset_label_without_a_song(self):
        self.assertIn("+0.00", self.app.lyrics_offset_label())


class TestSongFormats(PlayerAppTestCase):
    def test_loads_an_ak_file(self):
        self.assertTrue(self.app.load_song(make_song()))
        self.assertTrue(self.app.has_song())
        self.assertEqual(self.app.game_state.title, "Test Song")

    def test_lyrics_survive_the_archive(self):
        self.app.load_song(make_song())
        self.assertEqual([line["text"] for line in self.app.game_state.lyrics], ["first", "second"])

    def test_stems_come_out_playable(self):
        self.app.load_song(make_song())
        self.assertGreater(self.app.game_state.file_music.get_length(), 0)
        self.assertGreater(self.app.game_state.file_vocals.get_length(), 0)

    def test_an_unpacked_folder_is_not_a_song(self):
        self.assertFalse(self.app.load_song(make_staging()))
        self.assertFalse(self.app.has_song())

    def test_an_ak_renders_across_the_timeline(self):
        self.app.load_song(make_song())
        song = self.app.game_state
        song.update_and_print(self.app.screen)  # starts playback, which resets the clock

        seen = []
        for stamp in (0.5, 1.5, 2.5, 3.5, 99.0):
            seek(song, stamp)
            song.update_and_print(self.app.screen)
            seen.append(round(song.time_elapsed))

        # The clock really moved, rather than every frame being drawn at zero
        self.assertEqual(seen, [0, 2, 2, 4, 99])

    def test_a_broken_archive_is_rejected(self):
        broken = os.path.join(tempfile.mkdtemp(), "broken.ak")
        with open(broken, "wb") as f:
            f.write(b"not a zip at all")
        self.assertFalse(self.app.load_song(broken))
        self.assertFalse(self.app.has_song())

    def test_title_falls_back_to_the_file_name(self):
        self.app.load_song(make_song(song_info={"lyrics": []}, file_name="Fallback Name"))
        self.assertEqual(self.app.game_state.title, "Fallback Name")


class TestIdleScreenText(PlayerAppTestCase):
    def test_says_nothing_is_loaded_at_startup(self):
        self.assertEqual(self.app.game_state.text, NotStartedState.NOTHING_LOADED)

    def test_names_the_song_after_stopping(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        self.assertEqual(self.app.game_state.text, "Test Song")

    def test_the_name_survives_a_stop(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        self.assertEqual(self.app.game_state.text, "Test Song")

    def test_the_name_updates_when_another_song_loads(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        other = make_song(song_info={"title": "Another Song", "lyrics": []})
        self.app.load_song(other)
        self.app.stop_song()
        self.assertEqual(self.app.game_state.text, "Another Song")

    def test_a_rejected_path_does_not_change_the_name(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        self.app.load_song(tempfile.mkdtemp())
        self.assertEqual(self.app.game_state.text, "Test Song")

    def test_it_is_read_at_draw_time_not_at_construction(self):
        idle = self.app.game_state
        self.assertEqual(idle.text, NotStartedState.NOTHING_LOADED)
        self.app.game_status["current_title"] = "Later Song"
        self.assertEqual(idle.text, "Later Song")

    def test_falls_back_when_the_song_has_no_title(self):
        untitled = make_song(song_info={"lyrics": []}, file_name="Fallback Name")
        self.app.load_song(untitled)
        self.app.stop_song()
        # PlayingSong falls back to the file name, so something is always shown
        self.assertEqual(self.app.game_state.text, "Fallback Name")


class TestSliderVisibility(PlayerAppTestCase):
    def test_visible_just_after_the_mouse_moves(self):
        self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(400, 300)))
        self.assertTrue(self.app.controls_visible())

    def test_hidden_once_the_mouse_has_been_still(self):
        self.app.last_mouse_move = time.time() - 60
        self.assertFalse(self.app.controls_visible())

    def test_stays_visible_while_a_slider_is_being_dragged(self):
        self.app.last_mouse_move = time.time() - 60
        self.app.slider_vocals.dragging = True
        self.assertTrue(self.app.controls_visible())

    def test_sliders_sit_side_by_side_on_the_left(self):
        # They used to be at 1/3 and 2/3, right on top of the centred lyrics
        music = self.app.slider_music.layout(self.app.screen)
        vocals = self.app.slider_vocals.layout(self.app.screen)
        self.assertLess(music.centerx, self.app.screen.get_width() * 0.25)
        self.assertLess(vocals.centerx, self.app.screen.get_width() * 0.25)
        self.assertLess(music.centerx, vocals.centerx)

    def test_spacing_does_not_change_with_the_window_width(self):
        def gap(width):
            surface = pygame.Surface((width, 600))
            return self.app.slider_vocals.layout(surface).centerx - self.app.slider_music.layout(surface).centerx

        # Normalised positions would pull the pair apart on a wide screen
        self.assertEqual(gap(800), gap(2560))

    def test_labels_have_room_and_do_not_collide(self):
        font = self.app.slider_music.font
        widest = max(font.size(name)[0] for name in ("MUSIC", "VOCALS"))
        music = self.app.slider_music.layout(self.app.screen)
        vocals = self.app.slider_vocals.layout(self.app.screen)
        self.assertGreater(vocals.centerx - music.centerx, widest)
        # and the leftmost label is not clipped by the window edge
        self.assertGreater(music.centerx - font.size("MUSIC")[0] / 2, 0)

    def test_grab_areas_do_not_overlap_at_the_default_size(self):
        self.app.slider_music.update_and_print(self.app.screen)
        self.app.slider_vocals.update_and_print(self.app.screen)
        self.assertFalse(self.app.slider_music.hit_rect.colliderect(self.app.slider_vocals.hit_rect))

    def test_only_one_slider_can_own_a_drag(self):
        self.app.show_mixer = True
        self.app.slider_music.update_and_print(self.app.screen)
        self.app.slider_vocals.update_and_print(self.app.screen)
        self.app.slider_music.dragging = True
        with (
            mock.patch("pygame.mouse.get_pressed", return_value=(True, False, False)),
            mock.patch("pygame.mouse.get_pos", return_value=self.app.slider_vocals.hit_rect.center),
        ):
            self.app.update_sliders()
        self.assertFalse(self.app.slider_vocals.dragging)

    def test_a_drag_cannot_start_on_the_menu_strip(self):
        self.app.show_mixer = True
        self.app.slider_music.update_and_print(self.app.screen)
        top_of_bar = (self.app.slider_music.hit_rect.centerx, 2)
        with (
            mock.patch("pygame.mouse.get_pos", return_value=top_of_bar),
            mock.patch("pygame.mouse.get_pressed", return_value=(True, False, False)),
        ):
            self.app.update_sliders()
        self.assertFalse(self.app.slider_music.dragging)


class TestTransportOverlay(PlayerAppTestCase):
    """Play/pause and the ghost mixer toggle, along the bottom left corner."""

    def click(self, button):
        self.app.layout_transport()
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=button.rect.center)
        return self.app.handle_event(event)

    def test_sits_in_the_bottom_left_corner(self):
        play = self.app.layout_transport()
        height = self.app.screen.get_height()
        self.assertLess(play.left, 60)
        self.assertGreater(play.bottom, height - 80)

    def test_the_mixer_toggle_sits_to_the_right_of_play(self):
        self.app.layout_transport()
        self.assertGreater(self.app.mixer_button.rect.left, self.app.play_button.rect.right - 1)
        self.assertEqual(self.app.mixer_button.rect.top, self.app.play_button.rect.top)

    def test_the_two_buttons_do_not_overlap(self):
        self.app.layout_transport()
        self.assertFalse(self.app.play_button.rect.colliderect(self.app.mixer_button.rect))

    def test_they_follow_the_window_height(self):
        first = self.app.layout_transport().top
        self.app.screen = pygame.display.set_mode((800, 900))
        self.assertGreater(self.app.layout_transport().top, first)

    # --- transport
    def test_shows_play_until_a_song_runs(self):
        self.assertFalse(self.app.play_button.showing_pause)
        self.app.load_song(self.song)
        self.assertTrue(self.app.play_button.showing_pause)

    def test_shows_play_again_once_paused(self):
        self.app.load_song(self.song)
        self.app.toggle_play_pause()
        self.assertFalse(self.app.play_button.showing_pause)

    def test_clicking_pauses_and_resumes_without_stopping(self):
        self.app.load_song(self.song)
        self.assertTrue(self.click(self.app.play_button))
        self.assertTrue(self.app.is_paused())
        self.assertTrue(self.app.has_song())  # paused, not stopped

        self.click(self.app.play_button)
        self.assertFalse(self.app.is_paused())
        self.assertTrue(self.app.has_song())

    def test_space_does_the_same_as_the_button(self):
        self.app.load_song(self.song)
        space = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0)
        self.app.handle_event(space)
        self.assertTrue(self.app.is_paused())
        self.app.handle_event(space)
        self.assertFalse(self.app.is_paused())

    def test_clicking_play_reloads_the_last_song_after_a_stop(self):
        self.app.load_song(self.song)
        self.app.stop_song()
        self.assertFalse(self.app.has_song())
        self.click(self.app.play_button)
        self.assertTrue(self.app.has_song())

    def test_clicking_play_with_nothing_loaded_asks_for_a_song(self):
        asked = []
        self.app.folder_picker = lambda: asked.append(True)
        self.click(self.app.play_button)
        self.assertEqual(len(asked), 1)

    # --- mixer toggle
    def test_the_faders_are_hidden_to_start_with(self):
        self.assertFalse(self.app.show_mixer)
        self.assertFalse(self.app.mixer_visible())

    def test_clicking_the_ghost_button_reveals_the_faders(self):
        self.assertTrue(self.click(self.app.mixer_button))
        self.assertTrue(self.app.show_mixer)
        self.assertTrue(self.app.mixer_visible())

    def test_clicking_it_again_hides_them(self):
        self.click(self.app.mixer_button)
        self.click(self.app.mixer_button)
        self.assertFalse(self.app.show_mixer)

    def test_the_x_shortcut_does_the_same(self):
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x, mod=0))
        self.assertTrue(self.app.show_mixer)

    def test_the_faders_still_fade_with_the_mouse(self):
        self.app.show_mixer = True
        self.app.last_mouse_move = time.time() - 60
        self.assertFalse(self.app.mixer_visible())
        self.assertTrue(self.app.show_mixer)  # still toggled on, just not on screen

    def test_a_fader_cannot_be_dragged_while_hidden(self):
        self.app.slider_music.update_and_print(self.app.screen)
        with (
            mock.patch("pygame.mouse.get_pressed", return_value=(True, False, False)),
            mock.patch("pygame.mouse.get_pos", return_value=self.app.slider_music.hit_rect.center),
        ):
            self.app.update_sliders()
        self.assertFalse(self.app.slider_music.dragging)

    # --- hidden overlay swallows nothing
    def test_a_click_while_hidden_only_reveals_the_overlay(self):
        self.app.load_song(self.song)
        self.app.layout_transport()
        self.app.last_mouse_move = time.time() - 60
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=self.app.play_button.rect.center)
        self.assertFalse(self.app.handle_event(event))
        self.assertFalse(self.app.is_paused())

    def test_clicking_elsewhere_does_nothing(self):
        self.app.load_song(self.song)
        self.app.layout_transport()
        event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(700, 300))
        self.assertFalse(self.app.handle_event(event))
        self.assertFalse(self.app.is_paused())


class TestOpenManager(PlayerAppTestCase):
    def test_launches_the_manager_module(self):
        with mock.patch("any_karaoke.main.launch_module") as launch:
            launch.return_value = mock.Mock(poll=lambda: None)
            self.app.open_manager()
        launch.assert_called_once_with("any_karaoke.manager")
        self.assertIn("manager", self.app.toast.message)

    def test_does_not_launch_a_second_manager_while_one_is_open(self):
        still_running = mock.Mock(poll=lambda: None)
        with mock.patch("any_karaoke.main.launch_module", return_value=still_running) as launch:
            self.app.open_manager()
            self.app.open_manager()
            self.assertEqual(launch.call_count, 1)
        self.assertEqual(self.app.toast.message, "manager already open")

    def test_launches_again_once_the_previous_one_exited(self):
        exited = mock.Mock(poll=lambda: 0)
        self.app.manager_process = exited
        with mock.patch("any_karaoke.main.launch_module", return_value=exited) as launch:
            self.app.open_manager()
        self.assertEqual(launch.call_count, 1)

    def test_ctrl_m_reaches_the_action(self):
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=pygame.KMOD_CTRL)
        with mock.patch("any_karaoke.main.launch_module") as launch:
            launch.return_value = mock.Mock(poll=lambda: None)
            self.assertTrue(self.app.handle_event(event))
        launch.assert_called_once()


class TestMenuWiring(PlayerAppTestCase):
    def test_playback_items_are_disabled_until_a_song_loads(self):
        restart = self.app.menu_bar.menus[1].items[1]
        self.assertEqual(restart.label_text(), "Restart song")
        self.assertFalse(restart.is_enabled())
        self.app.load_song(self.song)
        self.assertTrue(restart.is_enabled())

    def test_play_pause_is_always_available(self):
        # It loads the last song, or asks for one, when nothing is playing
        self.assertTrue(self.app.menu_bar.menus[1].items[0].is_enabled())

    def test_every_shortcut_is_unique(self):
        seen = []
        for menu in self.app.menu_bar.menus:
            for item in menu.items:
                if item.key is not None:
                    seen.append((item.key, item.mods))
        self.assertEqual(len(seen), len(set(seen)))

    def test_ctrl_q_quits_through_the_menu_bar(self):
        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=pygame.KMOD_CTRL)
        self.app.handle_event(event)
        self.assertFalse(self.app.running)


if __name__ == "__main__":
    unittest.main()
