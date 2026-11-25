"""The accounts an agent is run as, and how each harness is signed in to (`accounts.*`).

Nothing here carries the value of anything an account sets: a daemon answers the names of an
account's variables and never what they hold, so an account can be listed, corrected and
copied by a program that is never handed a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from . import Family

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["Account", "Accounts", "Ask", "Backend", "Listing", "Way"]


@dataclass(frozen=True)
class Account:
    """One account: a named set of credentials for one harness."""

    cli: str
    """The harness it is for."""
    name: str
    """What it is called; `""` for what the daemon's machine is signed in to already."""
    way: str
    """The way of signing in it was made by, or `""`."""
    sets: tuple[str, ...]
    """The names of the variables it sets -- never their values."""
    made: str
    """When it was made, as an ISO 8601 time; `""` for the machine's own sign-in."""
    models: tuple[str, ...]
    """The models its harness last said it runs as this account."""
    asked: str
    """When the harness was last asked what it runs, as an ISO 8601 time; `""` if never."""
    serves: tuple[str, ...]
    """The other harnesses it could be copied to."""


@dataclass(frozen=True)
class Ask:
    """One thing a way of signing in asks for."""

    env: str
    """The variable the answer is kept as, which is what an answer is given by."""
    about: str
    """What it is."""
    secret: bool
    """Whether the answer is a credential, to be kept off a screen and a command line."""
    fixed: str
    """What it is where it is left unanswered, or `""` where it must be answered."""


@dataclass(frozen=True)
class Way:
    """One way of signing in to a harness."""

    name: str
    about: str
    group: str
    """The gateway it goes through, or `""`."""
    terminal: bool
    """Whether it runs the harness's own sign-in, which only a terminal can make."""
    asks: tuple[Ask, ...]


@dataclass(frozen=True)
class Backend:
    """One harness, and the ways it can be signed in to."""

    cli: str
    ways: tuple[Way, ...]
    wants: str
    """The line that installs what its gateway ways need, or `""` where nothing is missing."""

    def way(self, name: str) -> Way | None:
        """Its way of that name, or None."""
        return next((one for one in self.ways if one.name == name), None)


@dataclass(frozen=True)
class Listing:
    """Every account a daemon holds, and how each of its harnesses can be signed in to."""

    gateway: str
    """What the gateway is called."""
    accounts: tuple[Account, ...]
    backends: tuple[Backend, ...]
    said: dict[str, Any]
    """Everything the daemon answered."""

    def account(self, cli: str, name: str) -> Account | None:
        """The account of a harness called that, or None."""
        return next(
            (one for one in self.accounts if (one.cli, one.name) == (cli, name)), None
        )

    def backend(self, cli: str) -> Backend | None:
        """The harness called that, or None."""
        return next((one for one in self.backends if one.cli == cli), None)


def _listing(said: Mapping[str, Any]) -> Listing:
    return Listing(
        gateway=str(said.get("gateway", "")),
        accounts=tuple(
            Account(
                cli=str(one["cli"]),
                name=str(one["name"]),
                way=str(one.get("way") or ""),
                sets=tuple(one.get("sets") or ()),
                made=str(one.get("made") or ""),
                models=tuple(one.get("models") or ()),
                asked=str(one.get("asked") or ""),
                serves=tuple(one.get("serves") or ()),
            )
            for one in said.get("accounts") or ()
        ),
        backends=tuple(
            Backend(
                cli=str(one["cli"]),
                ways=tuple(
                    Way(
                        name=str(way["name"]),
                        about=str(way.get("about") or ""),
                        group=str(way.get("group") or ""),
                        terminal=bool(way.get("terminal")),
                        asks=tuple(
                            Ask(
                                env=str(ask["env"]),
                                about=str(ask.get("about") or ""),
                                secret=bool(ask.get("secret")),
                                fixed=str(ask.get("fixed") or ""),
                            )
                            for ask in way.get("asks") or ()
                        ),
                    )
                    for way in one.get("ways") or ()
                ),
                wants=str(one.get("wants") or ""),
            )
            for one in said.get("backends") or ()
        ),
        said=dict(said),
    )


class Accounts(Family):
    """The accounts an agent is run as."""

    METHODS: ClassVar = (
        "accounts.list",
        "accounts.create",
        "accounts.correct",
        "accounts.remove",
        "accounts.models",
        "accounts.copy",
    )

    def list(self) -> Listing:
        """Every account, and the ways each harness can be signed in to."""
        return _listing(self._call("accounts.list"))

    def create(
        self,
        cli: str,
        name: str,
        way: str,
        answers: Mapping[str, str] | None = None,
        *,
        idem: str | None = None,
    ) -> Listing:
        """Makes an account out of the answers to a way of signing in.

        Args:
          cli: The harness it is for.
          name: What it is to be called.
          way: The way it is made by, one whose `terminal` is false.
          answers: What each variable the way asks is, by the variable's name.
          idem: The key this is done once under.

        Returns:
          Every account as they are afterwards.

        Raises:
          hmz.sdk.Refused: 400 for an unknown way, one that needs a terminal, a variable left
            unanswered or an invalid name; 409 for a name taken.
        """
        return _listing(
            self._call(
                "accounts.create",
                cli=cli,
                name=name,
                way=way,
                answers=dict(answers or {}),
                idem=idem,
            )
        )

    def correct(
        self,
        cli: str,
        name: str,
        answers: Mapping[str, str] | None = None,
        *,
        idem: str | None = None,
    ) -> Listing:
        """Writes an account again, every variable not answered keeping what it was.

        Args:
          cli: The harness it is for.
          name: What it is called.
          answers: What changes, by the variable's name.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 404 for no such account; 400 for a variable its way does not ask,
            and for a way that needs a terminal.
        """
        return _listing(
            self._call(
                "accounts.correct",
                cli=cli,
                name=name,
                answers=dict(answers or {}),
                idem=idem,
            )
        )

    def remove(self, cli: str, name: str, *, idem: str | None = None) -> Listing:
        """Removes an account, credentials and all.

        Raises:
          hmz.sdk.Refused: 404 for no such account.
        """
        return _listing(self._call("accounts.remove", cli=cli, name=name, idem=idem))

    def models(
        self,
        cli: str,
        name: str = "",
        *,
        idem: str | None = None,
        wait: float | None = None,
    ) -> Listing:
        """Asks a harness what it runs as an account, and keeps what it says.

        Args:
          cli: The harness.
          name: The account; `""` for what the daemon's machine is signed in to already.
          idem: The key this is done once under.
          wait: How many seconds the harness is waited for, None for as long as it takes.

        Returns:
          Every account as they are afterwards, that one's `models` what was just said --
          where the daemon lists it: the machine's own sign-in is listed only for a harness
          that has accounts.

        Raises:
          hmz.sdk.Refused: 404 for no such account; 502 for a harness that will not answer.
        """
        return _listing(
            self._call("accounts.models", cli=cli, name=name, idem=idem, wait=wait)
        )

    def copy(
        self, cli: str, name: str, into: str, *, idem: str | None = None
    ) -> Listing:
        """Copies an account to another harness its credentials can run.

        Args:
          cli: The harness it is for.
          name: What it is called.
          into: The harness it is copied to, one of its `serves`.
          idem: The key this is done once under.

        Raises:
          hmz.sdk.Refused: 404 for no such account; 400 for a copy that cannot be made.
        """
        return _listing(
            self._call("accounts.copy", cli=cli, name=name, into=into, idem=idem)
        )
