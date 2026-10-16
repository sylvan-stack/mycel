"""Strict corpus ownership on exact file locations, with no shared default."""
from __future__ import annotations

from ._errors import MycelError


def corpus_value(value, *, code='store_format') -> str:
    if type(value) is not str or value not in ('documents', 'code'):
        raise MycelError(code, 'A file location has an incompatible corpus.')
    return value


def location_corpus(metadata, *, legacy=False) -> str | None:
    if type(metadata) is not dict:
        raise MycelError('store_format', 'A file location has incompatible metadata.')
    if legacy and 'corpus' not in metadata:
        return None
    return corpus_value(metadata.get('corpus'))


def require_captured_corpus(metadata, captured) -> None:
    if location_corpus(metadata) != corpus_value(captured.corpus, code='invalid_input'):
        raise MycelError('invalid_input', 'The file location corpus contradicts its checked capture.')
