import random
import unittest

from shortsbot import captions
from shortsbot.tts_client import Alignment


def make_alignment(text: str, char_duration: float = 0.1) -> Alignment:
    characters = list(text)
    start_times = [i * char_duration for i in range(len(characters))]
    end_times = [(i + 1) * char_duration for i in range(len(characters))]
    return Alignment(characters=characters, start_times=start_times, end_times=end_times)


class TestWordsFromAlignment(unittest.TestCase):
    def test_splits_on_whitespace(self):
        alignment = make_alignment("ab cd ef")
        words = captions.words_from_alignment(alignment)
        self.assertEqual([w.text for w in words], ["ab", "cd", "ef"])
        self.assertAlmostEqual(words[0].start, 0.0)
        self.assertAlmostEqual(words[0].end, 0.2)
        self.assertAlmostEqual(words[1].start, 0.3)
        self.assertAlmostEqual(words[1].end, 0.5)

    def test_applies_time_offset(self):
        alignment = make_alignment("hi")
        words = captions.words_from_alignment(alignment, time_offset=10.0)
        self.assertAlmostEqual(words[0].start, 10.0)


class TestChunkWords(unittest.TestCase):
    def test_pairs_words_with_odd_tail(self):
        alignment = make_alignment("ab cd ef")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=0.0)
        self.assertEqual([c.text for c in chunks], ["ab cd", "ef"])

    def test_chunk_end_equals_next_chunk_start(self):
        alignment = make_alignment("ab cd ef gh")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=0.0)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].end, chunks[1].start)

    def test_final_end_extends_last_chunk(self):
        alignment = make_alignment("ab cd")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, final_end=5.0)
        self.assertEqual(chunks[-1].end, 5.0)

    def test_no_blank_gaps_across_all_chunks(self):
        alignment = make_alignment("ab cd ef gh ij")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, final_end=100.0)
        for i in range(len(chunks) - 1):
            self.assertEqual(chunks[i].end, chunks[i + 1].start)

    def test_sentence_end_forces_new_chunk(self):
        alignment = make_alignment("Arguing. I hate that")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=0.0)
        # "Arguing." must not be merged with the next sentence's "I".
        self.assertEqual([c.text for c in chunks], ["Arguing.", "I hate", "that"])

    def test_question_and_exclamation_also_force_new_chunk(self):
        alignment = make_alignment("Really? Yes! Absolutely")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=0.0)
        self.assertEqual([c.text for c in chunks], ["Really?", "Yes!", "Absolutely"])

    def test_closing_parenthesis_forces_new_chunk(self):
        alignment = make_alignment("I said (obviously) that was true")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=0.0)
        # "(obviously)" must not be merged with the following "that".
        self.assertEqual(
            [c.text for c in chunks], ["I said", "(obviously)", "that was", "true"]
        )

    def test_single_word_chance_one_forces_every_chunk_solo(self):
        alignment = make_alignment("one two three four five six")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(words, chunk_size=2, single_word_chance=1.0)
        self.assertEqual([c.text for c in chunks], ["one", "two", "three", "four", "five", "six"])

    def test_single_word_chance_produces_mix_of_one_and_two_word_chunks(self):
        alignment = make_alignment("a b c d e f g h i j k l m n o p")
        words = captions.words_from_alignment(alignment)
        chunks = captions.chunk_words(
            words, chunk_size=2, single_word_chance=0.5, rng=random.Random(7)
        )
        lengths = {len(c.text.split()) for c in chunks}
        self.assertEqual(lengths, {1, 2})


if __name__ == "__main__":
    unittest.main()
