"""A flow's docker environment against a real daemon: a container of its own, and agents in it.

`tests/integration/flows/test_docker_envs.py` runs the driver against a stand-in `docker`, which
is everything but the daemon and the container. This is those two. The image is
`python:3.12-slim`, which has no sshd: everything reaches into the container over `docker exec`.
What is checked is where only a container could have answered -- `/.dockerenv`, which docker puts
in every container and on no host, the container's own hostname, its cgroup's limits, the GPUs
`nvidia-smi` sees in it -- and that the container is gone once the environment is closed.

The daemon is reached as docker's default here, and again as a daemon elsewhere would be: over
TCP through a port of the test's own, and over ssh through an ssh runtime written down with
everything an sshd of the test's own needs. Both are this machine's daemon, so the workdir is
one path on both sides.

With `--run-agents`, a real agent of every CLI installed here is put in a container and asked to
run a command there and write what it said into the workdir -- on the cheapest model each takes,
since that is one command a CLI.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from hmz.coganchor import backends
from hmz.coganchor.machines import gpus_listed, gpus_usable, info, store
from hmz.coganchor.machines.docker import CDI
from hmz.flows import (
    CPUEnvMixin,
    Env,
    EnvCollection,
    FilesEnvMixin,
    GPUEnvMixin,
    HarnessError,
    HarnessKind,
    HarnessRefused,
    HarnessThrottled,
    ImageEnvMixin,
    MemoryEnvMixin,
    ResourceUnmet,
    ShellEnvMixin,
)
from hmz.runtime.flowing.declaring import env_roles
from hmz.runtime.flowing.environments import open_env, probe
from hmz.runtime.flowing.specs import AgentSpec, parse_envs
from hmz.runtime.runner import Runner
from tests.flows.contracts import check_env_driver
from tests.machines.fixtures import IMAGE
from tests.stubs import written

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.runtime.flowing.declaring import EnvRole
    from hmz.runtime.flowing.spi import EnvDriver


class Slim(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = IMAGE


class Full(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12"


class Limited(Env, ShellEnvMixin, CPUEnvMixin, MemoryEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _cpu_count = 2
    _memory = 1 << 30


class OneGPU(Env, ShellEnvMixin, GPUEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _gpu_count = 1


class TwoGPUs(Env, ShellEnvMixin, GPUEnvMixin, ImageEnvMixin):
    _image = IMAGE
    _gpu_count = 2


class Envs(EnvCollection):
    slim: Slim
    full: Full
    limited: Limited
    gpu: OneGPU
    gpus: TwoGPUs


def _role(name: str) -> EnvRole:
    (role,) = [one for one in env_roles(Envs, globals(), {}) if one.name == name]
    return role


def _ours() -> list[str]:
    """Every container this process started that docker still has, running or not."""
    said = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            "label=humanize",
            "--filter",
            f"label=humanize.pid={os.getpid()}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return said.stdout.split()


@pytest.fixture(autouse=True)
def _leaves_no_container() -> Iterator[None]:
    """Every test here takes down what it started: nothing of this process is left running."""
    yield
    left = _ours()
    if left:
        subprocess.run(
            ["docker", "rm", "--force", *left], capture_output=True, check=False
        )
    assert not left, f"containers left behind: {left}"


def _opened(spec: str, role: str) -> EnvDriver:
    (said,) = parse_envs([spec])
    return open_env(said, _role(role))


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=tester@example.com",
            "-c",
            "user.name=tester",
            "-c",
            "commit.gpgsign=false",
            *argv,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _image(name: str) -> None:
    held = subprocess.run(
        ["docker", "image", "inspect", name], capture_output=True, check=False
    )
    if held.returncode:
        pytest.skip(f"needs {name} pulled here")


# ------------------------------------------------------------------------ a container here


@pytest.mark.timeout(300)
async def test_the_contract_holds_in_a_container_with_no_sshd(
    daemon: None, tmp_path: Path
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim=docker{work}", "slim")

    await probe(driver)
    status, out, _ = await driver.exec(
        [
            "sh",
            "-c",
            (
                "hostname; id -u; test -f /.dockerenv && echo inside; "
                "command -v sshd || echo no-sshd"
            ),
        ],
        timeout=60,
    )
    await check_env_driver(driver)

    hostname, uid, inside, sshd = out.split()
    assert status == 0
    assert sshd == "no-sshd", "the image has an sshd, and the test would prove nothing"
    assert (uid, inside) == (str(os.getuid()), "inside")
    assert hostname != os.uname().nodename
    assert (work / "contract" / "deep" / "a.bin").read_bytes() == b"bytes \x00\xff\n"
    assert _ours() == []


@pytest.mark.timeout(300)
async def test_worktrees_are_added_in_a_container_that_has_git(
    daemon: None, tmp_path: Path
) -> None:
    _image("python:3.12")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "file.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    driver = _opened(f"full=docker{repo}", "full")

    await probe(driver)
    await check_env_driver(driver, repo=True)


@pytest.mark.timeout(300)
async def test_what_a_role_declares_is_the_containers_limit(
    daemon: None, tmp_path: Path
) -> None:
    driver = _opened(f"limited=docker{tmp_path}", "limited")
    try:
        await probe(driver)
        status, out, err = await driver.exec(
            ["cat", "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.max"], timeout=60
        )
    finally:
        await driver.close()

    assert status == 0, err
    assert out.split() == ["200000", "100000", str(1 << 30)]
    assert (driver.cpu_count, driver.memory, driver.gpu_count) == (2, 1 << 30, 0)


# ------------------------------------------------------------------------------------ GPUs


def _devices() -> list[object]:
    """What the daemon here lists as its devices, read out of `docker info` as humanize reads it.

    The whole answer rather than `--format '{{json .DiscoveredDevices}}'`: a daemon older than
    that field prints a blank line for it, where the whole answer leaves it out -- and Docker
    28.0, which GitHub's runners have, is one.
    """
    return cast("list[object]", info().get("DiscoveredDevices") or [])


@pytest.fixture
def gpubox(daemon: None) -> str:
    """A runtime handing out this machine's first two GPUs, or a skip where it has not two."""
    devices = _devices()
    listed = gpus_listed(devices)
    if not {"0", "1"} <= set(listed):
        pytest.skip("needs a daemon listing two NVIDIA GPUs by their CDI names")
    usable = gpus_usable("local", IMAGE, devices, seconds=120) or ()
    if len(usable) < 2:
        pytest.skip(f"needs two GPUs that answer, and {len(usable)} of {listed} do")
    name = f"gpubox-{os.getpid()}"
    store.write(store.DockerRuntime(name=name, gpus=("0", "1")))
    return name


