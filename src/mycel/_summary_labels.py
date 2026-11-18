"""Generate and retain sentence labels on exact RAPTOR summary versions."""

from ._evidence import EvidenceError
from ._narrator.summary_label import sentence_label
from ._summary_writer import SummaryWriter


class SummaryLabels:
    def __init__(self, settings, program, guard):
        self.writer = SummaryWriter(program.label_argv, settings.values["summaries"]["at_once"],
                                    before_launch=guard)

    def write_many(self, summaries: tuple[bytes, ...]) -> tuple[str | None, ...]:
        labels = []
        for result in self.writer.write_many(summaries):
            try:
                label = None if result.response is None else sentence_label(result.response.decode("utf-8"))
            except ValueError:
                label = None
            labels.append(label)
        return tuple(labels)


def stored_summary_label(value: object) -> str | None:
    if value is None:
        return None
    try:
        label = sentence_label(value)
    except ValueError:
        raise EvidenceError("snapshot_corrupt") from None
    if label != value:
        raise EvidenceError("snapshot_corrupt")
    return label


def read_summary_label(connection, version: int) -> str | None:
    row = connection.execute(
        "SELECT metadata->'summaryLabel' FROM public.mycel_chunk_versions WHERE id=%s", (version,)
    ).fetchone()
    return None if row is None else stored_summary_label(row[0])


def retain_summary_label(connection, version: int, label: str | None) -> None:
    """Fill a missing label under the caller's publication transaction."""
    if label is None:
        return
    label = stored_summary_label(label)
    row = connection.execute(
        "UPDATE public.mycel_chunk_versions v SET metadata=v.metadata || jsonb_build_object('summaryLabel', %s::text) "
        "FROM public.mycel_chunks c WHERE c.id=v.chunk_id AND c.kind='summary' AND v.id=%s "
        "AND NOT (v.metadata ? 'summaryLabel') RETURNING v.id", (label, version)
    ).fetchone()
    if row != (version,) and read_summary_label(connection, version) != label:
        raise EvidenceError("snapshot_corrupt")
