"""What a command line says a run is given: its agents, environments, params and budget.

Three flags, each taking any number of occurrences and each occurrence a comma-separated
list::

    -a coder=claude/opus:high,reviewer=codex@work/gpt-5:medium
    -e repo=ssh@gpu-box/home/me/repo -e scratch=local/tmp/scratch
    -e box=docker/srv/x -e far=ssh@[me@far.host:2222]/srv/x
    -p rounds=3 -p tags=a,b,c
    -p budget.duration=1h30m,budget.cost=5 -p budget.output_tokens=200k

A comma separates two items only where what follows it -- spaces aside -- is a key and `=`,
so a value may hold commas of its own -- `tags=a,b,c` is one param -- and may not hold
`,<key>=`. What a run may spend is given as params too, one `budget.<limit>` apiece, which is
why no flow may have a param called `budget`.
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
    "fallbacks",
    "parse_agents",
    "parse_budget",
    "parse_duration",
    "parse_envs",
    "parse_params",
    "spelled",
    "where",
]


class SpecError(ValueError):
    """A flag's value that cannot be read. The message says which flag and what is wrong."""


class AgentSpecError(SpecError):
    """An `-a` that is not `<role>=<harness>[@<provider>]/<model>[:<effort>]`."""


class EnvSpecError(SpecError):
    """An `-e` that is not `<role>=<backend>[@<provider>][/<workdir>]`."""


class ParamSpecError(SpecError):
    """A `-p` that is not `<key>=<value>`."""


class BudgetSpecError(ParamSpecError):
    """A `-p budget.<limit>=` that is not a budget."""


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
      provider: The runtime saved under this name for that backend; for ssh alone, a host
        nobody saved, in the brackets `-e` writes one in -- `[me@gpu-box:2222]`; or "" for
        this machine: a directory here, docker's default here, the swarm this machine
        manages, this Mac's Apple containers.
      workdir: The directory there: absolute, or `~/...` under the home of whoever ssh
        logs in as. A docker one is a directory of the daemon's host, and a swarm one a
        directory of whichever node its task lands on.
    """

    role: str
    backend: EnvBackendKind
    provider: str
    workdir: PurePosixPath

    def __str__(self) -> str:
        """The spec written back as `-e` takes it."""
        return f"{self.role}={where(self.backend, self.provider, self.workdir)}"


#: The param a run's budget is given under, a limit apiece as `budget.<limit>`: the run's,
#: and so never a flow's.
BUDGET = "budget"

#: Where one item of a flag ends and the next begins: a comma followed by a key and `=`,
#: with any spaces between them, which are the separator's rather than the next item's.
_ITEMS = re.compile(rf",\s*(?=(?:{BUDGET}\.)?[A-Za-z_][\w-]*=)")

#: What a key is, which is what `_ITEMS` splits before: a param's, or one limit of the budget.
_KEY = re.compile(rf"(?:{BUDGET}\.)?[A-Za-z_][\w-]*")

#: `-e` read whole: the role, the backend, the provider after an `@` -- a name, or a host in
#: brackets, which may hold an `@` of its own as `user@host` does --, and the workdir from the
#: first `/` after it.
_ENV = re.compile(
    r"(?P<role>[^=]*)=(?P<backend>[^@/\[\]]*)"
    r"(?:@(?P<provider>\[[^\]/]*\]|[^/]*))?(?P<at>/.*)?"
)

#: What an ssh host nobody saved may be, inside its brackets: `host`, `user@host`, either with
#: `:port`, or an alias of the user's ssh config. Never beginning with `-`, which `ssh` would
#: read as an option.
DESTINATION = re.compile(
    r"(?:[A-Za-z0-9_][A-Za-z0-9._%+-]*@)?[A-Za-z0-9_][A-Za-z0-9._-]*(?::[0-9]{1,5})?"
)

#: What docker, the swarm and Apple's containers called their default here, before an `-e`
#: naming no provider was one on this machine: still how their machines here are known.
_HERE = "local"

#: The backends that have a default here as well as runtimes saved under names.
_HERES = (
    EnvBackendKind.DOCKER,
    EnvBackendKind.SWARM,
    EnvBackendKind.APPLE_CONTAINER,
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
                f"-a {said!r}: expected <role>=<harness>[@<provider>]/<model>[:<effort>]"
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

    An `@` is written only before a provider, and a provider is a runtime saved for that
    backend: `ssh@gpu-box/home/me/repo` is a directory of the ssh host saved as `gpu-box`, and
    `ssh@gpu-box/~/repo` one under the home directory there; `docker@gpubox/srv/repo` one of
    the host of the docker daemon saved as `gpubox`, which hands the role a container of its
    own; `swarm@cluster/srv/repo` one of whichever node of the swarm saved as `cluster` places
    the role's task; `apple-container@mac/Users/me/repo` one of this Mac's that an Apple
    container of its own holds, out of what the runtime saved as `mac` may hand out. Naming
    none is this machine: `local/home/me/repo` is a directory here -- `local` takes no provider
    at all --, `docker/srv/repo` one of docker's default here, `swarm/srv/repo` one of the
    swarm this machine manages, and `apple-container/Users/me/repo` one an Apple container
    holds with nothing saved. ssh always names one, and alone takes a host nobody saved, in
    brackets: `ssh@[me@gpu-box:2222]/srv/repo`. `ssh@gpu-box`, `docker@gpubox`,
    `swarm@cluster` or `apple-container@mac` alone is the workdir that runtime was saved with.

    What `-e` took before an `@` was a provider's alone -- `local@/...`, `docker@local/...`,
    `swarm@local/...`, `apple-container@local/...`, an ssh host nobody saved out of brackets --
    is refused, saying how it is spelled now: :func:`hmz.coganchor.machines.store.respelled`
    is what reads it where it was written down.

    Args:
      values: What each `-e` was given.

    Returns:
      One spec per environment, in the order they were written.

    Raises:
      EnvSpecError: For an item that is not an environment, names a runtime nobody saved or a
        host nobody saved for a backend other than ssh, or is spelled the old way; and for a
        role given twice.
    """
    specs: list[EnvSpec] = []
    roles: set[str] = set()
    backends = ", ".join(kind.value for kind in EnvBackendKind)
    for item in _items(values, "-e", EnvSpecError):
        said = item.strip()
        read = _ENV.fullmatch(said)
        if read is None:
            raise EnvSpecError(f"-e {said!r}: expected {_SPELLING}")
        role = read["role"].strip()
        if not role.isidentifier():
            raise EnvSpecError(f"-e {said!r}: the role {role!r} is not an identifier")
        try:
            backend = EnvBackendKind(read["backend"].strip())
        except ValueError:
            raise EnvSpecError(
                f"-e {said!r}: {read['backend']!r} is not a backend; one of {backends}"
            ) from None
        provider = _provider(said, role, backend, read["provider"], read["at"])
        at = read["at"] or _workdir_of(backend, provider)
        if at is None:
            raise EnvSpecError(
                f"-e {said!r}: expected {_SPELLING}; /<workdir> may be left off only "
                "for a runtime saved with one"
            )
        workdir = PurePosixPath(at[1:] if at[1:].startswith("~") else at)
        if role in roles:
            raise EnvSpecError(f"-e: the role {role!r} is given twice")
        roles.add(role)
        specs.append(EnvSpec(role, backend, provider, workdir))
    return specs


