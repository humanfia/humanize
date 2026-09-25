"""What a command line says a run is given: its agents, environments, params and budget.

Four flags, each taking any number of occurrences and each occurrence a comma-separated
list::

    -a coder=claude/opus:high,reviewer=codex@work/gpt-5:medium
    -e repo=ssh@gpu-box/home/me/repo -e scratch=local@/tmp/scratch
    -p rounds=3 -p tags=a,b,c
    -b duration=1h30m,cost=5 -b output_tokens=200k

A comma separates two items only where what follows it -- spaces aside -- is a key and `=`,
so a value may hold commas of its own -- `tags=a,b,c` is one param -- and may not hold
`,<key>=`.
"""

from __future__ import annotations

import datetime
import decimal
import functools
import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import pydantic

from hmz.flows import Budget, EnvBackendKind, HarnessKind

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

__all__ = [
    "AgentSpec",
    "AgentSpecError",
    "BudgetSpecError",
    "EnvSpec",
    "EnvSpecError",
    "ParamSpecError",
    "SpecError",
    "parse_agents",
    "parse_budget",
    "parse_duration",
    "parse_envs",
    "parse_params",
]


class SpecError(ValueError):
    """A flag's value that cannot be read. The message says which flag and what is wrong."""


class AgentSpecError(SpecError):
    """An `-a` that is not `<role>=<harness>[@<provider>]/<model>:<effort>`."""


class EnvSpecError(SpecError):
    """An `-e` that is not `<role>=<backend>[@<provider>]/<workdir>`."""


class ParamSpecError(SpecError):
    """A `-p` that is not `<key>=<value>`."""


class BudgetSpecError(SpecError):
    """A `-b` that is not a budget."""


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """One agent, as `-a` names it.

    Attributes:
      role: The role it fills.
      harness: Which CLI it is; `ACP` for one added by hand.
      provider: The account its turns run as, or "" for whoever the CLI is logged in as.
      model: The model.
      effort: The effort in the CLI's own words, or "" for the CLI's default.
      cli: The name the CLI is known by: the harness's own, or the name one added by hand
        was added under.
    """

    role: str
    harness: HarnessKind
    provider: str
    model: str
    effort: str
    cli: str

    def __str__(self) -> str:
        """The spec written back as `-a` takes it."""
        from hmz.coganchor.backends import AUTO

        account = f"@{self.provider}" if self.provider else ""
        return f"{self.role}={self.cli}{account}/{self.model}:{self.effort or AUTO}"


@dataclass(frozen=True, slots=True)
class EnvSpec:
    """One environment, as `-e` names it.

    Attributes:
      role: The role it fills.
      backend: Which kind of machine.
      provider: The ssh host -- `host` or `user@host` -- or "" for this machine.
      workdir: The directory there: absolute, or `~/...` under the home of whoever ssh
        logs in as.
    """

    role: str
    backend: EnvBackendKind
    provider: str
    workdir: PurePosixPath

    def __str__(self) -> str:
        """The spec written back as `-e` takes it."""
        return f"{self.role}={self.backend}@{self.provider}/{str(self.workdir).lstrip('/')}"


#: Where one item of a flag ends and the next begins: a comma followed by a key and `=`,
#: with any spaces between them, which are the separator's rather than the next item's.
_ITEMS = re.compile(r",\s*(?=[A-Za-z_][\w-]*=)")

#: What a key is, which is what `_ITEMS` splits before.
_KEY = re.compile(r"[A-Za-z_][\w-]*")

#: `-e` read whole: the role, the backend, the provider after an `@`, and the workdir from the
#: first `/` after it. The provider may hold an `@` of its own, as `user@host` does.
_ENV = re.compile(
    r"(?P<role>[^=]*)=(?P<backend>[^@/]*)(?:@(?P<provider>[^/]*))?(?P<at>/.*)?"
)


def _items(values: Sequence[str], flag: str, refused: type[SpecError]) -> Iterator[str]:
    """Every item of every occurrence of one flag, in the order they were written.

    Raises:
      SpecError: `refused`, for an empty item.
    """
    for value in values:
        for item in _ITEMS.split(value):
            if not item.strip():
                raise refused(f"{flag} {value!r}: an item is empty")
            yield item


