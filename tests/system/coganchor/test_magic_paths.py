"""Paths that reach a file through ``/proc`` rather than through the directories it is under.

Every modern coding CLI writes a file the atomic way -- open the directory, create a
temporary beneath it, rename it over the real name -- and several of them spell "beneath it"
as ``/proc/self/fd/<n>/name`` rather than as an ``*at`` call taking the descriptor. Claude
Code 2.1.272 does it on every ``Write`` and every ``Edit``, from whichever of its threads is
free, and falls back to ``/proc/<pid>/fd/<n>`` where ``self`` will not do.

The kernel reaches the same file either way. A supervisor matching the workspace by its
characters does not: ``/proc/self/fd/19/greeting.txt`` begins with nothing the workspace is
named with, so the create and the rename used to pass unexamined, the file landed in the
mirror, nothing carried it to the target -- and the agent, reading back through the plain
name, reported success. Two of the real-agent tests in
:mod:`tests.system.coganchor.test_agents` are exactly that, and these pin the behaviour
without needing a CLI, an account or a network -- though they do need this kernel to trace.

The first half drives the whole supervisor, with an interpreter doing what the CLIs do; the
second is the resolution on its own, against this process's own descriptors.
"""

from __future__ import annotations

import errno
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.supervising import MACHINE, PROVIDER, WITHOUT_BINDINGS, cred, traced

if (
    WITHOUT_BINDINGS
):  # what is imported below is the binding itself, so it is asked first
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor.linux import procfs
from hmz.coganchor.linux.procfs import resolve_magic

if TYPE_CHECKING:
    from tests.coganchor.fixtures import Anchorage


def dance(directory: str, name: str, content: str, whose: str = "self") -> str:
    """A program that writes one file the way the CLIs write one, and reads it back.

    Args:
      directory: The directory to write in, as this machine spells it.
      name: What to call the file.
      content: What to put in it.
      whose: Which spelling of the process to reach the descriptor through -- `self`, or the
        id written out, which is the fallback spelling in the same bundles.

    Returns:
      The program, as a `-c` argument.
    """
    owner = "'self'" if whose == "self" else "os.getpid()"
    return (
        "import os\n"
        f"held = os.open({directory!r}, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)\n"
        f"under = '/proc/%s/fd/%d' % ({owner}, held)\n"
        f"scratch = under + '/{name}.tmp'\n"
        "handle = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL"
        " | os.O_NOFOLLOW, 0o666)\n"
        f"os.write(handle, {content!r}.encode())\n"
        "os.close(handle)\n"
        f"os.rename(scratch, under + '/{name}')\n"
        f"print(open(under + '/{name}').read(), end='')\n"
    )


@pytest.mark.parametrize("whose", ["self", "written out"])
def test_a_file_written_through_a_descriptor_reaches_the_target(
    anchorage: Anchorage, whose: str
) -> None:
    """The defect itself: the create and the rename are the target's, however they are spelled."""
    program = dance(
        str(anchorage.mirror), "greeting.txt", "hello from the agent\n", whose
    )

    result = anchorage.run("python3", "-c", program)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello from the agent\n"
    assert anchorage.target_text("greeting.txt") == "hello from the agent\n"


def test_an_edit_through_a_descriptor_replaces_what_the_target_holds(
    anchorage: Anchorage,
) -> None:
    """The other failing case, and the one whose signature is an asymmetry.

    Before the links were followed this left the new content in the mirror and the old
    content on the target, which is worse than either alone: the agent read its own write
    back and believed it, and the file it was asked to change never changed.
    """
    anchorage.seed({"version.txt": "version = 1.0.0\n"})

    result = anchorage.run(
        "python3",
        "-c",
        dance(str(anchorage.mirror), "version.txt", "version = 2.0.0\n"),
    )

    assert result.returncode == 0, result.stderr
    assert anchorage.target_text("version.txt") == "version = 2.0.0\n"


def test_a_doubled_separator_reaches_the_target_too(anchorage: Anchorage) -> None:
    """The same defect without a descriptor: one extra slash, and the prefix matched nothing.

    The workspace half of it, which is silent data loss rather than a wrong account -- the
    write landed in the mirror at a path no layout claimed and was swept from under it later.
    """
    script = (
        f"handle = open('/{anchorage.mirror}/slashed.txt', 'w')\n"
        "handle.write('through two separators\\n')\n"
        "handle.close()\n"
    )

    result = anchorage.run("python3", "-c", script)

    assert result.returncode == 0, result.stderr
    assert anchorage.target_text("slashed.txt") == "through two separators\n"


