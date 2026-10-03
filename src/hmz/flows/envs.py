"""The environments a flow's agents work in, and what a flow may ask of each.

An environment is a working directory on a machine: this one, one reached over ssh, or a
container started for it on a docker daemon or a docker swarm. A flow declares the
environments it needs as an :class:`EnvCollection`, one role apiece, and says what it will do
in each by the mixins the role's type carries::

    class Repo(Env, ShellEnvMixin, FilesEnvMixin, GitWorktreeEnvMixin): ...

    class Envs(EnvCollection):
        repo: Repo

The flow is then handed an environment that can do exactly that and nothing more: a
`derive_worktree` on an environment declared without :class:`GitWorktreeEnvMixin` raises
:class:`~hmz.flows.errors.CapabilityNotGranted` whatever the machine could do.

Everything here is a protocol for a type checker. What a flow is handed at run time is the
runtime's own object, shaped however is fastest, and answers to these structurally.
"""

from __future__ import annotations

from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self, SupportsIndex, overload

from typing_extensions import ReadOnly, TypedDict

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator, Sequence

__all__ = [
    "BashEnvMixin",
    "CPUEnvMixin",
    "Env",
    "EnvBackendKind",
    "EnvCollection",
    "FilesEnvMixin",
    "GPUEnvMixin",
    "GitEnvMixin",
    "GitWorktreeEnvMixin",
    "ImageEnvMixin",
    "LocalEnv",
    "MemoryEnvMixin",
    "RewindableEnvMixin",
    "ScratchDirEnvMixin",
    "SequenceNotStr",
    "ShellEnvMixin",
    "TemporaryClonedDirEnvMixin",
]


class EnvBackendKind(StrEnum):
    """Where an environment's machine is, and so how it is reached."""

    #: This machine.
    LOCAL = auto()
    #: A machine reached over ssh, by a host name `ssh` itself resolves.
    SSH = auto()
    #: A container of its own, on a docker daemon a runtime names.
    DOCKER = auto()
    #: A container of its own, as the one task of a service on a docker swarm a runtime
    #: names, on whichever node the swarm placed it.
    SWARM = auto()


class SequenceNotStr[T](Protocol):
    """A sequence that is not a `str`.

    What an argv is typed as. A `str` is a `Sequence[str]` of its characters, so a script
    passed where an argv was meant would type-check as one; `str.__contains__` takes only a
    `str`, which is what keeps it from matching the `__contains__` here. Lists and tuples of
    strings match.
    """

    @overload
    def __getitem__(self, index: SupportsIndex, /) -> T: ...
    @overload
    def __getitem__(self, index: slice, /) -> Sequence[T]: ...
    def __contains__(self, value: object, /) -> bool: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[T]: ...
    def index(self, value: Any, start: int = 0, stop: int = ..., /) -> int: ...
    def count(self, value: Any, /) -> int: ...
    def __reversed__(self) -> Iterator[T]: ...


class Env(Protocol):
    """A working directory on a machine, as a flow is handed one."""

    @property
    def available(self) -> bool:
        """Whether the machine can be reached and the workdir exists, as last seen."""
        ...

    @property
    def backend(self) -> EnvBackendKind:
        """Which kind of machine it is on."""
        ...

    @property
    def provider(self) -> str:
        """Which machine of that kind: the ssh host, the docker or swarm runtime, or "" here."""
        ...

    @property
    def role(self) -> str:
        """The role it fills in the flow's `EnvCollection`."""
        ...

    @property
    def workdir(self) -> pathlib.PurePosixPath:
        """The directory on that machine that commands run in and relative paths are under.

        Absolute, or `~/...` for one under the home directory of whoever ssh logs in as.
        """
        ...

    async def derive_subdir(
        self,
        *,
        subdir: pathlib.PurePosixPath | str,
    ) -> Env:
        """An environment on the same machine whose workdir is a directory under this one's.

        Args:
          subdir: Where, relative to this workdir. It is created if missing.

        Returns:
          The environment, filling this one's role and granted what this one was.

        Raises:
          ValueError: If `subdir` is absolute or climbs out of this workdir.
          EnvError: If the directory could not be made.
        """
        ...


class LocalEnv(Env, Protocol):
    """An environment the runtime fills itself: the workspace the run was started in.

    A role typed as this, or as a subclass of it with mixins, needs no `-e`, and naming one
    with `-e` is an error. A flow calling another passes its own, or leaves it out and the
    callee gets the run's.
    """


class EnvCollection(TypedDict, extra_items=ReadOnly[Env]):
    """The environments a flow declares, one key per role.

    Subclassed to declare roles, each typed as `Env` or a subclass carrying mixins::

        class Envs(EnvCollection):
            repo: Repo
            scratch: NotRequired[Env]

    A `NotRequired` role may be left out by whoever runs the flow.
    """


# ------------------------------------------------------------------------------ the mixins


class CPUEnvMixin(Protocol):
    """Declares how many CPUs an environment must have for the role.

    Attributes:
      _cpu_count: The fewest logical CPUs the machine may have.
    """

    _cpu_count: ClassVar[int] = 1


