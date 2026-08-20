import json
import os
import tempfile
import unittest

from any_karaoke.song_files import (
    SONG_INFO_FILE,
    find_stem,
    is_karaoke_folder,
    missing_parts,
    song_info_path,
)


def make_song_folder(extension=".mp3", with_info=True, stems=("music", "vocals")):
    folder = tempfile.mkdtemp(prefix="song_")
    if with_info:
        with open(song_info_path(folder), "w", encoding="utf-8") as f:
            json.dump({"lyrics": []}, f)
    for stem in stems:
        with open(os.path.join(folder, stem + extension), "wb") as f:
            f.write(b"\0")
    return folder


class TestFindStem(unittest.TestCase):
    def test_finds_mp3(self):
        folder = make_song_folder(".mp3")
        self.assertTrue(find_stem(folder, "music").endswith("music.mp3"))

    def test_finds_wav(self):
        folder = make_song_folder(".wav")
        self.assertTrue(find_stem(folder, "music").endswith("music.wav"))

    def test_prefers_mp3_when_both_exist(self):
        folder = make_song_folder(".wav")
        with open(os.path.join(folder, "music.mp3"), "wb") as f:
            f.write(b"\0")
        self.assertTrue(find_stem(folder, "music").endswith("music.mp3"))

    def test_missing_stem_returns_none(self):
        folder = make_song_folder(".mp3", stems=("music",))
        self.assertIsNone(find_stem(folder, "vocals"))

    def test_none_folder(self):
        self.assertIsNone(find_stem(None, "music"))


class TestIsKaraokeFolder(unittest.TestCase):
    def test_mp3_folder_is_valid(self):
        self.assertTrue(is_karaoke_folder(make_song_folder(".mp3")))

    def test_wav_folder_still_valid(self):
        # Libraries extracted before the switch to mp3 must keep working
        self.assertTrue(is_karaoke_folder(make_song_folder(".wav")))

    def test_rejects_folder_without_song_info(self):
        self.assertFalse(is_karaoke_folder(make_song_folder(".mp3", with_info=False)))

    def test_rejects_folder_missing_a_stem(self):
        self.assertFalse(is_karaoke_folder(make_song_folder(".mp3", stems=("music",))))

    def test_rejects_empty_and_none(self):
        self.assertFalse(is_karaoke_folder(tempfile.mkdtemp()))
        self.assertFalse(is_karaoke_folder(None))


class TestMissingParts(unittest.TestCase):
    def test_lists_song_info_and_stems(self):
        missing = missing_parts(tempfile.mkdtemp())
        self.assertIn(SONG_INFO_FILE, missing)
        self.assertEqual(len(missing), 3)

    def test_empty_for_a_complete_folder(self):
        self.assertEqual(missing_parts(make_song_folder(".mp3")), [])


if __name__ == "__main__":
    unittest.main()
