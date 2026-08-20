import argparse
import json
import os
import re
from datetime import datetime

import eyed3
import requests

from any_karaoke.game_config import (
    MODEL_CACHE,
    EXTRACT_MODEL,
    WHISPER_MODEL,
    WHISPER_MODEL_CHOICES,
    OUTPUT_AUDIO_FORMAT,
    MP3_BITRATE,
)
from any_karaoke.song_files import SONG_INFO_FILE

# torch, whisperx and demucs come from the optional "extract" extra and are imported
# lazily so the rest of this module stays usable without them.

INVALID_PATH_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Stage names reported through ProgressReporter, in the order they happen
STAGE_TAGS = "reading tags"
STAGE_SEPARATE = "separating vocals"
STAGE_LYRICS = "fetching lyrics"
STAGE_TRANSCRIBE = "transcribing"
STAGE_ALIGN = "aligning"
STAGE_WRITE = "writing"


class ExtractionCancelled(Exception):
    """Raised when the caller asks for an in-progress extraction to stop."""


class ProgressReporter:
    """Receives progress from the extraction pipeline. This implementation prints.

    Subclasses drive a UI. Every method is called from whichever thread runs the
    extraction, so a UI subclass must not touch widgets directly.
    """

    def stage(self, name):
        print(f"[{name}]")

    def percent(self, value):
        """Progress within the current stage, 0 to 100."""

    def log(self, message):
        print(message)

    def check_cancelled(self):
        """Raise ExtractionCancelled if the work should stop."""


def sanitize_for_path(name):
    """Make an ID3 tag safe to use as a folder name."""
    cleaned = INVALID_PATH_CHARACTERS.sub("_", name).strip(" .")
    return cleaned or "untitled"


def stem_path(song_folder, stem_name, audio_format=OUTPUT_AUDIO_FORMAT):
    return os.path.join(song_folder, f"{stem_name}.{audio_format.lstrip('.')}")


def read_mp3_tags(mp3_path):
    """Read the ID3 tags we care about, falling back to placeholders."""
    tags = {
        "title": "untitled_" + datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
        "artist": "Unknown",
        "album": "Unknown",
        "duration": 0,
        "lyrics": "",
    }

    try:
        audiofile = eyed3.load(mp3_path)
    except Exception as error:
        # eyed3 raises its own error types on malformed tags, so catch broadly but say why
        print(f"Could not read tags from {mp3_path}: {error}")
        return tags

    if audiofile is None or audiofile.tag is None:
        print("No tags found in the MP3 file.")
        return tags

    if audiofile.tag.title:
        tags["title"] = audiofile.tag.title
    if audiofile.tag.artist:
        tags["artist"] = audiofile.tag.artist
    if audiofile.tag.album:
        tags["album"] = audiofile.tag.album
    if audiofile.info is not None:
        tags["duration"] = audiofile.info.time_secs
    if audiofile.tag.lyrics:
        tags["lyrics"] = audiofile.tag.lyrics[0].text

    return tags


def separation_percent(callback_info):
    """Turn a demucs callback dict into a 0 to 100 percentage.

    demucs works through `models` submodels, and within each one steps a segment window
    from 0 to `audio_length`. Keys are documented in demucs.api.Separator.
    """
    audio_length = callback_info.get("audio_length") or 0
    models = callback_info.get("models") or 1
    model_index = callback_info.get("model_idx_in_bag") or 0
    offset = callback_info.get("segment_offset") or 0

    if audio_length <= 0 or models <= 0:
        return 0.0

    within_model = min(1.0, offset / audio_length)
    overall = (model_index + within_model) / models

    return max(0.0, min(100.0, overall * 100.0))


def separate_vocals(
    mp3_path,
    song_folder,
    audio_format=OUTPUT_AUDIO_FORMAT,
    progress=None,
    separator=None,
):
    """Split the source file into music and vocals stems inside song_folder.

    Uses the demucs Python API rather than its CLI so progress and cancellation work and
    so the stems are written straight to their destination.
    """
    from demucs.api import save_audio

    progress = progress or ProgressReporter()
    progress.stage(STAGE_SEPARATE)

    if separator is None:
        separator = load_separator(progress=progress)
    else:
        separator.update_parameter(callback=_separation_callback(progress))

    try:
        origin, stems = separator.separate_audio_file(mp3_path)
    except KeyboardInterrupt:
        # How demucs asks a callback to abort the run
        raise ExtractionCancelled("separation cancelled")

    vocals = stems.pop("vocals")
    # demucs --two-stems defaults to other_method="add": everything that is not the
    # selected stem is summed, rather than subtracted from the original mix.
    music = None
    for stem in stems.values():
        music = stem if music is None else music + stem
    if music is None:
        music = origin - vocals

    music_path = stem_path(song_folder, "music", audio_format)
    vocals_path = stem_path(song_folder, "vocals", audio_format)

    save_kwargs = {"samplerate": separator.samplerate}
    if audio_format.lstrip(".") == "mp3":
        save_kwargs["bitrate"] = MP3_BITRATE

    save_audio(music, music_path, **save_kwargs)
    save_audio(vocals, vocals_path, **save_kwargs)
    progress.percent(100)

    return music_path, vocals_path


