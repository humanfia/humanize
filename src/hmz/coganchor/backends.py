"""What is true of each coding agent CLI, written down once.

Facts rather than code: what a backend is called, what it answers to on a command line, how
hard it thinks, where it keeps its home and which files under it a session is logged to. Four
things need these and none of them needs the others -- driving a backend, reading a run's cost
as it happens, gathering its trajectories afterwards, offering what it runs at a prompt -- so
they are here rather than in whichever of those was written first.

What it runs is not here, and cannot be: a model id is whatever that CLI shipped this week, on
whatever account the turns run as. :mod:`hmz.coganchor.models` asks the backend itself and keeps
what it says. The efforts are, because they are the backend's own vocabulary rather than a catalogue
-- `xhigh` means the same thing next release -- and a model narrows them to the ones it takes.

Nothing is imported to read this, which is what lets a trace being gathered and the model
list have it without paying for the agents themselves. The code that acts on a fact lives where its
purpose does: driving in :mod:`hmz.coganchor.agents`, reading back in :mod:`hmz.runtime.tracing`.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "ALIKE",
    "AS_CONFIGURED",
    "AUTO",
    "DSH_SDK",
    "FAULTS",
    "PROFILES",
    "SIGNS",
    "SWARM",
    "UNKNOWN",
    "Asked",
    "Bundled",
    "Hooked",
    "Model",
    "Profile",
    "Sign",
    "Way",
    "alike",
    "declared",
    "elsewhere",
    "forget",
    "installing",
    "journalled",
    "named",
    "permitted",
    "profiles",
    "program",
    "reachable",
    "read",
    "remember",
    "serves",
    "speaking",
    "trouble",
    "written",
]


@dataclass(frozen=True, slots=True)
class Asked:
    """One thing a person has to say for a way in to be usable.

    Attributes:
      env: The environment variable the answer becomes, which is how every one of these CLIs
        takes a credential that was not left behind by a login. It is also what the answer is
        called wherever it is written down.
      about: The question, as it is put to whoever is answering it.
      secret: Whether what they type is a secret, and so is neither echoed nor shown again.
      keep: Whether the answer is kept as that variable. False for one that is only handed to
        the command the way runs -- a key read off stdin ends up inside the CLI's own store,
        and keeping a second copy of it in an environment would be a second place to leak it.
      fixed: What it is when nobody is asked, for a question with an answer that is usually
        right.
    """

    env: str
    about: str
    secret: bool = False
    keep: bool = True
    fixed: str = ""


@dataclass(frozen=True, slots=True)
class Way:
    """One way of getting credentials into a backend, as that backend offers it.

    A CLI has more than one: the subscription it signs into, an API key of the vendor's own,
    a gateway speaking the vendor's protocol, an account on somebody's console. Each is a
    different thing to be told and lands somewhere different -- a login writes the CLI's own
    store, a key is an environment variable -- and a provider is one of these, answered.

    Attributes:
      name: What this way is called, which is what a provider says it was made by.
      about: One line saying what it is, for whoever is choosing between them.
      argv: The backend's own command to run for it, under the provider's own paths, with the
        terminal handed over -- which is what makes a login a login rather than a form. Empty
        for a way that is only answers.
      asks: What to ask before running it, in the order to ask.
      sets: What this way sets whatever the answers are, such as the variable that switches a
        backend onto a vendor's cloud.
      args: What to add to the backend's own command line for a turn run under it, with
        `{VARIABLE}` filled in from the answers -- for a backend told about a provider on its
        command line rather than through its environment.
      stdin: The variable whose answer is written to `argv`'s standard input, for a command
        that reads a key rather than prompting for one.
    """

    name: str
    about: str
    argv: tuple[str, ...] = ()
    asks: tuple[Asked, ...] = ()
    sets: tuple[tuple[str, str], ...] = ()
    args: tuple[str, ...] = ()
    stdin: str = ""


#: Every kind of failure a turn of one of these CLIs comes to a stop at. The names alone: what
#: is looked for in a message, and in which order, is :data:`SIGNS` -- one list read from the
#: top, so that a line saying both `429` and `timeout` is read as the rate limit it is rather
#: than as the wire going quiet, and a `403` that names a model is not read as a credential.
#:
#: A kind rather than a message, because the answer to each of them is a different answer:
#: waiting is what a rate limit wants and what a revoked key would only make longer; another
#: account is what a refused credential wants and what a retired model has no use for; another
#: place is what a CLI that is not installed wants and no account of it can give. Before this
#: there were two -- a turn that failed and a turn that could not come out differently -- so
#: every one of these was retried the same way, and a 401 was tried five times on a schedule.
#:
#: What each of them means:
#:
#: - `contended`: two turns at one local store. opencode's SQLite is shared across workspaces,
#:   and the loser of a race says `database is locked` before it has spoken to any provider.
#: - `throttled`: too many requests. The whole account rather than the one call, but for a
#:   while rather than for good: the service is limiting how fast it is asked, and waiting is
#:   what answers it, with another account after that.
#: - `spent`: a quota or a balance used up, which the service says in so many words --
#:   `insufficient_quota`, a credit balance too low, billing. It arrives as the same `429` a
#:   rate limit does and is answered the same way, but a person reading it has something to
#:   do that a person reading a rate limit does not, so it is said as what it is.
#: - `refused`: the credential, not the request -- 401, a login that has expired, a key that
#:   was revoked. The same key a second later is the same answer, so nothing here is tried
#:   again.
#: - `unlisted`: the model, not the credential. The key was good enough to be told no about
#:   one model: a gateway fronting several clouds serves the ids its own keys are entitled to,
#:   and the one the turn named is not among them. It says `403` like a refused credential and
#:   means something a person does something else about, so it is a kind of its own.
#: - `retired`: a model that is gone, or one the service says never existed. No account of
#:   this CLI has it either, so what answers it is another place.
#: - `missing`: nothing to run. The CLI is not installed, or will not start.
#: - `sandboxed`: the machine, not the account. A CLI that confines its own tool calls could
#:   not set that confinement up -- an unprivileged container with no user namespace to give
#:   bubblewrap -- and it says `Permission denied` while having been refused nothing at all.
#: - `unmirrored`: this machine's filesystem, not the account. The copy of another machine's
#:   workspace a harness here works in could not be made at its path -- one that may not be
#:   created here, or that is not a directory -- and it says `Permission denied` too.
#: - `fenced`: this run's network fence, not the account. The proxy a fenced turn reaches the
#:   network through refuses a host the role may not reach with a `403`, and the CLI passes
#:   that on as the `Forbidden` a refused credential is said in.
#: - `killed`: the process died rather than answered -- a signal, an out-of-memory kill.
#: - `dropped`: the wire. A connection reset, a broken pipe, a gateway that went away.
FAULTS = (
    "contended",
    "spent",
    "throttled",
    "refused",
    "unlisted",
    "retired",
    "missing",
    "sandboxed",
    "unmirrored",
    "fenced",
    "killed",
    "dropped",
)


@dataclass(frozen=True, slots=True)
class Sign:
    """One thing a CLI says when a turn stops, and which kind of failure that makes it.

    Written down here, beside everything else that is true of a backend, rather than as a
    regex in whichever driver met it first: what a CLI says when it fails is a fact about that
    CLI, and a fact about a CLI is written down once.

    Attributes:
      fault: The kind, as :data:`FAULTS` names them.
      says: What to look for in what it said, as a regular expression read without case. It is
        searched for rather than matched, these being sentences inside a stream rather than
        the whole of one.
    """

    fault: str
    says: str


#: What these CLIs say when a turn stops, for the failures every one of them can have.
#:
#: Every one of them is a program that speaks HTTP to a model provider, so the statuses and
#: the vendors' own words for them are shared: a `429` is a `429` whichever CLI was holding
#: the socket. What one CLI says and no other does goes on that backend's own profile, in
#: `signs`, and is read first.
#:
#: Read from the top, first one that matches. So the order is the whole of how one signature
#: is told from another that is also in the line, and a sentence goes in front of a number:
#: `403 key not allowed to access model` carries a status that means a credential and a
#: sentence that means a model, and a gateway account told to sign in again over a model id
#: is a person sent to fix something that was never broken. Which is why the two kinds a
#: credential's own words would otherwise swallow are written where they are -- after the
#: quota and the busy store, whose signatures are nobody else's, and before the 401.
SIGNS: tuple[Sign, ...] = (
    # This machine rather than anything a turn reached for, and first because the words
    # underneath it are a credential's: the anchor could not make the copy of the target's
    # workspace a harness here works in, and says so in these words
    # (`hmz.coganchor.anchor.UNMIRRORED`) ahead of why -- often `Permission denied`.
    Sign("unmirrored", r"cannot keep the local copy of the work at"),
    # The run's own fence rather than the provider, and in front of the credentials for the
    # same reason: the proxy that holds a fenced turn to the hosts its role may reach refuses
    # any other with `403 Forbidden` and says so in these words
    # (`hmz.coganchor.fence.proxy`), and nobody's sign-in was refused at all.
    Sign("fenced", r"is not a host this run may reach"),
    # Two turns at one store rather than anything to do with an account: opencode keeps its
    # sessions in a SQLite database shared across workspaces, and the loser of that race is
    # told so before it has spoken to a provider at all. Transient, and nothing else fixes it.
    Sign("contended", r"database (is|table .{0,40} is) locked"),
    Sign("contended", r"SQLITE_BUSY"),
    # A sign-in that refreshes itself, held by another turn the other way round: a copy of it
    # out on another machine, or turns here using it while this one would send one out.
    Sign("contended", r"signs in with a token that refreshes itself"),
    # A quota or a balance the account has used up, in the words the services use for it --
    # `insufficient_quota` is OpenAI's, `Quota exceeded` Google's, a credit balance too low
    # Anthropic's. In front of the rate limit because it comes as the same `429`, and a
    # plain `429` from a gateway said as a quota spent is a person sent to top up an account
    # that was only being asked too fast.
    Sign("spent", r"quota"),
    Sign("spent", r"insufficient[ _-]balance"),
    Sign("spent", r"credit balance is too low"),
    Sign("spent", r"billing"),
    # Too many requests, under every name the services put on it. `RESOURCE_EXHAUSTED` is
    # Google's word for that status and `overloaded_error` what Anthropic answers 529 with
    # -- each of them answered by waiting rather than by asking again now.
    Sign("throttled", r"\b429\b"),
    Sign("throttled", r"\b529\b"),
    Sign("throttled", r"too many requests"),
    Sign("throttled", r"rate[ _-]?limit"),
    Sign("throttled", r"resource[ _-]?exhausted"),
    # The same status said as a sentence, which is how Grok Build puts xAI's 429 on its last
    # line -- `Some resource has been exhausted: You are sending requests too quickly` -- with
    # the number only in a log line above it.
    Sign("throttled", r"resource has been exhausted"),
    Sign("throttled", r"sending requests too quickly"),
    Sign("throttled", r"overloaded"),
    Sign("throttled", r"usage limit"),
    # The machine rather than the account, and in front of the credentials because the word it
    # fails with is one of theirs. A CLI that confines its own tool calls asks the kernel for
    # a namespace to confine them in, and an unprivileged container has none to give: `bwrap:
    # setting up uid map: Permission denied` is grok under `--sandbox` on a machine that will
    # not let it, and nothing there was refused a key. Each of these says the sandbox itself
    # could not be got rather than merely naming one -- `bwrap:` is bubblewrap's own prefix on
    # its own errors, and a line that only mentions a sandbox is a line about a sandbox.
    Sign("sandboxed", r"\bbwrap: "),
    Sign(
        "sandboxed",
        r"(failed to|could not|cannot|unable to) "
        r"(create|set ?up|start|enter|initiali[sz]e)[^.]{0,30}(sandbox|namespace)",
    ),
    Sign(
        "sandboxed",
        r"(sandbox|landlock|seccomp|seatbelt)[^.]{0,40}"
        r"(denied|not (permitted|allowed|supported|available))",
    ),
    Sign(
        "sandboxed",
        r"user namespaces? [^.]{0,40}"
        r"(disabled|denied|not (permitted|allowed|supported|available|enabled))",
    ),
    # The model rather than the credential, and in front of the credentials for that reason:
    # a gateway fronting several clouds refuses an id its key is not entitled to with a `403`
    # and a sentence naming the model, and the status alone would send somebody to sign an
    # account in that was never refused. Seen against an OpenAI-compatible gateway as `403 key
    # not allowed to access model. This key can only access models=[...]. Tried to access
    # gpt-5.2`, and it is the shape every such gateway refuses an unentitled id in.
    Sign("unlisted", r"not allowed to access (the )?model"),
    Sign("unlisted", r"can only access models"),
    Sign("unlisted", r"(do(es)? not|don't|doesn't) have access to (the )?model"),
    Sign(
        "unlisted",
        r"not (entitled|authori[sz]ed|permitted) to (use|access) (the )?model",
    ),
    Sign("unlisted", r"model[^.]{0,40}(is )?not (allowed|enabled|entitled|permitted)"),
    # Codex on a subscription, told to run a model that account does not include. The model is
    # real and somebody else's account has it, which is what makes it this rather than a model
    # that has gone.
    Sign("unlisted", r"is not supported when using"),
    # The credential rather than the request. Another try with the same one is the same
    # answer, so the tries here are worth none at all and the next place is the whole of the
    # answer -- with a word to say that the account it left needs signing in again.
    Sign("refused", r"\b40[13]\b"),
    Sign("refused", r"unauthori[sz]ed|unauthenticated"),
    Sign("refused", r"authentication (is )?(required|failed|error)"),
    Sign("refused", r"invalid[ _-]?api[ _-]?key"),
    Sign("refused", r"permission[ _-]?denied"),
    Sign("refused", r"(not|no longer) (logged|signed) in"),
    Sign("refused", r"not logged into"),
    Sign("refused", r"please (run )?(login|log ?in|sign ?in)"),
    Sign("refused", r"no credential"),
    Sign("refused", r"(token|credentials?|session) (has |have )?expired"),
    # A sign-in that refreshes itself, revoked by its vendor -- which is what two copies of it
    # refreshing apart come to. Codex says `your refresh token was revoked`.
    Sign("refused", r"token (was |has been )?revoked"),
    Sign("refused", r"forbidden"),
    # A model that is gone, or one this account was never entitled to. No other account of
    # this CLI has it either, so what answers it is a place that names another model.
    Sign("retired", r"\b404\b"),
    Sign("retired", r"model[ _-]?not[ _-]?found"),
    Sign("retired", r"(unknown|unsupported|invalid|no such) model"),
    Sign(
        "retired",
        r"model[^.]{0,80}?(does not exist|is not available|was not found"
        r"|is not supported|retired|deprecated)",
    ),
    Sign("retired", r"does not exist or you do not have access"),
    # The process died rather than answered. Reopening is what answers it, and saying which
    # signal did it is the difference between a bug report and a machine that is out of memory.
    Sign("killed", r"out of memory|\bOOM\b|oom-?kill"),
    Sign("killed", r"SIG(KILL|SEGV|ABRT|BUS)"),
    Sign("killed", r"reached heap limit"),
    Sign("killed", r"segmentation fault"),
    # The wire. What answers it is a new transport and the conversation resumed by its id --
    # the session is the backend's own, so nothing about it was lost when the socket was.
    Sign("dropped", r"ECONNRESET|EPIPE|ECONNREFUSED|ETIMEDOUT|EAI_AGAIN|ENOTFOUND"),
    Sign("dropped", r"connection (was )?(reset|closed|refused|aborted|error|failed)"),
    Sign("dropped", r"APIConnectionError"),
    Sign("dropped", r"broken pipe|socket hang ?up|premature close"),
    Sign("dropped", r"fetch failed"),
    Sign("dropped", r"\b50[234]\b"),
    Sign("dropped", r"bad gateway|service unavailable|gateway time-?out"),
    Sign("dropped", r"timed out|timeout"),
)


@dataclass(frozen=True, slots=True)
class Hooked:
    """How one CLI takes a table of hooks written for a single run of it.

    A hook table under the CLI's own home is everybody's: it fires for the turns a person takes
    at their own prompt as well as for a flow's, and a flow that wrote one there would be a
    flow that changed that machine. What is wanted is a table this run is told about and
    nothing else reads, which these CLIs offer in three different shapes -- so which shape it
    is, and what it is called, is written down here beside everything else that is true of a
    backend.

    Attributes:
      seam: Which way the CLI is told: `flag` for a table named on its command line, `env` for
        one named by a variable of its own, `config` for one set as a key of the settings a
        turn is started with. The three are the whole of it, so a fourth is a typo rather than
        a seam and is refused where a type checker reads this.
      name: What that flag, variable or key is called, exactly as the CLI spells it.
    """

    seam: Literal["flag", "env", "config"]
    name: str


@dataclass(frozen=True, slots=True)
class Bundled:
    """One file inside a CLI's own install, and what says it is the file that was meant.

    A CLI shipped as a bundle is one file with the whole of it inside, minified and rewritten
    by whatever built it, so nothing about it is stable between releases: what was patched this
    morning is a different file tonight, under the same path. A fingerprint is what makes
    reaching into one safe -- a file that does not answer to this is one nobody here has seen,
    and is left alone rather than patched on the strength of its name.

    What it answers to is a shape rather than one build, and that is what keeps it true. A
    fingerprint written as the bytes of the release it was read off -- `VERSION:"2.1.269"` --
    is one that stops matching the morning the next release lands, and stops matching in
    silence: the patch reaches nothing, the run takes the shallower way in, and nobody is told
    the deeper road closed. The question a fingerprint is actually asked is whether the file at
    this path is the program this was written against rather than whatever the directory holds
    today, and what answers that is the bundle's shape -- that its graph parses, that it
    carries the constant a patch is written around, that the constant sits in one module a
    patch can be put in -- not which digits that constant happens to hold this week. So the
    shape is what is written down here, and which release is installed stops being a fact
    anybody has to keep up to date in order for the deeper road to stay open.

    Attributes:
      path: Where the file is, relative to the directory the CLI is installed in, as a glob:
        a bundle is versioned by the directory over it far more often than by its own name.
      says: A pattern -- a regular expression, matched against each module's source as bytes --
        that the module a patch is written into contains: the call being reached for or the
        constant beside it, spelled as the bundler leaves it and left open wherever a release
        varies it. A pattern rather than a literal, so bytes meant literally are escaped before
        they go in -- `re.escape` does it -- and a bracket that was left unescaped is refused
        below rather than quietly read as a group. Said rather than defaulted, since a bundle
        named by its path alone is the thing this exists to prevent.
      digest: The SHA-256 of that file whole, as it was last seen, and "" for a bundle
        recognized by what it contains rather than by being exactly one release -- which is
        most of them, a release a week being a digest a week.
    """

    path: str
    says: str
    digest: str = ""

    def __post_init__(self) -> None:
        """Refuses a fingerprint that is not a pattern, where it is written rather than read.

        The layer that matches this promises never to raise -- every way a bundle can fail to
        answer is a fall back and a line in the log -- so a pattern that will not compile would
        arrive there as a run that quietly took the shallower road for no reason it could name.
        Compiled here instead, and as the bytes it is actually matched against, so a typo is a
        module that will not import rather than a road that closed without saying so.

        Raises:
          ValueError: `says` is not a regular expression.
        """
        try:
            re.compile(self.says.encode())
        except (re.error, UnicodeEncodeError) as why:
            raise ValueError(f"a bundle fingerprint must be a pattern: {why}") from why


@dataclass(frozen=True, slots=True)
class Model:
    """One model a backend runs, and the efforts it runs at.

    What a backend answered when it was asked what it runs, rather than anything written down
    here: :mod:`hmz.coganchor.models` is what asks and what keeps the answer.

    Attributes:
      name: What to ask the backend for. The id it answers to, never an alias it also takes:
        `opus` is whichever Opus is newest today and something else tomorrow, so an epic that
        recorded it says nothing about what actually ran.
      efforts: The efforts this model takes, hardest first, which is not always all of the
        ones its backend has.
      swarms: Whether it also runs a turn as a fleet of subagents rather than as one agent,
        which is a second thing to say about a turn and not a harder version of the first --
        so it is chosen alongside the effort rather than among them.
    """

    name: str
    efforts: tuple[str, ...]
    swarms: bool = False


#: What an effort is prefixed with to ask for a turn run as a fleet of subagents rather than
#: as one agent: `max` and `swarmmax` are the same thinking at two widths. Written here beside
#: the ladders and beside `Profile.swarms`, because it is part of how a rung is spelled rather
#: than anything one driver invented: whatever reads an effort -- the interface that offers
#: one, the check that refuses one, the driver that sends one -- has to take the prefix off
#: before it has a rung, and a second copy of the word is a second chance for one of them to
#: read `swarmmax` as a rung no backend has.
SWARM = "swarm"

#: What is offered for a CLI that speaks only the Agent Client Protocol. The protocol says
#: nothing about which models an agent runs or how hard it may be asked to think -- both are
#: the agent's own -- so one of each is offered and neither is sent.
#:
#: Which makes it the word for there being no ladder rather than a rung on one, and the two
#: read differently wherever a rung is checked: a CLI somebody added runs at whatever they
#: configured it to run at, and refusing every word but this one would leave an added CLI
#: unusable at any effort a person would actually type.
_UNSAID = "as configured"

#: The written form of no rung at all: an agent asked for `auto` is an agent humanize says
#: nothing to its CLI about how hard to think, which leaves the model at whatever that CLI
#: gives it.
#:
#: It exists because a rung is not always a thing a model has. Cursor's `composer-2.5`,
#: `gemini-3.1-pro` and `auto` take no rung, Antigravity has models with no variants, and a
#: gateway serves plenty of models that reason at one setting and no other. Inside, such an
#: agent runs at `""` -- the absence of a rung, which every driver already knows to say
#: nothing about. But `""` cannot be written down: an agent is spelled `CLI/MODEL:EFFORT`
#: everywhere a person or a settings file names one, and `cursor-agent/composer-2.5:` is not
#: a line anybody would type. Nor can the effort just be left off where it is written back:
#: a model may hold a `:` of its own, and `qwen3:latest` written with no effort after it reads
#: back as `qwen3` at `latest`. So the absence gets a word.
#:
#: The two are one value and not two. Every way in normalises `auto` to `""` and every way
#: out writes `""` back as `auto`, so nothing downstream has to know there were ever two
#: spellings, and a backend whose ladder happens to be empty is asked for the same nothing
#: as a model that simply has no rungs.
AUTO = "auto"


def written(effort: str) -> str:
    """One effort as a line names it, which is where the absence of a rung gets its word.

    The inverse of what :func:`read` does to an `auto` it is given. Used wherever an agent is
    written back out -- a settings file, a run remembered for `hmz` to offer again, the line
    the interface shows -- so that an agent at no rung round-trips instead of becoming
    `MODEL:`, which is not a spec anything can read.

    Args:
      effort: The rung, in the backend's own wording, or "" for no rung at all.

    Returns:
      That rung, or :data:`AUTO` where there is none.
    """
    return effort or AUTO


#: The word a line uses for an agent nobody has narrowed. Inside that is `""`, no rung at all,
#: and on a screen `""` is a gap where a word was -- a gap that says nothing about whether
#: anybody chose it, and reads the same as a setting that had gone missing. This says the
#: thing that is true of such an agent wherever it is shown: it is allowed what it was
#: configured to be allowed, and the line is not narrowing it any further.
#:
#: Two words rather than one, and a space in the middle of them, because it is only ever
#: shown. `auto` is a word a person may type back at a line that showed it; this is not one of
#: the rungs and must never be readable as one, and a rung with a space in it is a rung
#: nothing takes.
AS_CONFIGURED = "as configured"


def permitted(permission: str) -> str:
    """What an agent may do as a line names it, the way :func:`written` names an effort.

    Args:
      permission: The rung, as one of `hmz.coganchor.agents.PERMISSIONS`, or "" for an agent
        nobody has been asked about.

    Returns:
      That rung, or :data:`AS_CONFIGURED` where there is none.
    """
    return permission or AS_CONFIGURED


#: How long a turn may say nothing before it is worth looking at, for a backend that has not
#: said otherwise. A quarter of an hour: every CLI here reports its tool calls as it makes
#: them, so a turn silent this long is either a model on one very long thought or a CLI that
#: has stopped -- and the first of those is rare enough to be worth interrupting once in order
#: to catch the second at all.
_SILENCE = 900.0


@dataclass(frozen=True, slots=True)
class Profile:
    """One coding agent CLI, as everything outside its driver needs to know it.

    Attributes:
      name: What this backend is called here, which is the command it is installed as.
      aliases: What a command line may call it, this name included. A backend is named twice
        where both spellings are what people call it, and neither is ambiguous.
      home_var: The environment variable that moves its home directory.
      home_dir: Where that home is by default, under this user's own.
      home_in: What to look under inside the directory that variable names, for a backend
        whose variable is the one every program shares -- `XDG_DATA_HOME` says where all of
        them keep their data, and this one's is a directory of its own under it. Empty for a
        backend whose variable names its home outright, which is what a variable of its own
        does.
      logs: The files one session is logged to under that home, as globs taking `{ident}`.
        Claude gets two -- a sub-agent it starts writes its own transcript, and the tokens it
        spends are the run's.
      encodes: Whether those globs name a session by its id written in URL-safe base64 rather
        than by the id itself. MiniMax Code's is: a session's directory is named for the
        moment it opened and `session_` and the id encoded, and nothing under its home is
        named for the id as the CLI states it. Read by :meth:`logged`, so that whatever looks
        for a log asks one question whichever of the two spellings it is under.
      sessions: Where under that home a session is kept: everything one writes, and
        everything a resumed or forked one reads back -- the transcripts, the index they are
        found by, what the CLI keeps per conversation beside them. Paths relative to the home,
        any part of which may be a glob of one name (`state_*.sqlite*`, `projects/*/x`), a
        directory standing for everything inside it. These, and only these, are what a
        humanize turn keeps in a directory of humanize's own instead: the settings, the
        skills and the credentials stay the CLI's. Read off what a turn of each actually
        wrote and read, with a tracer, rather than off its documentation. Empty for a
        backend nothing is written down about, whose sessions stay where it keeps them.
      told: Whether its driver tells the CLI where to keep those, so that nothing has to be
        answered for it: dsh is started by humanize's own SDK call, which names its session
        root outright.
      skills: The skill files under that home, as globs, each naming the `SKILL.md` of one
        skill -- which is where the CLI itself looks for the skills a user has installed.
        Empty for a backend that can be given no skills, and for one that offers no way of
        being told which of them to load: a list to choose from that nothing acts on is a
        list that lies.
      shared: The same, under the user's own home rather than under the backend's: `.agents`
        is the directory more than one of these has agreed to read, and a backend that reads
        it goes on reading it wherever `home_var` has moved its own home to.
      config: The same, under the directory every program keeps its configuration in --
        whatever `XDG_CONFIG_HOME` names, or `~/.config` where nothing has moved it. Each
        glob carries the backend's own directory under it, as `shared`'s carry `.agents`.
        Empty for a backend that keeps its skills beside its data, which is most of them:
        this is for opencode and mimocode, whose sessions and credentials are under the data
        home and whose skills are not, so that one `home_var` cannot name both.
      works: The same, under the workspace rather than under either home: a skill kept beside
        the project it is for. A backend may read more than one such directory.
      mounts: Which of those directories a flow's own skills are mounted into for the length
        of a session -- written as the directory rather than as a glob, since this is the one
        that is written to rather than read. Empty for a backend that reads none, whose
        skills are all its own installed ones: a flow that brings skills brings that backend
        none, which is a turn run without them rather than a run that will not start.
      efforts: How hard this backend can be asked to think, hardest first, in its own wording.
        The whole ladder it has words for; a model of it takes some of them, and which ones is
        the backend's to say when it is asked what it runs.
      beyond: The rungs of that ladder it takes but does not list -- a way of running a model
        that is real and undocumented. Written here because no listing of the backend's own
        will ever name one, so a model asked about would otherwise lose it.
      swarms: Whether a turn of this backend also runs as a fleet of subagents rather than as
        one agent. A property of the backend rather than of a model: it is a way of taking a
        turn, and every model that takes turns here takes them that way too.
      searches: Whether this backend can be told whether its agents may search the web. A
        property of the backend rather than of a model, for the reason `swarms` is: reaching
        the web is a tool the CLI hands its agent, and the CLI is what hands it. False for one
        with no way of being told, whose agents go on reaching the web exactly as that CLI
        lets them -- an agent configured not to search on a backend that cannot be told would
        be a setting that lies, so it is refused where it is written instead.
      silence: How long a turn of this backend may say nothing before it is worth looking at,
        in seconds. A fact about the CLI because it differs by CLI: one that streams its
        reasoning is never quiet while it thinks, and one that says nothing between tool calls
        is quiet for the whole of a long one. Generous everywhere -- a turn thinks for minutes
        and says nothing for most of them, so a window short enough to catch a wedge quickly
        is a window that kills healthy turns.
      restarts: Whether what holds a turn of this backend open may be put down and started
        again while the run continues. True for every CLI here: the transport is a process
        humanize spawned or a runtime it opened, and either can be replaced. This is where a
        backend whose transport is somebody else's to end would say so, and a watchdog that
        found one leaves its turn alone rather than reaching into it.
      resumes: Whether a conversation of this backend survives that, being picked back up by
        the id it was opened under. True for every CLI here, each of which takes a session id
        on the way back in; false for one that can only ever open a new session, whose turn
        taken again is a turn taken from nothing.
      shares: Whether one transport serves every conversation with an agent rather than one
        apiece -- an app server, a daemon. It changes what putting that transport down costs:
        one wedged turn freed, and every other turn on that agent ended with it, which is
        something whoever is watching has to be told rather than left to discover.
      forks: Whether this backend can carry a conversation it is already holding into a
        second one of its own -- `claude --fork-session`, codex's `thread/fork`, `opencode
        run --fork`, `kimi fork` -- which is the whole of what a session clone is made
        of. A property of the backend for the reason `searches` is: the CLI is what keeps a
        conversation, so the CLI is what copies one. False for a backend that can only
        resume the id it minted, whose sessions refuse to be cloned rather than handing back
        a second handle on the one conversation -- two flows each continuing what they take
        to be their own is the failure nothing downstream could explain.
      hooks: How this CLI takes a hook table meant for one run of it, or None for one that
        takes none -- which is either a CLI with no hooks of its own or one whose only hooks
        are the table under its home, where a run's own would be everybody's. What is written
        here is the seam and its name; what goes through it is the layer that uses it.
      preloads: The environment variable this CLI's own runtime takes a preload through, for
        reaching what a turn does from inside the process rather than from outside it --
        `NODE_OPTIONS` for the several of these that are Node programs. Empty for a CLI
        shipped as a binary with no runtime to load anything into, and for one whose runtime
        ignores the variable when it re-execs itself. What is put in it is the layer's; that
        there is somewhere to put it is the fact.
      bundles: The files inside this CLI's install that a layer reaching into it patches, each
        with what says it is the one meant. Empty for a CLI nothing here patches, which is
        every one of them until a layer says otherwise: a bundle is rewritten release by
        release, so reaching into one without a fingerprint is patching whatever happens to be
        at that path today.
      creds: What a login to this backend leaves behind: the paths it reads its credentials
        back out of and writes its refreshed ones to. One under this backend's home per entry,
        one under the user's own home where the entry starts with `~/` -- which is where some
        of them keep a second file -- and one under whatever `XDG_CONFIG_HOME` names where it
        starts with `config/`, which is where a CLI that shares a vendor's account with the
        vendor's other programs keeps it. A directory names everything inside it. These are the
        paths, and only these, that a turn run under a provider is pointed somewhere else: the
        sessions, the settings and the skills are the same ones the CLI already has.
      ways: How credentials get into this backend, one entry per kind it offers -- the
        subscription it signs into, a key, a gateway, an account on a console. What a person
        is offered when they make a provider for it, and what says nothing at all for a
        backend nobody has written the ways of down yet.
      ambient: The other variables this backend would take an account from, which no way of
        its own uses: the vendor's own name for a key, an endpoint somebody exported once, a
        switch onto a cloud. Named so that a turn under a provider can be run without them --
        a key in a shell profile is a key this CLI would rather have than the one it was
        signed in with, and nothing about that reads as wrong until the bill arrives.
      endpoint: Which one of those variables says where a turn of this backend actually goes.
        Named on its own, out of the several base URLs a profile lists, because it is the one
        whose value can be asked what it serves: a CLI pointed at somebody's gateway answers
        with the models it ships rather than with the gateway's, so what a turn could name is
        what is at the other end of this. Empty for a backend whose endpoint's ids are not
        ids a turn of it could name -- one that spells a model `provider/id` out of several
        endpoints at once, or one whose endpoint speaks a protocol of its own -- whose own
        answer is already the account's. :mod:`hmz.coganchor.models` is what reads it.
      signs: What this CLI says when a turn stops that no other one says, and which kind of
        failure each of those makes it. Read before :data:`SIGNS`, which is what every one of
        them says. Empty for a backend whose failures read like everybody else's.
      journal: The files this backend writes its own log to under its home, as globs -- for a
        CLI that keeps why a turn stopped somewhere other than the two streams it answered on.
        Antigravity is the one that does: it exits with a generic error and puts the HTTP
        status in here, so a turn rate-limited by it reads as a turn that simply failed unless
        this is looked at. Empty for the backends that say what went wrong where it happened.
      installs: The one line that puts this CLI on this machine, for the failure where there
        is nothing to run. A turn that fails for a missing CLI is a turn whose whole answer is
        that line, and a person reading `agy: not installed` should not also have to go and
        look it up. Empty for a backend whose install nobody has written down here.
      hosts: The hosts this CLI cannot take a turn without reaching, each exact or a
        `*.suffix` wildcard: its model API, where its sign-in is refreshed, and telemetry only
        where the CLI refuses to run without it. What a flow granting no network still lets
        it reach, through the fence's proxy -- see :func:`reachable`, which adds whatever an
        account points it at instead. Read off each CLI's own bundle rather than off its
        documentation. Empty for a backend nothing is written down about, which such a flow
        then lets reach nothing at all.
    """

    name: str
    aliases: tuple[str, ...]
    home_var: str
    home_dir: str
    logs: tuple[str, ...]
    efforts: tuple[str, ...]
    home_in: str = ""
    encodes: bool = False
    sessions: tuple[str, ...] = ()
    told: bool = False
    skills: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    config: tuple[str, ...] = ()
    works: tuple[str, ...] = ()
    mounts: str = ""
    beyond: tuple[str, ...] = ()
    swarms: bool = False
    searches: bool = False
    silence: float = _SILENCE
    restarts: bool = True
    resumes: bool = True
    shares: bool = False
    forks: bool = False
    hooks: Hooked | None = None
    preloads: str = ""
    bundles: tuple[Bundled, ...] = ()
    creds: tuple[str, ...] = ()
    ways: tuple[Way, ...] = ()
    ambient: tuple[str, ...] = ()
    endpoint: str = ""
    signs: tuple[Sign, ...] = ()
    journal: tuple[str, ...] = ()
    installs: str = ""
    hosts: tuple[str, ...] = ()

    def takes(self, effort: str) -> bool:
        """Whether this backend has a word for a rung by that name.

        Asked here because the ladder is written here: `efforts` is the whole of what a CLI
        will answer to, `beyond` the rungs of it that CLI takes without ever listing, and a
        turn asked for at anything else is a turn that CLI refuses -- or worse, one it runs
        while quietly ignoring what it was asked. Which is why this is asked where an agent
        is made rather than left for the first turn: `grok agent` starts perfectly well at a
        rung it has never heard of, and says so only at the first turn that goes out on its
        command line instead, which is the hardest place to read the answer.

        A fleet is a width rather than a rung, so the prefix comes off before the ladder is
        read: `swarmmax` is `max` run wide, and only on a backend that runs one wide at all.

        Args:
          effort: The rung, in this backend's own wording, `swarm`-prefixed or not.

        Returns:
          Whether it can be asked for. True for anything at all on a backend with no ladder
          to read it against: one nothing at all is written down about, and one known only by
          the protocol it speaks, whose single listed rung is :data:`_UNSAID` -- the word for
          there being no ladder rather than a rung on one. Refusing every other word there
          would leave a CLI somebody added unusable at any effort they would actually type,
          which is a check that has stopped measuring anything.
        """
        rung = effort.removeprefix(SWARM) if self.swarms else effort
        # No rung at all, however it was written. Every backend takes it, because it is not
        # something asked of the backend: it is humanize saying nothing about how hard to
        # think, which any CLI can be told by not being told.
        if not rung or rung == AUTO:
            return True
        if not self.efforts or self.efforts == (_UNSAID,):
            return True
        return rung in self.efforts or rung in self.beyond

    def logged(self, ident: str) -> tuple[str, ...]:
        """The globs one session is logged to under this backend's home.

        Args:
          ident: The session, by the id the backend gave it.

        Returns:
          `logs` with that id written in, spelled the way this backend names it on disk --
          as it is, or in URL-safe base64 with no padding where :attr:`encodes` says so.
        """
        spelled = (
            base64.urlsafe_b64encode(ident.encode()).decode().rstrip("=")
            if self.encodes
            else ident
        )
        return tuple(pattern.format(ident=spelled) for pattern in self.logs)

    def directory(self, environment: Mapping[str, str] | None = None) -> Path:
        """Where this backend keeps its state and its logs, wherever it has been moved to.

        Args:
          environment: The environment to read that from, or None for this process's own.
            A turn runs under its provider's environment rather than under ours, so whatever
            wants the home a *turn* wrote to has to say which environment that turn had --
            including its `HOME`, which is the only thing that moves the home of a backend
            with no variable of its own.

        Returns:
          The home directory. It may not exist: a backend that has never run has none.
        """
        said = environment if environment is not None else os.environ
        moved = said.get(self.home_var) if self.home_var else ""
        if moved:
            return Path(moved) / self.home_in
        under = said.get("HOME") if environment is not None else ""
        return (Path(under) if under else Path.home()) / self.home_dir

    @staticmethod
    def configuration() -> Path:
        """The directory programs keep their configuration in, wherever it has been moved to.

        Not this backend's own: `XDG_CONFIG_HOME` is the one variable every program that
        follows it shares, so what belongs to a backend is the directory under it, which
        `config` names as part of each glob.

        Returns:
          That directory. It may not exist, and a backend keeping nothing there never looks.
        """
        moved = os.environ.get("XDG_CONFIG_HOME")
        return Path(moved) if moved else Path.home() / ".config"

    def accounts(self) -> frozenset[str]:
        """Every variable this backend would take an account from, whoever set it.

        What the ways in name, and what is written down beside them: a CLI reads a key, a
        token or an endpoint out of the environment, and it does not care whether the person
        at this machine exported it or a provider did. So a turn under a provider has to be
        run with these unset unless that provider set them -- an `ANTHROPIC_API_KEY` left in
        somebody's shell profile outranks the credentials file a provider was signed into,
        and the turn would be taken as the wrong account without anything looking wrong.

        Returns:
          The variable names, which is nothing at all for a backend whose ways nobody has
          written down.
        """
        named = {one.env for way in self.ways for one in way.asks}
        named |= {name for way in self.ways for name, _ in way.sets}
        return frozenset(named | set(self.ambient))

    def hushes(self) -> frozenset[str]:
        """`accounts()`, and every other spelling of each that names the same credential.

        What a turn under a provider is actually run without. A CLI that reads one name for a
        credential reads its aliases too -- kimi takes an account from `MOONSHOT_API_KEY` as
        well as `KIMI_API_KEY`, opencode from `GOOGLE_API_KEY` as well as `GEMINI_API_KEY` --
        so one of those left in the environment is the same wrong account whichever of the two
        spellings carried it, and hushing only the name a backend's ways happened to write
        down would leave the other to supply it. `serves()` copies an account by its declared
        name, which is why that keeps the literal `accounts()`; this strips it by every name it
        answers to, and hushing one no backend reads costs nothing.

        Returns:
          The account variables and their aliases, to take away before a provider's turn.
        """
        return frozenset(name for one in self.accounts() for name in alike(one))

    def credentials(self) -> tuple[tuple[str, str], ...]:
        """Every path this backend keeps a credential at, and where it is kept relative to.

        Read here rather than written down twice: a path under the backend's own home moves
        with the variable that moves the home, one written `~/...` is under the user's own
        wherever that home went, and one written `config/...` is under whatever
        `XDG_CONFIG_HOME` names. Three roots because a CLI that keeps its account where every
        program keeps its configuration keeps it somewhere neither of the other two moves.

        Returns:
          One `(absolute path, name to keep it under)` pair per credential, the name being the
          path with the root it is under taken off -- `home/...` for the backend's own,
          `user/...` for the user's and `config/...` for the shared configuration directory,
          so that two files of the same name are two files.
        """
        held: list[tuple[str, str]] = []
        for said in self.creds:
            if said.startswith("~/"):
                held.append((str(Path.home() / said[2:]), f"user/{said[2:]}"))
            elif said.startswith("config/"):
                held.append((str(self.configuration() / said[len("config/") :]), said))
            else:
                held.append((str(self.directory() / said), f"home/{said}"))
        return tuple(held)

    def kept(
        self, at: Path, environment: Mapping[str, str] | None = None
    ) -> tuple[tuple[str, str], ...]:
        """Every place one of its sessions is kept, and where a humanize turn keeps it instead.

        The same path under a directory of humanize's own as under the CLI's home, so that
        what is kept there is laid out exactly as the CLI lays out its own and is read back
        by whatever reads the one.

        Args:
          at: Where humanize keeps sessions, a directory per backend inside it.
          environment: The environment the turn runs with, or None for this process's own,
            which is what says where the home it would have written to is.

        Returns:
          One `(the path the CLI names, the path it is answered with)` pair per entry of
          `sessions`, and one more where the home is reached through a link, for the same
          path spelled with the link followed. Nothing for a backend whose driver tells it
          where they go, or one nothing is written down about.
        """
        if self.told:
            return ()
        home = self.directory(environment)
        settled = Path(os.path.realpath(home))
        instead = at / self.name
        held: list[tuple[str, str]] = []
        for said in self.sessions:
            held.append((str(home / said), str(instead / said)))
            if settled != home:
                held.append((str(settled / said), str(instead / said)))
        return tuple(held)


#: What Claude Code documents on its own command line, for every model it runs, and above them
#: the one it does not document but takes: `ultracode` is `xhigh` with the turn opted into
#: orchestrating a fleet of its own, which is more work than any single-agent effort and so is
#: the top of this list. Hardest first, as every effort here is: the one to reach for is the
#: one at the top.
_CLAUDE = ("ultracode", "max", "xhigh", "high", "medium", "low")

#: What codex calls its reasoning levels. Which of them a model takes differs across its
#: models, and codex says which where it says what it runs.
_CODEX = ("ultra", "max", "xhigh", "high", "medium", "low")

#: What Kimi Code calls its thinking levels. It says which its models take too, and they
#: differ: this is the ladder, not a promise that every model has every rung.
_KIMI = ("max", "high", "medium", "low")

#: What pi calls its thinking levels, hardest first. `off` is the model asked not to think at
#: all, which is an effort like any other here: it is the least of them, not the absence of a
#: setting.
_PI = ("max", "xhigh", "high", "medium", "low", "minimal", "off")

#: What the official DeepSeek adapter in DeepSeek Harness calls its reasoning levels, hardest
#: first, as `@deepseek-ai/dsh-llm-deepseek` enumerates them in its own config schema:
#: `reasoningEffort` is a union of `off`, `low`, `high` and `max`. `off` is the model asked
#: not to reason, which is a rung like any other here rather than the absence of a setting --
#: the absence is the adapter sending no reasoning level at all, which is what an agent whose
#: effort never reaches the composition would get.
_DSH = ("max", "high", "low", "off")

#: The SDK dsh is driven through, written the way somebody installing it by hand has to write
#: it. The ceiling is the point of the line: 0.1.2a3 redesigned the configuration the driver
#: is written against, so an install told to fetch the newest resolves one that cannot open a
#: session at all. Said in one place because it is said in three -- the line offered when the
#: backend is missing, the one the interface prints, and the one the driver raises -- and
#: three hand-copies of a version range are three chances to leave one of them at the old
#: bound. It MUST be kept in step with `pyproject.toml`, which is the copy that binds.
DSH_SDK = "deepseek-harness-sdk>=0.1.1rc1,<0.1.2"

#: What Grok Build calls its reasoning levels, hardest first, which is what it says when it
#: is given one it has not got: `unknown effort level; use one of: xhigh, high, medium, low`.
#: Written as it enumerates them rather than as the fuller ladders beside it: a rung it
#: refuses is a turn that never starts, and it refuses one before it does anything else.
_GROK = ("xhigh", "high", "medium", "low")

#: What Qwen Code calls its reasoning levels, hardest first. It has no flag for them -- they
#: are a setting of its own `settings.json`, which is why a turn is pointed at one of ours.
#: `none` is the model asked not to reason at all, which is a rung like any other here: it is
#: the least of them, not the absence of a setting, and it is the one a model that takes no
#: reasoning parameter at all is reachable at.
_QWEN = ("max", "xhigh", "high", "medium", "low", "none")

#: What opencode and mimocode call a reasoning effort: a variant of the model, given as
#: `--variant`, and provider-specific. These are the ones the models they front take; a
#: provider with no variants of its own takes the flag and ignores it.
_VARIANTS = ("xhigh", "high", "medium", "low", "minimal")

#: What a gateway is asked for, whichever backend is being pointed at one: where it is and
#: what it takes. Written once because it is one question -- an endpoint speaking a vendor's
#: protocol is the same arrangement whoever is dialling it.
_GATEWAY = (
    "an endpoint speaking this CLI's own protocol -- a proxy, a router, another vendor"
)

#: What Antigravity CLI calls its reasoning levels, hardest first.
_AGY = ("high", "medium", "low")

#: What MiniMax Code calls a reasoning effort, hardest first, as 0.5.9's own model table writes
#: them for the one model of its own that takes any: `max`, `xhigh`, `high`, `medium` and
#: `low`, beside a `default` that is the absence of one and so is not a rung here. Its other
#: models take none at all, and are refused a turn given `--effort` rather than run at some
#: other strength -- which is why what a model takes is the catalogue's to say, per model.
_MCODE = ("max", "xhigh", "high", "medium", "low")

#: What Cursor calls a reasoning effort, hardest first. Not a flag of its own, and -- on a
#: signed-in account -- not the bracket its `--help` still documents either: `cursor-agent
#: models` lists the rung as a suffix of the id, `gpt-5.2-low` beside `gpt-5.2`, and an
#: account asked for `gpt-5.2[effort=low]` answers `Cannot use this model` with that same
#: list. So these are the words its own ids are spelled with, read off the catalogue of a
#: live account on 2026-09-17: seven of them rather than three, `gpt-5.6-sol-none` through
#: `claude-opus-4-8-max`, with `muse-spark-1.3-minimal` under `low`.
#:
#: `extra-high` is the eighth and it is one model's spelling of `xhigh`: `gpt-5.5-extra-high`
#: is the only id on that account written that way. It is here because what this list is for
#: is telling a rung in an id from the rest of the id, and a rung nothing here knows the
#: spelling of is one that reads as `high` -- a model named one rung under what it runs.
#: Which rungs a given model actually has is the catalogue's to say and not this list's: the
#: ladder is the vocabulary, and `hmz.coganchor.models` narrows it per model to the ids the
#: account was offered.
_CURSOR = ("max", "xhigh", "extra-high", "high", "medium", "low", "minimal", "none")

