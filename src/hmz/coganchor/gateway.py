"""A LiteLLM gateway on loopback, which puts a coding agent CLI in front of any endpoint at all.

Every CLI here speaks one protocol, or two, to whoever it is pointed at: Claude Code speaks
Anthropic's Messages API, and an account it can be run as is one that answers in it. litellm
speaks every vendor's API, gateways and clouds alike, and its proxy answers in the protocols the
CLIs speak. So a CLI pointed at a proxy of litellm's, under an account litellm holds, is that CLI
run as an account it has no way in for of its own: an OpenAI key, somebody's OpenAI-compatible
router, a model on Bedrock, Vertex or Azure.

One gateway is one `litellm` proxy, run by this Python as a process of its own, on a port of
loopback nothing else holds and under a master key nothing else knows -- which is what the CLI
is handed instead of the account. The account goes to the proxy alone, in a file only this user
can read, in a directory taken away with the gateway: never on a command line, and never in the
CLI's environment. It is started where the CLI runs, by the agent driving that CLI
(:attr:`hmz.coganchor.agents.base.AgentBase.gateway`), and goes when the agent does.

What a litellm account comes to as litellm's own parameters -- which model string a turn is sent
to, and which credentials go with it -- is said here once, for both of the places it is said
to litellm: a turn of the `litellm` backend in this process, and a gateway's configuration.
"""

from __future__ import annotations

import collections
import contextlib
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import weakref
from typing import TYPE_CHECKING, Any

from hmz.coganchor import backends

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import IO

    from hmz.coganchor.providers import Provider

__all__ = [
    "NEEDS",
    "Gateway",
    "argued",
    "configured",
    "credentials",
    "gatewayable",
    "prefix",
    "spelled",
    "spoken",
]

#: The modules a gateway cannot start without: litellm, and what its proxy refuses to start
#: without. Looked for rather than imported, which is seconds of a picker opening spent on a
#: library nothing is about to call.
NEEDS = ("litellm", "apscheduler", "backoff", "fastapi", "orjson", "uvicorn", "yaml")

#: The variables a gateway account is made of, and which protocol of litellm's it speaks.
_URL = "LITELLM_GATEWAY_URL"
_KEY = "LITELLM_GATEWAY_KEY"
_API = "LITELLM_GATEWAY_API"

#: The clouds, each as the provider litellm names it by, the variables its account was made
#: with and the litellm parameter each of them is passed as.
_CLOUDS: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "bedrock": (
        "bedrock",
        (("AWS_PROFILE", "aws_profile_name"), ("AWS_REGION_NAME", "aws_region_name")),
    ),
    "vertex": (
        "vertex_ai",
        (
            ("VERTEXAI_PROJECT", "vertex_project"),
            ("VERTEXAI_LOCATION", "vertex_location"),
        ),
    ),
    "azure": (
        "azure",
        (
            ("AZURE_API_BASE", "api_base"),
            ("AZURE_API_KEY", "api_key"),
            ("AZURE_API_VERSION", "api_version"),
        ),
    ),
}

#: What a vendor's key way is called after the vendor, which is the provider litellm names.
_KEYED = "-key"

#: How long a gateway is given to say it is up, in seconds. Generous: the proxy imports the
#: whole of litellm and a web server before it binds, which is seconds on a fast machine.
_READY = 120.0

#: How long it is given to go once it is told to, before it is killed.
_STOP = 5.0

#: How many of the last lines it said are kept, to say why it never came up.
_TAIL = 20

#: What a gateway's readiness is asked at: what it serves, which it answers under its master
#: key alone -- so a gateway that answers is this one, and not another on a port it let go of.
_READY_AT = "/v1/models"

#: The backends pointed at the gateway with `/v1` after it, and what that is: theirs take a
#: base URL with the API's version in it and add only the operation, as OpenAI's SDKs do --
#: where Anthropic's add `/v1/messages` themselves, and a CLI that adds the whole OpenAI path
#: itself is given the bare URL by not being here.
_VERSIONED_FOR = frozenset({"opencode", "mimo", "pi"})
_VERSIONED = "/v1"

#: What asks it, past any proxy the environment names.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def gatewayable() -> bool:
    """Whether a gateway can be started by this Python: whether all of :data:`NEEDS` is here.

    Returns:
      Whether the `[litellm]` extra is installed whole.
    """
    return all(importlib.util.find_spec(one) is not None for one in NEEDS)


