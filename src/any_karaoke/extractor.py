import os, shutil
import requests
import json
from datetime import datetime

import eyed3
import whisper

from demucs import separate


from any_karaoke.game_config import TEMP_PATH, EXTRACT_MODEL, WHISPER_MODEL


def safe_rename(src, dst):
    try:
        os.remove(dst)
    except OSError:
        pass
    os.rename(src, dst)


def extract_a_new_mp3_file(mp3_path, dst_folder):
    #################################################
    # TAGS & DIRECTORIES
    #################################################
    # get the tags
    audiofile = eyed3.load(mp3_path)
    # Check if tags are present
    title = "untititled" + f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    artist = "Unknown"
    album = "Unknown"
    mp3_length_seconds = 0
    lyrics_tag = ""

    if audiofile.tag is not None:
        # Access various tag attributes
        if audiofile.tag.title:
            title = audiofile.tag.title
        if audiofile.tag.artist:
            artist = audiofile.tag.artist
        if audiofile.tag.album:
            album = audiofile.tag.album
        mp3_length_seconds = audiofile.info.time_secs
        if audiofile.tag.lyrics:
            lyrics_tag = audiofile.tag.lyrics[0].text

    else:
        print("No tags found in the MP3 file.")

    # create the folders and path
    song_name = os.path.basename(mp3_path).replace(".mp3", "")
    dst_folder = os.path.join(dst_folder, title)
    os.makedirs(dst_folder, exist_ok=True)

    if lyrics_tag:
        with open(os.path.join(dst_folder, "mp3_lyrics.txt"), "w") as f:
            f.write(audiofile.tag.lyrics[0].text)

    #################################################
    # SEPARATE AUDIO
    #################################################
    ##### separate the track in a temp folder
    args_list = [
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
    separate.main(args_list)

    # move and rename
    os.makedirs(dst_folder, exist_ok=True)
    tmp_wav_path = os.path.join(TEMP_PATH, EXTRACT_MODEL, song_name, "no_vocals.wav")
    dst_wav_path = os.path.join(dst_folder, "music.wav")
    safe_rename(tmp_wav_path, dst_wav_path)

    tmp_wav_path = os.path.join(TEMP_PATH, EXTRACT_MODEL, song_name, "vocals.wav")
    dst_wav_path = os.path.join(dst_folder, "vocals.wav")
    safe_rename(tmp_wav_path, dst_wav_path)
    #################################################
    # GET LYRICS
    #################################################
    # try online
    online_lyrics = search_song_lyrics(artist, title)

    if online_lyrics:
        print(f"\nONLINE Lyrics for {title} by {artist}:\n")
        with open(os.path.join(dst_folder, "online_lyrics.txt"), "w") as f:
            f.write(online_lyrics)

    else:
        print(f"Lyrics for {title} by {artist} not found.")

    #################################################
    # ASR
    #################################################
    print("loading asr model")
    asr_model = whisper.load_model(WHISPER_MODEL)
    print("transcribing")
    asr_result = asr_model.transcribe(dst_wav_path)
    with open(os.path.join(dst_folder, "asr_result.json"), "w") as f:
        f.write(json.dumps(asr_result, ensure_ascii=True, indent=4))

    #################################################
    # FINAL EXPORT FORMAT
    #################################################
    final_lyrics = []
    # start with the ASR
    if asr_result:
        for i in asr_result["segments"]:
            final_lyrics.append(
                {"text": i["text"].strip(), "start": i["start"], "end": i["end"]}
            )

    full_info_dict = {
        "title": title,
        "artist": artist,
        "album": album,
        "duration": mp3_length_seconds,
        "lyrics": final_lyrics,
    }
    with open(os.path.join(dst_folder, "any_karaoke_file.json"), "w") as f:
        f.write(json.dumps(full_info_dict, ensure_ascii=True, indent=4))

    # clean-up


def search_song_lyrics(artist, title):
    search_url = f"https://api.lyrics.ovh/v1/{artist}/{title}"
    response = requests.get(search_url)

    if response.status_code == 200:
        data = response.json()

        if "lyrics" in data:
            # Extract and return the lyrics
            lyrics = data["lyrics"]
            return lyrics

    return None


def main():
    extract_a_new_mp3_file(
        r"D:\demucs_processed_files\05 Favorite Things.mp3",
        r"D:\demucs_processed_files\karaoke",
    )


if __name__ == "__main__":
    main()
