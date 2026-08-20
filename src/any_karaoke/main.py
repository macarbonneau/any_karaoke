import argparse
import sys
from tkinter import Tk, filedialog

import pygame

from any_karaoke.display_object import VolumeSlider
from any_karaoke.state_objects import NotStartedState, PlayingSong
from any_karaoke.game_config import BACK_COLOR, FPS
from any_karaoke.song_files import is_karaoke_folder, missing_parts


def ask_for_karaoke_folder():
    root = Tk()
    root.withdraw()  # Hide the main window
    try:
        return filedialog.askdirectory() or None
    finally:
        root.destroy()


def main(song_folder=None):
    # ========= Initialize Pygame =========
    pygame.init()
    pygame.mixer.init()
    channel_music = pygame.mixer.Channel(0)
    channel_vocals = pygame.mixer.Channel(1)

    # Create the game window (fullscreen)
    # screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen = pygame.display.set_mode((800, 600), pygame.RESIZABLE)
    pygame.display.set_caption("Any Karaoke")
    clock = pygame.time.Clock()

    game_status = {
        "current_song": None,
        "next_song": None,
        "channel_music": channel_music,
        "channel_vocals": channel_vocals,
    }
    current_game_state = NotStartedState(game_status)

    # Boot straight into a song when one was given on the command line
    if song_folder:
        if is_karaoke_folder(song_folder):
            game_status["current_song"] = song_folder
            current_game_state = PlayingSong(game_status)
        else:
            print(f"'{song_folder}' is not a karaoke folder, missing {missing_parts(song_folder)}")

    slider_music = VolumeSlider("music", 1 / 3.0, 0.5)
    slider_vocals = VolumeSlider("vocals", 2.0 / 3, 0.5, slider_value=10)

    # Keep the channels in sync with what the sliders show
    channel_music.set_volume(slider_music.volume)
    channel_vocals.set_volume(slider_vocals.volume)

    # ========= Main Game Loop =========
    while True:
        # ========= Handle Events =========
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and pygame.key.get_mods() & pygame.KMOD_CTRL:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_o and pygame.key.get_mods() & pygame.KMOD_CTRL:
                    dir_path = ask_for_karaoke_folder()
                    if not is_karaoke_folder(dir_path):
                        if dir_path:
                            print(f"'{dir_path}' is not a karaoke folder, missing {missing_parts(dir_path)}")
                        continue
                    channel_music.stop()
                    channel_vocals.stop()
                    game_status["current_song"] = dir_path
                    current_game_state = PlayingSong(game_status)

        # Get mouse position
        mouse_x, mouse_y = pygame.mouse.get_pos()

        # Check for slider interactions
        if pygame.mouse.get_pressed()[0]:
            music_volume = slider_music.handle_drag(mouse_x, mouse_y)
            if music_volume is not None:
                channel_music.set_volume(music_volume)

            vocals_volume = slider_vocals.handle_drag(mouse_x, mouse_y)
            if vocals_volume is not None:
                channel_vocals.set_volume(vocals_volume)

        # Clear the screen
        screen.fill(BACK_COLOR)

        # ========= Game State =========
        current_game_state.update_and_print(screen)

        # Check if the mouse is over the game window
        if (
            screen.get_width() * 0.1 < mouse_x <= screen.get_width() * 0.9
            and screen.get_height() * 0.1 < mouse_y <= screen.get_height() * 0.9
        ):
            slider_music.update_and_print(screen)
            slider_vocals.update_and_print(screen)

        # Update the display
        pygame.display.flip()
        # Cap the frame rate
        clock.tick(FPS)


def cli():
    parser = argparse.ArgumentParser(description="Play an Any Karaoke song folder.")
    parser.add_argument(
        "song_folder",
        nargs="?",
        help="Karaoke folder to open on start. Without it, use Ctrl+O in the window.",
    )
    args = parser.parse_args()
    main(song_folder=args.song_folder)


if __name__ == "__main__":
    cli()
