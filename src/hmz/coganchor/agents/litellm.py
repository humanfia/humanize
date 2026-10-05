"""A model called directly through litellm: one chat completion a turn, over the history.

Not a coding agent. There is no CLI, no tool, no filesystem and no hook of the model's own: a
turn is the conversation so far and the prompt, sent as one chat completion, and the answer is
what came back. Which is what a flow wants where the work is the model's judgement rather than
an agent's hands -- a reviewer that reads what it is shown, a classifier, a judge -- and it costs
one request rather than a CLI starting up.

The conversation is a file of humanize's own, one JSON line per message under the directory
this agent keeps its sessions in, so a turn after the first is the file read back and the
prompt put on the end of it, and a fork is the file copied under a new id as the fork's first
turn goes. What the model spent is on each answer's line, which is where the tally and the
trace read it.

The account is whatever litellm is handed: under an account of humanize's, its key, its
gateway or its cloud, passed on the call rather than through the environment -- a turn is a
call in this process, and this process's environment is everybody's. With no account, litellm
reads the variables it always reads, which is the machine's own account for every vendor it
speaks.
"""

# A session and the agent holding it are two halves of one object declared here.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import importlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Protocol, cast

from hmz.coganchor import backends

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Failed, Saying, Unrecoverable, Usage, say

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping

    from pydantic import BaseModel

    from hmz.coganchor.fence import Fence

__all__ = ["LiteLLMAgent", "LiteLLMAgentConfig", "LiteLLMSession"]

_EXTRA = (
    "litellm is not installed in this Python environment, where it is the [litellm] extra "
    "rather than part of every install: uv sync --extra litellm from a checkout, or pip "
    f"install '{backends.LITELLM_SDK}'"
)

#: How long the endpoint may say nothing, in seconds, before the turn is given up on.
_SILENCE = 600.0

#: The variables a gateway account is made of, and which protocol of litellm's it speaks.
_URL = "LITELLM_GATEWAY_URL"
_KEY = "LITELLM_GATEWAY_KEY"
_API = "LITELLM_GATEWAY_API"

#: The clouds, each as the variables its account was made with and the litellm parameter
#: each of them is passed as.
_CLOUDS: dict[str, tuple[tuple[str, str], ...]] = {
    "bedrock": (("AWS_PROFILE", "aws_profile_name"), ("AWS_REGION_NAME", "aws_region_name")),
    "vertex": (
        ("VERTEXAI_PROJECT", "vertex_project"),
        ("VERTEXAI_LOCATION", "vertex_location"),
    ),
    "azure": (
        ("AZURE_API_BASE", "api_base"),
        ("AZURE_API_KEY", "api_key"),
        ("AZURE_API_VERSION", "api_version"),
    ),
}

#: What litellm says when the conversation no longer fits the model, which another try at the
#: same length meets again.
_TOO_LONG = "ContextWindowExceededError"


class _LiteLLM(Protocol):
    """The part of litellm a turn uses."""

    def completion(self, **kwargs: object) -> Iterable[object]: ...


@dataclass(frozen=True, kw_only=True)
class LiteLLMAgentConfig(AgentConfig):
    """The model and effort every litellm session runs at.

    The model is a litellm model string, its provider in front -- `openai/gpt-5`,
    `anthropic/claude-sonnet-4-5`, `bedrock/...` -- which is how litellm knows where to send it.
    Under a gateway account a bare id is sent to the gateway in the protocol the account
    named.
    """


class LiteLLMAgent(AgentBase):
    """A model called through litellm, with no tools: see the module docstring."""

    #: What it counts: the four kinds a chat completion's usage names.
    counts: ClassVar[frozenset[str]] = frozenset(
        {"input", "output", "cache_read", "cache_write"}
    )

    def __init__(self, config: LiteLLMAgentConfig, *, name: str | None = None) -> None:
        super().__init__(config, name=name)

    def natively(self, fence: Fence) -> Fence:
        """The whole of it: a turn runs nothing, reads nothing and writes nothing.

        A turn is one request from this process to the model's endpoint, and the model has no
        tool to reach anything with. So there is nothing to put a fence around: what a flow's
        permission keeps an agent from is what this one cannot do at all.

        Args:
          fence: The fence this agent is held to.

        Returns:
          A fence that holds nothing more from outside.
        """
        return fence.without(filesystem=True, network=True)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> LiteLLMSession:
        """Opens a conversation, which has no history until its first turn."""
        return LiteLLMSession(self, cwd)


