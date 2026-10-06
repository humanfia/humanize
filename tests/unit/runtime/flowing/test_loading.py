"""What a ref names, and bringing its module in: `loading`, over flows written to a temp dir."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    FlowDefinitionError,
    FlowLoadConflict,
    FlowNotFound,
    FlowRefError,
    ParamsError,
)
from hmz.runtime.flowing.engine import FlowImpl
from hmz.runtime.flowing.index import kept
from hmz.runtime.flowing.loading import (
    FlowModule,
    Remote,
    forget,
    load,
    module_of,
    parse,
    pick,
)
from tests.unit.runtime.flowing.doubles_u10 import flow_dir, flow_file, settle, source

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def mine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """This project's own flows directory, empty."""
    project = settle(monkeypatch, tmp_path)
    at = project / ".hmz" / "flows"
    at.mkdir(parents=True)
    return at


def loaded(ref: str, asking: dict[str, Any] | None = None) -> FlowImpl:
    found = load(ref, {} if asking is None else asking)
    assert isinstance(found, FlowImpl)
    return found


# ------------------------------------------------------------------------------- refs


@pytest.mark.parametrize(
    ("ref", "url", "rev", "where", "sub"),
    [
        (":review", None, None, "", "review"),
        ("humanize1", None, None, "humanize1", ""),
        ("humanize1:gen-plan", None, None, "humanize1", "gen-plan"),
        ("alice/kernel", None, None, "alice/kernel", ""),
        ("@local/x:y", None, None, "@local/x", "y"),
        ("./flows/x", None, None, "./flows/x", ""),
        ("/abs/x:sub", None, None, "/abs/x", "sub"),
        ("~/x/y/z", None, None, "~/x/y/z", ""),
        (
            "git+https://github.com/o/r@v0.1.0#humanize1:rlcr",
            "https://github.com/o/r",
            "v0.1.0",
            "humanize1",
            "rlcr",
        ),
        ("git+https://github.com/o/r", "https://github.com/o/r", None, "", ""),
        ("git+https://github.com/o/r:sub", "https://github.com/o/r", None, "", "sub"),
        ("git+https://host:8443/o/r", "https://host:8443/o/r", None, "", ""),
        ("git+file:///srv/r#a/b/", "file:///srv/r", None, "a/b", ""),
        ("git+ssh://git@host/r@main#:x", "ssh://git@host/r", "main", "", "x"),
    ],
)
def test_parse_reads_a_ref(
    ref: str, url: str | None, rev: str | None, where: str, sub: str
) -> None:
    said = parse(ref)
    assert (said.url, said.rev, said.where, said.sub) == (url, rev, where, sub)
    assert repr(said).startswith("Ref(")


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "  ",
        ":",
        ":a b",
        "x:a b",
        ":x:y",
        "a/b/c",
        "https://github.com/o/r#x",
        "git+ftp://host/r",
        "git+https:///r",
        "git+https://host/",
        "git+https://host/r#../up",
        "git+https://host/r#.hidden",
        "git+https://host/r#x:a b",
    ],
)
def test_parse_refuses_what_is_no_ref(ref: str) -> None:
    with pytest.raises(FlowRefError):
        parse(ref)


# --------------------------------------------------------------------------- loading


def test_a_path_loads_the_flow_there(mine: Path) -> None:
    entry = flow_dir(mine.parent / "elsewhere", "zz_alpha")
    flow = loaded(str(entry.parent))
    assert (flow.name, flow.ref) == ("zz_alpha", "zz_alpha:zz_alpha")
    assert flow.home is not None
    assert flow.home.entry == entry
    assert loaded(str(entry.parent)) is flow
    assert loaded("./.hmz/elsewhere/zz_alpha") is flow


def test_a_name_loads_the_nearest_flow(mine: Path) -> None:
    flow_dir(mine, "zz_beta")
    flow_file(mine, "zz_gamma")
    assert loaded("zz_beta").name == "zz_beta"
    assert loaded("@local/zz_gamma").name == "zz_gamma"


@pytest.mark.parametrize(
    ("ref", "says"),
    [
        ("zz_nothing", "no flow is called 'zz_nothing'"),
        ("./zz_nothing", "there is no flow at ./zz_nothing"),
        ("@nowhere/x", "no flow is called"),
    ],
)
def test_a_ref_nothing_answers_to_is_not_found(mine: Path, ref: str, says: str) -> None:
    del mine
    with pytest.raises(FlowNotFound, match=says):
        load(ref, {})


