"""Reaching a target, as far as it can be reached without a second machine.

A target spelling is parsed here, the zipapp a target is bootstrapped from is built and run
here, the interpreter that runs it is looked for here, and the line ssh would carry is read
here -- every one of them against this repo's own code, a subprocess of this interpreter, or
a string, so all of it is offline and none of it asks the kernel for anything.

The two ways of reaching a target that cannot be stood in for -- a real ssh to localhost,
and a real seccomp filter with a real ptrace supervisor under it -- are in
`tests/system/coganchor/test_transport.py` instead.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import transport
from hmz.coganchor.proto import path_within
from hmz.coganchor.statepaths import COMMON_STATE_PATHS
from hmz.coganchor.transport import (
    MINIMUM_PYTHON,
    PYTHON_CANDIDATES,
    REMOTE_CACHE,
    REMOTE_MIRRORS,
    Road,
    Target,
    build_bundle,
    python_command,
    serve_line,
)
from tests.coganchor.fixtures import checkout

if TYPE_CHECKING:
    from pathlib import Path


def test_target_parsing() -> None:
    assert Target.parse("ssh://build-box") == Target("ssh", host="build-box")
    assert Target.parse("ssh://user@box:2222") == Target(
        "ssh", host="user@box", port=2222
    )
    assert Target.parse("docker://janus-9f2c") == Target("docker", host="janus-9f2c")
    assert Target.parse("tcp://10.0.0.5:7777") == Target(
        "tcp", host="10.0.0.5", port=7777
    )
    assert Target.parse("local") == Target("local")
    assert Target.parse("local:/srv/project") == Target("local", path="/srv/project")
    assert Target.parse("peer://cafe@broker:9001") == Target(
        "peer", host="broker", port=9001, path="cafe"
    )


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "box",
        "http://box",
        "docker://",
        "docker://box@",
        "docker://@unix:///run/docker.sock",
        "docker://box@nowhere",
        "tcp://box",
        "tcp://box:none",
        "peer://broker:9001",
        "peer://cafe@broker",
        "peer://@broker:9001",
    ],
)
def test_malformed_targets_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError, match=r"target|expected"):
        Target.parse(spec)


def test_target_descriptions_round_trip() -> None:
    for spec in (
        "ssh://build-box",
        "docker://janus-9f2c",
        "docker://janus-9f2c@ssh://me@gpu-box:2222",
        "docker://janus-9f2c@tcp://10.0.0.5:2376?tls=/etc/docker-certs",
        "tcp://10.0.0.5:7777",
        "peer://cafe1234@broker.example:9001",
        "local:/srv/project",
    ):
        assert Target.parse(spec).describe() == spec


def test_bundle_is_self_contained(tmp_path: Path) -> None:
    """The target needs nothing but python3, so the bundle must run alone."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    assert bundle.stat().st_size > 0

    result = subprocess.run(
        [sys.executable, str(bundle), "internal", "anchor", "serve", "--help"],
        capture_output=True,
        text=True,
        # An empty PYTHONPATH proves nothing is being imported from this repo.
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        cwd="/",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--export" in result.stdout


def test_the_bundle_carries_nothing_that_drives_an_agent(tmp_path: Path) -> None:
    """A target runs `anchor serve` and never a coding agent, so it is sent none of them.

    The package holds both halves now -- the anchor, and everything humanize knows about
    driving a CLI -- and only the first is any use on a target. Left in, the second is
    megabytes crossing a link and being cached at the far end for a line that cannot reach
    it. Asserted on what the archive holds rather than on what a run of it loads, which is
    already asked next door: a module nothing imports still ships.
    """
    bundle = build_bundle(tmp_path / "coganchor.pyz")

    carried = zipfile.ZipFile(bundle).namelist()

    assert not [
        name
        for name in carried
        if any(f"coganchor/{one}" in name for one in transport.DRIVING)
    ]
    # And the half that is any use is all there: an exclusion that took the wire with it
    # would leave a bundle that cannot start, which the run next door would report as a
    # failure to load rather than as a bundle missing a file.
    assert any(name.endswith("coganchor/proto.py") for name in carried)
    assert any("coganchor/serve/" in name for name in carried)


def test_the_bundle_is_the_same_wherever_it_is_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The target caches it by digest, so nothing but the source may change it."""
    here = build_bundle(tmp_path / "here.pyz").read_bytes()
    umask = os.umask(0o002)
    try:
        # A zip entry holds local wall-clock time, so west of UTC is where a bundle stamped with
        # a fixed instant both forks the digest and falls out of the range a zip can hold. The
        # umask is the other thing a second developer would differ in.
        monkeypatch.setenv("TZ", "America/Los_Angeles")
        time.tzset()
        elsewhere = build_bundle(tmp_path / "elsewhere.pyz").read_bytes()
    finally:
        os.umask(umask)
        monkeypatch.undo()
        time.tzset()
    assert here == elsewhere


def test_bundle_reports_failure_in_its_exit_status(tmp_path: Path) -> None:
    """A target that cannot start must not look like a clean exit."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    target = tmp_path / "target"
    target.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(bundle),
            "internal",
            "anchor",
            "serve",
            "--export",
            f"/project:{target}",
            "--listen",
            "bad",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, "the bundle swallowed a start-up failure"
    assert "malformed listen address" in result.stderr


def test_a_target_keeping_its_python_off_the_path_is_found_it_anyway(
    tmp_path: Path,
) -> None:
    """An interpreter that is not on the ``PATH`` is still an interpreter.

    macOS ships no ``python3`` on the ``PATH`` a remote command is given, so looking there
    and stopping is a target that fails for want of something it has. Driven with an empty
    ``PATH`` for real, which is the same target as a Mac's: the bare names answer to nothing
    and only the places one is kept are left.
    """
    said = "import sys; print(sys.version_info[0], sys.version_info[1])"
    kept = [
        candidate
        for candidate in PYTHON_CANDIDATES
        if candidate.startswith("/")
        and os.access(candidate, os.X_OK)
        # One too old is passed over, as the bundle passes it over: Ubuntu 22.04's own
        # /usr/bin/python3 is 3.10, and is no interpreter to find.
        and tuple(
            int(part)
            for part in subprocess.run(
                [candidate, "-c", said], capture_output=True, text=True, check=False
            ).stdout.split()
        )
        >= MINIMUM_PYTHON
    ]
    if not kept:
        pytest.skip(
            "this machine keeps no interpreter new enough at any of the absolute candidates"
        )
    empty = tmp_path / "empty"
    empty.mkdir()

    result = subprocess.run(
        python_command(["-c", said]),
        capture_output=True,
        text=True,
        env={"PATH": str(empty)},
        check=False,
    )

    assert result.returncode == 0, result.stderr
    found = tuple(int(part) for part in result.stdout.split())
    assert found >= MINIMUM_PYTHON, "an interpreter too old for the bundle was taken"


def test_a_target_with_no_python_at_all_says_what_it_looked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The answer is to install one of them, so the list is the message."""
    monkeypatch.setattr(
        "hmz.coganchor.transport.PYTHON_CANDIDATES", ("python3-not-here", "/no/python3")
    )

    result = subprocess.run(
        python_command(["-c", "pass"]), capture_output=True, text=True, check=False
    )

    assert result.returncode != 0
    assert "python3-not-here" in result.stderr
    assert "/no/python3" in result.stderr


def test_the_line_ssh_carries_survives_the_shell_that_reads_it_there() -> None:
    """Every word of it, however it was spelled, which is the one rule the road has.

    ``ssh`` hands the far side one string and a login shell reads it before anything runs.
    So the whole line is quoted, word by word, and what comes out the other end is the argv
    that went in -- a workspace path holding a space included. What the far shell is
    *supposed* to expand does not travel as a word at all: it is written into the script,
    where the ``sh`` running it is the one that reads it.
    """
    road = Road.to(Target.parse("ssh://build-box"))

    line = road.line(["/bin/echo", "/a b", "--export=/c d:/e f"])

    assert line[0] == "ssh"
    assert line[-2] == "build-box"
    words = shlex.split(line[-1])
    assert words == ["exec", "/bin/echo", "/a b", "--export=/c d:/e f"]


def test_the_home_the_bundle_lives_under_is_expanded_where_it_names_a_directory() -> (
    None
):
    """On the target, by the ``sh`` inside the line -- not here, and not by a login shell.

    A ``~`` or a ``$HOME`` that crossed as a word of its own would arrive quoted, and name a
    directory of that name under wherever the session began. So the archive's path is written
    into the script that looks for an interpreter, which is the one part of the line the far
    side's ``sh`` reads as text rather than takes as an argument.
    """
    bundle = f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz"

    argv = python_command(["internal", "anchor", "serve", "--stdio"], bundle=bundle)

    assert argv[:2] == ["/bin/sh", "-c"]
    assert f'exec "$py" "{bundle}" "$@"' in argv[2], (
        "the archive is not run by the script"
    )
    assert bundle not in argv[3:], (
        "the archive crossed as a word and will not be expanded"
    )
    assert argv[3:] == ["humanize", "internal", "anchor", "serve", "--stdio"]


def test_a_variable_the_far_side_sets_is_set_before_the_interpreter_is_looked_for() -> (
    None
):
    """And a directory made of it, since nothing over there is going to make one first."""
    argv = python_command(
        ["internal", "anchor"],
        bundle="/tmp/humanize/humanize-abc.pyz",
        setting=(("HUMANIZE_SHADOW", "$HOME/.cache/humanize/mirror-abc"),),
    )

    script = argv[2]
    assert script.index("HUMANIZE_SHADOW=") < script.index("for py in")
    assert 'mkdir -p "$HUMANIZE_SHADOW"' in script
    assert "export HUMANIZE_SHADOW" in script


def test_nothing_is_started_on_the_far_side_of_a_target_somebody_else_started() -> None:
    """A listening target and a meeting are found rather than run, so there is no road to one."""
    for spec in ("tcp://10.0.0.5:7777", "peer://cafe@broker:9001"):
        with pytest.raises(ValueError, match="nothing is started"):
            Road.to(Target.parse(spec))


def test_a_serving_half_sent_to_a_meeting_is_told_which_one() -> None:
    """Which is the whole of the difference between the two ways one is left answering."""
    from hmz.coganchor.rendezvous import Meeting

    over_a_pipe = serve_line(Target.parse("local"), ["/project"])
    at_a_meeting = serve_line(
        Target.parse("local"), ["/project"], meeting=Meeting("cafe", "broker", 9001)
    )

    assert "--stdio" in over_a_pipe
    assert "--peer" not in over_a_pipe
    assert at_a_meeting[at_a_meeting.index("--peer") + 1] == "cafe@broker:9001"
    assert "--stdio" not in at_a_meeting


def test_a_mirror_is_named_for_what_it_mirrors_and_kept_beside_the_archive() -> None:
    """So that the second turn against a workspace finds the files already there."""
    road = Road.to(Target.parse("ssh://build-box"))

    assert road.mirror("0123456789abcdef") == f"{REMOTE_MIRRORS}/0123456789abcdef"
    assert road.mirror("one") != road.mirror("another")


def test_a_mirror_is_never_under_the_state_directory_a_turn_keeps_to_itself() -> None:
    """Which would be a mirror no path was ever translated through.

    `~/.cache/humanize` is humanize's own state on whichever machine the agent runs on, and a
    supervised turn answers everything under it from *that* machine rather than from the
    target. A mirror below it is one the router never maps to the workspace, so the agent
    finds an empty directory and every command it runs lands somewhere else. The two are kept
    apart by being siblings, which `path_within` reads as two places rather than one.
    """
    road = Road.to(Target.parse("ssh://build-box"))

    for state in COMMON_STATE_PATHS:
        under = state.replace("~", "$HOME")
        assert path_within(road.mirror("0123456789abcdef"), under) is None, under


@pytest.fixture
def private_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary directory of this test's own, and a process that has built nothing in it.

    The archives this user builds live under the temporary directory, so pointing that
    somewhere new is a machine on which no archive was ever built.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(transport, "_bundle_held", None)
    monkeypatch.setattr(transport, "_stamp_held", None)
    return tmp_path


def test_an_unchanged_source_tree_is_not_packaged_a_second_time(
    private_temp: Path,
) -> None:
    """The archive already built for this tree is the one a session takes.

    Building it is the expensive part of reaching a target, and it is a function of the
    source alone -- so an unchanged tree has nothing to build, even for a process that has
    not built it itself.
    """
    first, digest = transport.bundled()
    made = first.stat().st_ino
    transport._bundle_held = None

    again, same = transport.bundled()

    assert (again, same) == (first, digest)
    assert again.stat().st_ino == made, "the archive was built a second time"


def test_this_users_archives_are_kept_where_nobody_else_can_write(
    private_temp: Path,
) -> None:
    archive, digest = transport.bundled()

    assert archive.parent == private_temp / f"humanize-{os.getuid()}"
    assert archive.name == f"humanize-{digest}.pyz"
    assert stat.S_IMODE(archive.parent.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(archive.stat().st_mode) & 0o077 == 0
    assert hashlib.sha256(archive.read_bytes()).hexdigest()[:16] == digest


def test_a_directory_somebody_else_could_write_is_not_trusted_with_the_archive(
    private_temp: Path,
) -> None:
    """In a temporary directory everybody shares, it could hold an archive of theirs."""
    planted = private_temp / f"humanize-{os.getuid()}"
    planted.mkdir(mode=0o700)
    planted.chmod(0o777)

    with pytest.raises(PermissionError, match="only this user can write"):
        transport.bundled()


def test_two_checkouts_never_ship_one_anothers_archive(private_temp: Path) -> None:
    """Each archive is named by what is in it, so two trees are two archives side by side.

    One shared path was what let a run from one checkout ship the other's code: whichever
    built last had the file, and a run that had worked out its digest before then pushed the
    other's bytes under its own name.
    """
    one = checkout(private_temp / "one", "one")
    two = checkout(private_temp / "two", "two")

    first = transport._built(one, transport._stamped(one))
    second = transport._built(two, transport._stamped(two))
    # And the first again, which a run of it alternating with the other's would ask for.
    third = transport._built(one, transport._stamped(one))

    assert first[1] != second[1]
    assert first[0] != second[0]
    assert third == first
    for (archive, digest), marker in ((first, "one"), (second, "two")):
        assert hashlib.sha256(archive.read_bytes()).hexdigest()[:16] == digest
        held = zipfile.ZipFile(archive).read("hmz/coganchor/checkout.py").decode()
        assert held == f"MARKER = {marker!r}\n"


def test_a_changed_source_tree_is_packaged_again(private_temp: Path) -> None:
    """A tree whose files have changed is another stamp, and so another build."""
    tree = checkout(private_temp / "tree", "before")
    before = transport._built(tree, transport._stamped(tree))

    (tree / "checkout.py").write_text("MARKER = 'after, and longer'\n")
    after = transport._built(tree, transport._stamped(tree))

    assert after[1] != before[1]
    held = zipfile.ZipFile(after[0]).read("hmz/coganchor/checkout.py")
    assert held == b"MARKER = 'after, and longer'\n"


def test_a_change_to_the_command_line_is_packaged_too(private_temp: Path) -> None:
    """It ships in the archive beside the anchor, so an edit to it is an edit to the archive."""
    tree = checkout(private_temp / "tree", "same")
    before = transport._stamped(tree)

    (tree.parent / "cli" / "__init__.py").write_text("# edited\n", "utf-8")

    assert transport._stamped(tree) != before


def test_an_archive_a_run_is_holding_is_built_again_once_swept(
    private_temp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run idle longer than the sweep waits finds its archive gone, and does not die of it."""
    archive, digest = transport.bundled()
    archive.unlink()
    monkeypatch.setattr(transport, "_RETOUCH", 0.0)

    again, same = transport.bundled()

    assert (again, same) == (archive, digest)
    assert again.exists()


def test_archives_nobody_has_used_in_a_while_are_swept(private_temp: Path) -> None:
    tree = checkout(private_temp / "tree", "old")
    old, _ = transport._built(tree, transport._stamped(tree))
    lately = old.with_name("humanize-feedfacefeedface.pyz")
    lately.write_bytes(b"used a moment ago")
    long_ago = time.time() - transport._KEPT_FOR - 60
    for stale in old.parent.iterdir():
        if stale != lately:
            os.utime(stale, (long_ago, long_ago))

    # And the one archive every checkout shared, which an earlier humanize kept beside it.
    legacy = old.parent.with_name(f"{old.parent.name}.pyz")
    legacy.write_bytes(b"whichever checkout built last")
    os.utime(legacy, (long_ago, long_ago))

    current, _ = transport.bundled()

    assert current.exists()
    assert lately.exists(), "an archive in use was swept"
    assert not old.exists(), "an archive nobody had used in a while was kept"
    assert not legacy.exists()


def test_a_directory_of_archives_nobody_else_can_write_is_said_as_a_failure_to_install(
    private_temp: Path,
) -> None:
    """Which is what a caller reaching a target is ready for, and names the target."""
    planted = private_temp / f"humanize-{os.getuid()}"
    planted.mkdir(mode=0o700)
    planted.chmod(0o777)

    with pytest.raises(
        ConnectionError, match="could not install humanize on ssh://box"
    ):
        Road.to(Target.parse("ssh://box")).installed()


def test_the_line_ssh_carries_runs_the_archive_when_a_real_shell_reads_it(
    tmp_path: Path,
) -> None:
    """The whole road, less the ssh: composed here, read by a shell, and the bundle runs.

    What `ssh` does with the line is hand it to a login shell on the far side, and everything
    this road has to get right happens in that shell -- the quoting survives it, the `$HOME`
    in the archive's path is expanded *by* it, and the interpreter search runs under it. So
    the line is handed to a real `sh` with a real `HOME` here instead. The only thing left out
    is the network, which is the one part that is not this repository's code.
    """
    # With a space in it, which is the thing a `$HOME` the far side expands has to survive.
    home = tmp_path / "my home"
    cache = home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    archive = cache / "humanize-0123456789abcdef.pyz"
    shutil.copy(build_bundle(), archive)
    # Named as the far side spells it, which is the whole point: a `$HOME` that crossed as a
    # word of its own would be quoted, and name a directory called `$HOME` under wherever the
    # session began.
    carried = Road.to(Target.parse("ssh://build-box")).line(
        python_command(
            ["internal", "anchor", "serve", "--help"],
            bundle=f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz",
        )
    )[-1]

    ran = subprocess.run(
        ["/bin/sh", "-c", carried],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home)},
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert "--export" in ran.stdout, "the archive under $HOME was not the one run"


