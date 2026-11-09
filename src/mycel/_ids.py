"""Store-wide identifier issuance and history under the checked store guard."""

from ._errors import ErrorCode, MycelError
from ._locks import atomic_transaction, identifier_allocation_guard, snapshot_transaction


FIRST_ISSUABLE = {"SYL": 341}


def issue_identifier(connection, series: str, purpose: str) -> str:
    """Allocate the next number and return its identifier after commit."""
    with identifier_allocation_guard(connection), atomic_transaction(connection):
        latest = connection.execute(
            "SELECT number FROM public.mycel_issued_identifiers "
            "WHERE series = %s ORDER BY number DESC LIMIT 1", (series,),
        ).fetchone()
        number = FIRST_ISSUABLE[series] if latest is None else latest[0] + 1
        if number >= 2**63:
            raise MycelError(ErrorCode.REFUSED, "This identifier series has no numbers left.")
        connection.execute(
            "INSERT INTO public.mycel_issued_identifiers (series, number, purpose) VALUES (%s, %s, %s)",
            (series, number, purpose),
        )
    return f"{series}-{number}"


def list_identifiers(connection, series: str) -> list[dict[str, str]]:
    """Read the committed issues for one series in number order."""
    with snapshot_transaction(connection):
        rows = connection.execute(
            "SELECT number, purpose FROM public.mycel_issued_identifiers WHERE series = %s ORDER BY number",
            (series,),
        ).fetchall()
    return [{"id": f"{series}-{number}", "for": purpose} for number, purpose in rows]