#: What `-e` takes, as a message says it.
_SPELLING = "<role>=<backend>[@<provider>][/<workdir>]"


def _provider(
    said: str, role: str, backend: EnvBackendKind, written: str | None, at: str | None
) -> str:
    """The provider one `-e` names, held to what its backend takes, or "" for this machine.

    Args:
      said: The item, as it was written.
      role: Its role.
      backend: Its backend.
      written: What followed its `@`, or None for no `@`.
      at: Its workdir from the `/`, or None for none written.

    Returns:
      A runtime's name, a host in brackets, or "".

    Raises:
      EnvSpecError: For a provider its backend does not take, saying how to write it where
        it is one spelled the old way.
    """
    provider = (written or "").strip()
    rest = at or "/<workdir>"

    def instead(one: str) -> str:
        return f"write {role}={where(backend, one)}{rest}"

    bracketed = len(provider) > 1 and provider[0] == "[" and provider[-1] == "]"
    if not bracketed and ("[" in provider or "]" in provider):
        raise EnvSpecError(f"-e {said!r}: expected {_SPELLING}")
    if backend is EnvBackendKind.LOCAL:
        if written is not None:
            raise EnvSpecError(f"-e {said!r}: local takes no provider; {instead('')}")
        return ""
    if bracketed:
        if backend is not EnvBackendKind.SSH:
            raise EnvSpecError(
                f"-e {said!r}: only ssh takes a host nobody saved; {backend}@<name> "
                f"names a {backend} runtime saved on the runtimes page of /settings"
            )
        host = provider[1:-1].strip()
        if not DESTINATION.fullmatch(host):
            raise EnvSpecError(
                f"-e {said!r}: {host!r} is not an ssh host, as [user@]host[:port]"
            )
        return f"[{host}]"
    if backend is EnvBackendKind.SSH and not provider:
        raise EnvSpecError(
            f"-e {said!r}: ssh needs a host: ssh@<saved host>{rest}, or "
            f"ssh@[user@host:port]{rest} for a host not saved"
        )
    if not provider:
        if written is not None:
            raise EnvSpecError(
                f"-e {said!r}: an @ is written only before a provider; {instead('')}"
            )
        return ""
    if _saved(backend, provider):
        return provider
    if backend is EnvBackendKind.SSH:
        raise EnvSpecError(
            f"-e {said!r}: no ssh host is saved as {provider!r}; "
            f"{instead(f'[{provider}]')} for a host not saved"
        )
    if provider == _HERE and backend in _HERES:
        raise EnvSpecError(
            f"-e {said!r}: {backend} on this machine names no provider; {instead('')}"
        )
    raise EnvSpecError(
        f"-e {said!r}: no {backend} runtime is saved as {provider!r}; save one on the "
        f"runtimes page of /settings, or {instead('')} for {backend} on this machine"
    )


