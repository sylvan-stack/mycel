"""Deterministic directory outlines from already stored structural records."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from ._errors import MycelError


def normalize_directory(value: str) -> str:
    if (not isinstance(value, str) or not value or '\0' in value
            or PurePosixPath(value).is_absolute()):
        raise MycelError('invalid_input', 'Overview requires a relative directory inside the code root.')
    parts = []
    for part in value.split('/'):
        if part in {'', '.'}:
            continue
        if part == '..':
            if not parts:
                raise MycelError('invalid_input', 'The overview directory escapes the code root.')
            parts.pop()
        else:
            parts.append(part)
    return '/'.join(parts) or '.'


@dataclass(frozen=True)
class OverviewSymbol:
    name: str
    kind: str
    position: int
    family: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class OverviewFile:
    path: str
    symbols: tuple[OverviewSymbol, ...] = ()


def _named(symbol):
    return (symbol.kind not in {'file', 'module', 'markup', 'script', 'style'}
            and bool(symbol.name) and not any(part.startswith('<') and part.endswith('>')
                                              for part in symbol.name.split('.')))


def _name(symbol):
    return symbol.name if symbol.display_name is None else symbol.display_name


def _escape(value):
    return ''.join('\\' + character if character in '\\`*_{}[]<>#' else
                   ' ' if character in '\r\n' else character for character in value)


def _limited(symbols, display):
    shown = [display(symbol) for symbol in symbols[:8]]
    if len(symbols) > 8:
        shown.append(f'+{len(symbols) - 8} more')
    return ', '.join(shown)


def render_sections(files: tuple[OverviewFile, ...]) -> tuple[dict, ...]:
    """All named declarations count, including declarations outside either cap."""
    grouped = {}
    for file in sorted(files, key=lambda item: item.path):
        parent = str(PurePosixPath(file.path).parent)
        grouped.setdefault(parent, []).append(file)
    sections = []
    for directory, members in sorted(grouped.items()):
        lines, count = [f'## {_escape(directory)}', ''], 0
        for file in members:
            symbols = tuple(symbol for symbol in file.symbols if _named(symbol))
            count += len(symbols)
            classes = sorted((symbol for symbol in symbols if symbol.kind == 'class'),
                             key=lambda symbol: (_name(symbol), symbol.position))
            methods = {symbol: [] for symbol in classes}
            other = []
            for symbol in symbols:
                if symbol.kind == 'class':
                    continue
                owners = [owner for owner in classes if owner.position <= symbol.position
                          and symbol.family in {owner.name, re.sub(r':(?:[2-9]|[1-9][0-9]+)$', '', owner.name)}]
                if symbol.kind == 'method' and owners:
                    methods[max(owners, key=lambda owner: owner.position)].append(symbol)
                else:
                    other.append(symbol)
            order = lambda symbol: (symbol.position, _name(symbol))
            descriptions = []
            for symbol in classes:
                children = sorted(methods[symbol], key=order)
                label = _escape(_name(symbol))
                if children:
                    label += ' (' + _limited(children,
                        lambda item: _escape(_name(item).rsplit('.', 1)[-1])) + ')'
                else:
                    label += ' [class]'
                descriptions.append(label)
            if other:
                descriptions.append(_limited(sorted(other, key=order),
                    lambda item: _escape(_name(item)) + ('' if item.kind == 'function'
                                                      else f' [{_escape(item.kind)}]')))
            line = '- **' + _escape(PurePosixPath(file.path).name) + '**'
            if descriptions:
                line += ' — ' + '; '.join(descriptions)
            lines.append(line)
        sections.append({'directory': directory, 'files': len(members),
                         'symbols': count, 'text': '\n'.join(lines) + '\n'})
    return tuple(sections)