def test_a_relative_ref_needs_a_flow_asking() -> None:
    with pytest.raises(FlowRefError, match="no flow is asking"):
        load(":x", {})


def test_a_flow_named_inside_a_module(mine: Path) -> None:
    flow_dir(mine, "zz_multi", source("zz_multi", "zz_other", "zz_third"))
    assert loaded("zz_multi").name == "zz_multi"
    assert loaded("zz_multi:zz_other").name == "zz_other"
    with pytest.raises(FlowNotFound, match="it holds zz_multi, zz_other, zz_third"):
        load("zz_multi:zz_none", {})


def test_a_flow_finds_its_neighbours(mine: Path) -> None:
    flow_dir(mine, "zz_left", source("zz_left", "zz_inner"))
    flow_dir(mine.parent / "apart", "zz_right")
    flow_dir(mine.parent / "apart", "zz_close")
    left = loaded("zz_left")
    right = loaded("./.hmz/apart/zz_right")
    asking = dict(left.globals)
    assert loaded(":zz_inner", asking).name == "zz_inner"
    with pytest.raises(FlowNotFound, match="beside the flow asking; there are"):
        load(":zz_none", asking)
    assert loaded("zz_close", dict(right.globals)).name == "zz_close"


def test_a_flow_installed_out_of_an_index_finds_what_was_installed_beside_it(
    mine: Path,
) -> None:
    del mine
    flow_dir(kept("theirs") / "alice", "zz_kernel")
    flow_dir(kept("theirs"), "zz_base")
    kernel = loaded(str(kept("theirs") / "alice" / "zz_kernel"))
    assert loaded("zz_base", dict(kernel.globals)).name == "zz_base"


@pytest.mark.parametrize(
    ("names", "hidden", "picked"),
    [
        (("zz_one",), "", "zz_one"),
        (("zz_a", "zz_b"), "zz_a", "zz_b"),
    ],
)
def test_a_bare_ref_is_the_only_visible_flow(
    mine: Path, names: tuple[str, ...], hidden: str, picked: str
) -> None:
    flow_dir(mine, "zz_bare", source(*names, hidden=hidden))
    assert loaded("zz_bare").name == picked


@pytest.mark.parametrize(
    ("text", "says"),
    [
        (
            source("zz_a", "zz_b"),
            "none is called 'zz_bare'; name one as zz_bare:<flow>",
        ),
        ("x = 1\n", "defines no flow"),
    ],
)
def test_a_bare_ref_that_could_mean_anything_is_refused(
    mine: Path, text: str, says: str
) -> None:
    flow_dir(mine, "zz_bare", text)
    with pytest.raises(FlowNotFound, match=says):
        load("zz_bare", {})


def test_a_module_that_will_not_import_is_a_definition_error(mine: Path) -> None:
    flow_dir(mine, "zz_broken", "raise RuntimeError('broken')\n")
    with pytest.raises(FlowDefinitionError, match="broken"):
        load("zz_broken", {})
    assert "zz_broken" not in sys.modules


def test_a_flow_exception_at_import_is_raised_as_it_is(mine: Path) -> None:
    flow_dir(
        mine,
        "zz_raises",
        "from hmz.flows import ParamsError\nraise ParamsError('no')\n",
    )
    with pytest.raises(ParamsError, match="no"):
        load("zz_raises", {})


def test_two_flows_of_one_name_are_refused(mine: Path) -> None:
    text = source("zz_twice", "zz_again").replace(
        "params=Params)", "params=Params, name='zz_twice')"
    )
    flow_dir(mine, "zz_twice", text)
    with pytest.raises(FlowDefinitionError, match="two flows are called 'zz_twice'"):
        load("zz_twice", {})


def test_a_module_that_would_replace_another_is_refused(mine: Path) -> None:
    entry = flow_dir(mine, "zz_shadow")
    (entry.parent / "json.py").write_text("x = 1\n")
    with pytest.raises(FlowLoadConflict, match="'json'"):
        load("zz_shadow", {})