def _way(provider: Provider) -> str:
    """Which of litellm's own ways an account was made by, whichever backend it is for."""
    if provider.cli == "litellm":
        return provider.way
    return backends.upstream(provider.way)


def prefix(provider: Provider | None) -> str:
    """The provider litellm sends this account's turns to, as it is written in front of an id.

    Args:
      provider: The account, or None for the variables this machine already has.

    Returns:
      `openai` for an OpenAI key, `bedrock` for Bedrock, the protocol a gateway account said
      for that gateway -- and "" for no account, or one that says nothing litellm can place.
    """
    if provider is None:
        return ""
    if api := provider.env.get(_API, ""):
        return api
    way = _way(provider)
    if way in _CLOUDS:
        return _CLOUDS[way][0]
    return way.removesuffix(_KEYED) if way.endswith(_KEYED) else ""


def spelled(model: str, provider: Provider | None) -> str:
    """The litellm model string a turn naming `model` is sent to, under this account.

    A bare id under an account is the account's provider's: `gpt-5` under an OpenAI key is
    `openai/gpt-5`, and under a gateway account the id that gateway serves, prefixed with the
    protocol it speaks. An id already written with that provider in front is left as it is.

    Args:
      model: The model as a turn names it.
      provider: The account the turn runs under, or None for none.

    Returns:
      The model string.
    """
    said = prefix(provider)
    if said and not model.startswith(f"{said}/"):
        return f"{said}/{model}"
    return model


def credentials(provider: Provider | None) -> dict[str, str]:
    """What the account a turn runs under is, as litellm's own parameters.

    Args:
      provider: The account, or None for none -- litellm then reads the variables of this
        machine's own, as it always does.

    Returns:
      The parameters, by litellm's names.

    Raises:
      ValueError: For an account made some way litellm does not offer.
    """
    if provider is None:
        return {}
    env = provider.env
    way = _way(provider)
    if way in _CLOUDS:
        return {
            name: env[variable]
            for variable, name in _CLOUDS[way][1]
            if env.get(variable)
        }
    if env.get(_URL):
        return {"api_base": env[_URL], "api_key": env.get(_KEY, "")}
    held = next(
        (
            one
            for profile in backends.PROFILES
            if profile.name == "litellm"
            for one in profile.ways
            if one.name == way
        ),
        None,
    )
    secret = (
        next((asked.env for asked in held.asks if asked.secret), None)
        if held is not None
        else None
    )
    if secret is None:
        raise ValueError(
            f"The account {provider.name!r} was made by {provider.way!r}, which litellm "
            "does not offer; make it again by one of its own ways"
        )
    return {"api_key": env.get(secret, "")}


def configured(provider: Provider, key: str) -> dict[str, Any]:
    """What a gateway for one account is told, as the proxy reads its configuration.

    Every model at all, sent the way :func:`spelled` sends it: one entry for an id already
    written with the account's provider in front, and one for a bare id, which gets it. Both
    with the account's credentials, which is the whole of where they go.

    Args:
      provider: The account.
      key: The master key the gateway is to take, and nothing else.

    Returns:
      The configuration, as a mapping to write down as YAML -- which JSON is.

    Raises:
      ValueError: For an account made some way litellm does not offer, or one that says no
        provider for litellm to send it to.
    """
    said = prefix(provider)
    if not said:
        raise ValueError(
            f"The account {provider.name!r} names no provider for the gateway to send "
            "its turns to"
        )
    params: dict[str, Any] = {"model": f"{said}/*", **credentials(provider)}
    if provider.env.get(_URL):
        # A turn asked in the Responses API, as codex asks every one, sent to somebody's
        # endpoint as chat completions: the one every endpoint calling itself OpenAI-compatible
        # speaks, where litellm would otherwise ask it in the Responses API. A vendor's own
        # is asked in whichever it speaks, and one that has no Responses API in chat
        # completions anyway.
        params["use_chat_completions_api"] = True
    return {
        "model_list": [
            {"model_name": f"{said}/*", "litellm_params": params},
            {"model_name": "*", "litellm_params": params},
        ],
        "litellm_settings": {
            # A parameter the CLI sends that the provider has no word for is left off rather
            # than failing the turn, as it is for a turn of litellm's own.
            "drop_params": True,
            # Chat completions to an OpenAI-shaped provider rather than the Responses API: the
            # one every endpoint calling itself OpenAI-compatible speaks.
            "use_chat_completions_url_for_anthropic_messages": True,
        },
        "general_settings": {"master_key": key},
    }