def _separation_callback(progress):
    """Bridge the demucs callback to a ProgressReporter."""

    def on_progress(callback_info):
        try:
            progress.check_cancelled()
        except ExtractionCancelled:
            # demucs documents KeyboardInterrupt as the way to abort from a callback
            raise KeyboardInterrupt
        progress.percent(separation_percent(callback_info))

    return on_progress


def load_separator(progress=None, model=EXTRACT_MODEL, shifts=1):
    """Build a demucs Separator on the best available device."""
    import torch
    from demucs.api import Separator

    progress = progress or ProgressReporter()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    progress.log(f"loading separation model '{model}' on {device}")

    return Separator(
        model=model,
        device=device,
        shifts=shifts,
        progress=False,
        callback=_separation_callback(progress),
    )


class WhisperModels:
    """Keeps the ASR and alignment models loaded across a batch.

    Loading the ASR model takes long enough that reloading it per song dominates a queue
    of short tracks. Alignment models are cached per language.
    """

    def __init__(self, whisper_model=WHISPER_MODEL):
        self.whisper_model = whisper_model
        self._asr = None
        self._align = {}

    @property
    def device(self):
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"

    def asr(self, progress=None):
        import whisperx

        if self._asr is None:
            progress = progress or ProgressReporter()
            device = self.device
            # float16 is only supported on GPU
            compute_type = "float16" if device == "cuda" else "int8"
            os.makedirs(MODEL_CACHE, exist_ok=True)
            progress.log(f"loading asr model '{self.whisper_model}' on {device}")
            self._asr = whisperx.load_model(
                self.whisper_model,
                device,
                compute_type=compute_type,
                download_root=MODEL_CACHE,
            )

        return self._asr

    def align(self, language, progress=None):
        import whisperx

        if language not in self._align:
            progress = progress or ProgressReporter()
            progress.log(f"loading alignment model for '{language}'")
            self._align[language] = whisperx.load_align_model(language_code=language, device=self.device)

        return self._align[language]

    def free(self):
        """Drop the models and release GPU memory."""
        self._asr = None
        self._align = {}
        release_gpu_memory()


def release_gpu_memory():
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def transcribe_and_align(
    vocals_path,
    dst_folder,
    whisper_model=WHISPER_MODEL,
    batch_size=16,
    progress=None,
    models=None,
):
    """Run whisperX transcription then forced alignment. Returns (asr_result, align_result)."""
    import whisperx

    progress = progress or ProgressReporter()
    models = models or WhisperModels(whisper_model)

    model = models.asr(progress=progress)

    progress.stage(STAGE_TRANSCRIBE)
    progress.check_cancelled()
    audio = whisperx.load_audio(vocals_path)
    asr_result = model.transcribe(
        audio,
        batch_size=batch_size,
        progress_callback=_percent_callback(progress),
    )
    write_json(os.path.join(dst_folder, "asr_result.json"), asr_result)

    progress.stage(STAGE_ALIGN)
    progress.check_cancelled()
    align_result = None
    try:
        model_a, metadata = models.align(asr_result["language"], progress=progress)
        align_result = whisperx.align(
            asr_result["segments"],
            model_a,
            metadata,
            audio,
            models.device,
            return_char_alignments=False,
            progress_callback=_percent_callback(progress),
        )
        write_json(os.path.join(dst_folder, "alignment_result.json"), align_result)
    except ExtractionCancelled:
        raise
    except Exception as error:
        # Alignment models are not available for every language
        progress.log(f"Alignment failed, falling back to segment timings: {error}")

    return asr_result, align_result


def _percent_callback(progress):
    """Bridge a whisperX progress_callback (0-100 float) to a ProgressReporter."""

    def on_progress(value):
        progress.check_cancelled()
        progress.percent(value)

    return on_progress


def build_lyrics(asr_result, align_result):
    """Prefer the aligned segments, which carry word level timings."""
    segments = None
    if align_result and align_result.get("segments"):
        segments = align_result["segments"]
    elif asr_result and asr_result.get("segments"):
        segments = asr_result["segments"]

    if not segments:
        return []

    lyrics = []
    for segment in segments:
        if segment.get("start") is None or segment.get("end") is None:
            continue

        line = {
            "text": segment.get("text", "").strip(),
            "start": segment["start"],
            "end": segment["end"],
        }

        words = [
            {"word": w["word"], "start": w["start"], "end": w["end"]}
            for w in segment.get("words", [])
            if w.get("start") is not None and w.get("end") is not None
        ]
        if words:
            line["words"] = words

        lyrics.append(line)

    return lyrics


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True, indent=4))