#: Every backend humanize drives, as each of them reported itself. Codex says which efforts
#: each of its models takes and they differ, so they are written down as it gave them.
PROFILES = (
    Profile(
        name="claude",
        # The API, where a subscription's sign-in is refreshed -- `TOKEN_URL` in the binary's
        # own OAuth block is `platform.claude.com/v1/oauth/token` -- and the subscription's
        # origin, which the same block names. Bedrock and Vertex are a cloud's hosts rather
        # than Anthropic's, and :func:`reachable` names them from the region an account of
        # either was made with.
        hosts=("api.anthropic.com", "platform.claude.com", "claude.ai"),
        installs="npm i -g @anthropic-ai/claude-code",
        # `WebSearch` and `WebFetch` are tools like any other to Claude, and
        # `--disallowedTools` is the flag that takes a tool away.
        searches=True,
        # `--fork-session`, which is `--resume` told to mint an id rather than reuse the
        # one it was handed: the earlier turns come with it and the next one is its own.
        forks=True,
        # Claude Code ships as one Bun standalone executable -- the whole CLI, minified and
        # packed behind a `---- Bun! ----` trailer -- so the file the launcher resolves to is
        # itself the bundle a patch reaches. Fingerprinted by the shape of the version it
        # inlines rather than by one release's digits, because this is the CLI that updates
        # itself while it runs: a literal here would be right for about a day and wrong in
        # silence after that. The constant is copied into dozens of modules, the entry among
        # them, and the entry is the one a patch of the program itself goes into. `*`, because
        # the file is named for its version -- `versions/<semver>` -- and the one that is the
        # resolved program is the one taken.
        bundles=(Bundled(path="*", says=r'VERSION:"\d+\.\d+\.\d+"'),),
        # `--settings` takes the whole of a settings file as a JSON literal on the command
        # line, hooks and all, for the length of one run -- which is the table this flow's
        # own moments are put in without a line of anybody's `settings.json` being written.
        hooks=Hooked(seam="flag", name="--settings"),
        aliases=("claude", "claude-code"),
        home_var="CLAUDE_CONFIG_DIR",
        home_dir=".claude",
        logs=("projects/*/{ident}.jsonl", "projects/*/{ident}/subagents/**/*.jsonl"),
        # Claude 2.1.283, traced through a turn, a `--resume` and a `--fork-session`: the
        # transcripts and the sub-agents' beside them under `projects/`, the running sessions
        # it registers under `sessions/`, and what it keeps per session id -- the files it
        # checkpointed, the environment its hooks set, its task lists old and new, the plans
        # a session in plan mode wrote. `projects/` holds the auto-memory of each project too,
        # which is kept with the run for being inside it: a session's memory is the run's.
        sessions=(
            "projects",
            "sessions",
            "file-history",
            "session-env",
            "tasks",
            "todos",
            "plans",
        ),
        efforts=_CLAUDE,
        # `ultracode` is real and undocumented, so the catalogue Claude Code answers with
        # will never name it: a model asked about keeps it whatever that list says.
        beyond=("ultracode",),
        # The skills a person installs, which is what there is to choose between: the ones
        # Claude ships with and the ones a plugin brought are the plugin's to say. Its own
        # two directories and no more -- it does not read the shared one, which is why a
        # skill kept there is symlinked into this. A turn is told which of these it may not
        # reach for, as `Skill(<name>)`.
        skills=("skills/*/SKILL.md",),
        works=(".claude/skills/*/SKILL.md",),
        # Where a flow's own skills go for the length of a session: the directory Claude
        # reads a project's skills out of, which is the one place a skill can be given to it
        # without touching what the person at this machine has installed.
        mounts=".claude/skills",
        # Three places, and the last of them is the one people forget: the session lives in
        # `.credentials.json`, the account it belongs to -- with the API key a run was
        # approved for beside it -- lives in `.claude.json`, which sits outside the home
        # directory until `CLAUDE_CONFIG_DIR` moves it inside, and the account Claude shares
        # with the vendor's other programs lives under `XDG_CONFIG_HOME`, which neither of
        # those moves. Both spellings of the second, so that a provider works whether or not
        # the home has been moved; and the third because a machine signed in there and
        # nowhere else would answer every provider's turns with its own account.
        creds=(
            ".credentials.json",
            ".claude.json",
            "~/.claude.json",
            "config/anthropic",
        ),
        # Everything else Claude Code would read an account out of: the two the ways already
        # name are there too, through `accounts()`. `ANTHROPIC_CONFIG_DIR` is an account for
        # the reason the others are -- it moves the shared configuration directory whole, and
        # a turn that read one this table had never heard of would be the wrong account.
        ambient=(
            "ANTHROPIC_CONFIG_DIR",
            "ANTHROPIC_CUSTOM_HEADERS",
            "ANTHROPIC_MODEL",
            "CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR",
            "CLAUDE_CODE_OAUTH_REFRESH_TOKEN",
            "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
            "CLAUDE_CODE_USE_FOUNDRY",
            "CLAUDE_CODE_USE_GATEWAY",
            "CLAUDE_CODE_USE_VERTEX",
            "CLAUDE_CODE_USE_BEDROCK",
        ),
        # Where a turn actually goes when it is not going to Anthropic: the gateway way sets
        # it, and Claude Code sends every request of that turn there under the id it was
        # given. Both protocols list what is behind it the same way, so what it serves is
        # what a turn may name.
        endpoint="ANTHROPIC_BASE_URL",
        ways=(
            Way(
                name="login",
                about="sign in to an Anthropic account, as `claude auth login` does",
                argv=("claude", "auth", "login"),
            ),
            Way(
                name="token",
                about="a long-lived token, as `claude setup-token` prints one",
                asks=(
                    Asked(
                        env="CLAUDE_CODE_OAUTH_TOKEN",
                        about="the token `claude setup-token` printed",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="key",
                about="an Anthropic API key, from the console",
                asks=(
                    Asked(
                        env="ANTHROPIC_API_KEY",
                        about="the API key",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(
                        env="ANTHROPIC_BASE_URL",
                        about="where it is, as a URL",
                    ),
                    # A bearer rather than a key: it is sent as `Authorization` and outranks
                    # the key, and it is the one an endpoint of somebody else's takes.
                    Asked(
                        env="ANTHROPIC_AUTH_TOKEN",
                        about="the token it takes",
                        secret=True,
                    ),
                ),
            ),
            Way(
                name="bedrock",
                about="Anthropic's models on an AWS account of yours",
                sets=(("CLAUDE_CODE_USE_BEDROCK", "1"),),
                asks=(
                    Asked(env="AWS_PROFILE", about="the AWS profile to run as"),
                    Asked(env="AWS_REGION", about="the region", fixed="us-east-1"),
                ),
            ),
            Way(
                name="vertex",
                about="Anthropic's models on a Google Cloud project of yours",
                sets=(("CLAUDE_CODE_USE_VERTEX", "1"),),
                asks=(
                    Asked(env="ANTHROPIC_VERTEX_PROJECT_ID", about="the project id"),
                    Asked(env="CLOUD_ML_REGION", about="the region", fixed="us-east5"),
                ),
            ),
        ),
    ),
    Profile(
        name="agy",
        # Its log is every request going to `daily-cloudcode-pa`, the binary names the plain
        # one beside it, the sign-in is refreshed at `oauth2` and read back at `www`'s
        # userinfo, and the key way talks to the Gemini API. Its eligibility check fetches the
        # account's profile picture from `lh3` and refuses to start a turn when it cannot
        # (agy 1.2.12). The feature-flag host it also names is left out: nothing it does fails
        # without it.
        hosts=(
            "cloudcode-pa.googleapis.com",
            "daily-cloudcode-pa.googleapis.com",
            "oauth2.googleapis.com",
            "www.googleapis.com",
            "generativelanguage.googleapis.com",
            "lh3.googleusercontent.com",
        ),
        # Told by the agent a turn is started as, which is one of humanize's without the web's
        # two tools where it may not search: agy has no flag or setting that takes one away.
        searches=True,
        aliases=("agy", "antigravity"),
        # `--conversation` picks one back up and that is the whole of what it offers: there
        # is no flag that says carry this one into another. Still true of agy 1.2.2, checked
        # on 2026-09-15 against its own `--help` and its subcommands. It does know how to
        # fork -- `/fork` is one of the commands it answers at a prompt -- but print mode
        # answers only the read-only ones of those, so there is nothing a turn taken here
        # could say to reach it and nothing that would hand back the second id a clone is.
        forks=False,
        # Nothing moves it: no variable of its own, and neither `XDG_CONFIG_HOME` nor the
        # names its siblings use are read. Only the home directory it is under, and a hidden
        # flag. So there is no variable to name here, and `directory()` reads the one place.
        home_var="",
        home_dir=".gemini/antigravity-cli",
        # One database per conversation, whose `steps` hold their payload as protobuf --
        # so a file per session after all, which is what makes it a directory that can be
        # staged and a conversation that can be read back. Not lines appended to, though:
        # a row is rewritten in place, so what has been spent is asked of the reader afresh
        # rather than counted off the bytes that arrived since the last look.
        logs=("conversations/{ident}.db",),
        # agy 1.2.3, traced through a turn and one more in the same conversation: its
        # database, the `brain/` it writes the transcript and a session's scratch into, the
        # annotations, implicit summaries and presence lock it keeps per conversation id, and
        # the three indexes of them -- the summaries database, the summaries protobuf, and the
        # recent list it caches. Its own log is not among them: `journal` below is read where
        # the CLI keeps it, being the process's rather than any conversation's.
        sessions=(
            "conversations",
            "brain",
            "annotations",
            "implicit",
            "presence",
            "conversation_summaries.db*",
            "jetbox_summaries_proto.pb",
            "cache/last_conversations.json",
        ),
        # The one backend here that fails without saying why. It exits with `Agent execution
        # terminated due to error` on both streams and puts the HTTP status in its own log --
        # which is how six rate-limited turns of the 2026-09-09 evaluation read as six turns
        # that simply failed. `cli.log` is the symlink to the newest; the dated ones are what
        # a run that has since restarted left behind, and the newest of those is this turn's.
        #
        # All of it re-checked against agy 1.2.2 on 2026-09-15: the generic line is still what
        # it exits with, and its home still holds `cli.log` pointing at `log/cli-<stamp>.log`.
        # It does take `--log-file`, which would name this turn's log rather than leaving it
        # to be found -- and is not used, because `journalled` is what reads it and looks under
        # this backend's home for the newest rather than being handed a path per turn. Naming
        # one would move the log away from the only thing that looks at it.
        journal=("cli.log", "log/cli-*.log"),
        efforts=_AGY,
        # Two places: the `skills/` of its own home, which is the global customization root it
        # loads whatever else it is doing, and `.agents/skills` under the workspace, which it
        # opens by name once it has been given that workspace -- traced, on a turn of its own
        # stream transport, opening `<workspace>/.agents/skills/<name>/SKILL.md`. Not under
        # the user's own home: it never looks there. So the shared one is where a flow's
        # skills are mounted, which is where its sibling backends put theirs.
        skills=("skills/*/SKILL.md",),
        works=(".agents/skills/*/SKILL.md",),
        mounts=".agents/skills",
        # What a sign-in leaves behind where there is no keyring to put it in -- a session on
        # a machine with no desktop, which is where a flow runs. The keyring is the first
        # choice and is not a path.
        creds=("antigravity-oauth-token",),
        ambient=(
            "AGY_ADC_AUTH",
            "CLOUD_CODE_URL",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_APPLICATION_CREDENTIALS",
            # Where the key way's requests actually go. Exported once in a shell profile it
            # sends every turn under an account of ours somewhere that account never named,
            # with its key -- and the answers come back looking exactly as they should.
            "GOOGLE_GEMINI_BASE_URL",
        ),
        # The Gemini endpoint a turn's requests go to. Google's own lists its models
        # somewhere else and in another shape, so this ordinarily falls back to asking agy;
        # a gateway put behind it that answers `/v1/models` is answered from there.
        endpoint="GOOGLE_GEMINI_BASE_URL",
        ways=(
            Way(
                name="login",
                about="sign in to a Google account, in a session opened for it",
                # It signs in from inside itself, so the way in is agy with the terminal
                # handed over: a headless turn then runs on what that left behind.
                argv=("agy",),
            ),
            Way(
                name="key",
                about="a Gemini API key, from AI Studio",
                asks=(Asked(env="GEMINI_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="adc",
                about="Google Application Default Credentials, for a service account",
                sets=(("AGY_ADC_AUTH", "1"),),
                asks=(
                    Asked(
                        env="GOOGLE_APPLICATION_CREDENTIALS",
                        about="the service account file, as a path",
                    ),
                ),
            ),
        ),
    ),
    Profile(
        name="codex",
        # A ChatGPT sign-in's turns go to `chatgpt.com/backend-api/codex` and are refreshed
        # at `auth.openai.com/oauth/token`; a key's go to the API.
        hosts=("chatgpt.com", "auth.openai.com", "api.openai.com"),
        installs="npm i -g @openai/codex",
        # `web_search` is a setting of the app server, `disabled` or `live`, and is sent in
        # both directions: a bare codex-cli 0.153.4 searches its cached index, and the older
        # `tools.web_search=false` it still takes does not stop it.
        searches=True,
        # And that app server is one per agent, not one per conversation: every thread of it
        # goes down together, which is what a watchdog has to say before it puts one down.
        shares=True,
        # `thread/fork` on that same app server: a thread id in, a thread of its own back,
        # holding what the first one had got to.
        forks=True,
        aliases=("codex",),
        home_var="CODEX_HOME",
        home_dir=".codex",
        logs=("sessions/**/rollout-*{ident}.jsonl",),
        # codex 0.153.4, traced through a turn, another on the same app server and a
        # `thread/fork` on a second one: the rollouts, archived or not, and the index of them,
        # and the databases a thread is a row of -- its state, its history, its goals, what is
        # queued for it, and the memories drawn out of it -- each named for its schema version,
        # which moves, and each with the write-ahead files beside it. And the locks and shell
        # snapshots it keeps per thread id. Its logs database is the process's, not a thread's.
        sessions=(
            "sessions",
            "archived_sessions",
            "session_index.jsonl",
            "state_*.sqlite*",
            "thread_history_*.sqlite*",
            "goals_*.sqlite*",
            "queue_*.sqlite*",
            "memories_*.sqlite*",
            "thread-writer-locks",
            "shell_snapshots",
        ),
        efforts=_CODEX,
        # Four places, which is what `skills/list` answers with: its own home, the shared
        # one under yours, and both of the directories a project may keep them in. A turn is
        # given the ones left on, as `skills.config` says which are off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".agents/skills/*/SKILL.md", ".codex/skills/*/SKILL.md"),
        # The shared one of its two, being the directory more than one of these CLIs has
        # agreed to read: a flow's skill mounted there is one whichever of them is driving.
        mounts=".agents/skills",
        # One file, whichever way it was signed into: the subscription's tokens and an API
        # key land in the same place, under the mode that says which of them is in force.
        creds=("auth.json",),
        # `CODEX_AUTHAPI_BASE_URL` is an account for the reason a key is: codex sends the
        # credential it was signed in with to whatever it names, so a turn run under a
        # provider with somebody's copy of it still exported would hand that provider's token
        # to somebody's endpoint. The Azure and the local ways' URLs are here although their
        # ways ask for them, because this is where a fence reads where a turn goes from: an
        # account of either sends every request there and nowhere else.
        ambient=(
            "AZURE_OPENAI_BASE_URL",
            "CODEX_API_KEY",
            "CODEX_AUTHAPI_BASE_URL",
            "CODEX_OSS_BASE_URL",
            "OPENAI_BASE_URL",
        ),
        # The OpenAI gateway way's own, rather than any of the ambient ones: codex takes a
        # provider as settings, and `model_providers.humanize.base_url` -- which is where
        # every request of such a turn goes -- is filled from this and from nothing else.
        # Azure's is a variable of its own rather than this one: what a resource lists at
        # `/models` is the models Azure has, and what a turn names is a deployment of one.
        endpoint="CODEX_PROVIDER_URL",
        ways=(
            Way(
                name="login",
                about="sign in to a ChatGPT account, in a browser",
                argv=("codex", "login"),
            ),
            Way(
                name="device",
                about="the same, from a machine with no browser on it",
                argv=("codex", "login", "--device-auth"),
            ),
            Way(
                name="key",
                about="an OpenAI API key, which codex keeps in its own store",
                argv=("codex", "login", "--with-api-key"),
                # Read off stdin by the command, which writes it where it keeps its own: an
                # environment holding a second copy would be a second place to leak it.
                asks=(
                    Asked(
                        env="OPENAI_API_KEY",
                        about="the API key",
                        secret=True,
                        keep=False,
                    ),
                ),
                stdin="OPENAI_API_KEY",
            ),
            Way(
                name="token",
                about="an access token, which is how an organisation hands one out",
                argv=("codex", "login", "--with-access-token"),
                asks=(
                    Asked(
                        env="CODEX_ACCESS_TOKEN",
                        about="the access token",
                        secret=True,
                        keep=False,
                    ),
                ),
                stdin="CODEX_ACCESS_TOKEN",
            ),
            # A ChatGPT workspace's account with no person signing in: codex trades the
            # identity token a platform mounts -- a cloud's, a CI runner's -- for the
            # workspace's own tokens at `auth.openai.com`, under the federation rule the
            # workspace's admin made for it. Read out of the environment each time it starts
            # rather than written to its store, so there is no command to run; and the file
            # is a path rather than a secret, what is in it being the platform's to rotate.
            Way(
                name="workload",
                about="a ChatGPT workspace's workload identity, where nobody signs in",
                asks=(
                    Asked(
                        env="OPENAI_FEDERATION_RULE_ID",
                        about="the federation rule's id",
                    ),
                    Asked(
                        env="OPENAI_IDENTITY_TOKEN_FILE",
                        about="the identity token's file, as a path",
                    ),
                ),
            ),
            Way(
                name="openai-gateway",
                about=(
                    "an endpoint speaking OpenAI's API -- a proxy, a router, another vendor"
                ),
                asks=(
                    Asked(env="CODEX_PROVIDER_URL", about="where it is, as a URL"),
                    Asked(
                        env="CODEX_PROVIDER_KEY", about="the key it takes", secret=True
                    ),
                ),
                # Codex takes a provider as settings rather than as variables, and `-c` is
                # how a setting is given for one run without writing anybody's config file.
                # The wire is written out rather than asked: codex takes one protocol now --
                # 0.160.0 refuses `wire_api = "chat"` as no longer supported, and will not
                # start at all on it -- so a question about it would be a question with one
                # answer and a way to get a provider that cannot run.
                args=(
                    "-c",
                    "model_provider=humanize",
                    "-c",
                    "model_providers.humanize.name=humanize",
                    "-c",
                    "model_providers.humanize.base_url={CODEX_PROVIDER_URL}",
                    "-c",
                    "model_providers.humanize.env_key=CODEX_PROVIDER_KEY",
                    "-c",
                    "model_providers.humanize.wire_api=responses",
                ),
            ),
            # Azure OpenAI is a provider codex has no built-in for and knows all the same: one
            # named `azure` is spoken to the way Azure's Responses API takes it, which is the
            # name this gives it. The version is a query parameter on every request, quoted
            # so that it is read as the string it is; the default is the one codex's own
            # example of an Azure provider names, and a resource on a newer one says so. The
            # key goes as a variable codex is told the name of, never on the command line.
            Way(
                name="azure",
                about="OpenAI's models on an Azure OpenAI resource of yours",
                asks=(
                    Asked(
                        env="AZURE_OPENAI_BASE_URL",
                        about="where it is, as https://<resource>.openai.azure.com/openai",
                    ),
                    Asked(env="AZURE_OPENAI_API_KEY", about="its key", secret=True),
                    Asked(
                        env="AZURE_OPENAI_API_VERSION",
                        about="the API version",
                        fixed="2025-04-01-preview",
                    ),
                ),
                args=(
                    "-c",
                    "model_provider=humanize",
                    "-c",
                    "model_providers.humanize.name=azure",
                    "-c",
                    "model_providers.humanize.base_url={AZURE_OPENAI_BASE_URL}",
                    "-c",
                    "model_providers.humanize.env_key=AZURE_OPENAI_API_KEY",
                    "-c",
                    (
                        "model_providers.humanize.query_params.api-version"
                        '="{AZURE_OPENAI_API_VERSION}"'
                    ),
                    "-c",
                    "model_providers.humanize.wire_api=responses",
                ),
            ),
            # Bedrock is one of codex's own providers, `amazon-bedrock`, and the one built-in
            # it lets a setting move: its endpoint, its auth, its headers and its `aws` table
            # and nothing else, the table being where the region and the profile go. Its
            # endpoint is made of the region -- `bedrock-mantle.<region>.api.aws` -- so the
            # region is asked for here rather than left to whatever this machine's AWS
            # configuration would say. A profile in that table outranks every other
            # credential codex would find, so a turn of this account is that profile's
            # whatever else is lying about.
            Way(
                name="bedrock",
                about="OpenAI's models on an AWS account of yours",
                asks=(
                    Asked(env="AWS_PROFILE", about="the AWS profile to run as"),
                    Asked(env="AWS_REGION", about="the region", fixed="us-east-1"),
                ),
                args=(
                    "-c",
                    "model_provider=amazon-bedrock",
                    "-c",
                    "model_providers.amazon-bedrock.aws.profile={AWS_PROFILE}",
                    "-c",
                    "model_providers.amazon-bedrock.aws.region={AWS_REGION}",
                ),
            ),
            # The same as a Bedrock API key rather than a profile: codex takes one from
            # `AWS_BEARER_TOKEN_BEDROCK` before any AWS credential it would otherwise find,
            # and refuses one it is given no region for.
            Way(
                name="bedrock-key",
                about="the same, with a Bedrock API key",
                asks=(
                    Asked(
                        env="AWS_BEARER_TOKEN_BEDROCK",
                        about="the Bedrock API key",
                        secret=True,
                    ),
                    Asked(env="AWS_REGION", about="the region", fixed="us-east-1"),
                ),
                args=(
                    "-c",
                    "model_provider=amazon-bedrock",
                    "-c",
                    "model_providers.amazon-bedrock.aws.region={AWS_REGION}",
                ),
            ),
            # Open models served by Ollama or by LM Studio, each a provider codex has built in
            # under its own name. `--oss` is how `codex exec` says the same and `codex
            # app-server` does not take it, so the provider is named as a setting instead.
            # Where the server is, is the one variable codex reads it from, which a server
            # on its usual port on this machine need not be asked about. Nothing to sign in
            # to and no key to keep.
            Way(
                name="ollama",
                about="open models served by Ollama",
                asks=(
                    Asked(
                        env="CODEX_OSS_BASE_URL",
                        about="where it is, as a URL",
                        fixed="http://localhost:11434/v1",
                    ),
                ),
                args=("-c", "model_provider=ollama"),
            ),
            Way(
                name="lmstudio",
                about="open models served by LM Studio",
                asks=(
                    Asked(
                        env="CODEX_OSS_BASE_URL",
                        about="where it is, as a URL",
                        fixed="http://localhost:1234/v1",
                    ),
                ),
                args=("-c", "model_provider=lmstudio"),
            ),
        ),
    ),
    Profile(
        name="dsh",
        # The model adapter's `PUBLIC_BASE_URL`, which its web search's endpoint is under too.
        # Its telemetry is sent only when feedback is, so nothing needs it.
        hosts=("api.deepseek.com",),
        # By composition, which is this backend's only way of saying anything: there is no
        # command line to put a flag on, and what an agent may reach for is what its
        # `cordis.yml` mounts. `dsh-web` and the two providers under it are what the
        # `web_search` and `web_fetch` tools of `dsh-tool-web` run on, and an agent told not
        # to search is one whose composition carries none of the four -- a tool that is not
        # in the process rather than one asked not to be reached for. Said in both directions
        # for the reason Codex's is: the bundled composition mounts no web at all, so on has
        # to be mounted or it would mean two things.
        searches=True,
        # Shorter than the rest, and for a reason of its own: this is the one backend driven
        # through an SDK rather than a command line, and the three minutes the driver gives
        # each of that SDK's requests is humanize's own -- `request_timeout_seconds` is None
        # by default there, which is every request waiting for as long as it takes. What that
        # bounds is the acknowledgement rather than the turn, so this is what bounds the turn:
        # quiet for twice the acknowledgement is the runtime having stopped answering rather
        # than the model still thinking, and there is nothing to wait for.
        silence=360.0,
        # The whole of the `[dsh]` extra, named as its packages rather than as
        # `hmz[dsh]`: the humanize saying this did not come from an index, so a line
        # that asks one for humanize is a line that fails.
        installs=f"pip install '{DSH_SDK}' 'python-dotenv>=1.2.3'",
        # Its own sentence for the one credential it takes, which names neither a status nor
        # a login: an SDK rather than a CLI, so nothing about it reads like HTTP.
        signs=(Sign("refused", r"needs a DeepSeek API key"),),
        aliases=("dsh", "deepseek-harness"),
        # Its harness names a session and runs turns in it; nothing in the protocol makes a
        # second one out of the first.
        forks=False,
        home_var="DSH_HOME",
        home_dir=".dsh",
        # The Python SDK's bundled JSONL persistence groups sessions under one project
        # directory. `DshAgentConfig.session_compression` keeps these logs uncompressed so
        # the running tally can read complete rows as they land -- the plugin's own default
        # is `zstd`, which answers only in whole frames, so an agent set to that is one this
        # path reads nothing from until its session is over.
        logs=("sessions/*/{ident}/session.jsonl",),
        # The session root the SDK is handed, which is the only thing a turn of it writes
        # under this home -- and the only backend here humanize tells where to keep them.
        sessions=("sessions",),
        told=True,
        efforts=_DSH,
        # None, and not for want of looking: the `dsh` command line reads `.dsh/skills` and
        # `.agents/skills`, but that is its web profile's own harness. What humanize drives is
        # the Python SDK, which carries no skills at all -- so a list here would be of skills
        # nothing in this session would ever load.
        # `DEEPSEEK_SEARCH_BASE_URL` beside the other two because the search provider mounted
        # for an agent that may search reads it, and reads it *instead of* `DEEPSEEK_BASE_URL`:
        # search speaks the Anthropic-compatible Messages API and chat completions do not, so
        # the harness gives the two endpoints two variables. It is the same key at the other
        # end of it, so one left in a shell profile is an account's key sent somewhere the
        # account never named -- which is what listing it here stops.
        ambient=("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_SEARCH_BASE_URL"),
        # Its SDK has no model-list request at all, so an endpoint that answers one is the
        # only way this backend ever says something other than the two names it ships with.
        endpoint="DEEPSEEK_BASE_URL",
        ways=(
            Way(
                name="key",
                about="a DeepSeek API key, from the platform",
                asks=(Asked(env="DEEPSEEK_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                # The same key the way above asks for, as Grok Build's gateway asks for the
                # same `XAI_API_KEY` its key way does: the adapter resolves one credential
                # under one name whether the endpoint at the other end is DeepSeek's own or
                # somebody's proxy, so a second variable here would be a second name for the
                # one thing the request carries. Both of these are what `endpoint` above
                # already names and what `ambient` already lists; this is the way in that
                # lets an account hold them. Without it a key made for a gateway was a key
                # sent to `https://api.deepseek.com` -- the adapter's own default, which
                # refuses every key that is not DeepSeek's own.
                asks=(
                    Asked(env="DEEPSEEK_BASE_URL", about="where it is, as a URL"),
                    Asked(
                        env="DEEPSEEK_API_KEY", about="the key it takes", secret=True
                    ),
                ),
            ),
        ),
    ),
    Profile(
        name="grok",
        # Its log is two hosts: the OIDC issuer a sign-in is refreshed at, and the chat proxy
        # every turn goes to. The API is the key way's.
        hosts=("cli-chat-proxy.grok.com", "auth.x.ai", "api.x.ai"),
        installs="npm i -g @xai-official/grok",
        # `--disable-web-search`, which Grok Build documents as `Disable web search and web
        # fetch tools` -- the one flag for the two tools a rung takes away where what is
        # taken away is the reaching outside the workspace. On the top-level command only,
        # so an agent told this is one whose every turn is a run of it.
        searches=True,
        # `--fork-session`, spelled and meant as Claude's is: resume, but under a new id.
        forks=True,
        # `grokbuild` among them because that is what the class driving it is called, and an
        # agent names its backend by its own class name.
        aliases=("grok", "grok-build", "grokbuild"),
        home_var="GROK_HOME",
        home_dir=".grok",
        # A directory per session, under one per directory the work was done in: the id names
        # the directory rather than a file, and `updates.jsonl` is the conversation itself --
        # the others beside it are the plan, the rewind points and what it was told.
        logs=("sessions/*/{ident}/updates.jsonl",),
        # grok 1.0.24, traced through a turn and another in the same session: a directory per
        # workspace per session, with the search index of them beside, and the registry of
        # the ones running -- its JSON, its lock and the temporary it is written through.
        sessions=("sessions", "active_sessions.*"),
        # What it says when the model it was handed is not in the catalogue it is
        # holding -- which is not the same as the model not being the account's.
        # `grok models` with no account answers out of a list built into the
        # binary (`grok-4.6`, `grok-4.5`, the plain xAI names); the ids a gateway
        # account runs are fetched, and where that fetch does not land it falls
        # back to the built-in list and refuses everything else by this sentence.
        # So a run of one process per turn asks for that catalogue once a turn,
        # and the turn after the endpoint gets busy is refused a model the turn
        # before it ran on perfectly well -- seen across a matrix of twenty-three
        # cells on one account, where the first turn of each worked and the rest
        # did not.
        #
        # `throttled` rather than `unlisted` for that reason: what is wrong is the
        # fetch rather than the list, so waiting is what answers it, and walking
        # to another account after that is right either way. A model that really
        # is not the account's ends up here too, waits, and is refused again --
        # a minute spent finding out, with grok's own sentence still saying what
        # it said.
        signs=(Sign("throttled", r"couldn't set model.*unknown model id"),),
        efforts=_GROK,
        # Eight places, which is what `grok inspect` answers with: its own home and the
        # shared one under yours, both of the directories a project may keep them in, and
        # the two other harnesses' directories it reads for compatibility -- at both tiers,
        # and on by default, as its own `Harness Compatibility` says.
        skills=("skills/*/SKILL.md",),
        shared=(
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".cursor/skills/*/SKILL.md",
        ),
        works=(
            ".grok/skills/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".cursor/skills/*/SKILL.md",
        ),
        # The shared one of the four, being the directory more than one of these CLIs has
        # agreed to read: a skill mounted there is a skill Codex and Kimi read too.
        mounts=".agents/skills",
        #
        # Two files: the accounts it has signed into, keyed by the way each was signed in, and
        # the tokens its MCP servers handed back, which are somebody else's and kept apart.
        creds=("auth.json", "mcp_credentials.json"),
        ambient=(
            "GROK_AUTH",
            "GROK_AUTH_PATH",
            "GROK_AUTH_PROVIDER_COMMAND",
            "GROK_CLI_CHAT_PROXY_BASE_URL",
            "GROK_CODE_XAI_API_KEY",
            "GROK_DEFAULT_MODEL",
            "GROK_MODELS_BASE_URL",
            "GROK_MODELS_LIST_URL",
            "GROK_OAUTH2_CLIENT_ID",
            "GROK_OAUTH2_ISSUER",
            "GROK_OIDC_CLIENT_ID",
            "GROK_OIDC_ISSUER",
        ),
        # The one a turn's requests go to, rather than `GROK_MODELS_BASE_URL`, which moves
        # only where the CLI looks up its own catalogue: a list from somewhere a turn does
        # not go is the same fresh-and-wrong answer as the CLI's own.
        endpoint="GROK_XAI_API_BASE_URL",
        ways=(
            Way(
                name="login",
                about="sign in to an xAI account, in a browser",
                argv=("grok", "login"),
            ),
            Way(
                name="device",
                about="the same, from a machine with no browser on it",
                argv=("grok", "login", "--device-auth"),
            ),
            Way(
                name="key",
                about="an xAI API key, from the console",
                asks=(Asked(env="XAI_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(
                        env="GROK_XAI_API_BASE_URL",
                        about="where it is, as a URL: its models are listed at /models",
                    ),
                    Asked(env="XAI_API_KEY", about="the key it takes", secret=True),
                ),
            ),
            Way(
                name="oidc",
                about="your own identity provider, for an organisation that signs in through one",
                asks=(
                    Asked(env="GROK_OIDC_ISSUER", about="the issuer, as a URL"),
                    Asked(env="GROK_OIDC_CLIENT_ID", about="the client id"),
                ),
            ),
        ),
    ),
    Profile(
        name="kimi",
        # Two regions, each an OAuth host and a coding API -- `.com` mainland, `.ai` global --
        # and the Moonshot platform's own two for a key.
        hosts=(
            "api.kimi.com",
            "auth.kimi.com",
            "api.kimi.ai",
            "auth.kimi.ai",
            "api.moonshot.ai",
            "api.moonshot.cn",
        ),
        # One daemon per agent serves every conversation with it, as Codex's app server does.
        # That daemon is `kimi web`, and not `kimi -p --output-format stream-json`, which
        # 0.42.0 does have: the prompt mode has no route into a turn already running, no
        # per-turn body to put a rung, a thinking level or a swarm width in, and no question
        # an unattended flow can answer. `kimi web` is where a session is a thing.
        shares=True,
        # `disabled_tools`, which the daemon's prompt body takes and which names `WebSearch`
        # and `FetchURL` -- the two tools 0.42.0 reaches the web with. A deny-list rather than
        # a word to the model: the session's tool policy is what filters the tool list a
        # request carries, so a withheld tool is not in the request at all, and the executor
        # refuses one reached for anyway. Said in both directions, because the list is session
        # state written to disk and a forked session would otherwise inherit a deny.
        searches=True,
        installs="npm i -g @moonshot-ai/kimi-code",
        # Installed as a Node script with a `node` shebang, so the runtime it starts on is one
        # `NODE_OPTIONS` is read by -- the daemon included, which is what a turn of it runs in.
        preloads="NODE_OPTIONS",
        aliases=("kimi", "kimi-code"),
        # `kimi fork`, which cuts a second session from one already on disk. The command
        # rather than its daemon's route for the same thing: that one is dispatched to a
        # manager knowing none of the workspaces its sessions are in, and refuses them all.
        forks=True,
        home_var="KIMI_CODE_HOME",
        home_dir=".kimi-code",
        logs=("server/events/{ident}.jsonl",),
        # `kimi web`, traced through a turn, another and a `kimi fork`: the sessions, a
        # directory per workspace, the index of them and the table of those workspaces, the
        # events the server logs per session, the search index, and what it checkpoints per
        # session. The registry of running servers is the process's and stays where it is.
        sessions=(
            "sessions",
            "session_index.jsonl",
            "workspaces.json",
            "server/events",
            "search-index",
            "file-history",
        ),
        efforts=_KIMI,
        # Every model Kimi runs takes a turn as a fleet as well as as one agent: `swarmmax`
        # and `max` are the same thinking at two widths.
        swarms=True,
        # Kimi Code discovers both its own and the shared skill directories without a command
        # line flag, including for sessions served by `kimi web`. The shared project directory
        # is also where a flow can mount one skill for Claude, Codex or Kimi without installing
        # it into any of their homes.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".kimi-code/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"),
        mounts=".agents/skills",
        #
        # A directory apiece: kimi keeps one file per endpoint it has signed into, named
        # after that endpoint, and a lock beside it that two of its processes rotate a
        # refresh token under. Both move together or a provider would refresh into the
        # other one's token.
        creds=("credentials", "oauth"),
        ambient=(
            "KIMI_API_KEY",
            "KIMI_BASE_URL",
            "KIMI_CODE_BASE_URL",
            "KIMI_CODE_CUSTOM_HEADERS",
            "KIMI_CODE_OAUTH_HOST",
            "KIMI_OAUTH_HOST",
            "KIMI_REGISTRY_API_KEY",
        ),
        # The `model` way's endpoint rather than either of the two that move Kimi's own
        # service: that way builds a provider out of it in memory and makes it the default,
        # so it is where the turns of such an account go.
        endpoint="KIMI_MODEL_BASE_URL",
        ways=(
            Way(
                name="login",
                about="sign in to a Kimi account, by the code it prints",
                argv=("kimi", "login"),
            ),
            Way(
                name="model",
                about=_GATEWAY,
                # Kimi builds a whole provider out of these and makes it the default, in
                # memory: nothing is written to the config file it would otherwise be in.
                asks=(
                    Asked(
                        env="KIMI_MODEL_NAME", about="the model to run, as it names it"
                    ),
                    Asked(env="KIMI_MODEL_API_KEY", about="the key", secret=True),
                    Asked(env="KIMI_MODEL_BASE_URL", about="where it is, as a URL"),
                    Asked(
                        env="KIMI_MODEL_PROVIDER_TYPE",
                        about="the protocol it speaks: anthropic, openai or kimi",
                        fixed="openai",
                    ),
                ),
            ),
        ),
    ),
    Profile(
        name="pi",
        # Its one way is a sign-in, and the providers it signs in to are these: Anthropic,
        # ChatGPT, GitHub Copilot (whose token is traded for at `api.github.com`), xAI, Kimi
        # and OpenRouter -- each one's API and where it is refreshed. Signing in itself, at
        # `github.com` and the like, is done before a turn rather than during one.
        hosts=(
            "api.anthropic.com",
            "platform.claude.com",
            "chatgpt.com",
            "auth.openai.com",
            "api.github.com",
            "api.individual.githubcopilot.com",
            "api.x.ai",
            "auth.x.ai",
            "api.kimi.com",
            "auth.kimi.com",
            "openrouter.ai",
        ),
        installs="npm i -g @earendil-works/pi-coding-agent",
        # A Node script under a `node` shebang, bundle and all, so `NODE_OPTIONS` is read
        # before it starts.
        preloads="NODE_OPTIONS",
        aliases=("pi",),
        # `--fork`, which takes the session to carry in and opens the new one on top of it.
        forks=True,
        home_var="PI_CODING_AGENT_DIR",
        home_dir=".pi/agent",
        # One file per session, named for the moment it opened and the id it was given, under
        # a directory per workspace. The id is the tail of the name, so a glob on it finds the
        # session whichever workspace it was opened in.
        logs=("sessions/*/*{ident}.jsonl",),
        # A turn, another and a `--fork` write nothing else under this home.
        sessions=("sessions",),
        efforts=_PI,
        # Two places, and both are yours: the `skills/` of its own home, and the shared one
        # under yours. Nothing under the workspace, though pi reads `.pi/skills` and
        # `.agents/skills` there too -- those are gated on the project having been trusted,
        # which a headless run has nobody to press: `--approve` overrides it for one run, and
        # pi shows no trust prompt at all under `-p`, `--mode json` or `--mode rpc`. So a
        # flow's skills are not mounted for pi: they would be copied into a directory the
        # session is not permitted to read, which is a mount that quietly does nothing. What
        # is not gated is `--skill <path>`, which loads a file or a directory outright and is
        # additive even under `--no-skills` -- so that is the road, and it is taken as
        # `PiAgentConfig(skill_paths=...)` where a flow asks for it rather than here, a mount
        # being a directory this table names and that one a flag its driver builds.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        #
        # One file holding every provider it has been signed into, and the lock its own
        # processes serialize a refresh under. Worth knowing what these cost: pi checks
        # whether `auth.json` has changed before nearly every credential it resolves --
        # measured at 614 to 823 `statx` of that one path per process, better than half of
        # every path syscall a pi start makes -- so a turn run under a provider takes the
        # supervisor's most expensive path, a rewritten one, some eight hundred times.
        # Every provider pi knows reads its own key out of the environment, and an agent under
        # a provider must not be handed one of somebody else's. The vendors' own names, which
        # is what pi looks for; a provider that wants one sets it itself. All of them rather
        # than the dozen best known: `pi --help` enumerates what it reads, and a name left off
        # this list is a turn that was meant to run as one account and quietly ran as another
        # -- which is not a thing anybody notices until the bill arrives. The cloud ones are
        # in for the same reason: on Bedrock and on Azure the region, the profile, the
        # resource and the deployment map are half the credential.
        creds=("auth.json", "auth.json.lock"),
        ambient=(
            "AI_GATEWAY_API_KEY",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
            "ANTHROPIC_OAUTH_TOKEN",
            "ANT_LING_API_KEY",
            "AWS_ACCESS_KEY_ID",
            "AWS_BEARER_TOKEN_BEDROCK",
            "AWS_PROFILE",
            "AWS_REGION",
            "AWS_SECRET_ACCESS_KEY",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_API_VERSION",
            "AZURE_OPENAI_BASE_URL",
            "AZURE_OPENAI_DEPLOYMENT_NAME_MAP",
            "AZURE_OPENAI_RESOURCE_NAME",
            "BASETEN_API_KEY",
            "CEREBRAS_API_KEY",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_API_KEY",
            "CLOUDFLARE_GATEWAY_ID",
            "DEEPSEEK_API_KEY",
            "FIREWORKS_API_KEY",
            "GEMINI_API_KEY",
            "GROQ_API_KEY",
            "KIMI_API_KEY",
            "MINIMAX_API_KEY",
            "MISTRAL_API_KEY",
            "MOONSHOT_API_KEY",
            "NVIDIA_API_KEY",
            "OPENAI_API_KEY",
            "OPENCODE_API_KEY",
            "OPENROUTER_API_KEY",
            "QWEN_TOKEN_PLAN_API_KEY",
            "QWEN_TOKEN_PLAN_CN_API_KEY",
            "TOGETHER_API_KEY",
            "XAI_API_KEY",
            "XIAOMI_API_KEY",
            "XIAOMI_TOKEN_PLAN_AMS_API_KEY",
            "XIAOMI_TOKEN_PLAN_CN_API_KEY",
            "XIAOMI_TOKEN_PLAN_SGP_API_KEY",
            "ZAI_API_KEY",
            "ZAI_CODING_CN_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="pi's own /login, in a session opened for it",
                # pi signs in from inside itself, so the way in is pi, handed the terminal:
                # `/login`, whichever provider, and `/exit` when it has landed. The one thing
                # that looks like a second way in is not one: `pi auth` prints a key or a
                # bearer token and checks whether a provider is ready, and every one of its
                # three subcommands reads what is already there rather than putting anything
                # there -- so this stays the only road in.
                argv=("pi",),
            ),
        ),
    ),
    Profile(
        name="qwen",
        # The Qwen OAuth host, which issues and refreshes the token, and the DashScope API a
        # token's `resource_url` names -- `portal.qwen.ai` for most, DashScope's own for the
        # rest, in either region.
        hosts=(
            "chat.qwen.ai",
            "portal.qwen.ai",
            "dashscope.aliyuncs.com",
            "dashscope-intl.aliyuncs.com",
        ),
        installs="npm i -g @qwen-code/qwen-code",
        # A Node script rather than a binary with a runtime inside it. Its entry point starts a
        # second `node` on its own bundle -- whichever copy of itself its updater has newest --
        # and the turn is taken in that one, which is the same program either way.
        preloads="NODE_OPTIONS",
        # `web_search` and `web_fetch` are what Qwen Code calls the two, and
        # `--exclude-tools` is what it takes a tool away with.
        searches=True,
        # `--fork-session`, which it takes alongside `--resume` and nowhere else.
        forks=True,
        # The same variable its effort is already said through: the system settings layer,
        # read for one process and outranking what the person who started the flow has
        # configured. Its `hooks` block is the one Claude Code wrote, spelled the same way.
        hooks=Hooked(seam="env", name="QWEN_CODE_SYSTEM_SETTINGS_PATH"),
        aliases=("qwen", "qwen-code"),
        home_var="QWEN_HOME",
        home_dir=".qwen",
        # One file per session, named for the session and nothing else, under a directory per
        # directory the work was done in.
        logs=("projects/*/chats/{ident}.jsonl",),
        # A turn, another and a fork write the chats and each project's memory beside them
        # under `projects/`, the per-project scratch under `tmp/`, and what is checkpointed
        # per session. The usage ledgers are the account's and stay where they are.
        sessions=("projects", "tmp", "file-history"),
        efforts=_QWEN,
        # Four places: its own home and the shared one under yours, and both of the
        # directories a project may keep them in -- `.qwen` and `.agents`, which is the pair
        # its own loader is written in terms of. The ones it ships with itself are not among
        # them: those are the CLI's, not a person's to add to or switch off.
        skills=("skills/*/SKILL.md",),
        shared=(".agents/skills/*/SKILL.md",),
        works=(".qwen/skills/*/SKILL.md", ".agents/skills/*/SKILL.md"),
        # The shared one of its two, so a flow's skills reach it there.
        mounts=".agents/skills",
        #
        # What its own sign-in leaves behind, and the lock two of its processes rotate the
        # token under. Everything else it runs as is a variable.
        creds=("oauth_creds.json", "oauth_creds.lock"),
        ambient=(
            "OPENAI_API_BASE",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "QWEN_API_KEY",
            "QWEN_BASE_URL",
            "QWEN_CODE_MODEL",
            "QWEN_MODEL",
            "QWEN_OAUTH_MODELS",
        ),
        # Qwen Code has no command that lists what it runs, being an OpenAI-compatible
        # client: its catalogue was never the CLI's to know, and this is the only place it
        # is written -- which is why the two names it ships pointed at are advisory.
        endpoint="OPENAI_BASE_URL",
        ways=(
            Way(
                name="login",
                about="sign in to a Qwen account, in a session opened for it",
                # It signs in from inside itself, so the way in is qwen with the terminal
                # handed over: `/auth`, whichever provider, and `/quit` when it has landed.
                argv=("qwen",),
            ),
            Way(
                name="key",
                about="a key for the OpenAI-compatible endpoint it runs against",
                asks=(
                    Asked(env="OPENAI_API_KEY", about="the API key", secret=True),
                    Asked(
                        env="OPENAI_BASE_URL",
                        about="where it is, as a URL",
                        fixed="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    ),
                ),
                # Said rather than left to be inferred: qwen-code 0.24 given only the two
                # variables answers "No auth type is selected" and takes no turn at all.
                args=("--auth-type", "openai"),
            ),
        ),
    ),
    Profile(
        name="opencode",
        # Zen, and the two subscriptions it signs in to itself: ChatGPT's and Copilot's. The
        # model catalogue it fetches falls back to a snapshot it ships, so it is not needed.
        hosts=(
            "opencode.ai",
            "chatgpt.com",
            "auth.openai.com",
            "api.githubcopilot.com",
        ),
        installs="npm i -g opencode-ai",
        # Two reaching-out tools it names -- the one that fetches a page and the one that
        # searches for pages -- and its permission table is where each is allowed or denied.
        searches=True,
        # `run --fork`, which forks the session it was given before carrying on in it.
        forks=True,
        # opencode is a Bun standalone executable too, and reached the same way -- the
        # `opencode.exe` the launcher resolves to is the bundle. Fingerprinted by the shape of
        # the version it inlines, which sits in one module of its own here rather than the
        # entry, so the pattern picks that module out on its own. The digits are left open for
        # the reason Claude Code's are; the bundler's other `var n=""` carry no version and so
        # match nothing, which is what keeps the one module one. Its modules carry no
        # precompiled bytecode, so a source edit is what runs without anything more.
        bundles=(Bundled(path="opencode.exe", says=r'var n="\d+\.\d+\.\d+"'),),
        aliases=("opencode",),
        # No home variable of its own: it keeps its data where every other program does, in a
        # directory of its own under the one `XDG_DATA_HOME` names.
        home_var="XDG_DATA_HOME",
        home_in="opencode",
        home_dir=".local/share/opencode",
        # None: a session here is rows of a database rather than a file, so there is no log to
        # read a run's cost out of as it is spent, and none to gather afterwards.
        logs=(),
        # That database and its write-ahead files, and the per-session JSON a release before
        # it kept -- traced through a turn, another and a `--fork`. The snapshots it takes of
        # a workspace are a cache of the workspace rather than of the session.
        sessions=("opencode.db*", "storage"),
        efforts=_VARIANTS,
        # Its own are under the configuration home rather than the data home this backend is
        # otherwise kept under -- `~/.config/opencode`, where its `opencode.json` is, not
        # `~/.local/share/opencode`, where its sessions and its logins are. Singular and
        # plural both: it reads `skill/` and `skills/` wherever it reads either.
        config=("opencode/skills/*/SKILL.md", "opencode/skill/*/SKILL.md"),
        # And the two it auto-loads from outside its own directories, which it calls external
        # skills: another harness's, and the shared one.
        shared=(".agents/skills/*/SKILL.md", ".claude/skills/*/SKILL.md"),
        works=(
            ".opencode/skills/*/SKILL.md",
            ".opencode/skill/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
        ),
        # The shared one of its three, as for the others that read it.
        mounts=".agents/skills",
        # One file per kind of thing signed into: the providers in one, the servers a session
        # reaches out to in the other.
        creds=("auth.json", "mcp-auth.json"),
        # The one that would bypass the file outright, and the vendors' own names it reads a
        # key under. Its catalogue knows a hundred and eighty of those; these are the ones a
        # machine is likely to be carrying already.
        ambient=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "DEEPSEEK_API_KEY",
            "GEMINI_API_KEY",
            "GITHUB_TOKEN",
            "OPENAI_API_KEY",
            "OPENCODE_AUTH_CONTENT",
            "OPENCODE_CONFIG_CONTENT",
            "OPENROUTER_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="opencode's own provider list, and whichever way that one takes",
                argv=("opencode", "auth", "login"),
            ),
            Way(
                name="wellknown",
                about="a provider that hands out its own credential, by URL",
                argv=("opencode", "auth", "login", "{OPENCODE_WELLKNOWN}"),
                asks=(
                    Asked(
                        env="OPENCODE_WELLKNOWN",
                        about="the URL to ask, which answers at /.well-known/opencode",
                        keep=False,
                    ),
                ),
            ),
            Way(
                name="zen",
                about="an OpenCode Zen key, which its own models run on",
                asks=(Asked(env="OPENCODE_API_KEY", about="the key", secret=True),),
            ),
        ),
    ),
    Profile(
        name="mimo",
        # MiMo's API, which serves both the free default and a key, and its token plan's
        # three regions.
        hosts=(
            "api.xiaomimimo.com",
            "token-plan-cn.xiaomimimo.com",
            "token-plan-sgp.xiaomimimo.com",
            "token-plan-ams.xiaomimimo.com",
        ),
        installs="npm i -g @mimo-ai/cli",
        # The one place mimocode differs from opencode in a way that matters here: what it is
        # installed as is a Node script, where opencode is a single-file Bun executable with
        # its runtime compiled in, which reads none of this. That script starts the same kind
        # of binary, though, so what a preload reaches of mimocode is its launcher.
        preloads="NODE_OPTIONS",
        # mimocode is opencode's, permission table and all, and a third reaching-out tool
        # besides the two: the one it looks an API or a library up with.
        searches=True,
        # And its `--fork` too: the same program under another name.
        forks=True,
        aliases=("mimo", "mimocode", "mimo-code"),
        home_var="XDG_DATA_HOME",
        home_in="mimocode",
        home_dir=".local/share/mimocode",
        logs=(),
        # opencode's, under its own name: the database, and the per-session diffs.
        sessions=("mimocode.db*", "storage"),
        efforts=_VARIANTS,
        # Its own and the open standard's, and nobody else's: 0.1.15 reads Claude Code's,
        # Codex's and opencode's only where `MIMOCODE_ENABLE_CLAUDE_CODE_SKILLS` and its two
        # siblings are set, which nothing here sets. The ones it ships under its own data
        # home -- its builtins, and the bundle its compose flows work by -- are not listed:
        # those came with the CLI rather than from whoever is running it.
        config=("mimocode/skills/*/SKILL.md", "mimocode/skill/*/SKILL.md"),
        shared=(".agents/skills/*/SKILL.md",),
        works=(
            ".mimocode/skills/*/SKILL.md",
            ".mimocode/skill/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
        ),
        mounts=".agents/skills",
        creds=("auth.json", "mcp-auth.json"),
        ambient=(
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_BASE_URL",
            "MIMOCODE_AUTH_CONTENT",
            "MIMOCODE_CONFIG_CONTENT",
            "MIMO_API_KEY",
            "OPENAI_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="mimocode's own provider list, and whichever way that one takes",
                argv=("mimo", "auth", "login"),
            ),
            Way(
                name="key",
                about="a MiMo key, which its own models run on",
                asks=(Asked(env="XIAOMI_API_KEY", about="the key", secret=True),),
            ),
        ),
    ),
    Profile(
        # Installed under two names, `agent` being the one its installer calls primary and
        # `cursor-agent` the one it has always also written. The second, because `agent` is a
        # name anything on a machine could have taken and this one has to be that CLI -- and
        # this name, because a backend here is called what it is installed as, so that `-a`
        # takes the word somebody would type at a shell to run the thing itself.
        name="cursor-agent",
        # `api2.cursor.sh` signs in and configures; the host a turn then goes to is one the
        # server names at run time, under `cursor.sh` rather than written in the bundle.
        hosts=("*.cursor.sh",),
        installs="curl https://cursor.com/install -fsS | bash",
        # Its own command line has no way of taking a tool away: what an agent may reach for
        # is `~/.cursor/cli-config.json`, which is the person at this machine's file and not
        # one a driver writes. So web search is refused off here rather than said and ignored.
        searches=False,
        # `--resume` picks a chat back up under its own id and it has no second spelling:
        # a conversation of Cursor's is one conversation.
        forks=False,
        aliases=("cursor-agent", "cursor-cli"),
        # Its own variable, else the directory every program keeps its configuration in, else
        # `~/.cursor` -- which is what `config` below covers the middle of.
        home_var="CURSOR_CONFIG_DIR",
        home_dir=".cursor",
        # None to read: a chat is kept in the agent store rather than as a file per session,
        # so there is no trajectory here for a trace to gather.
        logs=(),
        # That store, a directory per chat, and the transcripts it writes beside each project
        # it trusts. The rest of a project's directory is not a session's: it is the trust
        # itself, and the socket its worker listens on.
        sessions=("chats", "projects/*/agent-transcripts"),
        efforts=_CURSOR,
        # Both tiers, under the layout every one of these CLIs reads a skill in. It reads
        # several other CLIs' directories too, and those are theirs rather than this one's.
        skills=("skills/*/SKILL.md",),
        config=("cursor/skills/*/SKILL.md",),
        works=(".cursor/skills/*/SKILL.md",),
        mounts=".cursor/skills",
        # What a login leaves behind: the account it shows, in the settings file, and the
        # tokens, which are not under its home at all. `cursor-agent` puts `auth.json` under
        # the directory every program keeps its configuration in on Linux, and under
        # `~/.cursor` on macOS whatever `CURSOR_CONFIG_DIR` says -- both spelled here, since
        # a path nobody reads on this machine costs nothing to point somewhere else.
        creds=("cli-config.json", "config/cursor/auth.json", "~/.cursor/auth.json"),
        # `CURSOR_LOCAL_AGENT_API_KEY` because the key its own local runtime is served under
        # is still a key, read whoever exported it: one left in a shell profile is the account
        # a turn under a provider would be answered as. Its endpoint and its authless switch
        # are deliberately not here. They say which runtime a turn is, not whose it is, and a
        # turn taken away from the endpoint it was pointed at is a turn somewhere else.
        ambient=(
            "CURSOR_API_BASE_URL",
            "CURSOR_API_ENDPOINT",
            "CURSOR_API_KEY",
            "CURSOR_API_URL",
            "CURSOR_AUTH_TOKEN",
            "CURSOR_LOCAL_AGENT_API_KEY",
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a Cursor account, in a browser",
                argv=("cursor-agent", "login"),
            ),
            Way(
                name="key",
                about="a Cursor API key, from the dashboard",
                asks=(Asked(env="CURSOR_API_KEY", about="the API key", secret=True),),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                asks=(
                    Asked(env="CURSOR_API_ENDPOINT", about="where it is, as a URL"),
                    Asked(env="CURSOR_API_KEY", about="the key it takes", secret=True),
                ),
            ),
        ),
    ),
    Profile(
        # Installed from `@minimax-ai/code` as `mcode`, which is the name `-a` takes for the
        # reason `cursor-agent` is what that one takes: the word somebody would type at a
        # shell to run the thing itself.
        name="mcode",
        # Its agent service in each of the three places it is served from, which is where a
        # sign-in is refreshed, where the managed models answer and where its own permission
        # check and web search go; its API in both regions, where a key's turns go; and the
        # account pages a sign-in is made on. Read off 0.5.9's own bundle.
        hosts=(
            "agent.minimax.io",
            "agent.minimaxi.com",
            "agent.minimax.cn",
            "api.minimax.io",
            "api.minimaxi.com",
            "account.minimax.io",
            "account.minimax.cn",
        ),
        installs="npm i -g @minimax-ai/code",
        # `mcode exec` has no flag that takes a tool away, and the one file that could is
        # its `config.yaml` -- the person at this machine's, which a driver does not write.
        searches=False,
        # A conversation is resumed with `--session` under the id it was opened with, and
        # its command line has no way of cutting a second one from it: the forking it does
        # is a thing its interface offers a person, from `/history`.
        forks=False,
        aliases=("mcode", "minimax", "minimax-code"),
        home_var="MINIMAX_DATA_DIR",
        home_dir=".minimax",
        # A directory per session, under the day it was opened, named for the moment it
        # opened and the session's id in URL-safe base64. `messages.jsonl` inside it is the
        # conversation as the model saw it, a record per message, and every answer carries
        # what the request it came back on cost.
        logs=("v2/sessions/*/*/*/*-session_{ident}/messages.jsonl",),
        encodes=True,
        # The database a session is resumed out of, the directory per session the logs are
        # in, and where what a tool call ran is written out in full -- traced through a turn
        # and a second one resuming it. The rest of `v2/` is the runtime's own: its leases,
        # its migrations and its observability logs.
        sessions=("v2/sqlite", "v2/sessions", "background-tasks"),
        efforts=_MCODE,
        # Its own under its data home, and what it calls external skills: Claude Code's,
        # Codex's and the shared ones under yours, and a project's own, Claude Code's and the
        # shared ones under the workspace -- every one of them on unless its `config.yaml`
        # says otherwise. The ones it ships are in `.builtin-skills`, and are the CLI's
        # rather than a person's to add to or switch off.
        skills=("skills/*/SKILL.md",),
        shared=(
            ".agents/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".codex/skills/*/SKILL.md",
        ),
        works=(
            ".minimax/skills/*/SKILL.md",
            ".claude/skills/*/SKILL.md",
            ".agents/skills/*/SKILL.md",
        ),
        # The shared one of the three, as for the others that read it.
        mounts=".agents/skills",
        # Everything an account is: `config.yaml` holds a key and every provider added to it,
        # and `auth/` what a sign-in leaves -- a directory per build, and the lock two of its
        # processes refresh a token under.
        creds=("config.yaml", "auth"),
        # The endpoints and the region that say whose account a turn is taken as, and the
        # vendor's own names for a key. None of them is a way in of its own.
        ambient=(
            "MCODE_API_BASE_URL",
            "MCODE_AUTH_BASE_URL",
            "MCODE_AUTH_PROVIDER",
            "MCODE_CLIENT_ID",
            "MCODE_REGION",
            "MINIMAX_API_KEY",
            "MINIMAX_CN_API_KEY",
        ),
        # What it says when a turn stops on its sign-in, which none of the shared signs read:
        # `Sign in to MiniMax to use Agent features`, before a turn has started, and a managed
        # model's `OAuth bearer is not synced`, when one has.
        signs=(
            Sign("refused", r"sign in to minimax"),
            Sign("refused", r"oauth bearer is not synced"),
        ),
        ways=(
            Way(
                name="login",
                about="sign in to a MiniMax account, in a browser",
                argv=("mcode", "login"),
            ),
            Way(
                name="key",
                about="a MiniMax API key, from the platform",
                # Saved into its `config.yaml` and chosen as where its models run from. It
                # reads the key out of this variable rather than off its command line or
                # its standard input, so the variable is what the answer has to be.
                argv=("mcode", "provider", "set-minimax-key"),
                asks=(
                    Asked(
                        env="MCODE_PROVIDER_API_KEY", about="the API key", secret=True
                    ),
                ),
            ),
            Way(
                name="gateway",
                about=_GATEWAY,
                # A provider of its own, added to its `config.yaml` with the one model named
                # here and made the default -- after a request to it, so an endpoint that
                # does not answer is a way in that fails where it is made rather than a
                # provider nothing can use.
                argv=(
                    "mcode",
                    "provider",
                    "add",
                    "--name",
                    "gateway",
                    "--base-url",
                    "{MCODE_GATEWAY_URL}",
                    "--api-format",
                    "{MCODE_GATEWAY_FORMAT}",
                    "--model",
                    "{MCODE_GATEWAY_MODEL}",
                    "--api-key-env",
                    "MCODE_PROVIDER_API_KEY",
                    "--use",
                ),
                asks=(
                    Asked(env="MCODE_GATEWAY_URL", about="where it is, as a URL"),
                    Asked(
                        env="MCODE_PROVIDER_API_KEY",
                        about="the key it takes",
                        secret=True,
                    ),
                    Asked(
                        env="MCODE_GATEWAY_MODEL",
                        about="the model to run, as the endpoint names it",
                        keep=False,
                    ),
                    Asked(
                        env="MCODE_GATEWAY_FORMAT",
                        about=(
                            "the protocol it speaks: anthropic-messages, "
                            "openai-completions or openai-responses"
                        ),
                        fixed="openai-completions",
                        keep=False,
                    ),
                ),
            ),
        ),
    ),
)


#: Where in humanize's settings the CLIs somebody added themselves are written down. A setting
#: of the machine rather than of one workspace: a CLI is installed on a machine, and a flow
#: run in the next directory along is run against the same one.
#:
#: One entry per CLI, by name: the command that starts it, as a list -- or, for a CLI to be
#: held to a flow's permission, a mapping whose `command` is that list, whose `hosts` are
#: what it cannot take a turn without reaching while the flow grants no network, and whose
#: `state` is where it keeps what it writes as it runs. The protocol says neither, so they are
#: the person's to write down; see :func:`declared`.
_SPOKEN = "clis"


#: What was read out of the settings last time, and the moment the file carried then. Held
#: because this is asked far more often than it changes: every turn builds a watchdog, every
#: keystroke of a sheet that lists backends asks again, and each ask was opening and parsing
#: the file afresh. Re-read when the file under it has moved, which every write of it does.
_added: dict[str, tuple[str, ...]] | None = None
_added_at: tuple[int, int] | None = None
#: What each of those was declared to reach and to keep, read in the same pass.
_declared: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}


def _strings(said: object) -> tuple[str, ...]:
    """A list of strings out of a file, and nothing for anything that is not one."""
    if not isinstance(said, list):
        return ()
    return tuple(str(one) for one in cast("list[object]", said) if str(one).strip())


def speaking() -> dict[str, tuple[str, ...]]:
    """Every CLI somebody has added, and the command that starts each one.

    Returns:
      One entry per CLI, by the name it was added under, holding the command to run. Nothing
      at all where none has been added or where what was written cannot be read back -- a
      file nobody can read is a list to fill rather than a reason to refuse to start.
    """
    # Read where it is asked, never at import: the settings are YAML, which is not the
    # standard library's to read.
    from hmz.coganchor import settings

    global _added, _added_at, _declared
    at = settings.where()
    try:
        moved = at.stat()
        stamp = (moved.st_mtime_ns, moved.st_size)
    except OSError:
        # No file is an answer, and a cheap one: nothing has been added.
        _added, _added_at, _declared = {}, None, {}
        return {}
    if _added is not None and stamp == _added_at:
        return _added
    held = settings.read().get(_SPOKEN)
    if not isinstance(held, dict):
        _added, _added_at, _declared = {}, stamp, {}
        return {}
    found: dict[str, tuple[str, ...]] = {}
    declared: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for name, entry in cast("dict[str, object]", held).items():
        said = (
            cast("dict[str, object]", entry)
            if isinstance(entry, dict)
            else {"command": entry}
        )
        argv = said.get("command")
        if not isinstance(argv, list):
            continue
        given = tuple(str(one) for one in cast("list[object]", argv))
        if given:
            found[str(name)] = given
            declared[str(name)] = (
                _strings(said.get("hosts")),
                _strings(said.get("state")),
            )
    _added, _added_at, _declared = found, stamp, declared
    return found


def declared(name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """What an added CLI was declared to need under a flow's permission.

    A CLI known only by the protocol it speaks is one nothing here knows the model API or the
    state directory of, and a flow that grants it no network or no home to write would
    otherwise leave it no way to take a turn. So both are written down beside its command,
    by whoever added it.

    Args:
      name: What it was added under.

    Returns:
      The hosts it may still reach while the network is cut -- each as
      :attr:`Profile.hosts` spells one -- and the paths it keeps its state at, as written,
      `~` and all. Nothing for either where nothing was declared.
    """
    speaking()
    return _declared.get(name, ((), ()))


def _write(name: str, argv: Sequence[str] | None) -> bool:
    """Writes one added CLI down, or takes it away, and every other as the file has it now.

    Args:
      name: What it was added under.
      argv: The command that starts it, keeping what it was declared to need; None to take
        it away.

    Returns:
      Whether it was there already.
    """
    from hmz.coganchor import settings

    found: list[bool] = []

    def change(settled: dict[str, Any]) -> None:
        held = settled.get(_SPOKEN)
        entries = (
            dict(cast("dict[str, object]", held)) if isinstance(held, dict) else {}
        )
        found.append(name in entries)
        was = entries.pop(name, None)
        said = cast("dict[str, object]", was) if isinstance(was, dict) else {}
        hosts, state = _strings(said.get("hosts")), _strings(said.get("state"))
        if argv is None:
            pass
        elif hosts or state:
            entries[name] = {
                "command": list(argv),
                "hosts": list(hosts),
                "state": list(state),
            }
        else:
            entries[name] = list(argv)
        settled[_SPOKEN] = entries

    settings.changes(change)
    return any(found)


def remember(name: str, command: Sequence[str]) -> str:
    """Writes down a CLI that speaks the protocol, so that it is a backend from now on.

    Args:
      name: What to call it, which is what an `-a` will name and what the prompt will show.
        The command it is installed as, and only that: every backend humanize drives answers
        to the command that CLI registers -- `claude` is `claude`, `codex` is `codex` -- and
        an added one that answered to something else would be a name that says nothing about
        what is running. Blank to be called what the command is called, which is the answer
        this would refuse anything else in favour of anyway.
      command: What to run to start it, as argv -- `["my-agent", "--acp"]`. There is no
        discovery in the protocol and no flag every agent agrees on, so this is asked for.
        What it is called comes off the first word of it, so a CLI started through something
        else -- `npx @someone/agent`, `python -m agent` -- is called after the launcher, and
        a second one started the same way is the same name and replaces it. Which is the
        cost of a name that says what will actually run, and is paid by anything installed
        as a command of its own.

    Returns:
      What it was written down as, which is the command's own name.

    Raises:
      ValueError: If it has no command, if it was called something the command is not, or if
        it would shadow a backend humanize already drives -- two backends answering to one
        name is a name nobody can resolve.
      OSError: If the settings cannot be read, or written.
    """
    named_as = name.strip()
    argv = [str(one) for one in command if str(one).strip()]
    if not argv:
        raise ValueError("an added CLI needs a command to start it with")
    # The command's own name, so that one written as a path is still called what it is: a CLI
    # installed where PATH does not name it is the same CLI, and `/opt/mimo/bin/mimo` is mimo.
    runs = PurePath(argv[0]).name
    # Against what it runs rather than against what it was called, and before the name is: a
    # CLI humanize already drives is one this cannot add under any name, and saying which name
    # to use instead would be sending somebody round to the same refusal.
    if any(runs in one.aliases for one in PROFILES):
        raise ValueError(f"{runs} is already a backend humanize drives")
    named_as = named_as or runs
    if named_as != runs:
        raise ValueError(
            f"an added CLI is called what it runs, so {argv[0]} is added as {runs} "
            f"rather than as {named_as}"
        )
    _write(named_as, argv)
    return named_as


def forget(name: str) -> bool:
    """Takes an added CLI away again.

    Args:
      name: What it was added under.

    Returns:
      Whether there was one to take away.

    Raises:
      OSError: If the settings cannot be read, or written.
    """
    if name not in speaking():
        return False
    return _write(name, None)


#: What is assumed about a backend nothing at all is written down about -- a stand-in written
#: for a test, a name that answers to no profile -- when something has to assume anyway. A CLI
#: somebody added is not one of these: it has a profile of its own, which `_speaks` makes.
#:
#: It runs somewhere, so it is a process that can be put down and started again; and its
#: conversations are taken to not survive that, because nothing says they do and a watchdog
#: that promised a conversation back would be promising on behalf of a backend it has never
#: heard of. Nothing else here is true of it, which is why every other field is left at what
#: it says by default.
UNKNOWN = Profile(
    name="",
    aliases=(),
    home_var="",
    home_dir="",
    logs=(),
    efforts=(),
    resumes=False,
)


def profiles() -> tuple[Profile, ...]:
    """Every backend there is: the ones humanize drives, and the ones somebody added.

    Read each time rather than settled at import: a CLI added at the prompt is a backend from
    that moment, and a list built once would be a list that says otherwise until the next run.

    Returns:
      The built-in profiles in their own order, and then the added ones in the order they
      were written down.
    """
    return (*PROFILES, *(_speaks(name) for name in speaking()))


def _speaks(name: str) -> Profile:
    """The profile of a CLI known only by the protocol it speaks.

    Args:
      name: What it was added under.

    Returns:
      A profile saying the little there is to say: it has no home humanize can find, no logs
      it can read, and one rung of an effort ladder, because the protocol describes none of
      those. What it does have is a name to be chosen by, and two things that follow from the
      protocol itself: a conversation of its can be picked back up, and `session/fork` is a
      call in it.
    """
    return Profile(
        name=name,
        aliases=(name,),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(_UNSAID,),
        # The protocol has two ways of picking a conversation back up -- `session/resume`,
        # which restores it, and `session/load`, which replays it -- and an agent says at the
        # handshake which of them it serves. Every ACP server this was tried against serves
        # both, and one of them was checked the only way that means anything: a session opened
        # in one process, that process killed, and the conversation picked back up in the next
        # one still knowing what it had been told. An agent that serves neither refuses where
        # the conversation is picked up rather than here.
        resumes=True,
        # The protocol has the call, which is the most that can be known about a CLI known
        # only by the protocol it speaks. An agent that has not implemented it refuses where
        # it is asked rather than here -- which is still a refusal, and still not two flows
        # sharing one conversation.
        forks=True,
        # Whatever whoever added it declared it cannot take a turn without reaching, which
        # is all that can be known of its model API: see :func:`declared`.
        hosts=declared(name)[0],
    )


#: The credentials more than one of these backends runs on, and what each of them calls one.
#: A vendor's key is the vendor's rather than the CLI's -- an Anthropic key is an Anthropic
#: key whether Claude Code, pi, opencode or mimocode is holding it -- so an account made for
#: one backend is an account the others could be run as too.
#:
#: One entry per credential, holding every name it goes by. Most go by one: the variable is
#: the vendor's own and every CLI that reads it reads it under that name. The ones with two
#: are where a CLI named a vendor's credential after itself.
#:
#: Which backends actually read each of them is not written here: it is already written, as
#: what each backend's ways ask for and what it says it would take an account from. This is
#: only the sameness -- that `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_OAUTH_TOKEN` are one
#: subscription under two names.
ALIKE: tuple[tuple[str, ...], ...] = (
    ("ANTHROPIC_API_KEY",),
    ("ANTHROPIC_AUTH_TOKEN",),
    ("ANTHROPIC_BASE_URL",),
    ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN"),
    ("DEEPSEEK_API_KEY",),
    ("DEEPSEEK_BASE_URL",),
    ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    ("OPENAI_API_KEY",),
    ("OPENAI_BASE_URL", "OPENAI_API_BASE"),
    ("XAI_API_KEY", "GROK_CODE_XAI_API_KEY"),
)


def alike(variable: str) -> tuple[str, ...]:
    """Every name one credential goes by, across the backends that read it.

    Args:
      variable: What one of them calls it.

    Returns:
      All of its names, that one included, and just that one for a credential nothing else
      has a name for.
    """
    for held in ALIKE:
        if variable in held:
            return held
    return (variable,)


def serves(env: Mapping[str, str], backend: str) -> dict[str, str] | None:
    """What one account would be, spelled as another backend reads it.

    A vendor's key is the vendor's: an account made as an Anthropic key is an account pi,
    opencode and mimocode could each be run as, under whatever each of them calls it. What
    cannot travel is an account that is not variables at all -- a subscription signed into
    writes the CLI's own credential store, in that CLI's own format, and nothing else reads
    it.

    Args:
      env: What a turn under the account is run with.
      backend: The backend it would be copied to, by any name it answers to.

    Returns:
      The same account under the names that backend reads, or None where it could not be run
      as that backend at all -- because the backend is not one humanize drives, because the
      account holds nothing but files, or because one of the things it holds is a credential
      that backend has no name for.
    """
    profile = named(backend)
    if profile is None or not env:
        return None
    reads = profile.accounts()
    held: dict[str, str] = {}
    for variable, value in env.items():
        under = next((one for one in alike(variable) if one in reads), "")
        if not under:
            return None
        held[under] = value
    return held


def named(backend: str) -> Profile | None:
    """The backend a name stands for, whichever of its spellings was used.

    Args:
      backend: What it was called.

    Returns:
      Its profile, or None for a name no backend answers to.
    """
    return next((one for one in profiles() if backend in one.aliases), None)


#: The endings of the variables, among a backend's `ambient`, whose value says where it goes:
#: a base URL or an endpoint however it is spelled, or the host or issuer a sign-in is
#: refreshed at.
_ROUTING = ("_URL", "_BASE", "_HOST", "_ENDPOINT", "_ORIGIN", "_ISSUER")


def reachable(profile: Profile, environ: Mapping[str, str]) -> tuple[str, ...]:
    """The hosts a turn of this backend may still reach when a flow grants it no network.

    This is the one hole `online=NONE` leaves, and it is left on purpose. A coding agent CLI
    thinks on somebody else's machine: with its model API cut it is not an agent working
    offline but a process that cannot take a turn at all, and a scope that made every turn
    fail would be a scope nobody could use. So the fence lets through exactly what the CLI
    cannot run without -- its model API, and where its sign-in is refreshed -- and nothing
    else: not the web its agent would search, not a package index, not a host a command it
    runs names.

    Those are the profile's `hosts`, and whatever the environment the turn runs under points
    it at instead: the value of its `endpoint`, and of each of its `ambient` variables that
    names a base URL, an endpoint, an OAuth host or issuer. An account made for a gateway
    routes every request of its turns there, and the fence has to follow it or it would cut
    the one connection the turn is made of. It adds that host rather than replacing the
    vendor's with it: a CLI pointed elsewhere for its model may still refresh its sign-in at
    home. An account that switches the backend onto a cloud -- Bedrock, Vertex, Foundry --
    adds that cloud's hosts, for the same reason.

    Args:
      profile: The backend.
      environ: The environment a turn of it runs under -- the provider's, rather than this
        process's own.

    Returns:
      The hosts, in the order first named and each once. Each is exact or a `*.suffix`
      wildcard, reachable on the usual ports; one an account names with a port of its own --
      a gateway at `https://gw.example:8443` -- is written `host:port`, and reachable on that
      port alone. Empty for a backend nothing is written down about, which the fence then
      lets reach nothing: one it knows no hosts for is one it cannot keep a hole open for.
    """
    routing = [profile.endpoint] if profile.endpoint else []
    routing += [one for one in profile.ambient if one.endswith(_ROUTING)]
    said = [environ.get(one, "") for one in routing]
    for switch, (spelled, hosts, overrides) in _CLOUDS.items():
        if switch not in profile.ambient or not environ.get(switch):
            continue
        said += [environ.get(one, "") for one in overrides]
        values = {
            name: environ.get(name) or default for name, default in spelled.items()
        }
        # A region or a resource is one DNS label; anything else would be spelling a host
        # of the value's own choosing into the allow-list.
        if all(_LABEL.fullmatch(value) for value in values.values()):
            said += [host.format_map(values) for host in hosts]
    pointed = (_place(one) for one in said)
    return tuple(dict.fromkeys((*profile.hosts, *(one for one in pointed if one))))


_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


#: The clouds a backend can be switched onto, by the variable that switches it: the
#: variables its hosts are spelled out of, with what each is taken to be where the account
#: says nothing; the hosts the cloud's model API and its credentials are at; and the
#: variables that move that API somewhere else instead. Claude's Bedrock, Vertex and Foundry
#: ways, the accounts whose model API is a cloud's rather than Anthropic's, and whose host is
#: made of a region or a resource rather than written anywhere.
_CLOUDS: dict[str, tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]] = {
    "CLAUDE_CODE_USE_BEDROCK": (
        {"AWS_REGION": "us-east-1"},
        (
            "bedrock-runtime.{AWS_REGION}.amazonaws.com",
            "bedrock.{AWS_REGION}.amazonaws.com",
            "sts.{AWS_REGION}.amazonaws.com",
        ),
        ("ANTHROPIC_BEDROCK_BASE_URL",),
    ),
    "CLAUDE_CODE_USE_VERTEX": (
        {"CLOUD_ML_REGION": "us-east5"},
        (
            "{CLOUD_ML_REGION}-aiplatform.googleapis.com",
            "aiplatform.googleapis.com",
            "oauth2.googleapis.com",
        ),
        ("ANTHROPIC_VERTEX_BASE_URL",),
    ),
    "CLAUDE_CODE_USE_FOUNDRY": (
        {"ANTHROPIC_FOUNDRY_RESOURCE": ""},
        ("{ANTHROPIC_FOUNDRY_RESOURCE}.services.ai.azure.com",),
        ("ANTHROPIC_FOUNDRY_BASE_URL",),
    ),
}


def _place(value: str) -> str:
    """The host a variable's value names, whether it is written as a URL or as a bare host.

    Returns:
      The hostname, lower case and without a trailing dot, with `:port` after it where the
      value names a port -- in brackets first, for an IPv6 address -- or "" for a value that
      names no host.
    """
    value = value.strip()
    if not value:
        return ""
    try:
        split = urllib.parse.urlsplit(value if "://" in value else f"//{value}")
        host, port = (split.hostname or "").rstrip("."), split.port
    except ValueError:
        return ""
    if not host or port is None:
        return host
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


#: What a process's exit status says on its own, before anything it wrote is read. A shell
#: answers 127 for a command it could not find and 126 for one it could not run, and a process
#: that died on a signal has no exit status at all -- Python reports that as the negative of
#: the signal, and a shell as 128 plus it. None of those is a sentence to be read: the process
#: never got as far as saying anything, so the status is the whole of what there is.
#:
#: Held to the signals there actually are, which is what keeps it from reading a status that
#: is not one. Not every backend here exits: kimi is driven through a daemon and reports the
#: HTTP status of the call it made, so a rate-limited turn of it arrives as 429 -- and 429 is
#: greater than 128. No real HTTP status falls between 128 and 192, so bounding this to the
#: 64 signals a machine has is what tells the two apart.
_CANNOT_RUN = (126, 127)
_SIGNALLED = 128
_SIGNALS = 64

#: How much of the end of a stream is read for what a turn failed with. Long enough for the
#: last few lines of a protocol, and short enough that the transcript in front of them cannot
#: supply a word the failure did not: an agent asked to write a rate limiter says `rate limit`
#: in prose, and a turn of it that failed for something else must not read as throttled.
_READ = 4096


def trouble(
    backend: str, *said: str | bytes | None, status: int = 0, journal: str = ""
) -> str:
    """Which kind of failure a stopped turn was, out of what the CLI said about it.

    One classifier rather than a regex wherever a driver first met one: every one of these
    CLIs speaks HTTP to a model provider, so a `429` reads the same whichever of them was
    holding the socket, and what one of them says and no other does is written on that
    backend's own profile.

    Args:
      backend: The CLI, by any name it answers to. One nothing answers to is read by the
        signatures every backend shares, which is what an added CLI has.
      said: What it wrote, in the order to read it -- the stream it complains on first, since
        that is where a CLI puts the sentence it is failing with and a protocol stream is a
        wall of JSON the same sentence may also be buried in.
      status: How it exited, for the failures where it never got as far as saying anything.
      journal: What it wrote to a log of its own, read last: a CLI that exits with a generic
        error and keeps the status in its own log is one whose streams say nothing, so this is
        looked at only when they did not.

    Returns:
      One of :data:`FAULTS`, or "" for a failure nothing here recognises -- which is a turn
      tried again exactly as it always was, rather than one guessed at.
    """
    if status in _CANNOT_RUN:
        return "missing"
    if status < 0 or _SIGNALLED < status <= _SIGNALLED + _SIGNALS:
        return "killed"
    profile = named(backend)
    # The end of each: what a turn failed with is the last thing it said, and the megabyte of
    # transcript in front of that is where a false reading would come from -- an agent asked
    # to write a rate limiter says `rate limit` in prose.
    streams = [
        (one.decode("utf-8", "replace") if isinstance(one, bytes) else one or "")[
            -_READ:
        ]
        for one in (*said, journal)
    ]
    # This backend's own signatures across every stream before any of the shared ones, rather
    # than both together: a CLI that has a sentence of its own for a failure knows better than
    # a word that happens to be in the same line -- dsh says `needs a DeepSeek API key`, and a
    # line that also mentions a quota is not a quota that was spent.
    #
    # And within each, the order they are written in rather than the order the kinds are
    # named: a status says only that something was refused and a sentence says what, so the
    # one that says what is written in front. A `403 key not allowed to access model` read by
    # the number is a person told to sign an account in that refused nothing, and a `bwrap:
    # Permission denied` read by the word is the same person told it twice.
    for signs in ((profile.signs if profile is not None else ()), SIGNS):
        for held in streams:
            found = next(
                (
                    one.fault
                    for one in signs
                    if held and re.search(one.says, held, re.IGNORECASE)
                ),
                "",
            )
            if found:
                return found
    return ""


#: How far back a CLI's own log is read for a reason its streams did not carry, and how much
#: of the end of it. A log is appended to for as long as that CLI runs, so one nothing has
#: written to for five minutes is not the one this turn stopped in.
_LATELY = 300.0
_TAILED = 65536


def journalled(
    backend: str,
    environment: Mapping[str, str] | None = None,
    *,
    within: float = _LATELY,
) -> str:
    """The end of a CLI's own log, for one that keeps why a turn stopped only in there.

    Antigravity is the reason this exists: it exits with `Agent execution terminated due to
    error`, writes nothing about the status on either stream, and puts the HTTP 429 that
    actually stopped it in a log of its own. A turn of it that was rate-limited reads as a
    turn that simply failed unless somebody goes and looks.

    Args:
      backend: The CLI, by any name it answers to.
      environment: What the turn ran with, since a home is moved by a variable and a turn
        under a provider runs with that provider's environment rather than with ours.
      within: How recently the log must have been written to count as this turn's. Whoever
        is classifying a failure should pass how long that turn actually took: these logs are
        shared between every session of that CLI on this machine, so a window wider than the
        turn is a window somebody else's turn can be read out of.

    Returns:
      The end of the newest one, and "" for a backend that keeps no such log, one that has
      not written to it lately, and one whose log cannot be read.
    """
    profile = named(backend)
    if profile is None or not profile.journal:
        return ""
    home = profile.directory(environment)
    now = time.time()
    found: list[tuple[float, Path]] = []
    for glob in profile.journal:
        for at in home.glob(glob):
            try:
                when = at.stat().st_mtime
            except OSError:
                continue
            if now - when <= within:
                found.append((when, at))
    if not found:
        return ""
    newest = max(found)[1]
    try:
        with newest.open("rb") as reading:
            reading.seek(max(0, newest.stat().st_size - _TAILED))
            return reading.read().decode("utf-8", "replace")
    except OSError:
        return ""


def installing(backend: str) -> str:
    """The line that puts one of these CLIs on this machine.

    Args:
      backend: The CLI, by any name it answers to.

    Returns:
      The command, or a line saying to install it for a backend whose own nobody has written
      down here. Never "": a turn that failed for a missing CLI has nothing else to say, and
      an empty half-sentence would be worse than a general one.
    """
    profile = named(backend)
    if profile is not None and profile.installs:
        return profile.installs
    return (
        f"install {profile.name if profile is not None else backend} and put it on PATH"
    )


#: Where a coding agent's CLI lands when it is installed, besides wherever `PATH` names. A flow
#: is not always started from a shell somebody set up: a notebook kernel, a service, the
#: launcher of a runtime platform each hand their child the `PATH` they were given, and one
#: that is missing the directory an installer wrote to would make an agent that is installed
#: read as one that is not. Looked in after `PATH`, so whatever somebody put in front stays in
#: front, and only for a name -- a command given as a path is that path or nothing.
_INSTALLED_AT = (
    "~/.local/bin",  # where an installer run as a person puts it
    "/usr/local/bin",  # and where one run as root does
    "/opt/homebrew/bin",  # homebrew on apple silicon, which a bare login shell misses
    "/usr/bin",
    "/bin",
)


def program(command: str) -> str | None:
    """The program a backend's command runs, as the path to actually spawn.

    Args:
      command: What the CLI is installed as -- `codex` -- or a path to it.

    Returns:
      The program to run, and None where there is none: a name `PATH` does not have and no
      installer left anywhere this looks is a backend that is not installed here.
    """
    if os.sep in command:
        return command if _runnable(Path(command)) else None
    return shutil.which(command) or elsewhere(command)


def elsewhere(command: str) -> str | None:
    """Where a CLI is installed, for a command this machine's `PATH` does not name.

    Args:
      command: What the CLI is installed as.

    Returns:
      The path to run instead, and None for a command `PATH` already names -- which is run by
      the name it was written with, exactly as it always was -- and for one nothing has
      installed anywhere this looks.
    """
    if os.sep in command or shutil.which(command) is not None:
        return None
    return next(
        (
            str(at)
            for directory in _INSTALLED_AT
            if _runnable(at := Path(directory).expanduser() / command)
        ),
        None,
    )


def _runnable(path: Path) -> bool:
    """Whether that path is a program this machine would run."""
    return path.is_file() and os.access(path, os.X_OK)


def read(spec: str) -> tuple[str, Profile, str, str, str]:
    """Reads one `-a` into the place it fills, the backend to drive, what at, and as whom.

    One agent, though `-a` takes a list of them: whoever holds the line splits it on the
    commas and reads each piece here, so that a line naming three agents and mistyping one is
    answered about the one it got wrong rather than about all three.

    Args:
      spec: `[NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]`. NAME is the place the agent fills, which is
        a field of the tuple of agents the flow declares; a line that leaves it off fills the
        flow's places in the order it takes them. The CLI may name a provider after an `@`, as
        `claude@deepseek/MODEL:EFFORT`, which is the account that agent's turns run as.

    Returns:
      The place it fills -- "" where the line named none -- the backend, the model, the
      effort, and the provider, which is "" for an agent that runs as whoever is at this
      machine already runs its CLI.

    Raises:
      ValueError: If it is not that or names no backend there is. What it says is what a
        command line reports after the agent it could not read.
    """
    name, written, rest = spec.partition("=")
    name, spec = (name.strip(), rest) if written else ("", spec)
    if written and not name.isidentifier():
        raise ValueError(
            f"{name!r} is not a place a flow could declare: what is written before `=` is a "
            "field of the tuple of agents the flow declares, so it is a Python identifier"
        )
    # After the name and before anything else: a comma here is a list nobody split, and
    # reading one would quietly make a model out of every agent after the first.
    if "," in spec:
        raise ValueError(
            "expected one agent: a `,` separates several, each read on its own"
        )
    # Read from both ends: a model may hold slashes of its own -- Kimi Code's and opencode's
    # are `provider/id` -- and colons -- MiniMax Code's are `custom_provider:name/id` --
    # while a CLI and an effort never do. So the effort is what follows the last `:` only
    # where that is spelled as one, and left off it is no rung at all.
    from hmz.coganchor.spelling import parted

    backend, _, said = spec.partition("/")
    model, effort = parted(said)
    # The account, if one was named: a CLI is never spelled with an `@` in it, so the two are
    # told apart wherever the agent was written -- `-a`, a settings file, an interface. An
    # `@` with nothing after it is a line to correct rather than a line saying nothing: it
    # was typed to name an account, and running as whoever is at this machine is not that.
    backend, at, provider = backend.partition("@")
    if at and not provider.strip():
        raise ValueError(
            "expected an account after @, as in claude@deepseek/MODEL:EFFORT"
        )
    profile = named(backend.strip())
    if profile is None or not model.strip():
        raise ValueError("expected [NAME=]CLI[@PROVIDER]/MODEL[:EFFORT]")
    # `auto` is the written form of no rung at all, and this is where it stops being written:
    # everything downstream reads the absence as "", which is what every driver already knows
    # to say nothing about. So is an effort left off, and one that is empty rather than
    # absent -- what a spec round-tripped through a settings file may come back as: the
    # layers that keep a run written down carry the agent as the string they were given.
    rung = effort.strip()
    return name, profile, model.strip(), "" if rung == AUTO else rung, provider.strip()
