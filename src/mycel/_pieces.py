"""Report the parser's pieces from one working file and its pinned HEAD blob."""

from hashlib import sha256

from ._capture import CapturedFile, capture_file_versions
from ._cli import Invocation, Result
from ._errors import MycelError
from ._markdown import MarkdownDocument
from ._source_refs import SourceAddressError, parse_source_address


def _side(file: CapturedFile | None) -> dict:
    if file is None:
        return {"present": False, "pieces": []}
    parsed = file.parsed
    if parsed is None:
        raise MycelError("internal", "A captured file version has no parsed pieces.")
    if isinstance(parsed, MarkdownDocument):
        pieces = [{"name": chunk.name, "lineStart": chunk.span.line_start,
                   "lineEnd": chunk.span.line_end, "sha256": chunk.snapshot_hash}
                  for chunk in parsed.chunks]
    else:
        pieces = [{"name": chunk.symbol, "lineStart": chunk.line_start,
                   "lineEnd": chunk.line_end,
                   "sha256": sha256(file.source[chunk.byte_start:chunk.byte_end]).hexdigest()}
                  for chunk in parsed]
    return {"present": True, "pieces": pieces}


def handle_pieces(invocation: Invocation) -> Result:
    if invocation.settings is None:
        raise MycelError("internal", "Settings were not loaded for this invocation.")
    reference, = invocation.arguments
    try:
        address = parse_source_address(reference)
    except SourceAddressError as error:
        raise MycelError("invalid_input", str(error)) from None
    head, working, committed = capture_file_versions(invocation.settings, address)
    return Result({"path": address.address, "headCommit": head,
                   "working": _side(working), "committed": _side(committed)})
