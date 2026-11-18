"""Generate and retain sentence labels on exact RAPTOR summary versions."""

from ._errors import MycelError
from ._evidence import EvidenceError, exact_bytes
from ._locks import atomic_transaction, operation_guard, snapshot_transaction
from ._narrator.summary_label import sentence_label
from ._safeguards import InvocationPolicy, require_model_call
from ._summary_request import summary_command, summary_configuration_guard
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


def _unlabeled(connection, repository):
    rows = connection.execute(
        "SELECT v.id,v.snapshot_hash,v.source_bytes FROM public.mycel_chunk_versions v "
        "JOIN public.mycel_chunks c ON c.id=v.chunk_id "
        "JOIN public.mycel_generated_state g ON g.chunk_id=c.id AND g.kind='summary' "
        "JOIN public.mycel_locations l ON l.chunk_version=v.id AND l.kind='index' "
        "WHERE c.repository=%s AND c.kind='summary' AND NOT (v.metadata ? 'summaryLabel') ORDER BY v.id",
        (repository,),
    )
    return tuple((version, digest, exact_bytes(source)) for version, digest, source in rows)


def backfill_summary_labels(invocation, repository):
    """Fill missing labels for exact active versions without changing their content."""
    from ._cli import Result, invocation_store

    settings = invocation.settings
    require_model_call(InvocationPolicy("summaries", action="labels"), "summary")
    try:
        with invocation_store(invocation) as (connection, _), operation_guard(connection, repository, "summaries"):
            with snapshot_transaction(connection):
                captured = _unlabeled(connection, repository)
            if not captured:
                return Result({"repository": repository, "labeled": 0})

            program = summary_command(settings, operation="labels")
            guard = summary_configuration_guard(settings, "labels", program)
            labels = SummaryLabels(settings, program, guard).write_many(tuple(row[2] for row in captured))
            if any(label is None for label in labels):
                return Result({"repository": repository, "labeled": 0, "failed": labels.count(None)}, 1)

            with operation_guard(connection, repository, "pass"), atomic_transaction(connection):
                guard()
                if _unlabeled(connection, repository) != captured:
                    raise EvidenceError("inputs_changed")
                for (version, _, _), label in zip(captured, labels, strict=True):
                    retain_summary_label(connection, version, label)
                guard()
            return Result({"repository": repository, "labeled": len(labels)})
    except EvidenceError as error:
        if error.status == "inputs_changed":
            raise MycelError("busy", "The summaries or Narrator configuration changed during labeling.") from None
        raise MycelError("store_format", "A summary label could not be attached to its version.") from None
