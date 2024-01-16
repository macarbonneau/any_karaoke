from calendar import c
import os, sys
from any_karaoke.display_object import VolumeSlider
import pygame
from pygame.locals import QUIT
import os
from tkinter import Tk, filedialog

from any_karaoke.state_objects import NotStartedState, PlayingSong
from any_karaoke.game_config import (
    BACK_COLOR,
    DEFAULT_FONT_COLOR,
    DEFAULT_OBJECT_COLOR,
    FPS,
)


# Load audio files
def load_audio():
    root = Tk()
    root.withdraw()  # Hide the main window

    file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3;*.wav")])

    if file_path:
        return file_path
    else:
        return None


def load_any_karaoke_file():
    root = Tk()
    root.withdraw()  # Hide the main window

    dir_path = filedialog.askdirectory()

    if dir_path:
        return dir_path
    else:
        return None


def load_karaoke_audio(dir_path, channel1, channel2):
    music_path = os.path.join(dir_path, "music.wav")
    vox_path = os.path.join(dir_path, "vocals.wav")

    if not music_path or not vox_path:
        print("This is not a correct folder")
        return
    # Load audio files into mixer.Sound objects
    file1 = pygame.mixer.Sound(music_path)
    file2 = pygame.mixer.Sound(vox_path)

    # Set initial volumes
    channel1.set_volume(0.5)
    channel2.set_volume(0.5)

    # Play the sounds
    channel1.play(file1, loops=-1)
    channel2.play(file2, loops=-1)


def main():
    # ========= Initialize Pygame =========
    pygame.init()
    pygame.mixer.init()
    channel_music = pygame.mixer.Channel(0)
    channel_vocals = pygame.mixer.Channel(1)

    # Create the game window (fullscreen)
    # screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen = pygame.display.set_mode((600, 600), pygame.RESIZABLE)
    pygame.display.set_caption("Any Karaoke")
    clock = pygame.time.Clock()

    game_status = {
        "current_song": None,
        "next_song": None,
        "channel_music": channel_music,
        "channel_vocals": channel_vocals,
    }
    current_game_state = NotStartedState(game_status)

    slider_music = VolumeSlider("music", 100, 200)
    slider_vocals = VolumeSlider("vocals", 300, 200, slider_value=10)

    # ========= Main Game Loop =========

    # Game loop
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
                    game_status["current_song"] = load_any_karaoke_file()
                    current_game_state = PlayingSong(game_status)

        # Get mouse position
        mouse_x, mouse_y = pygame.mouse.get_pos()

        # Check for slider interactions
        if pygame.mouse.get_pressed()[0]:
            channel_music.set_volume(slider_music.set_volume(mouse_x, mouse_y))
            channel_vocals.set_volume(slider_vocals.set_volume(mouse_x, mouse_y))

        # Clear the screen
        screen.fill(BACK_COLOR)

        # ========= Game State =========
        current_game_state.update_and_print(screen)

        # Update the display
        pygame.display.flip()
        # Cap the frame rate
        clock.tick(FPS)


if __name__ == "__main__":
    main()