class MemoryEnvMixin(Protocol):
    """Declares how much memory an environment must have for the role.

    Attributes:
      _memory: The least memory the machine may have, in bytes.
    """

    _memory: ClassVar[int] = 0


class GPUEnvMixin(Protocol):
    """Declares how many GPUs, and how large, an environment must have for the role.

    Attributes:
      _gpu_count: The fewest GPUs the machine may have.
      _gpu_memory: The least memory each of them may have, in bytes.
    """

    _gpu_count: ClassVar[int] = 1
    _gpu_memory: ClassVar[int] = 0


class ImageEnvMixin(Protocol):
    """Declares what a container for the role is started from.

    Said of a docker or swarm environment only: one on this machine or over ssh is the
    machine it is, and the image says nothing of it. The image needs `/bin/sh` and a Python
    of at least 3.12, which is what reaches into it; nothing else of humanize is put there,
    an sshd least of all.

    Attributes:
      _image: The image, as `docker run` takes it; "" for the provider's own, or
        `python:3.12-slim` where that says none either.
    """

    _image: ClassVar[str] = ""


class ShellEnvMixin(Protocol):
    """Lets a flow run programs in the environment."""

    async def exec(
        self,
        argv: SequenceNotStr[str],
        *,
        timeout: float = 0,  # noqa: ASYNC109 -- the spec's, and the environment's to enforce
    ) -> tuple[int, str, str]:
        """Runs one program in the workdir, and waits for it.

        Args:
          argv: The program and its arguments, run as they are with no shell between.
          timeout: How many seconds it may take, or 0 for as long as it takes.

        Returns:
          Its exit status, then what it wrote on stdout and on stderr, decoded as UTF-8.

        Raises:
          EnvCommandTimeout: If it ran past `timeout`. It has been killed.
          EnvError: If it could not be started at all.
        """
        ...


class BashEnvMixin(ShellEnvMixin, Protocol):
    """Lets a flow run bash scripts in the environment as well as programs.

    `exec` takes a string as well as an argv, and runs it as `bash -c` would, in the workdir:
    same timeout, same answer, same exceptions as a program. A string `exec` on an
    environment declared without this is a type error, and raises
    :class:`~hmz.flows.errors.CapabilityNotGranted` at run time.

    The machine needs `bash` on its PATH: a flow declaring this for an environment on one
    without is refused, with :class:`~hmz.flows.errors.CapabilityMissing`, before anything
    runs.
    """

    @overload
    async def exec(
        self,
        argv: SequenceNotStr[str],
        *,
        timeout: float = 0,  # noqa: ASYNC109 -- the spec's, and the environment's to enforce
    ) -> tuple[int, str, str]: ...

    @overload
    async def exec(
        self,
        script: str,
        *,
        timeout: float = 0,  # noqa: ASYNC109 -- the spec's, and the environment's to enforce
    ) -> tuple[int, str, str]: ...


class FilesEnvMixin(Protocol):
    """Lets a flow read and write files in the environment."""

    async def read(self, path: str) -> bytes:
        """What a file holds.

        Args:
          path: The file, relative to the workdir or absolute.

        Returns:
          Its bytes.

        Raises:
          EnvFileNotFound: If there is no such file.
          EnvPermissionDenied: If it may not be read.
        """
        ...

    async def write(self, path: str, data: bytes) -> None:
        """Writes a file whole, making the directories above it as needed.

        Args:
          path: The file, relative to the workdir or absolute.
          data: What it holds afterwards.

        Raises:
          EnvPermissionDenied: If it may not be written.
        """
        ...


class GitWorktreeEnvMixin(Protocol):
    """Lets a flow check out more worktrees of the git repository the workdir is in.

    The machine needs `git` on its PATH: a flow declaring this for an environment on one
    without is refused, with :class:`~hmz.flows.errors.CapabilityMissing`, before anything
    runs.
    """

    async def derive_worktree(
        self,
        *,
        ref: str | None = None,
        dir: pathlib.PurePosixPath | str | None = None,  # noqa: A002 -- the spec's name
    ) -> Self:
        """An environment at a new worktree of this repository.

        Args:
          ref: What to check out, detached; None for what this workdir has checked out.
          dir: Where, relative to the workdir or absolute; None for a fresh directory the
            runtime picks.

        Returns:
          The environment, granted what this one was.

        Raises:
          WorktreeError: If the workdir is not in a repository, the ref is not known, or the
            directory is taken.
        """
        ...


class RewindableEnvMixin(Protocol):
    """What an environment that can be put back as it was offers: snapshots, and rewinding.

    An interface only. No environment is granted it by itself: a role declares a mixin that
    implements it -- :class:`GitEnvMixin` -- and code that only snapshots and rewinds, whatever
    does it underneath, is written against this.
    """

    async def snapshot(self, name: str | None = None) -> str:
        """Records the workdir as it is now, to rewind to later.

        Args:
          name: What to keep it under, replacing a snapshot already kept under it; None for a
            name of its own.

        Returns:
          The ref to hand :meth:`rewind` to put the workdir back as it is now.
        """
        ...

    async def rewind(self, ref: str) -> None:
        """Puts the workdir back as a ref has it, removing whatever the ref does not have.

        Args:
          ref: What :meth:`snapshot` answered, or another ref the environment knows.
        """
        ...

    async def snapshots(self) -> list[str]:
        """The refs of the snapshots kept, the oldest first."""
        ...


