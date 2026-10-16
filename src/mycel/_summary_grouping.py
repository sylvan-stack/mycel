"""The offline ``mycel-summary-v1`` grouping and estimated level planner.

Only retained vectors and explicit section payloads enter this module. It reads
no settings, source files or store, and starts no writer or embedding request.
The higher-level vectors are means, so a plan never claims generated text exists.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
import math
from numbers import Real
import os
from threading import RLock
import warnings

from ._errors import MycelError
from ._source_refs import SourceAddress, SourceAddressError
from ._summary_request import SummarySection


GROUPING_PROFILE = "mycel-summary-v1"
MAX_LEVELS = 5
TOP_NODES = 10
MEMBERSHIP_THRESHOLD = 0.10
NUMERICAL_PACKAGES = ("numpy", "scipy", "scikit-learn")
_NUMERICAL_LOCK = RLock()


@contextmanager
def _single_thread_environment():
    """Keep supported OpenMP configuration local to this numerical operation.

    Without an explicit OpenMP thread count sklearn can probe physical CPUs
    through a child process on some platforms. Native pool limits alone do not
    bypass that probe. Serialize environment changes and restore the caller's
    exact value, including absence, on every exit.
    """
    with _NUMERICAL_LOCK:
        previous = os.environ.get("OMP_NUM_THREADS")
        os.environ["OMP_NUM_THREADS"] = "1"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("OMP_NUM_THREADS", None)
            else:
                os.environ["OMP_NUM_THREADS"] = previous


def _invalid(reason="invalid_vectors"):
    raise MycelError("invalid_input", f"Summary grouping failed: {reason}.")


def _fit_failed():
    raise MycelError("refused", "Summary grouping failed: numerical_fit.")


def _vector(values) -> tuple[float, ...]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        _invalid()
    if any(not isinstance(value, Real) or isinstance(value, bool) for value in values):
        _invalid()
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        _invalid()
    if any(not math.isfinite(value) for value in result):
        _invalid()
    return result


def mean_vector(parts: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """Average complete multipart vectors without changing search vectors."""
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)) or not parts:
        _invalid()
    vectors = tuple(_vector(part) for part in parts)
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        _invalid()
    try:
        # Divide first: the mean of finite same-sign inputs can be representable
        # even when their unscaled sum would overflow.
        result = tuple(math.fsum(vector[column] / len(vectors) for vector in vectors)
                       for column in range(dimensions))
    except (OverflowError, ValueError):
        _invalid()
    return _vector(result)


@dataclass(frozen=True)
class SummaryNode:
    key: str
    place: SourceAddress
    position: int
    vector: tuple[float, ...]
    section: SummarySection | None = None

    def __post_init__(self):
        if (not isinstance(self.key, str) or not self.key or "\0" in self.key
                or not isinstance(self.place, SourceAddress) or self.place.root is None
                or self.place.name is None or type(self.position) is not int or self.position < 0):
            _invalid("invalid_members")
        try:
            self.place.address
        except SourceAddressError:
            _invalid("invalid_members")
        if self.section is not None and (not isinstance(self.section, SummarySection)
                or self.section.member.place != self.place or self.section.position != self.position):
            _invalid("invalid_members")
        object.__setattr__(self, "vector", _vector(self.vector))

    @property
    def order(self):
        return (self.place.root, self.place.path, self.position, self.place.address, self.key)


def _ordered(nodes: Sequence[SummaryNode]) -> tuple[SummaryNode, ...]:
    if (not isinstance(nodes, Sequence) or isinstance(nodes, (str, bytes))
            or any(not isinstance(node, SummaryNode) for node in nodes)):
        _invalid("invalid_members")
    if (len({node.key for node in nodes}) != len(nodes)
            or len({node.place.address for node in nodes}) != len(nodes)
            or len({node.place.repository for node in nodes}) > 1):
        _invalid("invalid_members")
    if nodes and any(len(node.vector) != len(nodes[0].vector) for node in nodes):
        _invalid()
    return tuple(sorted(nodes, key=lambda node: node.order))


def numerical_versions() -> dict[str, str]:
    """Actual installed numerical versions, retained alongside the profile."""
    try:
        return {package: version(package) for package in NUMERICAL_PACKAGES}
    except PackageNotFoundError:
        raise MycelError("settings", "Summary grouping numerical dependencies are unavailable.") from None


def group_summary_nodes(nodes: Sequence[SummaryNode]) -> tuple[tuple[SummaryNode, ...], ...]:
    """Soft Gaussian groups in component order, each with canonical members.

    An equal BIC leaves the smaller candidate selected. A probability tie in the
    fallback chooses the earlier component, and every member appears somewhere.
    Numerical failures are reported rather than changing the algorithm.
    """
    ordered = _ordered(nodes)
    count = len(ordered)
    if count <= 2:
        return (ordered,) if ordered else ()
    try:
        import numpy as np
        from sklearn.decomposition import PCA
        from sklearn.exceptions import ConvergenceWarning
        from sklearn.mixture import GaussianMixture
        from threadpoolctl import threadpool_limits
    except ImportError:
        raise MycelError("settings", "Summary grouping numerical dependencies are unavailable.") from None
    try:
        matrix = np.asarray(tuple(node.vector for node in ordered), dtype=np.float64)
        dimensions = min(10, matrix.shape[1], count - 1)
        maximum = min(150, count - 1, (count + 7) // 8)
        best, best_bic = None, math.inf
        # A single native thread also fixes reduction order across invocation
        # environments; the pinned distributions record the remaining runtime.
        with _single_thread_environment(), threadpool_limits(limits=1), warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            # Duplicate vectors can leave some fitted components empty while
            # still converging to a valid finite fit. Empty groups are discarded;
            # explicit convergence and finite-output checks report actual faults.
            warnings.simplefilter("ignore", category=ConvergenceWarning)
            if matrix.shape[1] > dimensions:
                matrix = PCA(n_components=dimensions, random_state=0).fit_transform(matrix)
            if not np.isfinite(matrix).all():
                _fit_failed()
            for components in range(1, maximum + 1):
                fitted = GaussianMixture(n_components=components, covariance_type="spherical",
                    reg_covar=1e-4, random_state=0).fit(matrix)
                if not fitted.converged_:
                    _fit_failed()
                bic = fitted.bic(matrix)
                if not math.isfinite(float(bic)):
                    _fit_failed()
                if bic < best_bic:
                    best, best_bic = fitted, bic
            probabilities = best.predict_proba(matrix)
        if (probabilities.shape != (count, best.n_components)
                or not np.isfinite(probabilities).all()
                or np.any(probabilities < 0) or np.any(probabilities > 1)
                or not np.allclose(probabilities.sum(axis=1), 1, rtol=0, atol=1e-8)):
            _fit_failed()
        groups = [[] for _ in range(best.n_components)]
        for node, row in zip(ordered, probabilities):
            assigned = [component for component, probability in enumerate(row)
                        if probability >= MEMBERSHIP_THRESHOLD]
            if not assigned:
                assigned = [int(np.argmax(row))]
            for component in assigned:
                groups[component].append(node)
        return tuple(tuple(group) for group in groups if group)
    except MycelError:
        raise
    except (ArithmeticError, ValueError, TypeError, RuntimeError, AttributeError):
        _fit_failed()


@dataclass(frozen=True)
class SummaryGroup:
    members: tuple[SummaryNode, ...]
    summary: SummaryNode

    def report(self):
        return {"summary": self.summary.place.address,
                "members": [member.place.address for member in self.members]}


@dataclass(frozen=True)
class SummaryLevel:
    level: int
    nodes_in: int
    groups: tuple[SummaryGroup, ...]
    moved_up: tuple[SummaryNode, ...]
    output_nodes: tuple[SummaryNode, ...]

    def report(self):
        return {"level": self.level, "nodesIn": self.nodes_in, "summaries": len(self.groups),
                "movedUp": len(self.moved_up), "groups": [group.report() for group in self.groups]}


@dataclass(frozen=True)
class SummaryPlan:
    sections: int
    levels: tuple[SummaryLevel, ...]
    numerical_versions: tuple[tuple[str, str], ...]
    profile: str = GROUPING_PROFILE

    @property
    def requests(self):
        return sum(len(level.groups) for level in self.levels)

    def report(self):
        return {"sections": self.sections, "levels": [level.report() for level in self.levels],
                "requests": self.requests, "estimated": True, "groupingProfile": self.profile,
                "numericalVersions": dict(self.numerical_versions)}


SplitGroup = Callable[[tuple[SummaryNode, ...], int], Sequence[Sequence[SummaryNode]]]


def plan_summary_levels(nodes: Sequence[SummaryNode], *, split_group: SplitGroup | None = None) -> SummaryPlan:
    """Estimate at most five levels using mean member vectors above each group.

    ``split_group`` can apply exact request framing to available section text.
    It must partition a statistical group, in its canonical order, retaining
    every member exactly once. A singleton statistical group moves up as-is;
    a singleton request part from a larger group still needs its own summary.
    """
    current = _ordered(nodes)
    sections = len(current)
    versions = tuple(numerical_versions().items())
    if split_group is not None and not callable(split_group):
        _invalid("invalid_split")
    levels = []
    for number in range(1, MAX_LEVELS + 1):
        if len(current) <= TOP_NODES:
            break
        grouped = group_summary_nodes(current)
        planned_parts, promoted = [], {}
        for members in grouped:
            if len(members) == 1:
                promoted.setdefault(members[0].key, members[0])
                continue
            parts = (members,) if split_group is None else split_group(members, number)
            if (not isinstance(parts, Sequence) or isinstance(parts, (str, bytes))
                    or not parts or any(not isinstance(part, Sequence) or not part for part in parts)):
                _invalid("invalid_split")
            try:
                ordered_parts = tuple(_ordered(part) for part in parts)
            except MycelError:
                _invalid("invalid_split")
            if any(tuple(part) != ordered for part, ordered in zip(parts, ordered_parts)):
                _invalid("invalid_split")
            parts = ordered_parts
            if tuple(member for part in parts for member in part) != members:
                _invalid("invalid_split")
            planned_parts.extend(parts)
        # Component labels are numerical fitting details. Public numbering is
        # fixed by the complete canonical member order, including request parts.
        planned_parts.sort(key=lambda part: tuple(member.order for member in part))
        summaries = []
        for ordinal, part in enumerate(planned_parts, 1):
            place = SourceAddress(part[0].place.repository, "index", "summaries", f"{number}/{ordinal}")
            summary = SummaryNode(f"summary:{number}/{ordinal}", place, ordinal,
                                  mean_vector(tuple(member.vector for member in part)))
            summaries.append(SummaryGroup(part, summary))
        moved_up = tuple(sorted(promoted.values(), key=lambda node: node.order))
        output = _ordered((*moved_up, *(group.summary for group in summaries)))
        levels.append(SummaryLevel(number, len(current), tuple(summaries), moved_up, output))
        current = output
        if not summaries:
            break
    return SummaryPlan(sections, tuple(levels), versions)
