"""CI restores a Rust cache `cache.yml` saves, as `CONTRIBUTING.md` says.

`.github/workflows/ci.yml` writes no cache: every `Swatinem/rust-cache` step in it restores
what `.github/workflows/cache.yml` saved on `main`. That action names a cache after its
`shared-key`, or the job's id where there is none, then the runner. Read here: a step in
`ci.yml` whose name no job of `cache.yml` saves under restores nothing, and builds its crate
cold on every run; and a cache whose manifest a push to `main` may change without starting
`cache.yml` stays stale until the weekly run.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

#: The tree being read: the repository `tests/` is in.
ROOT = Path(__file__).resolve().parents[2]

#: A Rust cache: the name the action keys it by, the runner, and the workspace it holds.
type Cache = tuple[str, str, str]


def _workflow(name: str) -> dict[Any, Any]:
    return cast(
        "dict[Any, Any]",
        yaml.safe_load((ROOT / ".github/workflows" / name).read_text()),
    )


def _caches(name: str) -> dict[Cache, str]:
    """Every Rust cache the workflow's jobs name, each with the job that names it."""
    caches: dict[Cache, str] = {}
    jobs = cast("dict[str, dict[str, Any]]", _workflow(name)["jobs"])
    for job_id, job in jobs.items():
        runners = (
            cast("list[str]", job["strategy"]["matrix"]["os"])
            if "matrix.os" in job["runs-on"]
            else [cast("str", job["runs-on"])]
        )
        for step in cast("list[dict[str, Any]]", job["steps"]):
            if not str(step.get("uses", "")).startswith("Swatinem/rust-cache@"):
                continue
            given = cast("dict[str, Any]", step["with"])
            for runner in runners:
                key = (given.get("shared-key", job_id), runner, given["workspaces"])
                caches[key] = job_id
    return caches


def _restored() -> list[Any]:
    return [
        pytest.param(cache, id=f"{job} on {cache[1]}")
        for cache, job in _caches("ci.yml").items()
    ]


@pytest.mark.parametrize("cache", _restored())
def test_a_rust_cache_ci_restores_is_one_cache_yml_saves(cache: Cache) -> None:
    assert cache in _caches("cache.yml"), f"no job of cache.yml saves {cache}"


def test_a_push_that_changes_a_rust_cache_s_manifest_starts_cache_yml() -> None:
    # PyYAML reads the bare key `on` as a boolean.
    starts = set(cast("list[str]", _workflow("cache.yml")[True]["push"]["paths"]))
    manifests = {
        f"{workspace}/{manifest}"
        for _, _, workspace in _caches("cache.yml")
        for manifest in ("Cargo.toml", "Cargo.lock")
    }

    assert not sorted(manifests - starts)
