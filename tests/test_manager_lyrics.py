import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import tkinter as tk  # noqa: E402

from any_karaoke.extractor import ProgressReporter, write_reference_lyrics  # noqa: E402
from any_karaoke.manager import ManagerWindow  # noqa: E402
from any_karaoke.song_files import LYRICS_ALIGNMENT_FILE  # noqa: E402

TAGS = {"title": "Song", "artist": "Band", "album": "A", "duration": 1, "lyrics": ""}


def read_scaffold(folder):
    with open(os.path.join(folder, LYRICS_ALIGNMENT_FILE), encoding="utf-8") as handle:
        return json.load(handle)


class TestLyricsSourcePriority(unittest.TestCase):
    """Pasted beats online beats the ID3 tag."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="lyrics_")

    def test_pasted_wins_and_skips_the_lookup(self):
        with mock.patch("any_karaoke.extractor.search_song_lyrics") as lookup:
            scaffold = write_reference_lyrics(self.folder, dict(TAGS), lyrics_text="pasted one\npasted two")
        lookup.assert_not_called()
        self.assertEqual(scaffold["source"], "pasted")
        self.assertEqual(read_scaffold(self.folder)["source"], "pasted")
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "pasted_lyrics.txt")))
        self.assertFalse(os.path.isfile(os.path.join(self.folder, "online_lyrics.txt")))

    def test_online_used_when_nothing_is_pasted(self):
        with mock.patch("any_karaoke.extractor.search_song_lyrics", return_value="online one\nonline two"):
            scaffold = write_reference_lyrics(self.folder, dict(TAGS))
        self.assertEqual(scaffold["source"], "online")
        self.assertEqual(read_scaffold(self.folder)["source"], "online")
        self.assertTrue(os.path.isfile(os.path.join(self.folder, "online_lyrics.txt")))

    def test_id3_used_when_the_lookup_finds_nothing(self):
        tags = dict(TAGS, lyrics="tagged line")
        with mock.patch("any_karaoke.extractor.search_song_lyrics", return_value=None):
            scaffold = write_reference_lyrics(self.folder, tags)
        self.assertEqual(scaffold["source"], "id3")
        self.assertEqual(read_scaffold(self.folder)["source"], "id3")

    def test_nothing_written_when_there_are_no_lyrics_at_all(self):
        with mock.patch("any_karaoke.extractor.search_song_lyrics", return_value=None):
            scaffold = write_reference_lyrics(self.folder, dict(TAGS))
        self.assertIsNone(scaffold)
        self.assertFalse(os.path.isfile(os.path.join(self.folder, LYRICS_ALIGNMENT_FILE)))

    def test_blank_pasted_text_falls_through_to_the_lookup(self):
        with mock.patch("any_karaoke.extractor.search_song_lyrics", return_value="online") as lookup:
            scaffold = write_reference_lyrics(self.folder, dict(TAGS), lyrics_text="   \n  ")
        lookup.assert_called_once()
        self.assertEqual(scaffold["source"], "online")

    def test_scaffold_carries_the_pasted_lines(self):
        write_reference_lyrics(self.folder, dict(TAGS), lyrics_text="one\ntwo\n\nthree")
        scaffold = read_scaffold(self.folder)
        self.assertEqual(scaffold["line_count"], 3)
        self.assertEqual([line["verse"] for line in scaffold["lines"]], [0, 0, 1])

    def test_a_reporter_is_optional(self):
        write_reference_lyrics(self.folder, dict(TAGS), lyrics_text="x", progress=ProgressReporter())


class ManagerTestCase(unittest.TestCase):
    """One Tk interpreter for the whole class.

    Creating and destroying a root per test churns Tcl hard enough to intermittently fail
    to load init.tcl on Windows, so each test gets a Toplevel inside a shared root instead.
    """

    root = None

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            # Tcl occasionally fails to load its own init library on this platform when
            # several test modules share a process. Skip rather than fail the suite: the
            # logic under test is unaffected, and these run normally on their own.
            raise unittest.SkipTest(f"Tk unavailable in this process: {error}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        if cls.root is not None:
            cls.root.destroy()
            cls.root = None

    def setUp(self):
        self.container = tk.Toplevel(self.root)
        self.container.withdraw()
        self.window = ManagerWindow(self.container, output_folder=tempfile.mkdtemp())
        self.addCleanup(self.container.destroy)
        self.addCleanup(self.window.shutdown)

    def add_song(self, name="song.mp3"):
        item = self.window.tree.insert("", "end", values=(name, "", "queued"))
        self.window.sources[item] = os.path.join("C:\\", name)
        return item


class TestPasteLyrics(ManagerTestCase):
    def paste(self, item, text):
        self.window.tree.selection_set(item)
        with mock.patch("any_karaoke.manager.ask_for_lyrics", return_value=text):
            self.window._paste_lyrics()

    def test_stores_against_the_selected_row(self):
        first, second = self.add_song("a.mp3"), self.add_song("b.mp3")
        self.paste(second, "some lyrics")
        self.assertEqual(self.window.pasted_lyrics, {second: "some lyrics"})
        self.assertNotIn(first, self.window.pasted_lyrics)

    def test_marks_the_lyrics_column(self):
        item = self.add_song()
        self.paste(item, "some lyrics")
        self.assertEqual(self.window.tree.set(item, "lyrics"), "custom")

    def test_saving_empty_text_clears_it(self):
        item = self.add_song()
        self.paste(item, "some lyrics")
        self.paste(item, "   ")
        self.assertNotIn(item, self.window.pasted_lyrics)
        self.assertEqual(self.window.tree.set(item, "lyrics"), "")

    def test_cancelling_leaves_the_stored_text_alone(self):
        item = self.add_song()
        self.paste(item, "keep me")
        self.paste(item, None)  # cancelled
        self.assertEqual(self.window.pasted_lyrics[item], "keep me")

    def test_nothing_selected_is_reported_not_crashed(self):
        self.add_song()
        self.window.tree.selection_remove(*self.window.tree.get_children())
        with mock.patch("any_karaoke.manager.messagebox.showinfo") as info:
            self.window._paste_lyrics()
        info.assert_called_once()

    def test_removing_a_row_drops_its_lyrics(self):
        item = self.add_song()
        self.paste(item, "some lyrics")
        self.window.tree.selection_set(item)
        self.window._remove_selected()
        self.assertEqual(self.window.pasted_lyrics, {})

    def test_clearing_the_queue_drops_every_pasted_set(self):
        item = self.add_song()
        self.paste(item, "some lyrics")
        self.window._clear_queue()
        self.assertEqual(self.window.pasted_lyrics, {})

    def test_status_updates_keep_the_lyrics_marker(self):
        item = self.add_song()
        self.paste(item, "some lyrics")
        self.window._set_status(item, "separating vocals")
        self.assertEqual(self.window.tree.set(item, "lyrics"), "custom")
        self.assertEqual(self.window.tree.set(item, "song"), "song.mp3")


class TestWorkerReceivesLyrics(ManagerTestCase):
    def test_start_snapshots_the_pasted_lyrics(self):
        item = self.add_song()
        self.window.pasted_lyrics[item] = "typed by hand"

        with mock.patch("any_karaoke.manager.threading.Thread") as thread:
            self.window._start()
        snapshot = thread.call_args.kwargs["args"][5]

        self.assertEqual(snapshot, {item: "typed by hand"})
        # A copy, so editing afterwards cannot change what the worker sees
        self.window.pasted_lyrics[item] = "changed later"
        self.assertEqual(snapshot[item], "typed by hand")

    def test_a_row_without_pasted_lyrics_passes_nothing(self):
        self.add_song()
        with mock.patch("any_karaoke.manager.threading.Thread") as thread:
            self.window._start()
        self.assertEqual(thread.call_args.kwargs["args"][5], {})


if __name__ == "__main__":
    unittest.main()
