import argparse
import sys
import time
from tkinter import Tk, filedialog

import pygame

from any_karaoke.assets import icon_path
from any_karaoke.display_object import PlayStopButton, Toast, VolumeSlider
from any_karaoke.game_config import (
    BACK_COLOR,
    FPS,
    LYRICS_NUDGE_STEP,
    BUTTON_TOP_GAP,
    MENU_BAR_HEIGHT,
    MIXER_LEFT,
    MIXER_SPACING,
    SLIDER_CENTER_Y,
    SLIDER_IDLE_SECONDS,
    SLIDER_MUSIC_ACCENT,
    SLIDER_VOCALS_ACCENT,
)
from any_karaoke.menu import Menu, MenuBar, MenuItem
from any_karaoke.processes import is_running, launch_module
from any_karaoke.song_files import AK_EXTENSION, is_song, missing_parts
from any_karaoke.state_objects import NotStartedState, PlayingSong

WINDOWED_SIZE = (800, 600)
MANAGER_MODULE = "any_karaoke.manager"


def set_window_icon():
    """Put the logo in the title bar and the taskbar. Silently skipped if it is missing."""
    path = icon_path()
    if not path:
        return False

    try:
        pygame.display.set_icon(pygame.image.load(path))
        return True
    except pygame.error:
        return False


def _with_hidden_root(action):
    root = Tk()
    root.withdraw()  # Hide the main window
    try:
        return action() or None
    finally:
        root.destroy()


def ask_for_song():
    return _with_hidden_root(
        lambda: filedialog.askopenfilename(
            title="Open a karaoke song",
            filetypes=[("Any Karaoke song", f"*{AK_EXTENSION}"), ("All files", "*.*")],
        )
    )