def _routes(profile: backends.Profile) -> backends.Way | None:
    """The way a backend is spoken to the gateway through, or None for one that has none."""
    return next((one for one in profile.ways if one.name == profile.routes), None)


def spoken(profile: backends.Profile, url: str, key: str) -> dict[str, str]:
    """What a CLI is run with to speak to a gateway: its own way, answered with the gateway.

    Args:
      profile: The backend.
      url: Where the gateway is.
      key: Its master key.

    Returns:
      The variables of the way :attr:`~hmz.coganchor.backends.Profile.routes` names, the one
      that says where to go answered with the gateway -- at `/v1` for opencode, mimo and pi,
      whose SDKs add only the operation -- and its secret with the key, what has an answer
      that is usually right answered with that, and what the way sets. Nothing for a backend
      that names no such way.
    """
    way = _routes(profile)
    if way is None:
        return {}
    where = f"{url}{_VERSIONED}" if profile.name in _VERSIONED_FOR else url
    held: dict[str, str] = {}
    for asked in way.asks:
        if asked.secret:
            held[asked.env] = key
        elif asked.env == profile.endpoint or asked.env.endswith(("_URL", "_BASE")):
            held[asked.env] = where
        elif asked.fixed:
            held[asked.env] = asked.fixed
    return held | dict(way.sets)


def argued(profile: backends.Profile, env: Mapping[str, str]) -> tuple[str, ...]:
    """What that way adds to the CLI's own command line, filled in from what :func:`spoken` said.

    Args:
      profile: The backend.
      env: What :func:`spoken` answered.

    Returns:
      The arguments, and none for a way that adds none.
    """
    way = _routes(profile)
    if way is None:
        return ()
    held: list[str] = []
    for one in way.args:
        said = one
        for name, value in env.items():
            said = said.replace("{" + name + "}", value)
        held.append(said)
    return tuple(held)


