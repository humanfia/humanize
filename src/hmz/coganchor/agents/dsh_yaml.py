"""DSH's YAML core scalar rules for skill metadata and static provider configuration."""

from __future__ import annotations

import re
from typing import Any

import yaml

__all__ = ["CoreLoader"]


class CoreLoader(yaml.SafeLoader):
    """The runtime's YAML 1.2 strings, without changing other backends' YAML readers.

    The runtime's core schema keeps dates and YAML 1.1 booleans such as `yes` as strings.
    Its numbers include `1e3` and `0o7`, but not binary or underscored YAML 1.1 integers.
    """

    def core_int(self, node: yaml.ScalarNode) -> int:
        """Read decimal integers, including leading zeroes, and explicit octal or hex."""
        value = self.construct_scalar(node)
        base = 8 if value.startswith("0o") else 16 if value.startswith("0x") else 10
        return int(value, base)

    def core_float(self, node: yaml.ScalarNode) -> float:
        """Read core-schema floats, including signed infinities and NaNs."""
        value = self.construct_scalar(node).lower()
        return float(value.replace(".inf", "inf").replace(".nan", "nan"))


CoreLoader.yaml_implicit_resolvers = {
    first: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag.rsplit(":", 1)[-1] not in {"bool", "timestamp", "int", "float", "merge"}
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
for _tag, _pattern, _letters in (
    ("bool", r"^(?:true|True|TRUE|false|False|FALSE)$", "tTfF"),
    ("int", r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$", "-+0123456789"),
    (
        "float",
        (
            r"^[-+]?(?:\.(?:inf|Inf|INF|nan|NaN|NAN)|"
            r"(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)[eE][-+]?[0-9]+|"
            r"\.[0-9]+|[0-9]+\.[0-9]*)$"
        ),
        "-+.0123456789",
    ),
):
    for _first in _letters:
        CoreLoader.yaml_implicit_resolvers.setdefault(_first, []).append(
            (f"tag:yaml.org,2002:{_tag}", re.compile(_pattern))
        )
CoreLoader.add_constructor("tag:yaml.org,2002:int", CoreLoader.core_int)
CoreLoader.add_constructor("tag:yaml.org,2002:float", CoreLoader.core_float)


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[Any, Any]:
    """Reject duplicate keys rather than showing a skill the runtime will refuse."""
    values = loader.construct_mapping(node, deep=True)
    if len(values) != len(node.value):
        raise yaml.constructor.ConstructorError(
            "while reading DSH YAML",
            node.start_mark,
            "duplicate mapping key",
            node.start_mark,
        )
    return values


CoreLoader.add_constructor("tag:yaml.org,2002:map", _unique_mapping)
