import unittest

from patch.streaming import SentenceAssembler


class SentenceAssemblerTests(unittest.TestCase):
    def test_emits_sentences_as_tokens_arrive(self) -> None:
        assembler = SentenceAssembler()
        tokens = ["Hello there", ", friend. ", "How are ", "you today? ", "I am"]
        sentences = []
        for token in tokens:
            sentences.extend(assembler.feed(token))
        self.assertEqual(sentences, ["Hello there, friend.", "How are you today?"])
        self.assertEqual(assembler.flush(), ["I am"])

    def test_short_fragment_merges_into_next_sentence(self) -> None:
        assembler = SentenceAssembler()
        sentences = assembler.feed("Hi! It is really nice to see you again today. ")
        self.assertEqual(sentences, ["Hi! It is really nice to see you again today."])

    def test_flush_empty_buffer(self) -> None:
        assembler = SentenceAssembler()
        self.assertEqual(assembler.flush(), [])

    def test_question_and_exclamation_boundaries(self) -> None:
        assembler = SentenceAssembler()
        sentences = assembler.feed("What a wonderful day outside! Should we go for a walk now? ")
        self.assertEqual(
            sentences,
            ["What a wonderful day outside!", "Should we go for a walk now?"],
        )


if __name__ == "__main__":
    unittest.main()
