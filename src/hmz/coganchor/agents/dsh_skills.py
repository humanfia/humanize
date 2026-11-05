"""The stock DSH skill provider's static user configuration, without loading plugins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import yaml

from .dsh_yaml import CoreLoader

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["configuration"]

_ID = "skill-filesystem"
_PACKAGE = "@deepseek-ai/dsh-skill-filesystem"
_STRINGS = {"providerName", "dshHome", "agentsHome", "bundledSkillDir"}
_BOOLEANS = {
    "includeDefaultRoots",
    "watch",
    "watchUsePolling",
    "watchFollowSymlinks",
}
_NUMBERS = {"watchStabilityThresholdMs", "watchPollIntervalMs", "watchMaxProjects"}


class _Expression:
    """A runtime expression, deliberately never evaluated by a configuration reader."""


class _PatchLoader(CoreLoader):
    """Keep unrelated plugin expressions opaque while reading the skill row."""


_PatchLoader.add_constructor(
    "tag:yaml.org,2002:js", lambda _loader, _node: _Expression()
)


def configuration(home: Path) -> dict[str, Any] | None:
    """Read the stock provider after the SDK-profile and home user patch layers.

    Cordis overrides replace a row's entire config, and a patch's optional name is an
    assertion, not a rename. No other plugin or credential configuration is returned or
    executed. Relative paths remain relative to the runtime's working directory.

    Args:
      home: The user's original DSH home, before session storage redirects it.

    Returns:
      The static provider configuration, empty for the package defaults, or None where
      the user disabled the provider.

    Raises:
      ValueError: A patch is unreadable or invalid, or the skill row uses dynamic expressions,
        insertion, context overrides or other configuration this reader cannot preserve.
        Such a row must never silently become a provider with default roots enabled.
    """
    row: dict[str, Any] = {}
    for path in (
        home / "profiles" / "sdk" / "cordis.patch.yml",
        home / "cordis.patch.yml",
    ):
        for patch in _patches(path):
            if "insert" in patch:
                if patch.get("id") == _ID or _contains_provider(patch["insert"]):
                    raise ValueError(
                        f"unsupported dsh skill provider insertion in {path}"
                    )
                continue
            if isinstance(patch.get("id"), (dict, list, _Expression)):
                raise ValueError(  # noqa: TRY004 -- all configuration failures share one API
                    f"dynamic dsh patch id cannot be inspected in {path}"
                )
            if patch.get("id") != _ID:
                continue
            name = patch.get("name")
            if name and name != _PACKAGE:
                if isinstance(name, str):
                    continue
                raise ValueError(f"dynamic dsh skill provider name in {path}")
            row.update(
                {
                    key: value
                    for key, value in patch.items()
                    if key not in {"id", "name"}
                }
            )
    if set(row) - {"config", "disabled", "group"}:
        raise ValueError("unsupported dsh skill provider row options")
    for key in ("disabled", "group"):
        if row.get(key) is not None and not isinstance(row[key], bool):
            raise ValueError(f"dsh skill provider {key} must be a static boolean")
    if row.get("group"):
        raise ValueError("unsupported dsh skill provider group override")
    if row.get("disabled"):
        return None
    value = row.get("config", {})
    if not isinstance(value, dict) or "__jsExpr" in value:
        raise ValueError("dsh skill provider config must be a static mapping")
    config = cast("dict[str, Any]", value)
    for key, value in config.items():
        valid = (
            (key in _STRINGS and isinstance(value, str))
            or (key in _BOOLEANS and isinstance(value, bool))
            or (
                key in _NUMBERS
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            )
            or (
                key == "customSkillDirs"
                and isinstance(value, list)
                and all(isinstance(item, str) for item in cast("list[Any]", value))
            )
        )
        if not valid:
            raise ValueError(
                f"unsupported or dynamic dsh skill provider setting {key!r}"
            )
    return config


def _patches(path: Path) -> list[dict[str, Any]]:
    """Read one native patch list; absent layers are empty, broken layers are errors."""
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError) as why:
        raise ValueError(f"cannot read dsh skill configuration in {path}") from why
    try:
        parsed: Any = yaml.load(source, Loader=_PatchLoader)  # noqa: S506 -- SafeLoader subclass
    except (yaml.YAMLError, ValueError):
        raise ValueError(f"invalid dsh skill configuration in {path}") from None
    if not isinstance(parsed, list) or any(
        not isinstance(item, dict) for item in cast("list[Any]", parsed)
    ):
        raise ValueError(f"dsh patch must be a list of mappings in {path}")
    return cast("list[dict[str, Any]]", parsed)


def _contains_provider(value: Any) -> bool:
    """Whether an insertion contains a skill provider or overrides its stock identity."""
    if isinstance(value, list):
        return any(_contains_provider(item) for item in cast("list[Any]", value))
    if isinstance(value, dict):
        row = cast("dict[str, Any]", value)
        return (
            row.get("id") == _ID
            or row.get("name") == _PACKAGE
            or (bool(row.get("group")) and _contains_provider(row.get("config")))
        )
    return False