def parse_agents(values: Sequence[str]) -> list[AgentSpec]:
    """Reads every `-a`.

    Args:
      values: What each `-a` was given.

    Returns:
      One spec per agent, in the order they were written.

    Raises:
      AgentSpecError: For an item that is not an agent, names no harness, or has no role,
        and for a role given twice.
    """
    from hmz.coganchor import backends

    harnesses = {kind.value for kind in HarnessKind} - {HarnessKind.ACP.value}
    specs: list[AgentSpec] = []
    roles: set[str] = set()
    for item in _items(values, "-a", AgentSpecError):
        said = item.strip()
        role, written, _ = said.partition("=")
        if not written or not role.strip():
            raise AgentSpecError(
                f"-a {said!r}: expected <role>=<harness>[@<provider>]/<model>:<effort>"
            )
        try:
            role, profile, model, effort, provider = backends.read(said)
        except ValueError as error:
            raise AgentSpecError(f"-a {said!r}: {error}") from error
        if role in roles:
            raise AgentSpecError(f"-a: the role {role!r} is given twice")
        roles.add(role)
        harness = (
            HarnessKind(profile.name) if profile.name in harnesses else HarnessKind.ACP
        )
        specs.append(AgentSpec(role, harness, provider, model, effort, profile.name))
    return specs


def parse_envs(values: Sequence[str]) -> list[EnvSpec]:
    """Reads every `-e`.

    `local@/home/me/repo` is a directory on this machine, and `local` takes no provider.
    `ssh@gpu-box/home/me/repo` is one on the host `gpu-box`, and `ssh@gpu-box/~/repo` one under
    the home directory there.

    Args:
      values: What each `-e` was given.

    Returns:
      One spec per environment, in the order they were written.

    Raises:
      EnvSpecError: For an item that is not an environment, and for a role given twice.
    """
    specs: list[EnvSpec] = []
    roles: set[str] = set()
    backends = ", ".join(kind.value for kind in EnvBackendKind)
    for item in _items(values, "-e", EnvSpecError):
        said = item.strip()
        read = _ENV.fullmatch(said)
        if read is None or read["at"] is None:
            raise EnvSpecError(
                f"-e {said!r}: expected <role>=<backend>[@<provider>]/<workdir>"
            )
        role = read["role"].strip()
        if not role.isidentifier():
            raise EnvSpecError(f"-e {said!r}: the role {role!r} is not an identifier")
        try:
            backend = EnvBackendKind(read["backend"].strip())
        except ValueError:
            raise EnvSpecError(
                f"-e {said!r}: {read['backend']!r} is not a backend; one of {backends}"
            ) from None
        provider = (read["provider"] or "").strip()
        if backend is EnvBackendKind.SSH and not provider:
            raise EnvSpecError(f"-e {said!r}: ssh needs a host, as in ssh@host/workdir")
        if backend is EnvBackendKind.LOCAL and provider:
            raise EnvSpecError(
                f"-e {said!r}: local takes no provider, as in local@/workdir"
            )
        at = read["at"]
        workdir = PurePosixPath(at[1:] if at[1:].startswith("~") else at)
        if role in roles:
            raise EnvSpecError(f"-e: the role {role!r} is given twice")
        roles.add(role)
        specs.append(EnvSpec(role, backend, provider, workdir))
    return specs


def parse_params(values: Sequence[str]) -> dict[str, str]:
    """Reads every `-p`.

    Args:
      values: What each `-p` was given.

    Returns:
      Each key and its value, exactly as written after the `=`. What the value means is the
      flow's params model's to say.

    Raises:
      ParamSpecError: For an item that is not `<key>=<value>`, and for a key given twice.
    """
    params: dict[str, str] = {}
    for item in _items(values, "-p", ParamSpecError):
        key, written, value = item.partition("=")
        key = key.strip()
        if not written or not _KEY.fullmatch(key):
            raise ParamSpecError(f"-p {item!r}: expected <key>=<value>")
        if key in params:
            raise ParamSpecError(f"-p: {key!r} is given twice")
        params[key] = value
    return params


#: What `-b` takes, and nothing else.
_BUDGET = ("duration", "cost", "output_tokens", "graceful")

#: What each unit of a written duration is, in seconds.
_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}

#: A duration written in units, as `1h30m` or `2d` or `1.5h`.
_UNITED = re.compile(r"(?:\d+(?:\.\d+)?[wdhms])+")
_UNIT = re.compile(r"(\d+(?:\.\d+)?)([wdhms])")

#: A count of tokens, as `200000`, `200_000`, `200k` or `1.5m`.
_TOKENS = re.compile(r"(\d+(?:\.\d+)?)([km]?)")

_YES = frozenset({"1", "true", "yes", "on"})
_NO = frozenset({"0", "false", "no", "off"})