def _saved(backend: str, name: str) -> bool:
    """Whether a runtime of a backend is written down under a name, whether or not it reads.

    One that cannot be read is still one: what opens it says that it cannot be, rather than
    this taking the name for a host nobody saved.
    """
    from hmz.coganchor.machines import store

    try:
        return store.saved(str(backend), name)
    except ValueError:
        return False  # a backend nothing is saved for, or a name no runtime may have


def _workdir_of(backend: str, provider: str) -> str | None:
    """The workdir the saved runtime an `-e` names was written down with, as `/...`.

    None where it names no provider, or one with no workdir of its own.
    """
    from hmz.coganchor.machines import store

    found = store.find(str(backend), provider)
    if found is None or not found.workdir:
        return None
    return found.workdir if found.workdir.startswith("/") else f"/{found.workdir}"


def where(backend: str, provider: str, workdir: str | PurePosixPath = "") -> str:
    """Where an environment is, as `-e` spells it after `<role>=`.

    Args:
      backend: Which kind of machine.
      provider: Which one: a saved runtime's name, an ssh host in brackets, or "" for this
        machine.
      workdir: The directory there -- absolute, or `~/...` --, or "" for none written.

    Returns:
      `<backend>[@<provider>][/<workdir>]`.
    """
    named = f"@{provider}" if provider else ""
    at = str(workdir).lstrip("/")
    return f"{backend}{named}/{at}" if workdir else f"{backend}{named}"


def spelled(backend: str, provider: str, workdir: str | PurePosixPath = "") -> str:
    """Where a driver works, as `-e` spells it, for a message or a record to say.

    A machine calls itself what `-e` once did: `local` for docker's default here, the swarm
    this machine manages and this Mac's Apple containers, and an ssh host nobody saved by the
    host alone. Those are spelled as `-e` takes them now -- `docker/...`, `ssh@[host]/...` --
    which turns on what is saved here.

    Args:
      backend: Which kind of machine.
      provider: What the machine calls itself.
      workdir: The directory there, or "" for none.

    Returns:
      `<backend>[@<provider>][/<workdir>]`.
    """
    from hmz.coganchor.machines.store import respelled

    return respelled(where(backend, provider, workdir))


def fallbacks(spec: EnvSpec) -> list[EnvSpec]:
    """What an environment moves to, in order, where the runtime its `-e` names cannot hold it.

    The fallback list of the saved runtime it names, each entry a spec of its own for the same
    role: in that runtime's saved workdir where it has one, and otherwise in the workdir given.
    Only the runtime the `-e` names is read: one fallen back to is never walked on down its
    own list. A spec naming no saved runtime -- this machine, docker's default here, an ssh
    host in brackets -- falls back to nothing. An entry `docker:local`, `swarm:local` or
    `apple-container:local` is docker's default here, the swarm this machine manages or this
    Mac's Apple containers, where nothing of theirs is saved as `local`: the one name a list
    has for them.

    Args:
      spec: The environment, as `-e` gave it.

    Returns:
      The specs to try after it, which are none where its runtime has no list.
    """
    from hmz.coganchor.machines import store

    onward: list[EnvSpec] = []
    for backend, name in store.fallbacks(str(spec.backend), spec.provider):
        found = store.find(backend, name)
        saved = found.workdir if found is not None else ""
        try:
            kind = EnvBackendKind(backend)
        except ValueError:
            continue  # a backend of the store's no environment is put on
        here = kind in _HERES and name == _HERE and not _saved(kind, name)
        onward.append(
            EnvSpec(
                spec.role,
                kind,
                "" if here else name,
                PurePosixPath(saved) if saved else spec.workdir,
            )
        )
    return onward


