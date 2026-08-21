import time

import pygame

from any_karaoke.display_object import Announce, LyricsDisplay
from any_karaoke.game_config import DEFAULT_FONT_COLOR, LYRICS_TIME_OFFSET
from any_karaoke.song_files import open_stem, read_lyrics_alignment, read_song_info, song_display_name


# ================================================
# Lyric lookups (pure functions, lyrics are ordered by start time)
# ================================================
def choose_lyrics(song_path, song_info):
    """Prefer the timed reference lyrics over the ASR transcription.

    The reference lyrics are the real words, where the transcription guesses ("Maybe
    that's a fact" for "Baby that's a fact"), and they come in short singable lines
    rather than the aligner's long segments. Songs extracted before lyrics_alignment.json
    existed, or whose matching found nothing, fall back to the transcription.
    """
    scaffold = read_lyrics_alignment(song_path)
    if scaffold:
        timed = [
            line for line in scaffold.get("lines", []) if line.get("start") is not None and line.get("end") is not None
        ]
        if timed:
            return timed

    return song_info.get("lyrics", [])


def find_line_at_time(lyrics, time_stamp):
    """The whole line record being sung, or None between lines."""
    for line in lyrics:
        if line["start"] <= time_stamp <= line["end"]:
            return line
    return None


def find_lyrics_at_time(lyrics, time_stamp):
    line = find_line_at_time(lyrics, time_stamp)
    return line["text"].strip() if line else None


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
        self.game_status = game_status
        self.paused = False
        self.paused_since = 0.0
        self.paused_total = 0.0
        self.reset_timer()

    def current_elapsed(self):
        """Seconds of playback so far, with any paused time removed."""
        reference = self.paused_since if self.paused else time.time()
        return reference - self.start_time - self.paused_total

    def update_and_print(self, screen):
        self.time_elapsed = self.current_elapsed()

    def reset_timer(self):
        self.start_time = time.time()
        self.time_elapsed = 0
        self.paused = False
        self.paused_since = 0.0
        self.paused_total = 0.0

    def pause(self):
        if not self.paused:
            self.paused = True
            self.paused_since = time.time()

    def resume(self):
        if self.paused:
            self.paused_total += time.time() - self.paused_since
            self.paused = False

    def toggle_pause(self):
        self.resume() if self.paused else self.pause()
        return self.paused


class NotStartedState(StateObject):
    """Idle screen. Names the loaded song, or says there is nothing loaded yet."""

    NOTHING_LOADED = "no song loaded"

    def __init__(self, game_status) -> None:
        super().__init__(game_status)
        self.message = Announce()

    @property
    def text(self):
        # Read at draw time, so stopping a song keeps showing which one it was
        return self.game_status.get("current_title") or self.NOTHING_LOADED

    def update_and_print(self, screen):
        super().update_and_print(screen)
        self.message.update_and_print(screen, self.text, color=DEFAULT_FONT_COLOR)


class PlayingSong(StateObject):
    def __init__(self, game_status, nb_past_lines=5, nb_next_lines=6) -> None:
        super().__init__(game_status)
        song_path = game_status["current_song"]
        song_info = read_song_info(song_path)
        self.title = song_info.get("title") or song_display_name(song_path)
        self.lyrics = choose_lyrics(song_path, song_info)
        self.nb_past_lines = nb_past_lines
        self.nb_next_lines = nb_next_lines
        self.displayed_lyrics = LyricsDisplay()
        # Starts from the config default but is adjustable at runtime from the View menu
        self.lyrics_offset = LYRICS_TIME_OFFSET

        # Stems may be mp3 or wav, inside a .ak archive or a legacy folder
        with open_stem(song_path, "music") as handle:
            self.file_music = pygame.mixer.Sound(file=handle)
        with open_stem(song_path, "vocals") as handle:
            self.file_vocals = pygame.mixer.Sound(file=handle)
        self.playing = False
        # Set by stop(), so update_and_print does not immediately start the song again
        self.stopped = False

    @property
    def lyrics_time(self):
        return self.time_elapsed + self.lyrics_offset

    @property
    def channels(self):
        return (self.game_status["channel_music"], self.game_status["channel_vocals"])

    def nudge_lyrics(self, delta):
        self.lyrics_offset += delta
        return self.lyrics_offset

    def pause(self):
        super().pause()
        for channel in self.channels:
            channel.pause()

    def resume(self):
        super().resume()
        for channel in self.channels:
            channel.unpause()

    def restart(self):
        """Play the song again from the beginning."""
        for channel in self.channels:
            channel.stop()
        self.playing = False
        self.stopped = False
        self.reset_timer()

    def stop(self):
        for channel in self.channels:
            channel.stop()
        self.playing = False
        self.stopped = True

    def update_and_print(self, screen):
        if not self.playing and not self.stopped:
            # reset_timer clears the pause accounting, so a pause requested before the
            # first frame has to be reapplied once the channels are actually running
            was_paused = self.paused

            self.game_status["channel_music"].play(self.file_music)
            self.game_status["channel_vocals"].play(self.file_vocals)
            self.playing = True
            self.reset_timer()

            if was_paused:
                self.pause()

        super().update_and_print(screen)

        time_stamp = self.lyrics_time
        past_lines = find_past_lines(self.lyrics, time_stamp, self.nb_past_lines)
        current = find_line_at_time(self.lyrics, time_stamp)
        next_lines = find_next_lines(self.lyrics, time_stamp, self.nb_next_lines)

        self.displayed_lyrics.update_and_print(
            screen,
            current["text"].strip() if current else None,
            past_lines,
            next_lines,
            # Word timings drive the karaoke highlight when the song has them
            current_words=(current or {}).get("words"),
            time_stamp=time_stamp,
        )
