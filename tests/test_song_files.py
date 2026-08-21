import json
import os
import tempfile
import unittest
import zipfile

from any_karaoke.song_files import (
    AK_EXTENSION,
    SONG_INFO_FILE,
    is_song,
    list_entries,
    missing_parts,
    open_stem,
    pack_song,
    read_song_info,
    song_display_name,
)

SONG_INFO = {"title": "Test Song", "artist": "A", "lyrics": [{"text": "hi", "start": 0, "end": 1}]}
MUSIC_BYTES = b"MUSIC-DATA-0123456789"
VOCALS_BYTES = b"VOCALS-DATA-9876543210"


def build_staging(extension=".mp3", with_info=True, stems=("music", "vocals"), extras=True):
    folder = tempfile.mkdtemp(prefix="staging_")
    if with_info:
        with open(os.path.join(folder, SONG_INFO_FILE), "w", encoding="utf-8") as f:
            json.dump(SONG_INFO, f)
    for stem in stems:
        payload = MUSIC_BYTES if stem == "music" else VOCALS_BYTES
        with open(os.path.join(folder, stem + extension), "wb") as f:
            f.write(payload)
    if extras:
        with open(os.path.join(folder, "online_lyrics.txt"), "w", encoding="utf-8") as f:
            f.write("la la la")
    return folder


def build_song(**kwargs):
    staging = build_staging(**kwargs)
    ak_path = os.path.join(tempfile.mkdtemp(prefix="library_"), "Test Song" + AK_EXTENSION)
    return pack_song(staging, ak_path)


class TestPackSong(unittest.TestCase):
    def test_produces_a_real_zip(self):
        song = build_song()
        self.assertTrue(zipfile.is_zipfile(song))
        self.assertTrue(song.endswith(AK_EXTENSION))

    def test_round_trips_every_file(self):
        staging = build_staging()
        song = pack_song(staging, os.path.join(tempfile.mkdtemp(), "s.ak"))
        self.assertEqual(sorted(os.listdir(staging)), sorted(list_entries(song)))

    def test_entries_sit_at_the_archive_root(self):
        for name in list_entries(build_song()):
            self.assertNotIn("/", name)

    def test_audio_is_stored_and_text_is_deflated(self):
        with zipfile.ZipFile(build_song()) as archive:
            by_name = {info.filename: info.compress_type for info in archive.infolist()}
        self.assertEqual(by_name["music.mp3"], zipfile.ZIP_STORED)
        self.assertEqual(by_name[SONG_INFO_FILE], zipfile.ZIP_DEFLATED)

    def test_overwrites_an_existing_archive(self):
        song = build_song()
        again = pack_song(build_staging(), song)
        self.assertEqual(again, song)
        self.assertTrue(is_song(song))

    def test_leaves_no_partial_file_behind(self):
        self.assertFalse(os.path.exists(build_song() + ".partial"))

    def test_creates_the_destination_folder(self):
        target = os.path.join(tempfile.mkdtemp(), "nested", "deeper", "s.ak")
        pack_song(build_staging(), target)
        self.assertTrue(os.path.isfile(target))


class TestIsSong(unittest.TestCase):
    def test_accepts_a_complete_song(self):
        self.assertTrue(is_song(build_song()))

    def test_accepts_wav_stems(self):
        self.assertTrue(is_song(build_song(extension=".wav")))

    def test_rejects_a_missing_stem(self):
        self.assertFalse(is_song(build_song(stems=("music",))))

    def test_rejects_a_missing_song_info(self):
        self.assertFalse(is_song(build_song(with_info=False)))

    def test_rejects_a_folder_of_loose_files(self):
        # An unpacked staging directory is not a song, only the packed .ak is
        self.assertFalse(is_song(build_staging()))

    def test_rejects_empty_and_none(self):
        self.assertFalse(is_song(tempfile.mkdtemp()))
        self.assertFalse(is_song(None))
        self.assertFalse(is_song(""))

    def test_rejects_a_missing_path(self):
        self.assertFalse(is_song(os.path.join(tempfile.mkdtemp(), "nope.ak")))

    def test_rejects_a_non_zip_named_ak(self):
        fake = os.path.join(tempfile.mkdtemp(), "fake.ak")
        with open(fake, "wb") as f:
            f.write(b"this is not a zip")
        self.assertFalse(is_song(fake))


class TestReadSongInfo(unittest.TestCase):
    def test_reads_the_description_back(self):
        self.assertEqual(read_song_info(build_song()), SONG_INFO)

    def test_lyrics_survive_the_round_trip(self):
        self.assertEqual(read_song_info(build_song())["lyrics"][0]["text"], "hi")


class TestOpenStem(unittest.TestCase):
    def test_returns_the_bytes_that_went_in(self):
        song = build_song()
        with open_stem(song, "music") as handle:
            self.assertEqual(handle.read(), MUSIC_BYTES)
        with open_stem(song, "vocals") as handle:
            self.assertEqual(handle.read(), VOCALS_BYTES)

    def test_works_with_wav_stems(self):
        with open_stem(build_song(extension=".wav"), "music") as handle:
            self.assertEqual(handle.read(), MUSIC_BYTES)

    def test_prefers_mp3_when_both_formats_are_present(self):
        staging = build_staging(extension=".wav")
        with open(os.path.join(staging, "music.mp3"), "wb") as f:
            f.write(b"THE-MP3-ONE")
        song = pack_song(staging, os.path.join(tempfile.mkdtemp(), "s.ak"))
        with open_stem(song, "music") as handle:
            self.assertEqual(handle.read(), b"THE-MP3-ONE")

    def test_raises_for_a_missing_stem(self):
        with self.assertRaises(FileNotFoundError):
            with open_stem(build_song(stems=("music",)), "vocals"):
                pass

    def test_the_handle_is_closed_afterwards(self):
        with open_stem(build_song(), "music") as handle:
            pass
        self.assertTrue(handle.closed)


class TestMissingParts(unittest.TestCase):
    def test_empty_for_a_complete_song(self):
        self.assertEqual(missing_parts(build_song()), [])

    def test_names_the_missing_stem(self):
        missing = missing_parts(build_song(stems=("music",)))
        self.assertEqual(len(missing), 1)
        self.assertIn("vocals", missing[0])

    def test_lists_everything_for_a_path_that_is_not_a_song(self):
        missing = missing_parts(tempfile.mkdtemp())
        self.assertIn(SONG_INFO_FILE, missing)
        self.assertEqual(len(missing), 3)


class TestSongDisplayName(unittest.TestCase):
    def test_strips_the_ak_extension(self):
        self.assertEqual(song_display_name(r"D:\songs\$10 Cowboy.ak"), "$10 Cowboy")

    def test_handles_a_bare_name(self):
        self.assertEqual(song_display_name("Title.ak"), "Title")


if __name__ == "__main__":
    unittest.main()
