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


def build_ak(**kwargs):
    staging = build_staging(**kwargs)
    ak_path = os.path.join(tempfile.mkdtemp(prefix="library_"), "Test Song" + AK_EXTENSION)
    return pack_song(staging, ak_path)


class TestPackSong(unittest.TestCase):
    def test_produces_a_real_zip(self):
        ak = build_ak()
        self.assertTrue(zipfile.is_zipfile(ak))
        self.assertTrue(ak.endswith(AK_EXTENSION))

    def test_round_trips_every_file(self):
        staging = build_staging()
        ak = pack_song(staging, os.path.join(tempfile.mkdtemp(), "s.ak"))
        self.assertEqual(sorted(os.listdir(staging)), sorted(list_entries(ak)))

    def test_entries_sit_at_the_archive_root(self):
        for name in list_entries(build_ak()):
            self.assertNotIn("/", name)

    def test_audio_is_stored_and_text_is_deflated(self):
        with zipfile.ZipFile(build_ak()) as archive:
            by_name = {info.filename: info.compress_type for info in archive.infolist()}
        self.assertEqual(by_name["music.mp3"], zipfile.ZIP_STORED)
        self.assertEqual(by_name[SONG_INFO_FILE], zipfile.ZIP_DEFLATED)

    def test_overwrites_an_existing_archive(self):
        ak = build_ak()
        again = pack_song(build_staging(), ak)
        self.assertEqual(again, ak)
        self.assertTrue(is_song(ak))

    def test_leaves_no_partial_file_behind(self):
        ak = build_ak()
        self.assertFalse(os.path.exists(ak + ".partial"))

    def test_creates_the_destination_folder(self):
        target = os.path.join(tempfile.mkdtemp(), "nested", "deeper", "s.ak")
        pack_song(build_staging(), target)
        self.assertTrue(os.path.isfile(target))


class BothLayoutsTestCase(unittest.TestCase):
    """Every check runs against a .ak and against a legacy folder."""

    def layouts(self, **kwargs):
        return {"ak": build_ak(**kwargs), "folder": build_staging(**kwargs)}


class TestIsSong(BothLayoutsTestCase):
    def test_accepts_a_complete_song(self):
        for label, path in self.layouts().items():
            self.assertTrue(is_song(path), label)

    def test_accepts_wav_stems(self):
        for label, path in self.layouts(extension=".wav").items():
            self.assertTrue(is_song(path), label)

    def test_rejects_a_missing_stem(self):
        for label, path in self.layouts(stems=("music",)).items():
            self.assertFalse(is_song(path), label)

    def test_rejects_a_missing_song_info(self):
        for label, path in self.layouts(with_info=False).items():
            self.assertFalse(is_song(path), label)

    def test_rejects_an_empty_folder_and_none(self):
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


class TestReadSongInfo(BothLayoutsTestCase):
    def test_same_result_from_both_layouts(self):
        results = {label: read_song_info(path) for label, path in self.layouts().items()}
        self.assertEqual(results["ak"], SONG_INFO)
        self.assertEqual(results["ak"], results["folder"])

    def test_lyrics_survive_the_round_trip(self):
        self.assertEqual(read_song_info(build_ak())["lyrics"][0]["text"], "hi")


class TestOpenStem(BothLayoutsTestCase):
    def test_returns_the_same_bytes_from_both_layouts(self):
        for label, path in self.layouts().items():
            with open_stem(path, "music") as handle:
                self.assertEqual(handle.read(), MUSIC_BYTES, label)
            with open_stem(path, "vocals") as handle:
                self.assertEqual(handle.read(), VOCALS_BYTES, label)

    def test_works_with_wav_stems(self):
        for label, path in self.layouts(extension=".wav").items():
            with open_stem(path, "music") as handle:
                self.assertEqual(handle.read(), MUSIC_BYTES, label)

    def test_prefers_mp3_when_both_formats_are_present(self):
        staging = build_staging(extension=".wav")
        with open(os.path.join(staging, "music.mp3"), "wb") as f:
            f.write(b"THE-MP3-ONE")
        for path in (staging, pack_song(staging, os.path.join(tempfile.mkdtemp(), "s.ak"))):
            with open_stem(path, "music") as handle:
                self.assertEqual(handle.read(), b"THE-MP3-ONE")

    def test_raises_for_a_missing_stem(self):
        for path in self.layouts(stems=("music",)).values():
            with self.assertRaises(FileNotFoundError):
                with open_stem(path, "vocals"):
                    pass

    def test_the_handle_is_closed_afterwards(self):
        path = build_staging()
        with open_stem(path, "music") as handle:
            pass
        self.assertTrue(handle.closed)


class TestMissingParts(BothLayoutsTestCase):
    def test_empty_for_a_complete_song(self):
        for label, path in self.layouts().items():
            self.assertEqual(missing_parts(path), [], label)

    def test_names_the_missing_stem(self):
        for path in self.layouts(stems=("music",)).values():
            self.assertEqual(len(missing_parts(path)), 1)
            self.assertIn("vocals", missing_parts(path)[0])

    def test_lists_everything_for_an_empty_folder(self):
        missing = missing_parts(tempfile.mkdtemp())
        self.assertIn(SONG_INFO_FILE, missing)
        self.assertEqual(len(missing), 3)


class TestSongDisplayName(unittest.TestCase):
    def test_strips_the_ak_extension(self):
        self.assertEqual(song_display_name(r"D:\songs\$10 Cowboy.ak"), "$10 Cowboy")

    def test_uses_the_folder_name_for_a_legacy_song(self):
        self.assertEqual(song_display_name(r"D:\songs\$10 Cowboy"), "$10 Cowboy")

    def test_tolerates_a_trailing_separator(self):
        self.assertEqual(song_display_name("D:\\songs\\Title\\"), "Title")


if __name__ == "__main__":
    unittest.main()
