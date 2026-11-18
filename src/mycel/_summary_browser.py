"""Read the published RAPTOR graph for a local, offline browser."""

from collections import defaultdict
from hashlib import sha256
from importlib.resources import files
import json
import os
from pathlib import Path
import tempfile

from ._errors import MycelError
from ._evidence import EvidenceError, exact_bytes
from ._resolver import require_read_transaction
from ._source_refs import parse_source_address
from ._summary_labels import stored_summary_label
from ._summary_store import PublishedSummaryState


_SUMMARIES = """
SELECT c.repository, c.id, v.id, v.snapshot_hash, v.source_bytes,
       l.location, g.state, v.metadata->'summaryLabel',
       EXISTS(SELECT 1 FROM public.mycel_stale_reasons s WHERE s.chunk_version=v.id)
FROM public.mycel_generated_state g
JOIN public.mycel_chunks c ON c.id=g.chunk_id AND c.repository=g.repository
JOIN public.mycel_chunk_versions v ON v.chunk_id=c.id
JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index'
WHERE g.kind='summary' AND c.kind='summary'
ORDER BY c.repository, v.id
"""

_VERSIONS = """
SELECT v.id, c.id, c.repository, v.snapshot_hash, v.source_bytes, v.metadata->'summaryLabel'
FROM public.mycel_chunk_versions v JOIN public.mycel_chunks c ON c.id=v.chunk_id
WHERE v.id=ANY(%s::bigint[])
"""

_SNAPSHOTS = """
SELECT repository, hash, bytes FROM public.mycel_snapshots
WHERE (repository, hash) IN (SELECT * FROM unnest(%s::text[], %s::text[]))
"""


def _incompatible():
    raise MycelError("store_format", "The published summary tree contains incompatible versioned text or links.")


def _text(raw, digest):
    source = exact_bytes(raw)
    if sha256(source).hexdigest() != digest:
        _incompatible()
    return source.decode("utf-8")


def _collect(connection) -> list[dict]:
    by_repository = defaultdict(dict)
    pins = {}
    orders = {}
    for repository, identifier, version, digest, raw, address, state, label, stale in connection.execute(_SUMMARIES):
        decoded = PublishedSummaryState.from_dict(state, repository=repository)
        place = parse_source_address(address)
        if (place.repository != repository or place.root != "index" or place.path != "summaries"
                or place.name is None or decoded.chunk_version != version):
            _incompatible()
        level, ordinal = map(int, place.name.split("/"))
        if level != decoded.level or ordinal < 1:
            _incompatible()
        identifier = str(identifier)
        nodes = by_repository[repository]
        if identifier in nodes:
            _incompatible()
        nodes[identifier] = {"address": address, "label": stored_summary_label(label) or address,
                             "text": _text(raw, digest), "summary": True, "stale": stale, "children": []}
        orders[identifier] = (level, ordinal)
        pins[identifier] = decoded.members

    wanted = {}
    for repository, nodes in by_repository.items():
        for identifier in nodes:
            for pin in pins[identifier]:
                if pin.chunk_id not in nodes:
                    wanted[(repository, pin.chunk_id, pin.chunk_version, pin.snapshot_hash)] = pin

    versions = {}
    if wanted:
        ids = sorted({key[2] for key in wanted})
        for version, identifier, repository, digest, raw, label in connection.execute(_VERSIONS, (ids,)):
            versions[(repository, str(identifier), version, digest)] = (raw, label)
    missing = sorted({(key[0], key[3]) for key in wanted.keys() - versions.keys()})
    snapshots = {}
    if missing:
        repositories, hashes = map(list, zip(*missing, strict=True))
        snapshots = {(repository, digest): raw for repository, digest, raw
                     in connection.execute(_SNAPSHOTS, (repositories, hashes))}

    trees = []
    for repository, nodes in sorted(by_repository.items()):
        summary_ids = sorted(nodes, key=orders.__getitem__)
        linked = set()
        for identifier in summary_ids:
            for pin in pins[identifier]:
                child = pin.chunk_id
                if child in orders:
                    if child not in nodes or orders[child][0] >= orders[identifier][0]:
                        _incompatible()
                    linked.add(child)
                else:
                    address = pin.place.address
                    child = f"source:{pin.chunk_version}:{address}"
                    if child not in nodes:
                        key = (repository, pin.chunk_id, pin.chunk_version, pin.snapshot_hash)
                        raw, label = versions.get(key, (snapshots.get((repository, pin.snapshot_hash)), None))
                        is_summary = pin.place.root == "index"
                        title = (stored_summary_label(label) or address if is_summary
                                 else pin.place.name or Path(pin.place.path).name)
                        nodes[child] = {"address": address, "label": title,
                                        "text": None if raw is None else _text(raw, pin.snapshot_hash),
                                        "summary": is_summary,
                                        "stale": False, "children": []}
                nodes[identifier]["children"].append(child)
        trees.append({"repository": repository, "roots": [key for key in summary_ids if key not in linked],
                      "nodes": nodes, "count": len(summary_ids)})
    return trees


def collect_summary_trees(connection) -> list[dict]:
    """Collect only published nodes and their retained children inside the caller's snapshot."""
    require_read_transaction(connection)
    try:
        return _collect(connection)
    except (EvidenceError, ValueError, TypeError):
        _incompatible()


def render_summary_browser(trees: list[dict], *, template_name: str = "summary-browser.html") -> str:
    template = files("mycel").joinpath("data", template_name).read_text(encoding="utf-8")
    payload = json.dumps(trees, separators=(",", ":")).replace("<", "\\u003c")
    placeholder = "__MYCEL_SUMMARY_DATA__"
    if template.count(placeholder) != 1:
        raise MycelError("internal", "The bundled summary browser template is invalid.")
    return template.replace(placeholder, payload, 1)


def write_summary_browser(output: Path, trees: list[dict], *, template_name: str = "summary-browser.html") -> None:
    """Publish a private standalone report without overwriting a previous export."""
    staged = None
    try:
        if output.exists() or output.is_symlink():
            raise FileExistsError
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".mycel-summary-browser-", delete=False) as stream:
            staged = Path(stream.name)
            stream.write(render_summary_browser(trees, template_name=template_name))
        os.link(staged, output)
    except FileExistsError:
        raise MycelError("refused", "The browser output file already exists.") from None
    except OSError:
        raise MycelError("io", "The browser output file could not be written.") from None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def summary_browser_output(filename: str) -> Path:
    try:
        output = Path(filename).expanduser().absolute()
    except (RuntimeError, ValueError):
        raise MycelError("invalid_input", "Choose a valid HTML output path.") from None
    if output.exists() or output.is_symlink():
        raise MycelError("refused", "The browser output file already exists.")
    return output


def export_summary_browser(invocation, filename: str):
    from ._cli import Result, invocation_store
    from ._locks import snapshot_transaction

    output = summary_browser_output(filename)
    with invocation_store(invocation) as (connection, _), snapshot_transaction(connection):
        trees = collect_summary_trees(connection)
    write_summary_browser(output, trees)
    return Result({"output": str(output), "trees": len(trees),
                   "summaries": sum(tree["count"] for tree in trees)})