@pytest.mark.timeout(300)
async def test_a_role_asking_one_gpu_sees_exactly_one(
    gpubox: str, tmp_path: Path
) -> None:
    driver = _opened(f"gpu=docker@{gpubox}{tmp_path}", "gpu")
    try:
        await probe(driver)
        status, out, err = await driver.exec(["nvidia-smi", "-L"], timeout=60)
    finally:
        await driver.close()

    assert status == 0, err
    assert len(out.strip().splitlines()) == 1, out
    assert (driver.gpu_count, driver.gpu_memory > 0) == (1, True)


@pytest.fixture
def failing(daemon: None) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Docker's default here, where it lists a GPU that does not answer, and what does answer.

    A skip anywhere else: what is tested is a GPU that failed after the daemon's CDI specs
    were written for it -- bound to the driver, listed still, and handed to nobody.
    """
    devices = _devices()
    listed = gpus_listed(devices, CDI)
    usable = gpus_usable("local", IMAGE, devices, seconds=120)
    if not usable or len(usable) >= len(listed):
        pytest.skip(
            f"needs a daemon listing a GPU that does not answer: it lists {listed}, and "
            f"{'nobody could ask which answer' if usable is None else usable} answer"
        )
    name = f"failing-{os.getpid()}"
    store.write(store.DockerRuntime(name=name))
    return name, usable


@pytest.mark.timeout(300)
async def test_a_gpu_that_does_not_answer_is_never_handed_out(
    failing: tuple[str, tuple[tuple[str, str], ...]], tmp_path: Path
) -> None:
    """Every GPU that answers is handed out, by UUID, and then nothing more is."""
    provider, usable = failing
    opened: list[EnvDriver] = []
    seen: list[str] = []
    try:
        for _ in usable:
            driver = _opened(f"gpu=docker@{provider}{tmp_path}", "gpu")
            opened.append(driver)
            await probe(driver)
            status, out, err = await driver.exec(
                ["nvidia-smi", "--query-gpu=uuid", "--format=csv,noheader"], timeout=60
            )
            assert status == 0, err
            seen += out.split()
        assert sorted(seen) == sorted(uuid for _, uuid in usable)
        last = _opened(f"gpu=docker@{provider}{tmp_path}", "gpu")
        opened.append(last)
        with pytest.raises(ResourceUnmet, match="bound but does not answer"):
            await probe(last)
    finally:
        for driver in opened:
            await driver.close()


@pytest.mark.timeout(300)
async def test_more_gpus_than_answer_is_refused_saying_how_many_do(
    failing: tuple[str, tuple[tuple[str, str], ...]], tmp_path: Path
) -> None:
    provider, usable = failing
    asked = len(usable) + 1
    if asked != TwoGPUs._gpu_count:
        pytest.skip(f"asks for two GPUs, and {len(usable)} answer here")
    driver = _opened(f"gpus=docker@{provider}{tmp_path}", "gpus")
    try:
        with pytest.raises(
            ResourceUnmet,
            match=rf"has {len(usable)} of {len(usable)} GPUs free, and 'gpus' asks for "
            rf"2 \({len(usable)} of the \d+ GPUs it lists are usable",
        ):
            await probe(driver)
    finally:
        await driver.close()


#: A flow holding a GPU until it is let go: it writes what `nvidia-smi` sees in its container,
#: named for its task, and waits for `release` to appear in the workdir.
_HOLDS = """
from hmz.flows import AgentCollection, Env, EnvCollection, FlowParams, GPUEnvMixin
from hmz.flows import BashEnvMixin, FilesEnvMixin, ImageEnvMixin, flow


