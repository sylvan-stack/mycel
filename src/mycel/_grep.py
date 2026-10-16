"""Literal system grep followed by a failure-contained, read-only search tail.

The option grammar only decides whether an informational tail is safe. It
never supplies, removes or rewrites an argument passed to the system program.
No settings, credential, provider or store is needed to run grep itself.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from ._errors import MycelError


_SHORT_VALUES = frozenset('efmABCDd')
_SHORT_SWITCHES = frozenset('EFGPiyvwxsnbHhrRaIoqLlcuUzZVT')
_LONG_VALUES = frozenset({'regexp', 'file', 'max-count', 'after-context', 'before-context', 'context',
    'binary-files', 'devices', 'directories', 'label', 'include', 'exclude', 'exclude-from', 'exclude-dir'})
_LONG_SWITCHES = frozenset({'extended-regexp', 'fixed-strings', 'basic-regexp', 'perl-regexp',
    'ignore-case', 'no-ignore-case', 'invert-match', 'word-regexp', 'line-regexp', 'null-data',
    'no-messages', 'quiet', 'silent', 'count', 'files-with-matches', 'files-without-match',
    'only-matching', 'line-number', 'byte-offset', 'with-filename', 'no-filename', 'initial-tab',
    'unix-byte-offsets', 'recursive', 'dereference-recursive', 'text', 'binary', 'help', 'version',
    'line-buffered', 'null', 'mmap'})
_LONG_OPTIONAL = frozenset({'color', 'colour'})
_NO_LINES_SHORT = frozenset('clLqV')
_NO_LINES_LONG = frozenset({'count', 'files-with-matches', 'files-without-match', 'quiet', 'silent',
                          'help', 'version'})
_SIGNS = frozenset('\\.^$*+?{}[]|()')


@dataclass(frozen=True)
class GrepSelection:
    pattern: str | None
    paths: tuple[str, ...] = ()
    reason: str | None = None

    @property
    def eligible(self) -> bool:
        """Grammar eligibility; query length and repository are checked later."""
        return self.reason is None and self.pattern is not None


def parse_grep_args(arguments: Sequence[str]) -> GrepSelection:
    """Recognize common GNU/BSD/POSIX forms; unknown syntax has no tail.

    Options may follow operands. Collect those operands before selecting the
    first explicit regexp, so ``path -e pattern`` keeps path as a path. Values
    attached to short options consume the rest of their cluster; optional long
    values consume only their equals form. ``--`` ends every option rule.
    """
    if isinstance(arguments, (str, bytes)):
        return GrepSelection(None, reason='unknown_option')
    args = tuple(arguments)
    if any(not isinstance(arg, str) or '\0' in arg for arg in args):
        return GrepSelection(None, reason='unknown_option')
    explicit, operands, reason = None, [], None
    options, index = True, 0
    while index < len(args):
        argument = args[index]
        index += 1
        if options and argument == '--':
            options = False
            continue
        if not options or argument == '-' or not argument.startswith('-'):
            operands.append(argument)
            continue
        if argument.startswith('--'):
            name, equals, attached = argument[2:].partition('=')
            if name in _LONG_VALUES:
                if equals:
                    value = attached
                elif index < len(args):
                    value, index = args[index], index + 1
                else:
                    return GrepSelection(None, reason='missing_option_value')
                if name == 'regexp' and explicit is None:
                    explicit = value
                elif name == 'file':
                    reason = 'pattern_file'
            elif name in _LONG_OPTIONAL:
                if equals and attached not in {'always', 'never', 'auto'}:
                    return GrepSelection(None, reason='unknown_option')
            elif name in _LONG_SWITCHES and not equals:
                if name in _NO_LINES_LONG:
                    reason = reason or 'non_matching_output'
            else:
                return GrepSelection(None, reason='unknown_option')
            continue
        cluster, offset = argument[1:], 0
        while offset < len(cluster):
            option = cluster[offset]
            offset += 1
            if option in _SHORT_VALUES:
                if offset < len(cluster):
                    value, offset = cluster[offset:], len(cluster)
                elif index < len(args):
                    value, index = args[index], index + 1
                else:
                    return GrepSelection(None, reason='missing_option_value')
                if option == 'e' and explicit is None:
                    explicit = value
                elif option == 'f':
                    reason = 'pattern_file'
            elif option in _SHORT_SWITCHES:
                if option in _NO_LINES_SHORT:
                    reason = reason or 'non_matching_output'
            elif option.isascii() and option.isdigit() and cluster[offset - 1:].isdigit():
                # The historical numeric context shorthand is an option,
                # never the query or a path. Ambiguous forms fail closed.
                offset = len(cluster)
            else:
                return GrepSelection(None, reason='unknown_option')
    if explicit is not None:
        return GrepSelection(explicit, tuple(operands), reason)
    if operands:
        return GrepSelection(operands[0], tuple(operands[1:]), reason)
    return GrepSelection(None, reason=reason or 'no_pattern')


def _without_signs(pattern: str) -> str:
    characters, in_class = [], False
    for character in pattern:
        if character == '[':
            in_class = True
        if character in _SIGNS or character == '-' and in_class:
            characters.append(' ')
        else:
            characters.append(character)
        if character == ']':
            in_class = False
    return ''.join(characters)


def semantic_query(pattern: str) -> str | None:
    """Keep dotted names exact; other regexp signs become word separators."""
    if not isinstance(pattern, str):
        return None
    plain = _without_signs(pattern)
    if sum(not character.isspace() for character in plain) < 3:
        return None
    if not any(character in _SIGNS - {'.'} for character in pattern):
        return pattern
    return ' '.join(plain.split())


def resolve_tail_repository(settings, paths: Sequence[str] = (), *, cwd=None) -> str | None:
    """Select the actual first-path/CWD repository, excluding organizations."""
    from ._scope import RepositoryLocations

    settings.require_valid()
    try:
        current = (Path.cwd() if cwd is None else Path(cwd)).resolve()
        anchor = (current / paths[0]).resolve() if paths and paths[0] != '-' else current
        locations = RepositoryLocations(settings)
        selected = locations.resolve_scope(cwd=anchor)
        if len(selected) != 1 or not selected[0].enabled:
            return None
        repository = selected[0]
        # An organization with one member also returns one record. Only an
        # actual repository folder may authorize this command's tail.
        bindings = [(len(folder.path.resolve().parts), 1)
                    for folder in (repository.code, repository.documents) if folder is not None
                    and anchor.is_relative_to(folder.path.resolve())]
        organizations = [(len(root.resolve().parts), 0)
                         for organization in locations.organizations
                         for root in (organization.root, organization.documents)
                         if anchor.is_relative_to(root.resolve())]
        if not bindings or organizations and max(organizations) > max(bindings):
            return None
        repository.require_folders()
        return repository.name
    except MycelError as error:
        if error.code in {'unknown_repository', 'refused'}:
            return None
        raise
    except (OSError, ValueError, RuntimeError):
        return None


def _one_line(value) -> str:
    if not isinstance(value, str):
        raise MycelError('internal', 'The related search returned an incompatible place.')
    return ''.join(character if character.isprintable() else '\\u' + format(ord(character), '04x')
                   for character in value)


def _label(place, *, document=False):
    if not isinstance(place, Mapping):
        raise MycelError('internal', 'The related search returned an incompatible place.')
    if all(isinstance(place.get(key), str) for key in ('repository', 'root', 'path')):
        value = place['repository'] + ':@' + place['root'] + '/' + place['path']
        name = place.get('name')
        if name is not None:
            value += (' › ' if document else '#') + _one_line(name)
        return _one_line(value)
    return _one_line(place.get('address'))


def _marks(place):
    return (' ⚠ stale' if place.get('stale') else '') + (' [heartwood]' if place.get('heartwood') else '')


def render_tail(payload) -> str:
    """Render normal ordered results and each cited section once; no scores."""
    from ._search_reply import SEARCH_REPLY

    if (not isinstance(payload, Mapping) or payload.get('schema') != SEARCH_REPLY
            or not isinstance(payload.get('results'), list) or len(payload['results']) > 5):
        raise MycelError('internal', 'The related search returned an incompatible reply.')
    if not payload['results']:
        return ''
    meaning = payload.get('meaning')
    description = ('wording only' if isinstance(meaning, Mapping) and meaning.get('used') is False
                   else 'not grep output')
    lines = ['── mycel: related search results (' + description + ') ──']
    documents = {}
    for result in payload['results']:
        if not isinstance(result, Mapping):
            raise MycelError('internal', 'The related search returned an incompatible reply.')
        line = '  ' + _label(result, document=result.get('origin') == 'document')
        span = result.get('lines')
        if result.get('origin') == 'code' and span is not None:
            if (not isinstance(span, Mapping) or type(span.get('start')) is not int
                    or type(span.get('end')) is not int or not 1 <= span['start'] <= span['end']):
                raise MycelError('internal', 'The related search returned incompatible code lines.')
            line += '  L' + str(span['start']) + '-' + str(span['end'])
        line += _marks(result)
        via = result.get('via')
        if via is not None:
            line += '  ⇐ via ' + _label(via, document=True) + _marks(via)
        lines.append(line)
        cited = result.get('documentedIn', [])
        if not isinstance(cited, list):
            raise MycelError('internal', 'The related search returned incompatible citations.')
        for document in [*cited, *((via,) if via is not None else ())]:
            label = _label(document, document=True)
            identifier = document.get('id')
            if identifier is not None and not isinstance(identifier, str):
                raise MycelError('internal', 'The related search returned an incompatible citation identity.')
            documents.setdefault(('id', identifier) if identifier else ('place', label), (label, _marks(document)))
    if documents:
        lines.append('── mycel: documented in ──')
        lines.extend('  ' + label + marks for label, marks in documents.values())
    # A PATH-selected grep may finish with bytes that have no final newline.
    # This delimiter belongs to the tail; the inherited grep prefix is intact.
    return '\n' + '\n'.join(lines) + '\n'


def search_tail(settings, query: str, repository: str):
    """Use one ordinary combined top-five search, with no freshness writes."""
    from ._cli import Invocation, invocation_store
    from ._freshness import Deadline
    from ._safeguards import InvocationPolicy
    from ._search import QueryEmbedding, prepare_query
    from ._search_store import search_from_store

    invocation = Invocation('grep', repositories=(repository,), settings=settings)
    with invocation_store(invocation) as (connection, inspection):
        if inspection.dimensions != settings.values['embedding']['dimensions']:
            embedding = QueryEmbedding(reason='The store vector dimensions differ from settings. Run mycel init before using meaning search.')
        else:
            embedding = prepare_query(settings, query, policy=InvocationPolicy('grep'))
        deadline = Deadline.after(settings.values['search']['freshness_seconds'])
        return search_from_store(connection, settings, query, (repository,),
            query_vector=embedding.vector, meaning_reason=embedding.reason,
            k=5, only=None, deadline=deadline, no_fresh=True)


def _quiet_failed_output(stream):
    """Prevent CPython's shutdown flush from changing grep's completed exit."""
    if stream is not sys.stdout and stream is not sys.stderr:
        return
    sink = None
    try:
        descriptor = stream.fileno()
        sink = os.open(os.devnull, os.O_WRONLY)
        if sink == descriptor:
            # A previously closed descriptor may itself be reused by open.
            # Keep that replacement alive for the interpreter's final flush.
            sink = None
        else:
            os.dup2(sink, descriptor)
        stream.flush()
    except BaseException:
        pass
    finally:
        if sink is not None:
            try:
                os.close(sink)
            except BaseException:
                pass


def _diagnostic(stream, message):
    try:
        stream.write('mycel grep: ' + _one_line(message) + '\n')
        stream.flush()
    except BaseException:
        _quiet_failed_output(stream)


def append_tail(invocation, status: int, *, stdout=None, stderr=None, settings_loader=None,
                search=None, cwd=None, environ=None) -> None:
    """Every optional failure ends here; the caller retains grep's status."""
    stdout, stderr = (sys.stdout if stdout is None else stdout), (sys.stderr if stderr is None else stderr)
    environment = os.environ if environ is None else environ
    if status not in {0, 1}:
        return
    writing = False
    try:
        if environment.get('MYCEL_GREP_PLAIN') == '1':
            return
        selected = parse_grep_args(invocation.arguments)
        if not selected.eligible:
            return
        query = semantic_query(selected.pattern)
        if query is None:
            return
        from ._settings import load_settings
        settings = invocation.settings
        if settings is None:
            settings = (settings_loader or load_settings)()
        settings.require_valid()
        repository = resolve_tail_repository(settings, selected.paths, cwd=cwd)
        if repository is None:
            return
        payload = (search_tail if search is None else search)(settings, query, repository)
        text = render_tail(payload)
        if text:
            writing = True
            stdout.write(text)
            stdout.flush()
    except KeyboardInterrupt:
        if writing:
            _quiet_failed_output(stdout)
        _diagnostic(stderr, 'The related search was stopped by the caller.')
    except BaseException as error:
        if writing:
            _quiet_failed_output(stdout)
        message = error.message if isinstance(error, MycelError) else 'The related search could not be completed.'
        _diagnostic(stderr, message)


def handle_grep(invocation, *, stdout=None, stderr=None):
    """Finish literal grep before loading any optional tail settings/services."""
    from ._cli import _plain_grep

    result = _plain_grep(invocation)
    append_tail(invocation, result.status, stdout=stdout, stderr=stderr)
    return result