def test_a_mirror_is_made_on_the_far_side_before_anything_looks_for_an_interpreter(
    tmp_path: Path,
) -> None:
    """Because nothing over there is going to make it, and the harness starts by filling it."""
    home = tmp_path / "home"
    home.mkdir()
    road = Road.to(Target.parse("ssh://build-box"))
    mirror = road.mirror("0123456789abcdef")

    carried = road.line(
        python_command(
            ["-c", "import os; print(os.environ['HUMANIZE_SHADOW'])"],
            setting=(("HUMANIZE_SHADOW", mirror),),
        )
    )[-1]
    ran = subprocess.run(
        ["/bin/sh", "-c", carried],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home)},
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    landed = home / ".cache" / "humanize-mirrors" / "0123456789abcdef"
    assert landed.is_dir(), (
        "the far side was not given the directory it was told to mirror in"
    )
    assert ran.stdout.strip() == str(landed)


def _install(
    home: Path, payload: bytes, *, digest: str = ""
) -> subprocess.CompletedProcess[bytes]:
    """Runs the install line as ssh would carry it, against a home of the test's own.

    Args:
      home: What `$HOME` is over there.
      payload: What arrives on its input.
      digest: What it is sent as, which is the digest of `payload` unless told otherwise.

    Returns:
      What it did.
    """
    digest = digest or hashlib.sha256(payload).hexdigest()[:16]
    carried = Road.to(Target.parse("ssh://build-box")).line(
        transport._installing(REMOTE_CACHE, f"humanize-{digest}.pyz", digest)
    )[-1]
    return subprocess.run(
        ["/bin/sh", "-c", carried],
        input=payload,
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home)},
        check=False,
    )


