import unittest

from any_karaoke.text_utils import split_into_sub_sentences, wrap_to_width


def fixed_width_measure(char_width=10):
    """Stand-in for pygame font measurement: every character is char_width wide."""
    return lambda text: len(text) * char_width


class TestSplitIntoSubSentences(unittest.TestCase):
    def test_single_chunk_returns_text(self):
        self.assertEqual(split_into_sub_sentences("hello world", 1), ["hello world"])

    def test_empty_text(self):
        self.assertEqual(split_into_sub_sentences("", 3), [])

    def test_splits_on_punctuation(self):
        result = split_into_sub_sentences("one thing, another thing, a third thing", 3)
        self.assertEqual(len(result), 3)
        self.assertNotIn(",", "".join(result))

    def test_falls_back_to_words_without_punctuation(self):
        result = split_into_sub_sentences("alpha bravo charlie delta echo foxtrot", 2)
        self.assertEqual(len(result), 2)
        self.assertEqual(" ".join(result), "alpha bravo charlie delta echo foxtrot")

    def test_no_empty_chunks(self):
        result = split_into_sub_sentences("a, , b, , c", 3)
        self.assertTrue(all(chunk for chunk in result))


class TestWrapToWidth(unittest.TestCase):
    def test_short_text_stays_on_one_line(self):
        self.assertEqual(wrap_to_width("hi", fixed_width_measure(), 100), ["hi"])

    def test_wraps_at_word_boundaries(self):
        # 100px / 10px per char = 10 characters per line
        result = wrap_to_width("aaa bbb ccc ddd", fixed_width_measure(), 100)
        self.assertEqual(result, ["aaa bbb", "ccc ddd"])
        self.assertTrue(all(len(line) <= 10 for line in result))

    def test_breaks_a_word_wider_than_the_line(self):
        # A single 15 character word cannot fit in 10 characters, so it must be broken
        result = wrap_to_width("supercalifragi", fixed_width_measure(), 100)
        self.assertTrue(len(result) > 1)
        self.assertTrue(all(len(line) <= 10 for line in result))
        self.assertEqual("".join(result), "supercalifragi")

    def test_empty_text(self):
        self.assertEqual(wrap_to_width("", fixed_width_measure(), 100), [])

    def test_zero_width_does_not_hang(self):
        self.assertEqual(wrap_to_width("some text", fixed_width_measure(), 0), ["some text"])


if __name__ == "__main__":
    unittest.main()
