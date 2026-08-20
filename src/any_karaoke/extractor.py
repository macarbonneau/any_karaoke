import argparse
import json
import os
import re
import shutil
from datetime import datetime

import eyed3
import requests

from any_karaoke.game_config import MODEL_CACHE, TEMP_PATH, EXTRACT_MODEL, WHISPER_MODEL

# torch, whisperx and demucs come from the optional "extract" extra and are imported
# lazily so the rest of this module stays usable without them.

INVALID_PATH_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_for_path(name):
    """Make an ID3 tag safe to use as a folder name."""
    cleaned = INVALID_PATH_CHARACTERS.sub("_", name).strip(" .")
    return cleaned or "untitled"


def safe_move(src, dst):
    """Move src over dst, replacing dst if it exists. Works across drives."""
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(src, dst)


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


def separate_vocals(mp3_path, dst_folder):
    """Split the mp3 into music.wav and vocals.wav inside dst_folder."""
    from demucs import separate

    os.makedirs(TEMP_PATH, exist_ok=True)
    separate.main(
        [
            mp3_path,
            "--two-stems",
            "vocals",
            "-n",
            EXTRACT_MODEL,
            "--shifts",
            "1",
            "-o",
            TEMP_PATH,
        ]
    )

    # demucs names its output folder after the input file name, not the ID3 title
    source_name = os.path.splitext(os.path.basename(mp3_path))[0]
    demucs_folder = os.path.join(TEMP_PATH, EXTRACT_MODEL, source_name)

    music_path = os.path.join(dst_folder, "music.wav")
    vocals_path = os.path.join(dst_folder, "vocals.wav")
    safe_move(os.path.join(demucs_folder, "no_vocals.wav"), music_path)
    safe_move(os.path.join(demucs_folder, "vocals.wav"), vocals_path)

    shutil.rmtree(demucs_folder, ignore_errors=True)

    return music_path, vocals_path


def transcribe_and_align(vocals_path, dst_folder, whisper_model=WHISPER_MODEL, batch_size=16):
    """Run whisperX transcription then forced alignment. Returns (asr_result, align_result)."""
    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    # float16 is only supported on GPU
    compute_type = "float16" if device == "cuda" else "int8"
    os.makedirs(MODEL_CACHE, exist_ok=True)

    print(f"loading asr model '{whisper_model}' on {device}")
    model = whisperx.load_model(whisper_model, device, compute_type=compute_type, download_root=MODEL_CACHE)

    print("transcribing")
    audio = whisperx.load_audio(vocals_path)
    asr_result = model.transcribe(audio, batch_size=batch_size)
    write_json(os.path.join(dst_folder, "asr_result.json"), asr_result)

    print("aligning")
    align_result = None
    try:
        model_a, metadata = whisperx.load_align_model(language_code=asr_result["language"], device=device)
        align_result = whisperx.align(
            asr_result["segments"],
            model_a,
            metadata,
            audio,
            device,
            return_char_alignments=False,
        )
        write_json(os.path.join(dst_folder, "alignment_result.json"), align_result)
    except Exception as error:
        # Alignment models are not available for every language
        print(f"Alignment failed, falling back to segment timings: {error}")

    return asr_result, align_result


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


def extract_a_new_mp3_file(mp3_path, dst_folder, whisper_model=WHISPER_MODEL):
    # ================================================
    # Tags & directories
    # ================================================
    # Fail before creating anything, so a bad path does not leave an empty song folder
    if not os.path.isfile(mp3_path):
        raise FileNotFoundError(f"No such mp3 file: {mp3_path}")

    tags = read_mp3_tags(mp3_path)
    song_folder = os.path.join(dst_folder, sanitize_for_path(tags["title"]))
    os.makedirs(song_folder, exist_ok=True)

    if tags["lyrics"]:
        with open(os.path.join(song_folder, "mp3_lyrics.txt"), "w", encoding="utf-8") as f:
            f.write(tags["lyrics"])

    # ================================================
    # Separate audio
    # ================================================
    _, vocals_path = separate_vocals(mp3_path, song_folder)

    # ================================================
    # Get lyrics
    # ================================================
    online_lyrics = search_song_lyrics(tags["artist"], tags["title"])
    if online_lyrics:
        print(f"\nONLINE Lyrics for {tags['title']} by {tags['artist']}:\n")
        with open(os.path.join(song_folder, "online_lyrics.txt"), "w", encoding="utf-8") as f:
            f.write(online_lyrics)
    else:
        print(f"Lyrics for {tags['title']} by {tags['artist']} not found.")

    # ================================================
    # ASR + alignment
    # ================================================
    asr_result, align_result = transcribe_and_align(vocals_path, song_folder, whisper_model=whisper_model)

    # ================================================
    # Final export format
    # ================================================
    full_info_dict = {
        "title": tags["title"],
        "artist": tags["artist"],
        "album": tags["album"],
        "duration": tags["duration"],
        "lyrics": build_lyrics(asr_result, align_result),
    }
    write_json(os.path.join(song_folder, "any_karaoke_file.json"), full_info_dict)
    print(f"Wrote karaoke folder: {song_folder}")

    return song_folder


def search_song_lyrics(artist, title):
    search_url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
    try:
        response = requests.get(search_url, timeout=10)
    except requests.RequestException as error:
        print(f"Lyrics lookup failed: {error}")
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
    parser.add_argument("--whisper-model", default=WHISPER_MODEL, help="whisperX model name")
    args = parser.parse_args()

    if not os.path.isfile(args.mp3_path):
        parser.error(f"no such mp3 file: {args.mp3_path}")

    extract_a_new_mp3_file(args.mp3_path, args.dst_folder, whisper_model=args.whisper_model)


if __name__ == "__main__":
    main()