def _named(payload: bytes) -> str:
    """What an archive holding these bytes is called, here and on every target."""
    return f"humanize-{hashlib.sha256(payload).hexdigest()[:16]}.pyz"


def test_the_archive_is_installed_where_a_home_with_a_space_in_it_says(
    tmp_path: Path,
) -> None:
    """The cache's path crosses with its `$HOME` in it, and the far side expands it."""
    home = tmp_path / "my home"
    home.mkdir()
    payload = b"an archive, near enough"

    ran = _install(home, payload)

    assert ran.returncode == 0, ran.stderr
    landed = home / ".cache" / "humanize" / _named(payload)
    assert landed.read_bytes() == payload
    assert sorted(one.name for one in landed.parent.iterdir()) == [landed.name], (
        "a half-written archive was left behind"
    )


def test_an_archive_already_there_is_left_exactly_where_it_is(tmp_path: Path) -> None:
    """A copy there that answers to its name may be the one a live session is reading.

    The archive is named by what is in it, so a second push would write the same file over a
    path something else may be importing from.
    """
    home = tmp_path / "home"
    payload = b"the one that is already here"
    cache = home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    already = cache / _named(payload)
    already.write_bytes(payload)
    made = already.stat().st_ino

    ran = _install(home, payload)

    assert ran.returncode == 0, ran.stderr
    assert already.stat().st_ino == made