def test_a_descriptor_outside_the_workspace_is_not_a_way_into_it(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A resolved path is held to the prefix rules exactly as a literal one is.

    The defect is that writes escaped outward; a resolution in front of those rules is
    exactly where the opposite would live, so the descriptor is pointed somewhere that is
    this machine's own and the file must stay there -- not be claimed for the target, and
    not be pushed anywhere.
    """
    outside = tmp_path / "outside"
    outside.mkdir()

    result = anchorage.run(
        "python3", "-c", dance(str(outside), "local.txt", "this machine's own\n")
    )

    assert result.returncode == 0, result.stderr
    assert (outside / "local.txt").read_text() == "this machine's own\n"
    assert not (anchorage.target / "local.txt").exists()
    assert not (anchorage.mirror / "local.txt").exists()


def test_a_descriptor_that_is_not_there_fails_rather_than_passing_through(
    anchorage: Anchorage,
) -> None:
    """An unresolvable descriptor is refused, which is what the kernel does with one too.

    Letting it past is the one answer that is not available: a path nobody can resolve is a
    path nobody can hold against the workspace, and the call would then run against whatever
    the descriptor turns out to name.
    """
    script = (
        "import os\n"
        "try:\n"
        "    os.open('/proc/self/fd/4095/sneaked.txt',"
        " os.O_WRONLY | os.O_CREAT, 0o666)\n"
        "except OSError as exc:\n"
        "    print(exc.errno)\n"
    )

    result = anchorage.run("python3", "-c", script)

    assert result.stdout.strip() == str(errno.ENOENT), result.stderr
    assert not (anchorage.target / "sneaked.txt").exists()


def test_a_step_out_of_a_descriptor_lands_where_the_kernel_lands(
    anchorage: Anchorage,
) -> None:
    """`..` after a link is the directory above the *file*, not above `/proc/self/fd`.

    Collapsing it first -- which is what tidying a path before following its links does --
    would make this `/proc/self/fd/stepped.txt` and mirror a directory that is not there,
    while the kernel wrote the file in the workspace with nothing forwarding it.
    """
    anchorage.seed({"sub/marker.txt": "here\n"})

    script = (
        "import os\n"
        f"held = os.open({str(anchorage.mirror / 'sub')!r},"
        " os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)\n"
        "under = '/proc/self/fd/%d/..' % held\n"
        "handle = os.open(under + '/stepped.txt', os.O_WRONLY | os.O_CREAT, 0o666)\n"
        "os.write(handle, b'one level up\\n')\n"
        "os.close(handle)\n"
    )

    result = anchorage.run("python3", "-c", script)

    assert result.returncode == 0, result.stderr
    assert anchorage.target_text("stepped.txt") == "one level up\n"


def reaching(parent: str, below: str) -> str:
    """A program that reads one file through a descriptor on a directory *above* it.

    The descriptor has to be taken somewhere a redirect does not name, or the swap would
    already have been applied to the `open` that made it and the file it points at would be
    the provider's -- which is the answer this is trying not to be given for free.

    Args:
      parent: The directory to hold open, which nothing answers.
      below: What to name beneath it, which is the path a redirect does answer.

    Returns:
      The program, as a `-c` argument.
    """
    return (
        "import os\n"
        f"held = os.open({parent!r}, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)\n"
        f"print(open('/proc/self/fd/%d/{below}' % held).read().strip())\n"
    )


@pytest.mark.timeout(60)
def test_an_anchored_credential_is_answered_through_a_descriptor_too(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    """A path answered with another must be answered however the syscall spells it.

    This is the half of the defect that is not about the workspace at all. A turn runs as an
    account by having the credential it names answered with the provider's copy; a name that
    reaches the same file through a descriptor used to arrive after the rule that would have
    answered it, so the turn read whoever is signed in at this machine and ran as them.
    """
    named = tmp_path / "home" / ".claude" / ".credentials.json"
    named.parent.mkdir(parents=True)
    named.write_text(MACHINE)
    instead = tmp_path / "provider" / "home" / ".credentials.json"
    instead.parent.mkdir(parents=True)
    instead.write_text(PROVIDER)

    result = anchorage.run(
        "python3",
        "-c",
        reaching(str(tmp_path / "home"), ".claude/.credentials.json"),
        redirects=((str(named), str(instead)),),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == PROVIDER


@traced
def test_a_chain_of_descriptors_is_refused_rather_than_answered_with_nothing(
    tmp_path: Path,
) -> None:
    """A path this cannot resolve fails the call; it is never let through unanswered.

    Spelled through more descriptors than anyone follows, so that nothing can resolve it --
    which a process can arrange on purpose. Letting such a call run is how a turn reads the
    account of whoever is signed in at this machine, so it is cancelled instead, exactly as a
    path that cannot be planted is.
    """
    named, instead = _two_accounts(tmp_path)
    script = (
        "import os\n"
        "links = os.open('/proc/self/fd', os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)\n"
        f"home = os.open({str(tmp_path / 'home')!r},"
        " os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)\n"
        "far = '/proc/self/fd/' + '/'.join([str(links)] * 45)\n"
        "try:\n"
        "    print(open(far + '/%d/.claude/.credentials.json' % home).read())\n"
        "except OSError as exc:\n"
        "    print('refused', exc.errno)\n"
    )

    done = cred([f"--map={named}={instead}", "--", "python3", "-c", script])

    assert MACHINE not in done.stdout, done.stdout
    # The errno a cancelled call is given, rather than the `ELOOP` the kernel would have
    # answered with had the call been let through to find out.
    assert done.stdout.strip() == f"refused {errno.EIO}", done.stderr


@traced
def test_a_doubled_separator_does_not_get_past_the_answering_either(
    tmp_path: Path,
) -> None:
    """One extra slash used to be the whole of a bypass, and it is the same defect.

    `os.path.normpath` leaves exactly two leading separators alone, so the path this names
    matched no entry in the table while the kernel opened the file at this machine.
    """
    named, instead = _two_accounts(tmp_path)

    done = cred(
        [
            f"--map={named}={instead}",
            "--",
            "python3",
            "-c",
            f"print(open('/{named}/.credentials.json').read())",
        ]
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == PROVIDER


def _two_accounts(tmp_path: Path) -> tuple[Path, Path]:
    """The store at this machine and the provider's copy of it, each holding its own token."""
    named = tmp_path / "home" / ".claude"
    named.mkdir(parents=True)
    (named / ".credentials.json").write_text(MACHINE)
    instead = tmp_path / "provider"
    instead.mkdir()
    (instead / ".credentials.json").write_text(PROVIDER)
    return named, instead


@traced
def test_a_redirected_run_answers_through_a_descriptor_too(tmp_path: Path) -> None:
    """The same, for a turn run under a provider without being anchored.

    Two supervisors read paths out of a tracee and hold them against a table, and a hole in
    either is the same account read by the same CLI: Claude Code opens the directory its
    store is in and names the file beneath it, which is this exactly.
    """
    named, instead = _two_accounts(tmp_path)

    done = cred(
        [
            f"--map={named}={instead}",
            "--",
            "python3",
            "-c",
            reaching(str(tmp_path / "home"), ".claude/.credentials.json"),
        ]
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == PROVIDER


# --------------------------------------------------------------- the resolution alone


def test_a_path_with_no_proc_in_it_is_handed_straight_back() -> None:
    """The answer for every path but a handful in a session, and it must cost nothing."""
    named = "/srv/project/src/main.py"

    assert resolve_magic(os.getpid(), named) is named


@pytest.mark.parametrize("whose", ["self", "thread-self", "written out"])
def test_every_spelling_of_the_process_reaches_the_same_descriptor(
    tmp_path: Path, whose: str
) -> None:
    """`self` means the tracee, and a number written out means whoever it names.

    The threads of one of these CLIs share a descriptor table, so a thread naming the thread
    group's id means its own descriptor -- which is the fallback spelling in Claude Code's own
    bundle, and would resolve against the supervisor if `self` were read as this process.
    """
    held = os.open(tmp_path, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    owner = str(os.getpid()) if whose == "written out" else whose
    try:
        settled = resolve_magic(os.getpid(), f"/proc/{owner}/fd/{held}/leaf.txt")
    finally:
        os.close(held)

    assert settled == f"{tmp_path}/leaf.txt"


def test_self_is_the_thread_group_and_thread_self_is_the_thread() -> None:
    """Procfs makes the two different, and a thread is where the difference shows.

    `/proc/self` is answered with the thread group, so a thread naming it gets the leader's
    descriptors. Almost every thread shares them -- `pthread_create` passes `CLONE_FILES` --
    but nothing makes it, and a thread cloned without it has a table of its own. Reading
    `self` as the stopped thread would then resolve a credential against a descriptor the
    kernel was never going to use, which is the one shape of this a hostile turn could still
    have arranged.
    """
    held = os.open("/", os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    seen: dict[str, object] = {}

    def inside() -> None:
        tid = threading.get_native_id()
        seen["tid"] = tid
        seen["group"] = procfs._thread_group(tid)
        seen["self"] = resolve_magic(tid, f"/proc/self/fd/{held}/leaf.txt")
        seen["thread"] = resolve_magic(tid, f"/proc/thread-self/fd/{held}/leaf.txt")

    thread = threading.Thread(target=inside)
    thread.start()
    thread.join()
    os.close(held)

    assert seen["tid"] != os.getpid()  # or the case this is about does not arise
    assert seen["group"] == os.getpid()
    # This interpreter's threads do share a table, so both spellings land on the same file.
    # What the assertion above pins is that they got there by different ids.
    assert seen["self"] == "/leaf.txt"
    assert seen["thread"] == "/leaf.txt"


def test_a_descriptor_reached_one_thread_down_resolves_too(tmp_path: Path) -> None:
    """`/proc/<pid>/task/<tid>/fd/<n>` is the same descriptor by a longer name."""
    held = os.open(tmp_path, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    named = f"/proc/self/task/{os.getpid()}/fd/{held}/leaf.txt"
    try:
        settled = resolve_magic(os.getpid(), named)
    finally:
        os.close(held)

    assert settled == f"{tmp_path}/leaf.txt"


def test_a_step_above_a_descriptor_is_taken_from_where_it_points(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "sub"
    nested.mkdir()
    held = os.open(nested, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    try:
        settled = resolve_magic(os.getpid(), f"/proc/self/fd/{held}/../beside.txt")
    finally:
        os.close(held)

    assert settled == f"{tmp_path}/beside.txt"


@pytest.mark.parametrize(
    "spelling", ["//proc/self/fd", "/./proc/self/fd", "/proc/./self/fd"]
)
def test_an_untidy_spelling_is_followed_all_the_same(
    tmp_path: Path, spelling: str
) -> None:
    """A rule that only looked at tidy paths would be dodged by adding a separator.

    The kernel reads `//proc/self/fd/<n>/x` and `/proc/self/fd/<n>/x` as the same file, so
    anything that told them apart would be a way round the whole of this.
    """
    held = os.open(tmp_path, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    try:
        settled = resolve_magic(os.getpid(), f"{spelling}/{held}/leaf.txt")
    finally:
        os.close(held)

    assert settled == f"{tmp_path}/leaf.txt"


def test_a_name_under_proc_that_is_not_a_link_is_left_alone() -> None:
    """`/proc/self/stat` is a file to read, not a descriptor to follow."""
    assert resolve_magic(os.getpid(), "/proc/self/stat") == "/proc/self/stat"


def test_the_root_and_the_working_directory_are_followed_too(tmp_path: Path) -> None:
    """The other two links a path can carry below it, and the same way round the rules.

    `root` is the loud one: for a process nobody has confined it is `/`, so
    `/proc/self/root/<the workspace>/file` names a workspace file while beginning with
    nothing the workspace is named with.
    """
    here = Path.cwd()

    assert resolve_magic(os.getpid(), f"/proc/self/root{tmp_path}/x") == f"{tmp_path}/x"
    assert resolve_magic(os.getpid(), "/proc/self/cwd/x") == str(here / "x")


def test_a_descriptor_that_is_not_a_file_of_this_machine_is_left_alone() -> None:
    """A pipe has no path, so there is nothing to hold against the workspace.

    Reading the link back gives `pipe:[...]`, which is not a path and must not be treated as
    one: the call runs against the spelling the process gave, which is what opens the pipe.
    """
    read, write = os.pipe()
    named = f"/proc/self/fd/{read}"
    try:
        assert resolve_magic(os.getpid(), named) == named
    finally:
        os.close(read)
        os.close(write)


def test_a_descriptor_whose_file_has_been_unlinked_is_left_alone(
    tmp_path: Path,
) -> None:
    """`readlink` answers `<path> (deleted)`, and a real file may be named that way.

    So the suffix is not trimmed off and the descriptor is left to the kernel: the name is
    gone, nothing can be reached under it, and inventing a path would have this machine
    mirror a file the target never had.
    """
    doomed = tmp_path / "doomed.txt"
    doomed.write_text("briefly\n")
    held = os.open(doomed, os.O_RDONLY)
    doomed.unlink()
    named = f"/proc/self/fd/{held}"
    try:
        assert resolve_magic(os.getpid(), named) == named
    finally:
        os.close(held)


def test_a_descriptor_that_is_not_there_is_refused(tmp_path: Path) -> None:
    """Fail closed: an unresolved descriptor is a path that could be anywhere.

    Including the credentials a session answers with another, which is why the answer is an
    errno rather than a shrug. The kernel is about to refuse the call for the same reason.
    """
    held = os.open(tmp_path, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    os.close(held)

    with pytest.raises(OSError) as raised:  # noqa: PT011 -- the errno below is the match
        resolve_magic(os.getpid(), f"/proc/self/fd/{held}/leaf.txt")

    assert raised.value.errno == errno.ENOENT


def chained(held: int, hops: int) -> str:
    """A path crossing ``hops`` magic links, by naming a descriptor on the descriptors."""
    return "/proc/self/fd/" + "/".join([str(held)] * hops)


def test_a_chain_the_kernel_would_follow_is_followed(tmp_path: Path) -> None:
    """The bound is the kernel's, so nothing refuses a path the call itself would have served.

    A lower one would not merely be untidy: an unresolved path fails the syscall, so a tracee
    wanting one nobody examined would only have to spell it through a descriptor more than
    the bound allows.
    """
    links = os.open("/proc/self/fd", os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    leaf = os.open(tmp_path, os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    try:
        settled = resolve_magic(os.getpid(), f"{chained(links, 30)}/{leaf}/leaf.txt")
    finally:
        os.close(leaf)
        os.close(links)

    assert settled == f"{tmp_path}/leaf.txt"


def test_a_descriptor_pointing_at_the_descriptors_is_not_followed_for_ever() -> None:
    """One resolution can uncover another, so the chain is bounded the way the kernel bounds it."""
    held = os.open("/proc/self/fd", os.O_RDONLY | os.O_PATH | os.O_DIRECTORY)
    try:
        with pytest.raises(OSError) as raised:  # noqa: PT011 -- the errno below is the match
            resolve_magic(os.getpid(), chained(held, 45))
    finally:
        os.close(held)

    assert raised.value.errno == errno.ELOOP


def test_the_image_a_process_re_execs_itself_as_is_followed(tmp_path: Path) -> None:
    """`/proc/self/exe` names a program rather than carrying a path below it.

    Left alone, a runtime re-execing itself that way would have the supervisor hand the
    target the literal `/proc/self/exe`, which on that machine names the serving helper's own
    image -- so the agent's re-exec would silently become a different program.
    """
    assert resolve_magic(os.getpid(), "/proc/self/exe") == os.path.realpath(
        sys.executable
    )
    assert resolve_magic(os.getpid(), f"/proc/{os.getpid()}/exe").startswith("/")
    assert str(
        tmp_path
    )  # the fixture is what keeps this out of somebody's own directory


@pytest.mark.parametrize("named", ["//srv/a project/x", "///srv/a project/x"])
def test_a_doubled_separator_is_collapsed_the_way_the_kernel_collapses_it(
    named: str,
) -> None:
    """The same defect by another route, and the reason this settles more than `/proc`.

    Linux reads `//srv/...` as `/srv/...`; `os.path.normpath` is required by POSIX to leave
    exactly two leading separators alone. So a name spelled with one extra slash used to match
    no prefix this layer holds paths against -- not the workspace, and not a credential.
    """
    assert resolve_magic(os.getpid(), named) == "/srv/a project/x"