class Box(Env, BashEnvMixin, FilesEnvMixin, GPUEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"
    _gpu_count = 1


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def holds(task, *, agents, envs, params, ctx):
    box = envs["box"]
    status, out, err = await box.exec(["nvidia-smi", "-L"])
    assert status == 0, err
    await box.write(f"{task}.txt", out.encode())
    await box.exec("while [ ! -e release ]; do sleep 0.2; done", timeout=240)
"""


def _hmz(flow: Path, spec: str, task: str, cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-Pm",
            "hmz",
            "exec",
            "-f",
            str(flow),
            "-e",
            spec,
            "-p",
            "budget.cost=1",
            task,
        ],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.mark.timeout(600)
def test_runs_at_once_get_gpus_of_their_own_and_one_too_many_is_refused(
    gpubox: str, tmp_path: Path
) -> None:
    flow = written(tmp_path / "flows", "holds", _HOLDS)
    (Path(tmp_path) / "project").mkdir()
    runs = [
        _hmz(flow, f"box=docker@{gpubox}{tmp_path}", task, tmp_path / "project")
        for task in ("first", "second")
    ]
    try:
        deadline = time.monotonic() + 240
        while not all(
            (tmp_path / f"{one}.txt").exists() for one in ("first", "second")
        ):
            for run in runs:
                if run.poll() is not None:
                    _, err = run.communicate()
                    pytest.fail(f"a run holding a GPU ended: {err}")
            assert time.monotonic() < deadline, "the runs never got their GPUs"
            time.sleep(0.5)

        third = _hmz(
            flow, f"box=docker@{gpubox}{tmp_path}", "third", tmp_path / "project"
        )
        _, refused = third.communicate(timeout=240)
    finally:
        (tmp_path / "release").touch()
        ended = [run.communicate(timeout=240) for run in runs]

    assert [run.returncode for run in runs] == [0, 0], ended
    first, second = (
        (tmp_path / f"{one}.txt").read_text() for one in ("first", "second")
    )
    assert len(first.splitlines()) == len(second.splitlines()) == 1
    assert first != second, "two runs were given one GPU"
    assert third.returncode == 2, refused
    assert f"docker@{gpubox} has 0 of 2 GPUs free, and 'box' asks for 1" in refused
    assert not (tmp_path / "third.txt").exists()
    held = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--quiet",
            "--filter",
            f"label=humanize.provider={gpubox}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert held.stdout.split() == [], "a run left its container behind"


#: A flow holding its container until it is ended from outside: it says it has one, and waits.
_WAITS = """
from hmz.flows import AgentCollection, Env, EnvCollection, FilesEnvMixin, FlowParams
from hmz.flows import ImageEnvMixin, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Envs(EnvCollection):
    box: Box


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def waits(task, *, agents, envs, params, ctx):
    await envs["box"].write("up.txt", b"up")
    await envs["box"].exec(["sleep", "240"], timeout=300)
"""


@pytest.mark.timeout(300)
@pytest.mark.parametrize("ending", [signal.SIGTERM, signal.SIGHUP])
def test_a_run_terminated_mid_run_takes_its_container_down(
    daemon: None, tmp_path: Path, ending: signal.Signals
) -> None:
    """Rather than leave it running until the next run on its runtime finds it."""
    flow = written(tmp_path / "flows", "waits", _WAITS)
    work = tmp_path / "work"
    work.mkdir()
    run = _hmz(flow, f"box=docker{work}", "go", tmp_path)
    try:
        deadline = time.monotonic() + 240
        while not (work / "up.txt").exists():
            assert run.poll() is None, run.communicate()
            assert time.monotonic() < deadline, "the run never had its container"
            time.sleep(0.2)
        held = _of(run.pid)
        run.send_signal(ending)
        _, err = run.communicate(timeout=120)
    finally:
        if run.poll() is None:
            run.kill()
        left = _of(run.pid)
        if left:
            subprocess.run(["docker", "rm", "--force", *left], check=False)

    assert len(held) == 1, held
    assert run.returncode == 128 + ending, err
    assert left == [], "the run left its container behind"


def _of(pid: int) -> list[str]:
    """Every container a process of that pid started that docker still has."""
    said = subprocess.run(
        [
            *("docker", "ps", "--all", "--quiet", "--filter", "label=humanize"),
            *("--filter", f"label=humanize.pid={pid}"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return said.stdout.split()


async def test_a_role_asking_more_gpus_than_there_are_is_refused_before_starting(
    gpubox: str, tmp_path: Path
) -> None:
    class Three(Env, ShellEnvMixin, GPUEnvMixin):
        _gpu_count = 3

    class Many(EnvCollection):
        many: Three

    (role,) = env_roles(Many, {}, {"Three": Three})
    (spec,) = parse_envs([f"many=docker@{gpubox}{tmp_path}"])
    driver = open_env(spec, role)
    try:
        with pytest.raises(ResourceUnmet, match=r"has 2 of 2 GPUs free.*asks for 3"):
            await probe(driver)
    finally:
        await driver.close()
    assert _ours() == []


# ------------------------------------------------------------------------------ snapshots

#: A flow that snapshots its container's workdir, changes it, and rewinds it: to the snapshot,
#: then a commit back. It writes what it found along the way to `seen.json`, which the
#: rewind to the commit leaves alone as the repository ignores it.
_REWINDS = """
import json

from hmz.flows import AgentCollection, Env, EnvCollection, FilesEnvMixin, FlowParams
from hmz.flows import GitEnvMixin, ImageEnvMixin, flow


class Repo(Env, FilesEnvMixin, GitEnvMixin, ImageEnvMixin):
    _image = "IMAGE"


class Envs(EnvCollection):
    repo: Repo


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def rewinds(task, *, agents, envs, params, ctx):
    repo = envs["repo"]
    seen = {}
    ref = await repo.snapshot("before")
    await repo.write("file.txt", b"changed")
    await repo.write("added.txt", b"added")
    await repo.rewind(ref)
    seen["file"] = (await repo.read("file.txt")).decode()
    seen["added"] = await _has(repo, "added.txt")
    await repo.rewind("HEAD~1")
    seen["first"] = (await repo.read("file.txt")).decode()
    seen["snapshots"] = await repo.snapshots()
    await repo.write("seen.json", json.dumps(seen).encode())


async def _has(repo, path):
    try:
        await repo.read(path)
    except FileNotFoundError:
        return False
    return True
"""


def _two_commits(at: Path) -> None:
    at.mkdir()
    _git(at, "init", "-q")
    (at / ".gitignore").write_text("seen.json\n")
    (at / "file.txt").write_text("first\n")
    _git(at, "add", ".")
    _git(at, "commit", "-q", "-m", "first")
    (at / "file.txt").write_text("second\n")
    _git(at, "commit", "-qam", "second")


@pytest.mark.timeout(300)
def test_a_container_with_git_snapshots_and_rewinds(
    daemon: None, tmp_path: Path
) -> None:
    _image("python:3.12")
    flow = written(
        tmp_path / "flows", "rewinds", _REWINDS.replace("IMAGE", "python:3.12")
    )
    repo = tmp_path / "repo"
    _two_commits(repo)

    run = _hmz(flow, f"repo=docker{repo}", "go", tmp_path)
    _, err = run.communicate(timeout=240)

    assert run.returncode == 0, err
    assert json.loads((repo / "seen.json").read_text()) == {
        "file": "second\n",
        "added": False,
        "first": "first\n",
        "snapshots": ["refs/hmz/snapshots/before"],
    }


@pytest.mark.timeout(300)
def test_a_container_without_git_is_refused_before_the_flow_runs(
    daemon: None, tmp_path: Path
) -> None:
    flow = written(tmp_path / "flows", "rewinds", _REWINDS.replace("IMAGE", IMAGE))
    repo = tmp_path / "repo"
    _two_commits(repo)

    run = _hmz(flow, f"repo=docker{repo}", "go", tmp_path)
    _, refused = run.communicate(timeout=240)

    assert run.returncode == 2, refused
    assert "'repo' needs GitEnvMixin" in refused, refused
    assert "needs git on the machine's PATH" in refused, refused
    assert not (repo / "seen.json").exists()
    assert _git_out(repo, "for-each-ref", "refs/hmz") == ""


_BRANCHES = """
from hmz.flows import AgentCollection, Env, EnvCollection, FilesEnvMixin, FlowParams
from hmz.flows import GitWorktreeEnvMixin, ImageEnvMixin, flow


class Repo(Env, FilesEnvMixin, GitWorktreeEnvMixin, ImageEnvMixin):
    _image = "IMAGE"


class Envs(EnvCollection):
    repo: Repo


@flow(agents=AgentCollection, envs=Envs, params=FlowParams)
async def branches(task, *, agents, envs, params, ctx):
    repo = envs["repo"]
    tree = await repo.derive_worktree(ref="HEAD~1")
    await repo.write("seen.txt", await tree.read("file.txt"))
"""


@pytest.mark.timeout(300)
@pytest.mark.parametrize(("image", "served"), [(IMAGE, False), ("python:3.12", True)])
def test_a_worktree_is_added_only_in_a_container_that_has_git(
    daemon: None, tmp_path: Path, image: str, *, served: bool
) -> None:
    _image(image)
    flow = written(tmp_path / "flows", "branches", _BRANCHES.replace("IMAGE", image))
    repo = tmp_path / "repo"
    _two_commits(repo)

    run = _hmz(flow, f"repo=docker{repo}", "go", tmp_path)
    _, err = run.communicate(timeout=240)

    if served:
        assert run.returncode == 0, err
        assert (repo / "seen.txt").read_text() == "first\n"
        return
    assert run.returncode == 2, err
    assert "'repo' needs GitWorktreeEnvMixin" in err, err
    assert "GitWorktreeEnvMixin needs git on the machine's PATH" in err, err
    assert not (repo / "seen.txt").exists()
    assert len(_git_out(repo, "worktree", "list").splitlines()) == 1


def _git_out(cwd: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


# ------------------------------------------------------------------------ daemons elsewhere


@pytest.mark.timeout(300)
@pytest.mark.parametrize("road", ["forwarded", "ssh_runtime"])
async def test_a_daemon_elsewhere_holds_the_container(
    road: str, request: pytest.FixtureRequest, tmp_path: Path
) -> None:
    endpoint = str(request.getfixturevalue(road))
    name = f"far-{road.replace('_', '-')}"
    store.write(store.DockerRuntime(name=name, endpoint=endpoint))
    work = tmp_path / "work"
    work.mkdir()
    driver = _opened(f"slim=docker@{name}{work}", "slim")
    try:
        await probe(driver)
        status, out, err = await driver.exec(
            ["sh", "-c", "id -u; test -f /.dockerenv && echo inside"], timeout=120
        )
        await driver.write("there.txt", b"written in a container elsewhere\n")
        sub = await driver.derive_subdir("deeper")
        await sub.write("x.txt", b"x")
    finally:
        await driver.close()

    assert status == 0, err
    assert out.split() == [str(os.getuid()), "inside"]
    assert (work / "there.txt").read_text() == "written in a container elsewhere\n"
    assert (work / "deeper" / "x.txt").read_text() == "x"


# ------------------------------------------------------------------ agents in a container

#: A flow putting its one agent in a container, and writing down what the container is called.
_BOXED = """
from hmz.flows import Agent, AgentCollection, Env, EnvCollection, FilesEnvMixin
from hmz.flows import FlowParams, ImageEnvMixin, ShellEnvMixin, flow


class Box(Env, ShellEnvMixin, FilesEnvMixin, ImageEnvMixin):
    _image = "python:3.12-slim"


class Agents(AgentCollection):
    coder: Agent


class Envs(EnvCollection):
    box: Box


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def boxed(task, *, agents, envs, params, ctx):
    box = envs["box"]
    _, name, _ = await box.exec(["hostname"])
    await box.write("truth.txt", name.encode())
    session = await agents["coder"].spawn(env=box)
    return await agents["coder"].run(task, session=session)
"""

_ASKED = (
    "Use your shell tool to run exactly this one command, then reply with the single word "
    "done: cat /etc/os-release > os-release.txt; hostname > proof.txt; "
    "test -f /.dockerenv && echo inside > dockerenv.txt"
)


def _cheapest(cli: str) -> tuple[str, str]:
    """The model and effort a CLI is cheapest to ask here.

    The one its driver tests pick where the CLI still offers it when asked now, and otherwise
    the first it offers at the least effort that one takes: a catalogue written down a week ago
    may name a model the account has since lost.
    """
    from hmz.coganchor import models
    from tests.system.agents.test_harness_drivers import _model

    model, effort = _model(HarnessKind(cli))
    try:
        offered = models.ask(cli)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return model, effort
    if not offered or model in {one.name for one in offered}:
        return model, effort
    first = offered[0]
    return first.name, first.efforts[-1] if first.efforts else ""


def _boxed(cli: str, env: str, tmp_path: Path, model: str, effort: str) -> Path:
    """Runs the flow once with its agent of this CLI and its environment as given."""
    flow = written(tmp_path / "flows", "boxed", _BOXED)
    work = tmp_path / "work"
    work.mkdir()
    Runner(
        flow,
        agents=[AgentSpec("coder", HarnessKind(cli), "", model, effort, cli)],
        envs={"box": f"{env}{work}"},
        budget={"cost": 1},
        workspace=tmp_path,
    ).run(_ASKED)
    return work


@pytest.mark.agent
@pytest.mark.timeout(900)
@pytest.mark.parametrize("cli", [one.name for one in backends.PROFILES], ids=str)
def test_an_agent_of_every_cli_works_inside_its_container(
    cli: str, daemon: None, asking: None, tmp_path: Path
) -> None:
    """A real turn in a container, checked where only the container could have answered.

    A turn the CLI will not take is asked again with no container at all: one refused there
    too is this machine's sign-in, and is skipped saying so; one taken there is humanize's to
    answer for, and fails.
    """
    if backends.program(cli) is None:
        pytest.skip(f"{cli} is not installed here")
    released = Path("/etc/os-release")
    if released.exists() and "Debian" in released.read_text():
        pytest.skip("this machine is Debian, as the image is")
    model, effort = _cheapest(cli)
    try:
        work = _boxed(cli, "docker", tmp_path / "boxed", model, effort)
    except (HarnessThrottled, HarnessRefused) as spent:
        # A quota spent or a sign-in refused is the account's wherever the turn was taken,
        # and a turn taken here a moment later -- the next window of a rate limit -- would
        # say nothing about the container.
        pytest.skip(f"{cli}'s account would not take the turn: {spent}")
    except HarnessError as refused:
        try:
            _boxed(cli, "local", tmp_path / "here", model, effort)
        except HarnessError as here:
            pytest.skip(f"{cli} will not take a turn on this machine at all: {here}")
        raise AssertionError(
            f"{cli} took a turn here and not in a container"
        ) from refused

    truth = (work / "truth.txt").read_text().strip()
    assert (work / "proof.txt").read_text().strip() == truth
    assert (work / "dockerenv.txt").read_text().strip() == "inside"
    assert "Debian" in (work / "os-release.txt").read_text()
