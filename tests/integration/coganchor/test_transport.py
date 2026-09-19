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
import os
import shlex
import shutil
import subprocess
import sys
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
    kept = [
        candidate
        for candidate in PYTHON_CANDIDATES
        if candidate.startswith("/") and os.access(candidate, os.X_OK)
    ]
    if not kept:
        pytest.skip(
            "this machine keeps no interpreter at any of the absolute candidates"
        )
    empty = tmp_path / "empty"
    empty.mkdir()

    said = "import sys; print(sys.version_info[0], sys.version_info[1])"
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


def test_an_unchanged_source_tree_is_not_packaged_a_second_time(tmp_path: Path) -> None:
    """The archive already built for this tree is the one a session takes.

    Building it is the expensive part of reaching a target, and it is a function of the
    source alone -- so an unchanged tree has nothing to build.
    """
    destination = tmp_path / "coganchor.pyz"
    build_bundle(destination)
    first = destination.stat()

    build_bundle(destination)

    again = destination.stat()
    assert (again.st_ino, again.st_mtime_ns) == (first.st_ino, first.st_mtime_ns)


def test_a_changed_source_tree_is_packaged_again(tmp_path: Path) -> None:
    """The stamp beside it says which tree the archive was made from, and only that."""
    destination = tmp_path / "coganchor.pyz"
    build_bundle(destination)
    stamp = destination.with_suffix(".stamp")
    assert stamp.exists()

    stamp.write_text("a tree this was not built from\n")
    build_bundle(destination)

    assert stamp.read_text().strip() != "a tree this was not built from"


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


def test_the_archive_is_installed_where_a_home_with_a_space_in_it_says(
    tmp_path: Path,
) -> None:
    """The install line names the archive four times, and the far side expands every one."""
    home = tmp_path / "my home"
    home.mkdir()
    where = f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz"

    installing = transport._INSTALL.format(file=where)
    ran = subprocess.run(
        ["/bin/sh", "-c", installing],
        input=b"an archive, near enough",
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home)},
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    landed = home / ".cache" / "humanize" / "humanize-0123456789abcdef.pyz"
    assert landed.read_bytes() == b"an archive, near enough"
    assert not list(landed.parent.glob("*.part")), (
        "a half-written archive was left behind"
    )


def test_an_archive_already_there_is_left_exactly_where_it_is(tmp_path: Path) -> None:
    """A copy already there is the same bytes, and may be the one a live session is reading.

    The archive is named by what is in it, so a second push would write the same file over a
    path something else may be importing from.
    """
    home = tmp_path / "home"
    cache = home / ".cache" / "humanize"
    cache.mkdir(parents=True)
    already = cache / "humanize-0123456789abcdef.pyz"
    already.write_bytes(b"the one that is already here")

    ran = subprocess.run(
        [
            "/bin/sh",
            "-c",
            transport._INSTALL.format(file=f"{REMOTE_CACHE}/{already.name}"),
        ],
        input=b"a second copy of the same thing",
        capture_output=True,
        env={"PATH": os.environ["PATH"], "HOME": str(home)},
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert already.read_bytes() == b"the one that is already here"


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
    where = f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz"
    installing = transport._INSTALL.format(file=where)
    payload = b"an archive, near enough" * 4096

    def pushed(_which: int) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["/bin/sh", "-c", installing],
            input=payload,
            capture_output=True,
            env={"PATH": os.environ["PATH"], "HOME": str(home)},
            check=False,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pushing:
        done = list(pushing.map(pushed, range(16)))

    assert [one.returncode for one in done] == [0] * 16, [
        one.stderr.decode() for one in done if one.returncode
    ]
    landed = home / ".cache" / "humanize" / "humanize-0123456789abcdef.pyz"
    assert landed.read_bytes() == payload
    assert sorted(one.name for one in landed.parent.iterdir()) == [landed.name]
