import threading
import unittest

from any_karaoke.extractor import (
    ExtractionCancelled,
    ProgressReporter,
    separation_percent,
    stem_path,
)
from any_karaoke.manager import GuiReporter, QueueWriter


def demucs_info(offset, audio_length=1000, models=1, model_index=0):
    return {
        "segment_offset": offset,
        "audio_length": audio_length,
        "models": models,
        "model_idx_in_bag": model_index,
        "shift_idx": 0,
        "state": "start",
    }


class TestSeparationPercent(unittest.TestCase):
    def test_start_and_end_of_a_single_model(self):
        self.assertEqual(separation_percent(demucs_info(0)), 0.0)
        self.assertEqual(separation_percent(demucs_info(1000)), 100.0)

    def test_midpoint(self):
        self.assertAlmostEqual(separation_percent(demucs_info(500)), 50.0)

    def test_monotonic_across_a_bag_of_models(self):
        values = [
            separation_percent(demucs_info(o, models=2, model_index=m)) for m in (0, 1) for o in range(0, 1001, 250)
        ]
        self.assertEqual(values, sorted(values))
        self.assertEqual(values[0], 0.0)
        self.assertEqual(values[-1], 100.0)

    def test_second_model_starts_at_half(self):
        self.assertAlmostEqual(separation_percent(demucs_info(0, models=2, model_index=1)), 50.0)

    def test_never_exceeds_100_when_offset_overshoots(self):
        self.assertEqual(separation_percent(demucs_info(5000)), 100.0)

    def test_missing_or_zero_keys_do_not_divide_by_zero(self):
        self.assertEqual(separation_percent({}), 0.0)
        self.assertEqual(separation_percent(demucs_info(10, audio_length=0)), 0.0)


class TestStemPath(unittest.TestCase):
    def test_mp3_and_wav(self):
        self.assertTrue(stem_path("folder", "music", "mp3").endswith("music.mp3"))
        self.assertTrue(stem_path("folder", "vocals", "wav").endswith("vocals.wav"))

    def test_tolerates_a_leading_dot(self):
        self.assertTrue(stem_path("folder", "music", ".mp3").endswith("music.mp3"))


class TestProgressReporter(unittest.TestCase):
    def test_base_reporter_never_cancels(self):
        self.assertIsNone(ProgressReporter().check_cancelled())


class TestGuiReporter(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.event = threading.Event()
        # A plain list stands in for the queue; only .put is used
        self.reporter = GuiReporter(_Sink(self.sent), self.event, "item1")

    def test_stage_and_percent_are_tagged_with_the_item(self):
        self.reporter.stage("separating vocals")
        self.reporter.percent(42.5)
        self.assertEqual(self.sent[0], ("stage", "item1", "separating vocals"))
        self.assertEqual(self.sent[1], ("percent", "item1", 42.5))

    def test_check_cancelled_raises_once_the_event_is_set(self):
        self.reporter.check_cancelled()
        self.event.set()
        with self.assertRaises(ExtractionCancelled):
            self.reporter.check_cancelled()


class TestQueueWriter(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.writer = QueueWriter(_Sink(self.sent))

    def messages(self):
        return [payload for kind, payload in self.sent if kind == "log"]

    def test_splits_on_newlines(self):
        self.writer.write("first\nsecond\n")
        self.assertEqual(self.messages(), ["first", "second"])

    def test_buffers_a_partial_line_until_flush(self):
        self.writer.write("partial")
        self.assertEqual(self.messages(), [])
        self.writer.flush()
        self.assertEqual(self.messages(), ["partial"])

    def test_carriage_returns_become_separate_lines_not_one_blob(self):
        # tqdm style output: each \r update is its own log line rather than a growing one
        self.writer.write("10%\r20%\r30%\n")
        self.assertEqual(self.messages(), ["10%", "20%", "30%"])

    def test_blank_lines_are_dropped(self):
        self.writer.write("\n\n  \nreal\n")
        self.assertEqual(self.messages(), ["real"])


class _Sink:
    """Minimal stand-in for queue.Queue."""

    def __init__(self, collected):
        self.collected = collected

    def put(self, item):
        self.collected.append(item)


if __name__ == "__main__":
    unittest.main()