def test_what_a_flow_keeps_beside_it_is_imported_by_its_plain_name(mine: Path) -> None:
    entry = flow_dir(
        mine,
        "zz_parent",
        "from zz_helper import ANSWER\n" + source("zz_parent"),
    )
    (entry.parent / "zz_helper.py").write_text("ANSWER = 42\n")
    flow = loaded("zz_parent")
    assert flow.globals["ANSWER"] == 42
    assert "zz_helper" in sys.modules
    forget()
    assert "zz_helper" not in sys.modules
    assert "zz_parent" not in sys.modules


# --------------------------------------------------------------------------- modules


def test_a_module_is_imported_once_and_again_when_it_changes(mine: Path) -> None:
    entry = flow_dir(mine, "zz_mod")
    held = module_of(entry, None)
    assert isinstance(held, FlowModule)
    assert (held.name, held.stem, held.verse, held.pins) == (
        "zz_mod",
        "zz_mod",
        mine,
        0,
    )
    assert repr(held) == f"<flow module zz_mod at {mine / 'zz_mod'}>"
    assert module_of(entry, None) is held
    entry.write_text(source("zz_mod", doc="Changed now."))
    again = module_of(entry, None)
    assert again is not held
    assert again.flows()["zz_mod"].description == "Changed now."


def test_a_one_file_flow_is_its_own_module(mine: Path) -> None:
    entry = flow_file(mine, "zz_single")
    held = module_of(entry, None)
    assert (held.at, held.stem, held.verse) == (entry, "zz_single", mine)
    assert pick(held, "", "zz_single").name == "zz_single"


def test_a_module_owns_only_the_flows_defined_inside_it(mine: Path) -> None:
    flow_dir(mine, "zz_lender")
    entry = flow_dir(
        mine,
        "zz_borrower",
        "from hmz.flows import load\nlent = load('zz_lender')\n"
        + source("zz_borrower"),
    )
    held = module_of(entry, None)
    assert held.module.lent.name == "zz_lender"
    assert list(held.flows()) == ["zz_borrower"]


def test_forget_under_a_directory_leaves_the_rest(mine: Path) -> None:
    near = module_of(flow_dir(mine, "zz_near"), None)
    far = module_of(flow_dir(mine.parent / "far", "zz_far"), None)
    forget(mine.parent / "far")
    assert module_of(near.entry, None) is near
    assert module_of(far.entry, None) is not far
    forget()
    assert module_of(near.entry, None) is not near


# ---------------------------------------------------------------------------- remote


def test_a_repository_ref_is_not_fetched_until_it_is_used(tmp_path: Path) -> None:
    remote = load("git+file:///srv/nowhere@v1#tools/zz_tool", {})
    assert isinstance(remote, Remote)
    assert (
        repr(remote) == "<flow git+file:///srv/nowhere@v1#tools/zz_tool (not fetched)>"
    )
    checkout = tmp_path / "checkout"
    flow_dir(checkout / "tools", "zz_tool")
    flow = remote.settle(checkout, None)
    assert flow.name == "zz_tool"
    assert remote.flow is flow
    assert remote.name == "zz_tool"
    assert remote.description is None
    assert remote.resumable is False
    assert remote.expected_params is flow.expected_params
    assert remote.expected_agents is flow.expected_agents
    assert remote.expected_envs is flow.expected_envs
    assert "(not fetched)" not in repr(remote)


def test_a_repository_ref_may_name_a_one_file_flow(tmp_path: Path) -> None:
    remote = load("git+file:///srv/r#tools/zz_file.py", {})
    assert isinstance(remote, Remote)
    flow_file(tmp_path / "tools", "zz_file")
    assert remote.settle(tmp_path, None).name == "zz_file"


def test_a_repository_with_no_flow_where_it_says_points_at_one(tmp_path: Path) -> None:
    remote = load("git+file:///srv/r#zz_old", {})
    assert isinstance(remote, Remote)
    flow_dir(tmp_path / "flows", "zz_old")
    with pytest.raises(FlowNotFound, match="there is one at #flows/zz_old"):
        remote.settle(tmp_path, None)
    root = load("git+file:///srv/r", {})
    assert isinstance(root, Remote)
    with pytest.raises(FlowNotFound, match="has no flow in its root"):
        root.settle(tmp_path, None)
