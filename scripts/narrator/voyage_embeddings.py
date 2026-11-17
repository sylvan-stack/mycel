"""Embed an ordered JSON array of claims with Voyage and report token usage."""

import argparse
from http.client import HTTPException, HTTPSConnection
import json
import sys
import time

from narrator import (
    ATTEMPT_SECONDS,
    EMBEDDING_OUTPUT_BYTES,
    MAX_CANDIDATES,
    MODEL_OUTPUT_BYTES,
    NarratorError,
    _embedding_vectors,
    _interrupt_on_termination,
    _read_stdin,
    _run_command,
    _time_left,
    command_argument,
)


# JSON ASCII escapes can expand the UTF-8 claim strings from the model reply.
INPUT_BYTES = 4 * MODEL_OUTPUT_BYTES
KEY_BYTES = 4_096
POST_TIMEOUT_SECONDS = 45


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise ValueError("invalid Voyage adapter arguments")


def _read_claims(deadline: float) -> list[str]:
    raw = _read_stdin(deadline, INPUT_BYTES)
    if len(raw) > INPUT_BYTES:
        raise ValueError("embedding input exceeds its byte limit")
    claims = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(claims, list) or not 1 <= len(claims) <= MAX_CANDIDATES
        or any(not isinstance(claim, str) or not claim.strip() for claim in claims)
    ):
        raise ValueError("expected a bounded array of claims")
    return claims


def _read_key(argv: tuple[str, ...], deadline: float) -> str:
    raw = _run_command(argv, b"", deadline, output_limit=KEY_BYTES, cleanup_grace=0)
    key = raw.decode("ascii").strip()
    if not key or any(not 33 <= ord(character) <= 126 for character in key):
        raise ValueError("invalid credential command response")
    return key


def _embed(claims: list[str], model: str, key: str, deadline: float) -> dict[str, object]:
    body = json.dumps({"input": claims, "model": model, "truncation": False}).encode("utf-8")
    connection = HTTPSConnection("api.voyageai.com", timeout=min(POST_TIMEOUT_SECONDS, _time_left(deadline)))
    try:
        connection.request("POST", "/v1/embeddings", body, {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        with connection.getresponse() as response:
            if response.status != 200:
                raise ValueError("Voyage request failed")
            raw = response.read(EMBEDDING_OUTPUT_BYTES + 1)
    finally:
        connection.close()
    if len(raw) > EMBEDDING_OUTPUT_BYTES:
        raise ValueError("Voyage response exceeds its byte limit")
    received = json.loads(raw.decode("utf-8"))
    if not isinstance(received, dict):
        raise ValueError("invalid Voyage response")
    rows = received.get("data")
    if not isinstance(rows, list) or len(rows) != len(claims):
        raise ValueError("Voyage returned the wrong number of rows")
    indexed: dict[int, object] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid Voyage response row")
        index = row.get("index")
        if type(index) is not int or not 0 <= index < len(claims) or index in indexed:
            raise ValueError("invalid Voyage response index")
        indexed[index] = row.get("embedding")
    vectors = _embedding_vectors([indexed[index] for index in range(len(claims))], len(claims))

    usage = received.get("usage")
    total = usage.get("total_tokens") if isinstance(usage, dict) else None
    _time_left(deadline)
    return {"response": vectors, "usage": {"total_tokens": total} if type(total) is int and total >= 0 else None}


def main() -> int:
    parser = _ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--model", required=True)
    parser.add_argument("--key-command", required=True, help="absolute executable and arguments as a JSON array")
    try:
        args = parser.parse_args()
        if not args.model.strip():
            raise ValueError("empty Voyage model")
        command = command_argument(args.key_command)
        deadline = time.monotonic() + ATTEMPT_SECONDS
        with _interrupt_on_termination():
            claims = _read_claims(deadline)
            key = _read_key(command, deadline)
            result = _embed(claims, args.model, key, deadline)
            output = json.dumps(result, allow_nan=False, separators=(",", ":"))
            _time_left(deadline)
            print(output)
    except (HTTPException, KeyboardInterrupt, NarratorError, OSError, RecursionError, ValueError):
        print("Voyage embedding adapter failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