@functools.cache
def _iso() -> pydantic.TypeAdapter[datetime.timedelta]:
    """What reads the ISO 8601 and `HH:MM:SS` forms of a duration."""
    return pydantic.TypeAdapter(datetime.timedelta)


def parse_duration(text: str) -> datetime.timedelta:
    """Reads a duration as a person writes one.

    Args:
      text: Seconds (`90`, `1.5`); units of weeks, days, hours, minutes and seconds, each at
        most once (`1h30m`, `2d`, `90s`); ISO 8601 (`PT1H30M`); or `HH:MM:SS`.

    Returns:
      The duration.

    Raises:
      ValueError: If it is none of those, or is negative or not finite.
    """
    said = text.strip()
    try:
        seconds = float(said)
    except ValueError:
        pass
    else:
        return _seconds(seconds, text)
    if _UNITED.fullmatch(said.lower()):
        parts = _UNIT.findall(said.lower())
        units = [unit for _, unit in parts]
        if len(set(units)) != len(units):
            raise ValueError(f"{text!r} names a unit twice")
        return _seconds(sum(float(n) * _UNITS[unit] for n, unit in parts), text)
    try:
        read = _iso().validate_python(said)
    except pydantic.ValidationError:
        raise ValueError(
            f"{text!r} is not a duration: write seconds, 1h30m, or ISO 8601 like PT1H30M"
        ) from None
    if read < datetime.timedelta(0):
        raise ValueError(f"{text!r} is negative")
    return read


def _seconds(seconds: float, text: str) -> datetime.timedelta:
    """A number of seconds as a duration, refusing what no duration is."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(f"{text!r} is not a duration: it is negative or not finite")
    try:
        return datetime.timedelta(seconds=seconds)
    except OverflowError:
        raise ValueError(f"{text!r} is too long a duration") from None


def _cost(text: str) -> float:
    """A cost in USD, with or without a `$`, `inf` for no limit."""
    try:
        cost = float(text.strip().removeprefix("$"))
    except ValueError:
        raise ValueError(f"{text!r} is not a cost in USD") from None
    if math.isnan(cost) or cost < 0:
        raise ValueError(f"{text!r} is not a cost in USD")
    return cost


def _tokens(text: str) -> int:
    """A count of tokens: a whole number, or thousands and millions as `k` and `m`."""
    said = text.strip().lower().replace("_", "")
    read = _TOKENS.fullmatch(said)
    if read is None:
        raise ValueError(f"{text!r} is not a count of tokens, as in 200000 or 200k")
    # Decimal rather than float, so that 1.001k is 1001 and a long count stays exact.
    count = decimal.Decimal(read[1]) * {"": 1, "k": 1_000, "m": 1_000_000}[read[2]]
    if count != count.to_integral_value():
        raise ValueError(f"{text!r} is not a whole number of tokens")
    return int(count)


def _flag(text: str) -> bool:
    """A yes or no."""
    said = text.strip().lower()
    if said in _YES:
        return True
    if said in _NO:
        return False
    raise ValueError(f"{text!r} is not true or false")


def parse_budget(values: Sequence[str]) -> Budget:
    """Reads every `-b` into one budget.

    Args:
      values: What each `-b` was given: `duration=`, `cost=`, `output_tokens=` and
        `graceful=`, each at most once across all of them.

    Returns:
      The budget.

    Raises:
      BudgetSpecError: For an unknown or repeated key, a value that cannot be read, or a
        budget that limits nothing.
    """
    said: dict[str, str] = {}
    for item in _items(values, "-b", BudgetSpecError):
        key, written, value = item.partition("=")
        key = key.strip()
        if not written or key not in _BUDGET:
            raise BudgetSpecError(
                f"-b {item!r}: expected one of {', '.join(_BUDGET)}, as key=value"
            )
        if key in said:
            raise BudgetSpecError(f"-b: {key!r} is given twice")
        said[key] = value
    readers = {
        "duration": parse_duration,
        "cost": _cost,
        "output_tokens": _tokens,
        "graceful": _flag,
    }
    fields: dict[str, Any] = {}
    for key, value in said.items():
        try:
            fields[key] = readers[key](value)
        except ValueError as error:
            raise BudgetSpecError(f"-b {key}: {error}") from error
    try:
        return Budget.model_validate(fields)
    except pydantic.ValidationError as error:
        raise BudgetSpecError(
            f"-b: {'; '.join(one['msg'] for one in error.errors())}"
        ) from error
