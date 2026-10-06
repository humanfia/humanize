"""What the flowing unit tests write to disk: a project, flows, and indexes of them."""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: A commit, written out in full, as an index's manifest names one.
COMMIT = "a" * 40


def settle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Runs the test in a project of its own, with a home directory of its own.

    Returns:
      The project's directory, which is the working directory now.
    """
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv("HOME", str(tmp_path / "me"))
    return project


def cloned(at: Path, url: str) -> Path:
    """Makes `at` look like a clone of `url`, as a flowverse's index is read."""
    (at / ".git").mkdir(parents=True, exist_ok=True)
    (at / ".git" / "config").write_text(f'[remote "origin"]\n\turl = {url}\n')
    return at


def release(
    index: Path, flow: str, version: str, /, *, owner: str = "", **said: object
) -> Path:
    """Writes one release's manifest into an index, as `flows/[<owner>/]<flow>/<version>/`."""
    at = (
        index / "flows" / owner / flow / version
        if owner
        else index / "flows" / flow / version
    )
    at.mkdir(parents=True, exist_ok=True)
    fields: dict[str, object] = {
        "name": flow,
        "version": version,
        "repo": f"{owner or 'humanfia'}/{flow}",
        "commit": COMMIT,
    }
    fields.update(said)
    (at / "flow.yaml").write_text(yaml.safe_dump(fields))
    return at / "flow.yaml"


def source(*names: str, doc: str = "", module_doc: str = "", hidden: str = "") -> str:
    """A flow module defining one flow per name, each answering `<name>:<task>`.

    Args:
      names: The flows, by what each is called.
      doc: The first line of each flow's docstring, or "" for none.
      module_doc: The module's docstring, or "" for none.
      hidden: A flow among `names` to define hidden.
    """
    flows = "".join(
        f"\n\n@flow(agents=AgentCollection, envs=EnvCollection, params=Params"
        f"{', hidden=True' if one == hidden else ''})\n"
        f"async def {one}(task, *, agents, envs, params, ctx):\n"
        + (f'    """{doc}"""\n' if doc else "")
        + f'    return "{one}:" + task\n'
        for one in names
    )
    head = f'"""{module_doc}"""\n\n' if module_doc else ""
    return (
        head
        + "from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow\n\n\n"
        "class Params(FlowParams):\n    pass\n" + flows
    )


def flow_dir(under: Path, name: str, text: str | None = None) -> Path:
    """Writes a flow that is a directory, `<under>/<name>/__init__.py`.

    Returns:
      Its entry point.
    """
    at = under / name
    at.mkdir(parents=True, exist_ok=True)
    entry = at / "__init__.py"
    entry.write_text(source(name) if text is None else text)
    return entry


def flow_file(under: Path, name: str, text: str | None = None) -> Path:
    """Writes a flow that is one file, `<under>/<name>.py`."""
    under.mkdir(parents=True, exist_ok=True)
    entry = under / f"{name}.py"
    entry.write_text(source(name) if text is None else text)
    return entry
