import os
import time
import random
import json

import pygame
from any_karaoke.display_object import Announce, VolumeSlider, LyricsDisplay
from any_karaoke.game_config import DEFAULT_FONT_COLOR


class StateObject:
    def __init__(self, game_status) -> None:
        self.start_time = time.time()
        self.time_elapsed = 0
        self.game_status = game_status

    def update_and_print(self, screen):
        self.time_elapsed = time.time() - self.start_time

    def reset_timer(self):
        self.start_time = time.time()
        self.time_elapsed = 0


class NotStartedState(StateObject):
    def __init__(self, game_status) -> None:
        super().__init__(game_status)
        self.message = Announce()

    def update_and_print(self, screen):
        super().update_and_print(screen)
        self.message.update_and_print(
            screen, "waiting to start", color=DEFAULT_FONT_COLOR
        )


class PlayingSong(StateObject):
    def __init__(self, game_status) -> None:
        super().__init__(game_status)
        with open(
            os.path.join(game_status["current_song"], "any_karaoke_file.json"), "r"
        ) as f:
            song_info = json.load(f)
        self.lyrics = song_info["lyrics"]
        self.displayed_text = Announce()
        self.displayed_lyrics = LyricsDisplay()

        # Load audio files into mixer.Sound objects
        self.file_music = pygame.mixer.Sound(
            os.path.join(game_status["current_song"], "music.wav")
        )
        self.file_vocals = pygame.mixer.Sound(
            os.path.join(game_status["current_song"], "vocals.wav")
        )
        self.playing = False

    def update_and_print(self, screen):
        super().update_and_print(screen)
        if not self.playing:
            # Play the sounds
            self.game_status["channel_music"].play(self.file_music)
            self.game_status["channel_vocals"].play(self.file_vocals)
            self.playing = True
            self.reset_timer()

        past_lines = self.find_past_lines(5)
        current_line = self.find_lyrics_at_time(self.time_elapsed)
        next_lines = self.find_next_several_lines(nb_lines=6)

        self.displayed_lyrics.update_and_print(
            screen, current_line, past_lines, next_lines
        )

    def find_lyrics_at_time(self, time_stamp):
        for i in self.lyrics:
            if time_stamp >= i["start"]:
                if time_stamp <= i["end"]:
                    return i["text"].strip()
        return None

    def find_next_several_lines(self, time_stamp=None, nb_lines=1):
        if not time_stamp:
            time_stamp = self.time_elapsed
        coming_lines = []
        for i in self.lyrics:
            if i["start"] >= time_stamp:
                if len(coming_lines) < nb_lines:
                    coming_lines.append(i["text"].strip())

        return coming_lines

    def find_next_line(self):
        lines = self.find_next_several_lines()
        if lines:
            return lines[0]
        else:
            return None

    def find_past_lines(self, nb_lines=None):
        past_lines = []
        time_stamp = self.time_elapsed

        for i in self.lyrics:
            if i["end"] < time_stamp:
                past_lines.append(i["text"].strip())
        if nb_lines:
            if len(past_lines) > nb_lines:
                past_lines = past_lines[:-nb_lines]

        return past_lines