def song_folder_for(mp3_path, dst_folder):
    """Where a source file's karaoke folder will land, without creating anything.

    The GUI needs this up front to decide whether a song has already been extracted.
    """
    tags = read_mp3_tags(mp3_path) if os.path.isfile(mp3_path) else {"title": "untitled"}
    return os.path.join(dst_folder, sanitize_for_path(tags["title"]))


def extract_a_new_mp3_file(
    mp3_path,
    dst_folder,
    whisper_model=WHISPER_MODEL,
    audio_format=OUTPUT_AUDIO_FORMAT,
    progress=None,
    models=None,
    separator=None,
):
    progress = progress or ProgressReporter()

    # ================================================
    # Tags & directories
    # ================================================
    # Fail before creating anything, so a bad path does not leave an empty song folder
    if not os.path.isfile(mp3_path):
        raise FileNotFoundError(f"No such mp3 file: {mp3_path}")

    progress.stage(STAGE_TAGS)
    progress.check_cancelled()
    tags = read_mp3_tags(mp3_path)
    song_folder = os.path.join(dst_folder, sanitize_for_path(tags["title"]))
    os.makedirs(song_folder, exist_ok=True)

    if tags["lyrics"]:
        with open(os.path.join(song_folder, "mp3_lyrics.txt"), "w", encoding="utf-8") as f:
            f.write(tags["lyrics"])

    # ================================================
    # Separate audio
    # ================================================
    _, vocals_path = separate_vocals(
        mp3_path,
        song_folder,
        audio_format=audio_format,
        progress=progress,
        separator=separator,
    )
    release_gpu_memory()

    # ================================================
    # Get lyrics
    # ================================================
    progress.stage(STAGE_LYRICS)
    progress.check_cancelled()
    online_lyrics = search_song_lyrics(tags["artist"], tags["title"], progress=progress)
    if online_lyrics:
        progress.log(f"found online lyrics for {tags['title']} by {tags['artist']}")
        with open(os.path.join(song_folder, "online_lyrics.txt"), "w", encoding="utf-8") as f:
            f.write(online_lyrics)
    else:
        progress.log(f"no online lyrics for {tags['title']} by {tags['artist']}")

    # ================================================
    # ASR + alignment
    # ================================================
    asr_result, align_result = transcribe_and_align(
        vocals_path,
        song_folder,
        whisper_model=whisper_model,
        progress=progress,
        models=models,
    )

    # ================================================
    # Final export format
    # ================================================
    progress.stage(STAGE_WRITE)
    full_info_dict = {
        "title": tags["title"],
        "artist": tags["artist"],
        "album": tags["album"],
        "duration": tags["duration"],
        "lyrics": build_lyrics(asr_result, align_result),
    }
    write_json(os.path.join(song_folder, SONG_INFO_FILE), full_info_dict)
    progress.percent(100)
    progress.log(f"wrote karaoke folder: {song_folder}")

    return song_folder


def search_song_lyrics(artist, title, progress=None):
    progress = progress or ProgressReporter()
    search_url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
    try:
        response = requests.get(search_url, timeout=10)
    except requests.RequestException as error:
        progress.log(f"Lyrics lookup failed: {error}")
        return None

    if response.status_code == 200:
        try:
            data = response.json()
        except ValueError:
            return None
        if "lyrics" in data:
            # Extract and return the lyrics
            return data["lyrics"]

    return None


def main():
    parser = argparse.ArgumentParser(description="Turn an mp3 file into an Any Karaoke folder.")
    parser.add_argument("mp3_path", help="Path to the source mp3 file")
    parser.add_argument("dst_folder", help="Folder the karaoke song folder is created in")
    parser.add_argument(
        "--whisper-model",
        default=WHISPER_MODEL,
        choices=WHISPER_MODEL_CHOICES,
        help="whisperX model name",
    )
    parser.add_argument(
        "--format",
        dest="audio_format",
        default=OUTPUT_AUDIO_FORMAT,
        choices=("mp3", "wav"),
        help=f"stem output format (mp3 is encoded at {MP3_BITRATE}kbps)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.mp3_path):
        parser.error(f"no such mp3 file: {args.mp3_path}")

    extract_a_new_mp3_file(
        args.mp3_path,
        args.dst_folder,
        whisper_model=args.whisper_model,
        audio_format=args.audio_format,
    )


if __name__ == "__main__":
    main()