class GitEnvMixin(RewindableEnvMixin, Protocol):
    """Snapshots and rewinds the git worktree the workdir is in, with git.

    The machine needs `git` on its PATH: a flow declaring this for an environment on one
    without is refused, with :class:`~hmz.flows.errors.CapabilityMissing`, before anything
    runs. The workdir needs to be in a git worktree when these are called; it is not made
    one.

    What is snapshotted and rewound is the whole worktree -- a workdir below its top along
    with the rest of it -- and the commit it has checked out and its index. Files git ignores
    are neither recorded nor removed, and nor is a `.hmz/` at its top, where a workspace keeps
    its own flows -- or a `.humanize/`, what that was called before.
    """

    async def snapshot(self, name: str | None = None) -> str:
        """Records the worktree as it is now, untracked files included, as a commit.

        Nothing the worktree has checked out moves, and neither its index nor its files are
        touched: the commit is kept under `refs/hmz/snapshots/<name>` in the repository,
        until something removes it.

        Args:
          name: What to keep it under, as git would take a ref's name, replacing a snapshot
            already kept under it; None for a name of its own.

        Returns:
          `refs/hmz/snapshots/<name>`.

        Raises:
          RewindError: If the workdir is not in a git worktree, the name is not one git can
            keep a ref under, or git would not.
        """
        ...

    async def rewind(self, ref: str) -> None:
        """Puts the worktree back as a ref has it, as `git reset --hard` and `git clean` would.

        A snapshot is put back whole: the commit that was checked out when it was taken, the
        index as it was, and its files -- untracked ones as untracked. Any other commit git
        knows by that ref -- a commit, `HEAD~1`, a branch, a tag -- is checked out with its
        files, the index matching them. Either way the branch checked out, if any, is moved
        to that commit rather than another checked out, files that are neither in it nor
        ignored are removed -- repositories cloned inside too -- and a merge, cherry-pick or
        revert under way is forgotten. What is checked out moves last, so a rewind git
        refuses partway leaves it where it was.

        Args:
          ref: What :meth:`snapshot` answered, or any ref git knows of a commit.

        Raises:
          RewindError: If the workdir is not in a git worktree, git knows no commit by that
            ref, `HEAD` is detached and the snapshot was taken before the first commit, or
            git would not.
        """
        ...

    async def snapshots(self) -> list[str]:
        """The refs of the snapshots kept in the repository, the oldest first.

        Oldest to the second: ones taken within the same second are in the order of their
        names, which for names of the runtime's own is the order they were taken in. Every
        worktree of the repository shares them.

        Raises:
          RewindError: If the workdir is not in a git worktree.
        """
        ...


class TemporaryClonedDirEnvMixin(Protocol):
    """Lets a flow work in a throwaway copy of the workdir.

    Served on every machine, with nothing but `sh` and `cp`. The one copy that needs `git`
    as well is of a workdir that is a linked git worktree, which is made a repository of its
    own: on a machine without git that copy fails, with
    :class:`~hmz.flows.errors.EnvError`, rather than the flow being refused for it.
    """

    async def derive_temp_clone(self, id: str) -> Self:  # noqa: A002 -- the spec's name
        """An environment at a temporary copy of the workdir.

        The copy is removed when the flow that made it ends, unless that flow is resumable
        -- then it is kept so the run can pick it up again.

        Args:
          id: Which copy. The same id from the same environment is the same copy, made once.

        Returns:
          The environment, granted what this one was.

        Raises:
          TempCloneBusy: If another environment holds the copy under that id.
        """
        ...

    async def destroy_temp_clone(self, id: str) -> None:  # noqa: A002 -- the spec's name
        """Removes a copy now, and frees its id. Removing one that is not there is a no-op.

        Args:
          id: Which copy.
        """
        ...


class ScratchDirEnvMixin(Protocol):
    """Lets a flow keep files in an empty directory beside the workdir, on the same machine."""

    async def derive_scratch(self, id: str) -> Self:  # noqa: A002 -- the spec's name
        """An environment at a scratch directory, empty when first made.

        It is removed when the flow that made it ends, unless that flow is resumable.

        Args:
          id: Which one. The same id is the same directory.

        Returns:
          The environment, granted what this one was.

        Raises:
          ScratchError: If it could not be made.
        """
        ...

    async def destroy_scratch(self, id: str) -> None:  # noqa: A002 -- the spec's name
        """Removes a scratch directory now. Removing one that is not there is a no-op.

        Args:
          id: Which one.

        Raises:
          ScratchError: If it could not be removed.
        """
        ...