def _free() -> int:
    """A TCP port on loopback that nothing is listening on as this is asked."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Gateway:
    """One litellm proxy on loopback, holding one account: see the module docstring.

    Attributes:
      port: The port of loopback it listens on.
      url: Where it is, as a base URL with no path.
      key: The master key it takes, which is the only credential the CLI is handed.
      account: The account it holds, as it was when it was started.
    """

    def __init__(self, provider: Provider, *, seconds: float = _READY) -> None:
        """Starts the proxy and waits for it to say it is up.

        Args:
          provider: The account to hold.
          seconds: How long it is given to come up.

        Raises:
          subprocess.CalledProcessError: If it cannot be started here, stops before it is up,
            or does not come up in time -- a turn that could not reach its model, which is a
            failed turn like any other.
        """
        self.account = provider
        self.key = f"sk-{secrets.token_urlsafe(32)}"
        self.port = _free()
        self.url = f"http://127.0.0.1:{self.port}"
        argv = [sys.executable, "-m", "litellm.proxy.proxy_cli"]
        if not gatewayable():
            raise subprocess.CalledProcessError(
                127,
                argv,
                "",
                "litellm's gateway is not installed in this Python environment, where it is "
                "the [litellm] extra: uv sync --extra litellm from a checkout, or install "
                "hmz[litellm]",
            )
        try:
            said = configured(provider, self.key)
        except ValueError as why:
            raise subprocess.CalledProcessError(1, argv, "", str(why)) from why
        # A directory of its own, which `mkdtemp` makes this user's alone, and the file in it
        # this user's alone from the moment it exists: it holds the account.
        self._folder = tempfile.mkdtemp(prefix="hmz-gateway-")
        config = os.path.join(self._folder, "config.yaml")  # noqa: PTH118
        descriptor = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as written:
            json.dump(said, written)
        argv += ["--config", config, "--host", "127.0.0.1", "--port", str(self.port)]
        self._argv = argv
        env = dict(os.environ)
        # Its catalogue of models and prices as it shipped rather than fetched as it starts,
        # and no database somebody's shell names: what it holds is this file and nothing else.
        env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
        for one in ("DATABASE_URL", "LITELLM_MASTER_KEY", "CONFIG_FILE_PATH"):
            env.pop(one, None)
        self._secrets = tuple(
            value
            for value in (*credentials(provider).values(), self.key)
            if len(value) > 3  # noqa: PLR2004 -- too short to be anybody's secret, or to hide
        )
        self._said: collections.deque[str] = collections.deque(maxlen=_TAIL)
        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                env=env,
                start_new_session=os.name != "nt",
            )
        except OSError:
            shutil.rmtree(self._folder, ignore_errors=True)
            raise
        # Taken down when the gateway is collected, or at exit for one held to the end.
        self._down = weakref.finalize(self, _taken_down, self._proc, self._folder)
        # A pipe nobody drains stops the proxy writing to it; the last of it is kept to say
        # why it stopped, should it stop.
        # Handed the stream and nothing of the gateway, which it would otherwise keep from
        # ever being collected -- and so from ever being taken down by being collected.
        threading.Thread(
            target=_drains,
            args=(self._proc.stdout, self._said),
            name="hmz-gateway",
            daemon=True,
        ).start()
        try:
            self._waits(seconds)
        except BaseException:
            self.stop()
            raise

    def _waits(self, seconds: float) -> None:
        """Waits for the proxy to answer, under its own key -- which only this one takes.

        Asked directly rather than through whatever proxy this process's environment names: the
        gateway is on loopback, and a proxy elsewhere has never heard of it.

        Raises:
          subprocess.CalledProcessError: If it stops first, or does not answer in time.
        """
        until = time.monotonic() + seconds
        asked = urllib.request.Request(  # noqa: S310 -- loopback, at the port chosen here
            f"{self.url}{_READY_AT}", headers={"Authorization": f"Bearer {self.key}"}
        )
        while True:
            status = self._proc.poll()
            if status is not None:
                raise subprocess.CalledProcessError(
                    status or 1, self._argv, "", self._why("stopped before it was up")
                )
            # Loopback, at the port this process chose: http, whatever the audit rule fears.
            with (
                contextlib.suppress(OSError, urllib.error.URLError),
                _DIRECT.open(asked, timeout=1) as answer,
            ):
                if answer.status == 200:  # noqa: PLR2004 -- OK
                    return
            if time.monotonic() > until:
                raise subprocess.CalledProcessError(
                    1, self._argv, "", self._why(f"was not up after {seconds:g}s")
                )
            time.sleep(0.2)

    def _why(self, what: str) -> str:
        """What the proxy last said, with every secret it holds struck out."""
        said = "\n".join(self._said)
        for one in self._secrets:
            said = said.replace(one, "***")
        return f"the LiteLLM gateway {what}" + (f":\n{said}" if said else "")

    @property
    def running(self) -> bool:
        """Whether the proxy is still there."""
        return self._down.alive and self._proc.poll() is None

    def stop(self) -> None:
        """Takes the proxy down, and its configuration with it. Stopping it twice is once."""
        self._down()


def _drains(stream: IO[str] | None, said: collections.deque[str]) -> None:
    """Reads what a proxy says, keeping the last of it."""
    if stream is None:
        return
    with contextlib.suppress(OSError, ValueError):
        for line in stream:
            said.append(line.rstrip())


def _taken_down(proc: subprocess.Popen[str], folder: str) -> None:
    """Takes a proxy and everything it started down, and removes its configuration.

    A function of its own rather than a method, since it runs as a finalizer: it must hold
    nothing of the gateway it takes down.
    """
    try:
        if os.name == "nt":
            if proc.poll() is None:
                proc.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=_STOP)
                proc.kill()
            proc.wait()
            return
        import psutil

        # Only while it is ours: the pid of one already gone and reaped is anybody's, and so
        # is the group named after it.
        if proc.poll() is not None:
            return
        kin: list[psutil.Process] = []
        with contextlib.suppress(psutil.Error):
            kin = psutil.Process(proc.pid).children(recursive=True)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=_STOP)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        for one in kin:
            with contextlib.suppress(psutil.Error):
                one.kill()
    finally:
        shutil.rmtree(folder, ignore_errors=True)