class PlayerApp:
    """Owns the window, the mixer channels and the current game state.

    Menu items bind straight to the action methods, so the menu, the keyboard shortcuts
    and the loop all drive the same code.
    """

    def __init__(self, song_folder=None, folder_picker=ask_for_song):
        pygame.init()
        pygame.mixer.init()

        self.channel_music = pygame.mixer.Channel(0)
        self.channel_vocals = pygame.mixer.Channel(1)
        self.folder_picker = folder_picker

        self.windowed_size = WINDOWED_SIZE
        self.fullscreen = False
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        pygame.display.set_caption("Any Karaoke")
        set_window_icon()
        self.clock = pygame.time.Clock()
        self.running = True

        self.game_status = {
            "current_song": None,
            "current_title": None,
            "channel_music": self.channel_music,
            "channel_vocals": self.channel_vocals,
        }
        self.game_state = NotStartedState(self.game_status)

        self.slider_music = VolumeSlider("music", 0, SLIDER_CENTER_Y, accent=SLIDER_MUSIC_ACCENT, pixel_x=MIXER_LEFT)
        self.slider_vocals = VolumeSlider(
            "vocals",
            0,
            SLIDER_CENTER_Y,
            accent=SLIDER_VOCALS_ACCENT,
            slider_value=10,
            pixel_x=MIXER_LEFT + MIXER_SPACING,
        )
        self.play_button = PlayStopButton(self.has_song)
        self.last_mouse_move = time.time()
        # Keep the channels in sync with what the sliders show
        self.channel_music.set_volume(self.slider_music.volume)
        self.channel_vocals.set_volume(self.slider_vocals.volume)
        self.vocals_percent_before_mute = None
        self.manager_process = None

        self.toast = Toast()
        self.menu_bar = MenuBar(self.build_menus())

        if song_folder:
            self.load_song(song_folder)

    # ================================================
    # Menu definition
    # ================================================
    def build_menus(self):
        has_song = self.has_song

        return [
            Menu(
                "File",
                [
                    MenuItem(
                        "Open song",
                        self.open_song,
                        pygame.K_o,
                        pygame.KMOD_CTRL,
                        "Ctrl+O",
                    ),
                    MenuItem(
                        "Manage library",
                        self.open_manager,
                        pygame.K_m,
                        pygame.KMOD_CTRL,
                        "Ctrl+M",
                    ),
                    MenuItem("Quit", self.quit, pygame.K_q, pygame.KMOD_CTRL, "Ctrl+Q"),
                ],
            ),
            Menu(
                "Playback",
                [
                    MenuItem(
                        "Pause / Resume",
                        self.toggle_pause,
                        pygame.K_SPACE,
                        shortcut_text="Space",
                        enabled=has_song,
                        checked=self.is_paused,
                    ),
                    MenuItem("Restart song", self.restart_song, pygame.K_r, shortcut_text="R", enabled=has_song),
                    MenuItem("Stop", self.stop_song, pygame.K_s, shortcut_text="S", enabled=has_song),
                    MenuItem(
                        "Guide vocals",
                        self.toggle_vocals,
                        pygame.K_v,
                        shortcut_text="V",
                        checked=self.vocals_audible,
                    ),
                ],
            ),
            Menu(
                "View",
                [
                    MenuItem(
                        "Fullscreen",
                        self.toggle_fullscreen,
                        pygame.K_F11,
                        shortcut_text="F11",
                        checked=lambda: self.fullscreen,
                    ),
                    MenuItem(
                        "Lyrics earlier",
                        self.nudge_lyrics_earlier,
                        pygame.K_LEFTBRACKET,
                        shortcut_text="[",
                        enabled=has_song,
                    ),
                    MenuItem(
                        "Lyrics later",
                        self.nudge_lyrics_later,
                        pygame.K_RIGHTBRACKET,
                        shortcut_text="]",
                        enabled=has_song,
                    ),
                    # Read only row showing where the offset currently sits
                    MenuItem(self.lyrics_offset_label, None, enabled=lambda: False),
                ],
            ),
        ]

    # ================================================
    # State helpers
    # ================================================
    def has_song(self):
        return isinstance(self.game_state, PlayingSong)

    def is_paused(self):
        return self.has_song() and self.game_state.paused

    def vocals_audible(self):
        return self.slider_vocals.slider_value > 0

    def lyrics_offset_label(self):
        offset = self.game_state.lyrics_offset if self.has_song() else 0.0
        return f"offset {offset:+.2f}s"

    # ================================================
    # Actions
    # ================================================
    def load_song(self, path):
        if not is_song(path):
            message = f"not a karaoke song, missing {', '.join(missing_parts(path))}"
            print(f"'{path}': {message}")
            self.toast.show(message)
            return False

        self.channel_music.stop()
        self.channel_vocals.stop()
        self.game_status["current_song"] = path
        self.game_state = PlayingSong(self.game_status)
        # Kept so the idle screen can still name the song after it is stopped
        self.game_status["current_title"] = self.game_state.title
        self.toast.show(self.game_state.title)
        return True

    def open_song(self):
        chosen = self.folder_picker()
        if chosen:
            self.load_song(chosen)

    def open_manager(self):
        """Start the manager window in its own process, at most one at a time."""
        if is_running(self.manager_process):
            self.toast.show("manager already open")
            return

        self.manager_process = launch_module(MANAGER_MODULE)
        self.toast.show("opening the manager")

    def quit(self):
        self.running = False

    def toggle_pause(self):
        if not self.has_song():
            return
        self.toast.show("paused" if self.game_state.toggle_pause() else "resumed")

    def restart_song(self):
        if self.has_song():
            self.game_state.restart()
            self.toast.show("restarted")

    def stop_song(self):
        if self.has_song():
            self.game_state.stop()
            self.game_state = NotStartedState(self.game_status)
            self.toast.show("stopped")

    def toggle_play_stop(self):
        """Transport button: stop what is playing, or start the last song again."""
        if self.has_song():
            self.stop_song()
            return

        last_song = self.game_status.get("current_song")
        if last_song:
            self.load_song(last_song)
        else:
            # Nothing has been loaded yet, so ask for something to play
            self.open_song()

    def toggle_vocals(self):
        """Mute or restore the guide vocal, moving the slider so the display stays honest."""
        if self.vocals_audible():
            self.vocals_percent_before_mute = self.slider_vocals.slider_value
            self.channel_vocals.set_volume(self.slider_vocals.set_percent(0))
            self.toast.show("guide vocals off")
        else:
            restored = self.vocals_percent_before_mute
            if not restored:
                restored = 10
            self.channel_vocals.set_volume(self.slider_vocals.set_percent(restored))
            self.toast.show(f"guide vocals on ({int(self.slider_vocals.slider_value)}%)")

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.windowed_size = self.screen.get_size()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.toast.show("fullscreen" if self.fullscreen else "windowed")

    def nudge_lyrics_earlier(self):
        self._nudge(LYRICS_NUDGE_STEP)

    def nudge_lyrics_later(self):
        self._nudge(-LYRICS_NUDGE_STEP)

    def _nudge(self, delta):
        if self.has_song():
            self.toast.show(f"lyrics offset {self.game_state.nudge_lyrics(delta):+.2f}s")

    # ================================================
    # Loop
    # ================================================
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return True

        # Read visibility before the timer is refreshed, otherwise this very event would
        # reveal the mixer and immediately press a button that was not on screen
        mixer_was_visible = self.sliders_visible()
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            self.last_mouse_move = time.time()

        if event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.windowed_size = (event.w, event.h)

        # The menu bar gets first refusal, so its clicks never reach the mixer
        if self.menu_bar.handle_event(event, self.screen.get_width()):
            return True

        clicked = event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        if clicked and mixer_was_visible and self.play_button.hit(event.pos):
            self.toggle_play_stop()
            return True

        return False

    def update_sliders(self):
        mouse_pos = pygame.mouse.get_pos()
        blocked = mouse_pos[1] <= MENU_BAR_HEIGHT or self.menu_bar.is_open()
        # A started drag keeps going even over the menu strip, it just cannot start there
        pressed = pygame.mouse.get_pressed()[0] and not blocked

        music_volume = self.slider_music.update_drag(mouse_pos, pressed)
        if music_volume is not None:
            self.channel_music.set_volume(music_volume)

        # The two sit close together, so only one can own a drag at a time
        vocals_volume = self.slider_vocals.update_drag(mouse_pos, pressed and not self.slider_music.dragging)
        if vocals_volume is not None:
            self.channel_vocals.set_volume(vocals_volume)
            self.vocals_percent_before_mute = None

    def layout_play_button(self):
        """Centre the button under the pair of sliders, below their percentage labels."""
        tracks = (self.slider_music.track_rect, self.slider_vocals.track_rect)
        centre_x = sum(track.centerx for track in tracks) / 2
        return self.play_button.layout(centre_x, max(track.bottom for track in tracks) + BUTTON_TOP_GAP)

    def sliders_visible(self):
        """Shown while the mouse is being used, and for as long as one is being dragged.

        Nobody moves the mouse while singing, so the mixer gets out of the way on its own.
        """
        if self.slider_music.dragging or self.slider_vocals.dragging:
            return True
        return (time.time() - self.last_mouse_move) < SLIDER_IDLE_SECONDS

    def draw(self):
        screen = self.screen

        screen.fill(BACK_COLOR)
        self.game_state.update_and_print(screen)

        if self.sliders_visible():
            self.slider_music.update_and_print(screen)
            self.slider_vocals.update_and_print(screen)
            self.layout_play_button()
            self.play_button.update_and_print(screen)

        self.toast.update_and_print(screen)
        self.menu_bar.update_and_print(screen)
        pygame.display.flip()

    def tick(self):
        for event in pygame.event.get():
            self.handle_event(event)
        self.update_sliders()
        self.draw()
        self.clock.tick(FPS)

    def run(self):
        while self.running:
            self.tick()
        pygame.quit()


def main(song_folder=None):
    PlayerApp(song_folder=song_folder).run()


def cli():
    parser = argparse.ArgumentParser(description="Play an Any Karaoke song folder.")
    parser.add_argument(
        "song_folder",
        nargs="?",
        help="Karaoke folder to open on start. Without it, use Ctrl+O in the window.",
    )
    args = parser.parse_args()
    main(song_folder=args.song_folder)
    sys.exit(0)


if __name__ == "__main__":
    cli()
