"""Which agents are installed here, and what each one runs: what `Hmz.installed` answers.

Installed backends are found here, and optional backends somebody can add are named separately
so the picker can teach them how. An effort a model does not take is not offered against it.
What each backend runs is what that backend last said it runs, which the runtime accounts keep --
read off the disk here, because asking means starting a coding agent and a prompt cannot wait
on one.

Nothing is asked of the backends either. Measured on the machine this was written on,
`claude --help` took over thirty seconds, `codex app-server` seventy-six, and `kimi web` about
a minute. So a catalogue is filled where there is time for it -- when an account is made, and
on the key that says to ask again -- and read here.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor.backends import (
    DSH_SDK,
    LITELLM_SDK,
    named,
    profiles,
    program,
    speaking,
)

if TYPE_CHECKING:
    from hmz.coganchor.backends import Model
    from hmz.runtime.doing.accounts import Accounts

__all__ = ["adding", "installable", "installed", "ready_to_open"]

#: The backends that want something of this Python environment as well as of this machine,
#: by the modules that say the extra carrying one is installed. Every module of it, because
#: half an extra is a backend that starts and then stops somewhere further in. A backend
#: named here without its extra is offered with the line that adds it rather than hidden,
#: because somebody who has the CLI and not the package is owed the difference.
_EXTRAS = {
    "dsh": ("deepseek_harness", "dotenv"),
    "kimi": ("websockets",),
    "litellm": ("litellm",),
}

#: What each backend behind an extra is missing when it is missing, and the packages of that
#: extra: the line for a humanize installed from a repository or a checkout, which an index
#: has no `hmz[...]` of.
_LINES = {
    "dsh": ("DeepSeek Harness is not installed", f"'{DSH_SDK}' 'python-dotenv>=1.2.3'"),
    "kimi": (
        "Kimi Code is installed, but the websockets package is not",
        "'websockets>=15,<18'",
    ),
    "litellm": ("litellm is not installed", f"'{LITELLM_SDK}'"),
}


def installed(accounts: Accounts) -> dict[str, tuple[Model, ...]]:
    """The backends on this machine, and what each last said it runs.

    Costs a look for each backend's program and one file read, so it can be asked for at a
    prompt.

    Args:
      accounts: The accounts of the workspace asking, which keep what each backend runs.

    Returns:
      One entry per backend that is on this machine, as the models it last said it runs for
      the account nobody chose. Empty for one that has never been asked, which is a catalogue
      to fill rather than a backend with nothing in it.
    """
    return {
        profile.name: accounts.models(profile.name)
        for profile in profiles()
        if _is_installed(profile.name)
    }


def installable(accounts: Accounts) -> dict[str, tuple[Model, ...]]:
    """Optional backends that can be added to this humanize installation.

    These are kept apart from :func:`installed`: they belong in the agent picker so that
    somebody can discover and install them, but they must not make an unopened prompt look
    ready to run or be asked for models in the background.

    Args:
      accounts: The accounts of the workspace asking, which keep what each backend runs.

    Returns:
      One entry per supported optional backend whose extra is missing from this Python
      environment, with the models it will offer once installed. A backend whose program is
      not here either is not one of them: what it is missing is the program, and a line that
      names a package alone would be an answer to the smaller half.
    """
    return {
        backend: accounts.models(backend)
        for backend in _EXTRAS
        if _is_here(backend) and not _has_extra(backend)
    }


def adding(backend: str) -> str:
    """The line that adds an optional backend to this Python environment.

    Said wherever something is offered that the extra would bring -- a backend in a picker,
    or the ways into a CLI through the local LiteLLM gateway -- rather than hidden.

    Args:
      backend: The backend whose extra it is.

    Returns:
      What is missing, and the command that adds it: the extra of the release running, for a
      humanize from an index, and its packages for one installed from anywhere else.
    """
    if (extra := _LINES.get(backend)) is None:
        return f"install {backend}, then reopen humanize"
    missing, requirement = extra
    # A humanize from an index has no `direct_url.json` (PEP 610), and that index has its
    # extra, pinned to the version running so that nothing else of humanize is installed.
    # And one that is no distribution at all -- a checkout on `PYTHONPATH` -- is anywhere else.
    try:
        hmz = importlib.metadata.distribution("hmz")
    except importlib.metadata.PackageNotFoundError:
        hmz = None
    if hmz is not None and hmz.read_text("direct_url.json") is None:
        requirement = shlex.quote(f"hmz[{backend}]=={hmz.version}")
    executable = str(Path(sys.executable).absolute())
    command = f"uv pip install --python {shlex.quote(executable)} {requirement}"
    return f"{missing}; run: {command}; then reopen hmz"


def _is_installed(backend: str) -> bool:
    """Whether a backend's program and whatever else it needs are both installed here."""
    return _is_here(backend) and _has_extra(backend)


def _has_extra(backend: str) -> bool:
    """Whether the whole of the extra a backend is driven through is installed here."""
    return all(
        importlib.util.find_spec(module) is not None
        for module in _EXTRAS.get(backend, ())
    )


def _is_here(backend: str) -> bool:
    """Whether the program a backend's turns are taken by is on this machine."""
    # dsh is driven through its SDK rather than its CLI, and litellm is a model called from
    # this process, so for neither is there a program to look for.
    if backend in ("dsh", "litellm"):
        return True
    # A CLI somebody added is started by the command they gave rather than by its own name.
    if (added := speaking().get(backend)) is not None:
        return bool(added) and program(added[0]) is not None
    # And one humanize drives is started by the command it is installed as, which is its own
    # name.
    profile = named(backend)
    return program(profile.name if profile is not None else backend) is not None


def ready_to_open(backend: str, where: Path) -> bool:
    """Whether an installed backend may be chosen without somebody choosing it.

    A CLI on ``PATH`` is there because somebody installed it, and installing it is a choice
    about what to run agents on. DeepSeek Harness is different: what says it is here is a
    package, which somebody may have added for one agent rather than for all of them, and
    which says nothing about whether its local account has been configured. It remains
    installed and selectable without a key, but must not make a new prompt look ready to run.

    Args:
      backend: The backend being considered as the implicit fallback.
      where: The workspace its local account would run in.

    Returns:
      Whether the backend may be used as the implicit local fallback. Never litellm: a
      model with no tools is something a flow asks for by name, and never what a prompt
      falls back to doing work with.
    """
    if backend == "litellm":
        return False
    if backend != "dsh":
        return True

    # Local so discovering ordinary CLIs does not import any agent implementation. The SDK
    # runtime itself remains lazy inside the dsh driver and is not started by this check.
    from hmz.coganchor.agents.dsh import native_ready

    return native_ready(where)
