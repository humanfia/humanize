"""The pictures of `docs/tutorials/nightly-in-ci.md`: a flow run every night by a CI job.

What a job's steps print, taken at a terminal as the page has its reader try them first: the
line the job runs, kept in `ci/nightly.sh`; that line refused for want of a budget; the run's
events read with `jq`; the epic exported as one archive; and what the backup target holds
afterwards. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_nightly_in_ci.py`.

A runner has no flow installed, so the line names a release of `ralph_loop` by its
repository. That repository is staged here, made up on this machine where the suite tells git
GitHub is, so that the line on the page is the line that runs. The backup target is a bare
repository in the made-up home.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import tomlkit

from hmz import config
from tests.integration.conftest import FLOWS
from tests.system.docs import shots

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-nightly-in-ci"

#: The task the job sets every night, as `TASK.md` says it.
_TASK = "Do the first open item in TODO.md.\n"

#: The line the job runs, as the page has it kept in the repository.
_NIGHTLY = """\
#!/bin/sh
# What the nightly job runs. More options of `hmz exec` go after it: a budget is required.
hmz exec \\
  -f 'git+https://github.com/humanfia/ralph-loop-flow@v0.1.0#ralph_loop' \\
  -a agent=claude/claude-opus-4-1:high \\
  "$@" "$(cat TASK.md)"
"""

#: The script that exports the epic the job just ran, as the page has it.
_EXPORT = '''\
"""Export the newest epic of this directory as one .hmzepic file."""

import os

from hmz.sdk import Hmz

epics = Hmz().epics
archive, manifest = epics.bundled(
    epics.all()[-1], output=os.environ.get("RUNNER_TEMP", ".")
)
print(f"{archive.name}: {len(manifest['sessions'])} sessions")
'''

#: What the agent says it did, a round at a time.
_ROUNDS = [
    "Did 'discount codes at checkout': WELCOME10 takes 10% off. 4 passed.",
    "Did 'say so when the cart is empty': charge() refuses one. 5 passed.",
    "Read TODO.md again: every item is ticked, and 5 tests pass.",
]

#: A budget that ends the stand-in's loop after its second round.
_SMALL = "budget.output_tokens=200"


def _git(at: Path, *argv: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Humanfia",
            "-c",
            "user.email=flows@example.com",
            *argv,
        ],
        cwd=at,
        check=True,
        capture_output=True,
    )


def _released(tmp_path: Path) -> None:
    """Stages the release of `ralph_loop` the line names: its repository, tagged.

    The suite tells git that `https://github.com/` is `<tmp_path>/no-github/`.
    """
    repo = tmp_path / "no-github" / "humanfia" / "ralph-loop-flow"
    shutil.copytree(
        FLOWS / "ralph_loop",
        repo / "ralph_loop",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "ralph_loop")
    _git(repo, "tag", "v0.1.0")


def _project(world: World) -> None:
    """Commits to the project what the page has its reader commit, and scripts the agent."""
    (world.workspace / "TASK.md").write_text(_TASK)
    (world.workspace / "TODO.md").write_text(
        "- [ ] discount codes at checkout\n- [ ] say so when the cart is empty\n"
    )
    ci = world.workspace / "ci"
    ci.mkdir()
    (ci / "nightly.sh").write_text(_NIGHTLY)
    (ci / "export.py").write_text(_EXPORT)
    _git(world.workspace, "add", "-A")
    _git(world.workspace, "commit", "-q", "-m", "Add the nightly job")
    world.says(
        {
            "TODO.md": {
                "text": _ROUNDS,
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                        "result": "4 passed in 0.12s",
                        "takes": 0.6,
                    }
                ],
                "after": 0.6,
            }
        }
    )


def _target(world: World) -> None:
    """Writes a backup target into settings, as the job's step does: a bare repository."""
    held = world.home / "epics.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(held)], check=True)
    settings = config() / "settings.toml"
    assert not settings.exists(), "the made-up home has settings of its own to keep"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        tomlkit.dumps(
            {
                "backup": {
                    "targets": [
                        {"name": "nightly", "url": str(held), "policies": ["end"]}
                    ]
                }
            }
        )
    )


def test_the_line_is_tried_by_hand(world: World, tmp_path: Path) -> None:
    _released(tmp_path)
    _project(world)
    reel = shots.Reel(f"{_PAGE}-try")
    reel.cli(
        ["sh", "ci/nightly.sh", "-p", _SMALL],
        rows=15,
        hold=4.0,
        frames=16,
    )
    reel.save()


def test_a_line_with_no_budget_is_refused(world: World, tmp_path: Path) -> None:
    _released(tmp_path)
    _project(world)
    shots.cli(["sh", "ci/nightly.sh"], f"{_PAGE}-refused")


def test_the_run_is_read_exported_and_backed_up(world: World, tmp_path: Path) -> None:
    _released(tmp_path)
    _project(world)
    _target(world)
    # The job's own step: the events to a file outside the checkout, the epic backed up.
    kept = Path(tempfile.mkdtemp(prefix="runner-", dir=world.home))
    with (kept / "events.ndjson").open("wb") as events:
        ran = subprocess.run(
            [
                "sh",
                "ci/nightly.sh",
                "-p",
                _SMALL,
                "--backup",
                "nightly",
                "--json",
            ],
            cwd=world.workspace,
            stdout=events,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
        )
    assert ran.returncode == 0, ran.stderr
    shots.cli(
        ["jq", "-r", "[.kind, .text] | @tsv", "events.ndjson"],
        f"{_PAGE}-events",
        cwd=kept,
    )
    shots.cli(["python", "ci/export.py"], f"{_PAGE}-export")
    shots.cli(["hmz", "backup", "--list"], f"{_PAGE}-backup", columns=120)
