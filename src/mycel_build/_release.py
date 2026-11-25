"""Stage and publish the same frozen Mycel distribution."""

from pathlib import Path

from ._core import BuildError
from ._publication import publish
from ._registry import registry_path, update_staging
from ._staging import create_stage, source_inputs


def create_release(source_root: Path, lock_path: Path, assets: Path, registry: Path, target: str,
                   *, store_settings: Path | None = None) -> dict:
    """Publish a sealed Build from the source captured during staging."""
    root = registry_path(registry)
    record = create_stage(source_root, lock_path, assets, root, target)
    try:
        identity, frozen = source_inputs(source_root)
        if identity != record["source"]:
            raise BuildError("busy", "Source changed during packaging.")
    except (BuildError, OSError, KeyboardInterrupt) as error:
        try:
            error.partialResult = update_staging(
                root, record["build"], failed=True,
                fields={"reason": "Could not bind publication to the staged source."},
            )
        except (BuildError, OSError):
            pass
        raise
    return publish(root, record["build"], frozen=frozen, source_identity=identity)