class LiteLLMSession(SessionBase):
    """One conversation with a model, kept as a file of its messages."""

    #: Handed the schema, as litellm's `response_format`, rather than asked in the prompt.
    shapes: ClassVar[bool] = True

    #: The history is a file rather than a directory's, so a fork goes wherever it is asked.
    forks_elsewhere: ClassVar[bool] = True

    def __init__(
        self, agent: LiteLLMAgent, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        #: The id the turn now opening this conversation will adopt, while it runs.
        self._attempt_id: str | None = None
        #: The answer being streamed now, so that a cut can close it from another thread.
        self._live: object | None = None

    @property
    def named(self) -> str | None:
        """The id, including the one whose opening turn is still running."""
        return super().named or self._attempt_id

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends the history and the prompt as one chat completion, and reads the answer."""
        session_id = self._id or f"session-{uuid.uuid4().hex}"
        self._attempt_id = session_id
        model = self._model()
        saying = Saying()
        usage = Usage()
        history: list[dict[str, str]] = []
        asked = {"role": "user", "content": prompt}
        try:
            module = _litellm()
            history = self._history()
            call: dict[str, object] = {
                "model": model,
                "messages": [*history, asked],
                "stream": True,
                "stream_options": {"include_usage": True},
                "timeout": _SILENCE,
                # A parameter one provider takes and another refuses -- a reasoning effort
                # sent to a model with none -- is left off rather than failing the turn.
                "drop_params": True,
                **self._credentials(),
            }
            if effort := self.effort:
                call["reasoning_effort"] = effort
            if schema is not None:
                call["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                    },
                }
            answer = module.completion(**call)
            self._live = answer
            for chunk in answer:
                for choice in _listed(_field(chunk, "choices")):
                    delta = _field(choice, "delta")
                    for kind, name in (
                        ("reasoning", "reasoning_content"),
                        ("text", "content"),
                    ):
                        piece = _field(delta, name)
                        if isinstance(piece, str) and piece:
                            saying.delta(kind, piece)
                spent = _usage(_field(chunk, "usage"))
                if spent.total:
                    usage = spent
                if self._cut:
                    break
            if usage.total:
                self._spends(usage)
            said = list(saying.rest())
            text = "".join(one.text for one in said if one.kind == "text")
            reasoning = "".join(one.text for one in said if one.kind == "reasoning")
            self._keep(session_id, history, asked, text, reasoning, usage, model)
            self._adopt(session_id)
            for event in said:
                yield self._shows(event)
            tokens = int(usage.total)
            result = Event(
                kind="result",
                text=text,
                tokens={model: tokens} if tokens else {},
                spent=usage,
            )
            if not self._agent._watchers:
                say(result.text, sys.stdout)
            yield result
        except (ModuleNotFoundError, ValueError, RuntimeError):
            raise
        except Exception as why:
            rest = saying.rest()
            for event in rest:
                yield self._shows(event)
            said = f"{type(why).__name__}: {why}"
            kind = Unrecoverable if _TOO_LONG in said else Failed
            if self._cut:
                # Taken away underneath its own reader, which is the cut rather than a
                # failure of the turn's own: the turn answers with what had been said, and
                # the conversation goes on from it.
                text = "".join(one.text for one in rest if one.kind == "text")
                self._keep(session_id, history, asked, text, "", usage, model)
                self._adopt(session_id)
                raise OSError(said) from why
            yield self._shows(Event(kind="failed", text=said))
            raise kind(1, ["litellm", model], output="", stderr=said) from why
        finally:
            self._attempt_id = None
            self._live = None

    def _cuts(self) -> None:
        """Closes the answer being streamed, which is what stops the turn now."""
        live = self._live
        for holder in (live, _field(live, "completion_stream")):
            close = getattr(holder, "close", None)
            if callable(close):
                with contextlib.suppress(Exception):
                    close()

    def _shows(self, event: Event) -> Event:
        """Shows an event on an unwatched run and returns it for the stream."""
        if not self._agent._watchers:
            say(event.text, sys.stderr)
        return event

    def _model(self) -> str:
        """The litellm model string this turn is sent to.

        Under a gateway account, a bare id prefixed with the protocol the account named: the
        gateway serves the id, and litellm needs to know how to speak to it.
        """
        model = self._agent.config.model
        provider = self._agent.provider
        api = provider.env.get(_API, "") if provider is not None else ""
        if api and not model.startswith(f"{api}/"):
            return f"{api}/{model}"
        return model

    def _credentials(self) -> dict[str, object]:
        """What the account this turn runs under is, as litellm's own parameters.

        Passed on the call rather than set in the environment, which is this process's and
        every other turn's. Nothing at all with no account, for litellm to read the variables
        of this machine's own as it always does.

        Raises:
          Failed: For an account made some way this backend does not offer.
        """
        provider = self._agent.provider
        if provider is None:
            return {}
        env = provider.env
        if provider.way in _CLOUDS:
            return {
                name: env[variable]
                for variable, name in _CLOUDS[provider.way]
                if env.get(variable)
            }
        if env.get(_URL):
            return {"api_base": env[_URL], "api_key": env.get(_KEY, "")}
        way = next(
            (
                one
                for profile in backends.PROFILES
                if profile.name == "litellm"
                for one in profile.ways
                if one.name == provider.way
            ),
            None,
        )
        secret = next(
            (asked.env for asked in way.asks if asked.secret), None
        ) if way is not None else None
        if secret is None:
            said = (
                f"The account {provider.name!r} was made by {provider.way!r}, which "
                "litellm does not offer; make it again by one of its own ways"
            )
            raise Failed(1, ["litellm", provider.name], output="", stderr=said)
        return {"api_key": env.get(secret, "")}

    def _file(self, session_id: str) -> Path:
        """Where one conversation of this agent is kept."""
        kept = self._agent.kept()
        assert kept is not None  # noqa: S101 -- litellm's home is always known
        return kept / "sessions" / f"{session_id}.jsonl"

    def _history(self) -> list[dict[str, str]]:
        """The conversation so far, as the messages a chat completion is sent.

        Read off this conversation's own file once it has one, and off the one it was forked
        from for a fork's first turn, which is where the fork is cut.

        Raises:
          RuntimeError: If a conversation that has turns has no file to read them from.
        """
        whose = self._id or self._forked_from
        if whose is None:
            return []
        path = self._file(whose)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            raise RuntimeError(f"litellm: no conversation kept at {path}") from None
        held: list[dict[str, str]] = []
        for line in lines:
            row = _mapping(_loaded(line))
            message = _mapping(row.get("message"))
            role, content = message.get("role"), message.get("content")
            if isinstance(role, str) and isinstance(content, str):
                held.append({"role": role, "content": content})
        return held

    def _keep(
        self,
        session_id: str,
        history: list[dict[str, str]],
        asked: dict[str, str],
        text: str,
        reasoning: str,
        usage: Usage,
        model: str,
    ) -> None:
        """Writes the turn down: the whole file for the turn that opens a conversation, the
        two new lines for every turn after it.
        """
        path = self._file(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        rows: list[dict[str, object]] = []
        if self._id is None:
            rows.append(
                {
                    "type": "session",
                    "id": session_id,
                    "parent": self._forked_from,
                    "cwd": self.cwd,
                    "model": model,
                    "timestamp": now,
                }
            )
            rows += [
                {"type": "message", "timestamp": now, "message": one}
                for one in history
            ]
        rows.append({"type": "message", "timestamp": now, "message": asked})
        answer: dict[str, object] = {
            "role": "assistant",
            "content": text,
            "model": model,
            "usage": dict(usage),
        }
        if reasoning:
            answer["reasoning"] = reasoning
        rows.append({"type": "message", "timestamp": time.time(), "message": answer})
        with path.open("a" if self._id is not None else "w", encoding="utf-8") as kept:
            kept.writelines(json.dumps(row) + "\n" for row in rows)


def _litellm() -> _LiteLLM:
    """Loads litellm only when a turn needs it."""
    try:
        module = importlib.import_module("litellm")
    except ModuleNotFoundError as why:
        if why.name != "litellm":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    return cast("_LiteLLM", module)


def _field(held: object, name: str) -> object:
    """One field of a litellm object or of a mapping, or None where it has none."""
    if isinstance(held, dict):
        return cast("dict[str, object]", held).get(name)
    return getattr(held, name, None)


def _listed(held: object) -> list[object]:
    """A list off the wire, or nothing for anything else."""
    return cast("list[object]", held) if isinstance(held, list) else []


def _mapping(held: object) -> Mapping[str, object]:
    """A mapping off the wire, or an empty one for anything else."""
    return cast("Mapping[str, object]", held) if isinstance(held, dict) else {}


def _loaded(line: str) -> object:
    """One line of a conversation's file, or None for one that is not JSON."""
    try:
        return cast("object", json.loads(line))
    except json.JSONDecodeError:
        return None


def _count(held: object) -> float:
    """A token count off the wire, or nothing for anything else."""
    return (
        float(held)
        if isinstance(held, int | float) and not isinstance(held, bool)
        else 0.0
    )


def _usage(held: object) -> Usage:
    """A chat completion's usage, under humanize's names and with its kinds apart.

    A prompt's cached tokens are inside its `prompt_tokens` on the OpenAI contract, so they
    are taken back out of the input rather than counted twice; Anthropic's cache writes are
    beside it.
    """
    if held is None:
        return Usage()
    prompt = _count(_field(held, "prompt_tokens"))
    read = _count(_field(_field(held, "prompt_tokens_details"), "cached_tokens"))
    written = _count(_field(held, "cache_creation_input_tokens"))
    kinds = {
        "input": max(prompt - read - written, 0.0),
        "output": _count(_field(held, "completion_tokens")),
    }
    if read:
        kinds["cache_read"] = read
    if written:
        kinds["cache_write"] = written
    return Usage(kinds)
