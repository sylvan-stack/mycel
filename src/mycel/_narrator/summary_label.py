"""Sentence labels for standalone Narrator."""

import unicodedata


WORD_LIMIT = 20
_SENTENCE_MARKS = frozenset(".!?。！？…‽")


def sentence_label(text: str) -> str:
    """Canonicalize and validate one short sentence, counting every word."""
    if not isinstance(text, str):
        raise ValueError("expected a sentence label")
    words = text.split()
    label = " ".join(words)
    if (not 0 < len(words) <= WORD_LIMIT
            or not any(character.isalnum() for character in label)
            or label[-1:] not in _SENTENCE_MARKS
            or any(character in _SENTENCE_MARKS for character in label[:-1])
            or any(unicodedata.category(character) == "Cc" for character in label)):
        raise ValueError("expected one sentence of at most 20 words")
    return label