def test_a_copy_that_is_not_what_its_name_says_is_replaced(tmp_path: Path) -> None:
    """A name is only a promise, and a target must never run what it did not promise.

    A push cut short, or a humanize of another checkout that pushed its own bytes under this
    name, leaves a file there that the old install trusted for being there at all -- and
    every later session on that machine would have run it.
    """
    home = tmp_path / "home"
    payload = b"what this checkout built"
    cache = home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    stale = cache / _named(payload)
    stale.write_bytes(b"what another checkout built")

    ran = _install(home, payload)

    assert ran.returncode == 0, ran.stderr
    assert stale.read_bytes() == payload


def test_an_archive_that_arrives_damaged_is_refused(tmp_path: Path) -> None:
    """Better no archive than one cut short in the pipe, cached under a name it is not."""
    home = tmp_path / "home"
    payload = b"the whole archive"

    ran = _install(home, payload[:8], digest=hashlib.sha256(payload).hexdigest()[:16])

    assert ran.returncode != 0
    assert b"are not" in ran.stderr
    cache = home / ".cache" / "humanize"
    assert not cache.exists() or not list(cache.iterdir())


def test_an_install_sweeps_the_archives_nobody_has_used_in_a_while(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    cache = home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    stale = cache / "humanize-0123456789abcdef.pyz"
    stale.write_bytes(b"from a checkout nobody runs any more")
    lately = cache / "humanize-fedcba9876543210.pyz"
    lately.write_bytes(b"from a checkout somebody ran this morning")
    other = cache / "something-else"
    other.write_bytes(b"not an archive")
    long_ago = time.time() - transport._KEPT_FOR - 60
    for old in (stale, other):
        os.utime(old, (long_ago, long_ago))

    ran = _install(home, b"this one")

    assert ran.returncode == 0, ran.stderr
    assert not stale.exists()
    assert lately.exists()
    assert other.exists(), "the sweep took something that was not an archive"


def test_two_sessions_installing_the_archive_at_once_both_succeed(
    tmp_path: Path,
) -> None:
    """Which is the ordinary case rather than the unlucky one: a fleet comes up by the hundred.

    Both write, both rename, and whichever loses replaces a file holding the identical bytes.
    A shared temporary name instead would have the second one find nothing there to move, and
    that session would fail for having been the second to arrive.
    """
    home = tmp_path / "home"
    home.mkdir()
    payload = b"an archive, near enough" * 4096

    def pushed(_which: int) -> subprocess.CompletedProcess[bytes]:
        return _install(home, payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pushing:
        done = list(pushing.map(pushed, range(16)))

    assert [one.returncode for one in done] == [0] * 16, [
        one.stderr.decode() for one in done if one.returncode
    ]
    landed = home / ".cache" / "humanize" / _named(payload)
    assert landed.read_bytes() == payload
    assert sorted(one.name for one in landed.parent.iterdir()) == [landed.name]