def parse_params(values: Sequence[str]) -> dict[str, str]:
    """Reads every `-p` that is a param of the flow's.

    Args:
      values: What each `-p` was given.

    Returns:
      Each key and its value, exactly as written after the `=`. What the value means is the
      flow's params model's to say. A `budget.<limit>` is the run's rather than the flow's,
      and is left to :func:`parse_budget`.

    Raises:
      ParamSpecError: For an item that is not `<key>=<value>`, for `budget` with no limit,
        and for a key given twice.
    """
    return {
        key: value
        for key, value in _params(values).items()
        if not key.startswith(f"{BUDGET}.")
    }


def _params(values: Sequence[str]) -> dict[str, str]:
    """Every `-p`, the flow's params and the budget's limits alike, by key.

    Raises:
      ParamSpecError: For an item that is not `<key>=<value>`, for `budget` with no limit,
        and for a key given twice.
    """
    params: dict[str, str] = {}
    for item in _items(values, "-p", ParamSpecError):
        key, written, value = item.partition("=")
        key = key.strip()
        if not written or not _KEY.fullmatch(key):
            raise ParamSpecError(f"-p {item!r}: expected <key>=<value>")
        if key == BUDGET:
            raise ParamSpecError(
                f"-p {item!r}: a budget is given a limit at a time, as budget.cost=5"
            )
        if key in params:
            raise ParamSpecError(f"-p: {key!r} is given twice")
        params[key] = value
    return params


#: The limits a budget takes, each as `-p budget.<limit>=`, and nothing else.
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
            f"{text!r} is not a duration: use seconds, 1h30m, or ISO 8601 like PT1H30M"
        ) from None
    if read < datetime.timedelta(0):
        raise ValueError(f"{text!r} is negative")
    return read


def _seconds(seconds: float, text: str) -> datetime.timedelta:
    """A number of seconds as a duration, refusing what no duration is."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError(
            f"{text!r} is not a valid duration: must be finite and not negative"
        )
    try:
        return datetime.timedelta(seconds=seconds)
    except OverflowError:
        raise ValueError(f"duration {text!r} is too long") from None


def _cost(text: str) -> float:
    """A cost in USD, with or without a `$`, `inf` for no limit."""
    try:
        cost = float(text.strip().removeprefix("$"))
    except ValueError:
        raise ValueError(f"{text!r} is not a valid USD cost") from None
    if math.isnan(cost) or cost < 0:
        raise ValueError(f"{text!r} is not a valid USD cost")
    return cost


def _tokens(text: str) -> int:
    """A count of tokens: a whole number, or thousands and millions as `k` and `m`."""
    said = text.strip().lower().replace("_", "")
    read = _TOKENS.fullmatch(said)
    if read is None:
        raise ValueError(
            f"{text!r} is not a valid token count: expected a number like 200000 "
            "or 200k"
        )
    # Decimal rather than float, so that 1.001k is 1001 and a long count stays exact.
    count = decimal.Decimal(read[1]) * {"": 1, "k": 1_000, "m": 1_000_000}[read[2]]
    if count != count.to_integral_value():
        raise ValueError(f"{text!r} must be a whole number of tokens")
    return int(count)


def _flag(text: str) -> bool:
    """A yes or no."""
    said = text.strip().lower()
    if said in _YES:
        return True
    if said in _NO:
        return False
    raise ValueError(f"{text!r} must be true or false")


def parse_budget(values: Sequence[str]) -> Budget | None:
    """Reads every `-p budget.<limit>=` into one budget.

    Args:
      values: What each `-p` was given: of which `budget.duration=`, `budget.cost=`,
        `budget.output_tokens=` and `budget.graceful=` are read, each at most once across
        all of them, and the flow's own params left alone.

    Returns:
      The budget, or None where no `-p` named a limit.

    Raises:
      ParamSpecError: For a `-p` that cannot be read at all.
      BudgetSpecError: For an unknown limit, a value that cannot be read, or a budget that
        limits nothing.
    """
    said = {
        key.removeprefix(f"{BUDGET}."): value
        for key, value in _params(values).items()
        if key.startswith(f"{BUDGET}.")
    }
    if not said:
        return None
    for key in said:
        if key not in _BUDGET:
            raise BudgetSpecError(
                f"-p {BUDGET}.{key}: not a limit; one of "
                f"{', '.join(f'{BUDGET}.{one}' for one in _BUDGET)}"
            )
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
            raise BudgetSpecError(f"-p {BUDGET}.{key}: {error}") from error
    try:
        return Budget.model_validate(fields)
    except pydantic.ValidationError as error:
        raise BudgetSpecError(
            f"-p {BUDGET}.*: {'; '.join(one['msg'] for one in error.errors())}"
        ) from error
