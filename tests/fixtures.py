"""Private automatic-check fixtures; never shipped as product adapters.

The repository builder may mutate only its generated checkout. The embedding
stand-in accepts the same finite request contract as Voyage while using the
caller's exact packaged token counter, never a network endpoint.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable, Iterator, Mapping, Sequence
import unicodedata


class EmbeddingFixtureFailure(RuntimeError):
    """An explicitly injected service fault, without a provider response body."""

    def __init__(self, kind: str):
        self.kind = kind
        super().__init__("Fictional embedding service failure: " + kind)


@dataclass(frozen=True)
class EmbeddingAttempt:
    inputs: tuple[str, ...]
    model: str
    dimensions: int
    input_type: str
    tokens: tuple[int, ...]
    submitted_tokens: tuple[int, ...]
    failure: str | None


class EmbeddingStandIn:
    """Deterministic word-sharing vectors with exact model-limit checks."""

    FAILURES = frozenset({"connection", "deadline", "rate_limit", "server", "content",
                          "authentication", "authorization", "missing_model"})

    def __init__(self, count_tokens: Callable[[str, str], int | tuple[int, int]], *,
                 model: str = "voyage-code-4", input_cap: int = 31_744,
                 batch_cap: int = 31_744, inputs_cap: int = 64):
        if not callable(count_tokens):
            raise TypeError("fixtures require the exact packaged token counter")
        if any(type(value) is not int or value < 1 for value in (input_cap, batch_cap, inputs_cap)):
            raise ValueError("fixture caps must be positive integers")
        self.count_tokens = count_tokens
        self.model = model
        self.input_cap = input_cap
        self.batch_cap = batch_cap
        self.inputs_cap = inputs_cap
        self.attempts: list[EmbeddingAttempt] = []
        self._failures: dict[int, str] = {}
        self.reject_input: Callable[[str], bool] | None = None
        self.response_mutator: Callable[[dict], dict] | None = None

    def fail_attempt(self, number: int, kind: str) -> None:
        if type(number) is not int or number < 1 or kind not in self.FAILURES:
            raise ValueError("unknown fixture failure or attempt number")
        self._failures[number] = kind

    @staticmethod
    def vector(text: str, dimensions: int) -> list[float]:
        """Stable signed feature hashing; shared words retain shared features."""
        if type(dimensions) is not int or dimensions < 1:
            raise ValueError("fixture dimensions must be positive")
        words = re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())
        counts = Counter(words or ["<empty>"])
        result = [0.0] * dimensions
        for word, count in sorted(counts.items()):
            digest = sha256(word.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % dimensions
            result[index] += count if digest[8] & 1 else -count
        length = math.sqrt(sum(value * value for value in result))
        if not length:
            result[0] = 1.0
            length = 1.0
        return [value / length for value in result]

    def embed(self, inputs: Sequence[str], *, model: str, dimensions: int,
              input_type: str, output_dtype: str = "float", truncation: bool = False) -> dict:
        if isinstance(inputs, (str, bytes)) or not inputs or not all(isinstance(x, str) for x in inputs):
            raise ValueError("fixture inputs must be a nonempty sequence of complete texts")
        if model != self.model:
            raise EmbeddingFixtureFailure("missing_model")
        if dimensions not in (256, 512, 1024, 2048) or type(dimensions) is not int:
            raise ValueError("unsupported fixture dimensions")
        if input_type not in {"document", "query"} or output_dtype != "float" or truncation is not False:
            raise ValueError("fixture requests must explicitly disable truncation")
        texts = tuple(inputs)
        counted = tuple(self.count_tokens(text, input_type) for text in texts)
        pairs = tuple((value, value) if type(value) is int else value for value in counted)
        if any(not isinstance(value, tuple) or len(value) != 2
               or any(type(count) is not int or count < 0 for count in value) for value in pairs):
            raise ValueError("the fixture counter must return complete-input token counts")
        submitted = tuple(value[0] for value in pairs)
        tokens = tuple(max(value) for value in pairs)
        fault = self._failures.get(len(self.attempts) + 1)
        if (len(texts) > self.inputs_cap or any(value > self.input_cap for value in tokens)
                or sum(tokens) > self.batch_cap
                or self.reject_input is not None and any(self.reject_input(text) for text in texts)):
            fault = "content"
        self.attempts.append(EmbeddingAttempt(texts, model, dimensions, input_type, tokens, submitted, fault))
        if fault:
            raise EmbeddingFixtureFailure(fault)
        response = {"object": "list", "model": model,
                    "data": [{"object": "embedding", "index": index,
                              "embedding": self.vector(text, dimensions)}
                             for index, text in enumerate(texts)],
                    "usage": {"total_tokens": sum(submitted)}}
        return self.response_mutator(response) if self.response_mutator else response

    def request(self, body: Mapping) -> dict:
        """Test adapters inject this callable rather than an alternate URL."""
        required = {"input", "model", "output_dimension", "output_dtype", "input_type", "truncation"}
        if set(body) != required:
            raise ValueError("fixture request contract has missing or unknown fields")
        return self.embed(body["input"], model=body["model"], dimensions=body["output_dimension"],
                          output_dtype=body["output_dtype"], input_type=body["input_type"],
                          truncation=body["truncation"])


@dataclass(frozen=True)
class RepositoryFixture:
    root: Path
    code: Path
    artifacts: Path
    overlapping_artifacts: Path
    branch: str
    base_commit: str
    second_commit: str
    stash_commit: str

    def snapshot(self) -> dict[str, str]:
        """Observe every file, including Git metadata, to detect mutation."""
        return {str(path.relative_to(self.root)): sha256(path.read_bytes()).hexdigest()
                for path in sorted(self.root.rglob("*")) if path.is_file()}


@contextmanager
def repository_fixture() -> Iterator[RepositoryFixture]:
    """Make fictional checkout/branch/stash data with overlapping roots."""
    executable = shutil.which("git", path="/usr/bin:/bin")
    if not executable:
        raise RuntimeError("Git is required for the fictional repository fixture")
    with tempfile.TemporaryDirectory(prefix="mycel_check_repositories_") as directory:
        root = Path(directory)
        code = root / "checkout"
        artifacts = root / "artifacts"
        code.mkdir()
        artifacts.mkdir()
        (code / "docs").mkdir()
        (code / "src").mkdir()
        (code / "README.md").write_text("# Checkout\n\nDisk and base branch text.\n", encoding="utf-8")
        (code / "docs/guide.md").write_text("# Guide\n\nA checkout document.\n", encoding="utf-8")
        (code / "src/worker.py").write_text("def work():\n    return 'base'\n", encoding="utf-8")
        (artifacts / "README.md").write_text("# Artifact\n\nA distinct same-relative-path file.\n", encoding="utf-8")
        home = root / "home"
        home.mkdir()
        env = {**os.environ, "PATH": "/usr/bin:/bin", "LC_ALL": "C",
               "GIT_TERMINAL_PROMPT": "0"}

        def setup(*args: str) -> str:
            reply = subprocess.run([executable, *args], cwd=code, env=env, check=False,
                                   capture_output=True, timeout=10)
            if reply.returncode:
                raise RuntimeError("fictional Git fixture could not be prepared")
            return reply.stdout.decode("utf-8").strip()

        setup("init", "--initial-branch=fixture-base")
        setup("add", "--", "README.md", "docs/guide.md", "src/worker.py")
        setup("commit", "--message", "Base fixture")
        base_commit = setup("rev-parse", "HEAD")
        setup("checkout", "-b", "fixture-second")
        (code / "README.md").write_text("# Checkout\n\nSecond branch text.\n", encoding="utf-8")
        setup("add", "--", "README.md")
        setup("commit", "--message", "Second fixture")
        second_commit = setup("rev-parse", "HEAD")
        setup("checkout", "fixture-base")
        (code / "docs/guide.md").write_text("# Guide\n\nStashed guide text.\n", encoding="utf-8")
        setup("stash", "push", "--message", "Fixture stash")
        stash_commit = setup("rev-parse", "refs/stash")
        yield RepositoryFixture(root, code, artifacts, code / "docs", "fixture-base",
                                base_commit, second_commit, stash_commit)
