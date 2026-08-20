import time
import json

import pygame

from any_karaoke.display_object import Announce, LyricsDisplay
from any_karaoke.game_config import DEFAULT_FONT_COLOR, LYRICS_TIME_OFFSET
from any_karaoke.song_files import find_stem, song_info_path


# ================================================
# Lyric lookups (pure functions, lyrics are ordered by start time)
# ================================================
def find_lyrics_at_time(lyrics, time_stamp):
    for line in lyrics:
        if line["start"] <= time_stamp <= line["end"]:
            return line["text"].strip()
    return None


def find_next_lines(lyrics, time_stamp, nb_lines=1):
    coming_lines = []
    for line in lyrics:
        if line["start"] >= time_stamp:
            coming_lines.append(line["text"].strip())
            if len(coming_lines) >= nb_lines:
                break
    return coming_lines


def find_past_lines(lyrics, time_stamp, nb_lines=None):
    past_lines = [line["text"].strip() for line in lyrics if line["end"] < time_stamp]
    if nb_lines:
        # keep the most recent lines, not the oldest ones
        past_lines = past_lines[-nb_lines:]
    return past_lines


# ================================================
# Game states
# ================================================
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
        self.message.update_and_print(screen, "waiting to start", color=DEFAULT_FONT_COLOR)


class PlayingSong(StateObject):
    def __init__(self, game_status, nb_past_lines=5, nb_next_lines=6) -> None:
        super().__init__(game_status)
        song_dir = game_status["current_song"]
        with open(song_info_path(song_dir), "r", encoding="utf-8") as f:
            song_info = json.load(f)
        self.lyrics = song_info.get("lyrics", [])
        self.nb_past_lines = nb_past_lines
        self.nb_next_lines = nb_next_lines
        self.displayed_text = Announce()
        self.displayed_lyrics = LyricsDisplay()

        # Load audio files into mixer.Sound objects. Stems may be mp3 or wav.
        self.file_music = pygame.mixer.Sound(find_stem(song_dir, "music"))
        self.file_vocals = pygame.mixer.Sound(find_stem(song_dir, "vocals"))
        self.playing = False

    @property
    def lyrics_time(self):
        return self.time_elapsed + LYRICS_TIME_OFFSET

    def update_and_print(self, screen):
        super().update_and_print(screen)
        if not self.playing:
            # Play the sounds
            self.game_status["channel_music"].play(self.file_music)
            self.game_status["channel_vocals"].play(self.file_vocals)
            self.playing = True
            self.reset_timer()

        time_stamp = self.lyrics_time
        past_lines = find_past_lines(self.lyrics, time_stamp, self.nb_past_lines)
        current_line = find_lyrics_at_time(self.lyrics, time_stamp)
        next_lines = find_next_lines(self.lyrics, time_stamp, self.nb_next_lines)

        self.displayed_lyrics.update_and_print(screen, current_line, past_lines, next_lines)
