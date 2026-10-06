"""Where a flow is and what it is called: `finding`, over a project and a home in a temp dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from hmz.flows import FlowNotFound, FlowRefError
from hmz.runtime.flowing.finding import (
    BUILTIN_AT,
    ENTRY,
    Offer,
    about,
    at,
    builtin,
    entry,
    find,
    fork,
    found,
    inside,
    offered,
    offers,
    privileged,
    resolved,
    within,
)
from hmz.runtime.flowing.index import RECORD
from hmz.runtime.flowing.verses import INDEX, LOCAL, OFFICIAL, USER, named, under
from tests.unit.runtime.flowing.doubles_u10 import (
    cloned,
    flow_dir,
    flow_file,
    release,
    settle,
    source,
)


class Places:
    """This project's own flows, and yours."""

    def __init__(self, project: Path) -> None:
        self.project = project
        self.mine = project / ".hmz" / "flows"
        self.yours = project.parent / "me" / ".hmz" / "flows"


@pytest.fixture
def places(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Places:
    return Places(settle(monkeypatch, tmp_path))


# ----------------------------------------------------------------- one directory


def test_entry_is_a_directory_before_a_file(tmp_path: Path) -> None:
    assert entry(tmp_path, "x") is None
    alone = flow_file(tmp_path, "x")
    assert entry(tmp_path, "x") == alone
    whole = flow_dir(tmp_path, "x")
    assert entry(tmp_path, "x") == whole
    assert whole.name == ENTRY


def test_offered_lists_the_flows_in_a_directory(tmp_path: Path) -> None:
    assert offered(tmp_path / "nothing") == []
    flow_dir(tmp_path, "b")
    flow_file(tmp_path, "b")
    flow_file(tmp_path, "a")
    flow_file(tmp_path, "_private")
    flow_file(tmp_path, ".hidden")
    (tmp_path / "plain").mkdir()
    (tmp_path / "notes.txt").write_text("")
    assert offered(tmp_path) == ["a", "b"]


def test_within_looks_in_every_directory_a_place_keeps(places: Places) -> None:
    local = named(LOCAL)
    official = named(OFFICIAL)
    assert local is not None
    assert official is not None
    assert within(local, "zz_x") is None
    flow_file(places.mine, "zz_x")
    assert within(local, "zz_x") == Path(".hmz/flows/zz_x.py")
    assert within(official, "chat") == BUILTIN_AT / "chat" / ENTRY


# ------------------------------------------------------------------------- finding


def test_find_takes_a_name_nearest_first(places: Places) -> None:
    yours = flow_dir(places.yours, "zz_both")
    assert find("zz_both") == str(yours.resolve())
    mine = flow_dir(places.mine, "zz_both")
    assert find("zz_both") == str(mine.resolve())
    assert find("@user/zz_both") == str(yours.resolve())
    assert find("@local/zz_both:inner") == str(mine.resolve())
    assert find("chat") == str((BUILTIN_AT / "chat" / ENTRY).resolve())


@pytest.mark.parametrize(
    "name", ["zz_none", "@local/zz_none", "@nowhere/x", "a/b/c", "demo.py", "./zz_none"]
)
def test_find_is_empty_for_what_nothing_answers_to(places: Places, name: str) -> None:
    (places.project / "demo.py").write_text("")
    assert find(name) == ""


def test_find_takes_a_path_in_either_shape(places: Places) -> None:
    whole = flow_dir(places.project / "work", "zz_dir")
    alone = flow_file(places.project / "work", "zz_file")
    assert find("./work/zz_dir") == str(whole.resolve())
    assert find("./work/zz_file") == str(alone.resolve())
    assert find("./work/zz_file.py") == str(alone.resolve())
    assert find(f"{alone}:sub") == str(alone.resolve())


def test_at_is_a_flows_own_directory(places: Places) -> None:
    whole = flow_dir(places.mine, "zz_dir")
    flow_file(places.mine, "zz_file")
    assert at("zz_dir") == str(whole.parent.resolve())
    assert at("zz_file") == ""
    assert at("zz_none") == ""


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("x", ""),
        ("x:sub", "sub"),
        ("@local/x:sub", "sub"),
        ("./a:b/c", ""),
        ("C:/x", ""),
    ],
)
def test_inside_is_the_name_after_the_colon(name: str, expected: str) -> None:
    assert inside(name) == expected


# -------------------------------------------------------------------------- offers


def test_offers_list_every_visible_flow_by_its_name(places: Places) -> None:
    flow_dir(
        places.mine,
        "zz_multi",
        source(
            "zz_multi", "zz_b", "zz_a", "zz_secret", doc="Does it.", hidden="zz_secret"
        ),
    )
    flow_file(
        places.mine, "zz_doc", source("zz_doc", module_doc="Module says.\n\nMore.")
    )
    flow_file(places.mine, "zz_two", source("zz_x", "zz_y"))
    flow_file(places.mine, "zz_broken", "raise RuntimeError('no')\n")
    flow_file(places.mine, "zz_empty", "x = 1\n")
    flow_file(places.mine, "zz_hid", source("zz_hid", hidden="zz_hid"))
    local = named(LOCAL)
    assert local is not None
    assert offers(local) == [
        Offer(LOCAL, "@local/zz_broken", ""),
        Offer(LOCAL, "@local/zz_doc", "Module says."),
        Offer(LOCAL, "@local/zz_multi", "Does it."),
        Offer(LOCAL, "@local/zz_multi:zz_a", "Does it."),
        Offer(LOCAL, "@local/zz_multi:zz_b", "Does it."),
        Offer(LOCAL, "@local/zz_two:zz_x", ""),
        Offer(LOCAL, "@local/zz_two:zz_y", ""),
    ]


def test_found_lists_humanizes_own_first_and_yours_last(places: Places) -> None:
    flow_file(places.yours, "zz_yours")
    flow_file(places.mine, "zz_mine")
    listed = found()
    assert listed[0].whose == OFFICIAL
    assert Offer(OFFICIAL, "chat", about("chat")) in listed
    assert listed[-2:] == [
        Offer(LOCAL, "@local/zz_mine", ""),
        Offer(USER, "@user/zz_yours", ""),
    ]


# ---------------------------------------------------------------------- resolving


def test_resolved_loads_the_flow_a_name_comes_to(places: Places) -> None:
    flow_dir(places.mine, "zz_r", source("zz_r", "zz_s", doc="Said."))
    flow = resolved("zz_r:zz_s")
    assert (flow.name, flow.description) == ("zz_s", "Said.")
    assert builtin(flow) is False
    assert privileged(flow) is False


def test_chat_is_humanizes_own_and_trusted_with_every_capability(
    places: Places,
) -> None:
    del places
    chat = resolved("chat")
    assert builtin(chat) is True
    assert privileged(chat) is True


def test_resolved_fetches_a_repository_ref_on_this_thread(
    places: Places, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.runtime.flowing import loading

    checkout = places.project / "checkout"
    flow_dir(checkout, "zz_far")

    def pinned(url: str, rev: str | None) -> Path:
        del url, rev
        return checkout

    monkeypatch.setattr(loading, "pinned", pinned)
    assert resolved("git+file:///srv/r#zz_far").name == "zz_far"


def test_resolved_says_why_a_name_is_not_there(places: Places) -> None:
    with pytest.raises(
        FlowNotFound, match="the official flowverse has not been fetched yet"
    ):
        resolved("zz_none")
    cloned(under() / OFFICIAL / INDEX, "https://github.com/humanfia/flowverse")
    with pytest.raises(FlowNotFound) as no_reason:
        resolved("zz_none")
    assert str(no_reason.value).count(":") == 1
    release(under() / OFFICIAL / INDEX, "zz_listed", "1.0.0")
    with pytest.raises(FlowNotFound, match="not installed -- install it from /flow"):
        resolved("zz_listed")
    flow_file(places.mine, "zz_old")
    with pytest.raises(FlowNotFound, match="is called @local/zz_old now"):
        resolved("local/zz_old")
    flow_dir(places.project, "zz_here")
    with pytest.raises(FlowNotFound, match=r"a path starts with \./"):
        resolved("zz_here")


def test_resolved_passes_on_a_module_missing_the_flow_named(places: Places) -> None:
    flow_file(places.mine, "zz_mod")
    with pytest.raises(FlowNotFound, match="holds no flow called 'zz_none'"):
        resolved("zz_mod:zz_none")


def test_resolved_refuses_what_is_no_ref(places: Places) -> None:
    del places
    with pytest.raises(FlowRefError):
        resolved(":x")


def test_about_says_what_a_flow_says_about_itself(places: Places) -> None:
    flow_file(places.mine, "zz_doc", source("zz_doc", module_doc="From the module."))
    flow_file(places.mine, "zz_own", source("zz_own", "zz_in", doc="From the flow."))
    flow_file(places.mine, "zz_bad", "raise RuntimeError('no')\n")
    assert about("zz_doc") == "From the module."
    assert about("zz_own") == "From the flow."
    assert about("zz_own:zz_in") == "From the flow."
    assert about("zz_bad") == ""
    assert about("zz_none") == ""


# ---------------------------------------------------------------------------- fork


def test_fork_copies_a_flow_into_this_project(places: Places) -> None:
    theirs = flow_dir(places.yours, "zz_f")
    (theirs.parent / "zz_helper.py").write_text("x = 1\n")
    (theirs.parent / RECORD).write_text("{}")
    copied = fork("@user/zz_f")
    assert Path(copied) == Path(".hmz/flows/zz_f")
    assert (Path(copied) / ENTRY).read_text() == theirs.read_text()
    assert (Path(copied) / "zz_helper.py").is_file()
    assert not (Path(copied) / RECORD).exists()
    assert [one.name for one in places.mine.iterdir()] == ["zz_f"]
    assert find("zz_f") == str((places.mine / "zz_f" / ENTRY).resolve())


def test_fork_copies_a_one_file_flow_as_one_file(
    places: Places, tmp_path: Path
) -> None:
    flow_file(places.yours, "zz_one")
    copied = fork("@user/zz_one", tmp_path / "into")
    assert Path(copied) == tmp_path / "into" / "zz_one.py"
    assert Path(copied).is_file()


@pytest.mark.parametrize(
    ("make", "says"),
    [
        (False, "no flow called zz_g to copy"),
        (True, "already a flow of your own"),
    ],
)
def test_fork_refuses(places: Places, *, make: bool, says: str) -> None:
    if make:
        flow_dir(places.yours, "zz_g")
        flow_file(places.mine, "zz_g")
    with pytest.raises(ValueError, match=says):
        fork("@user/zz_g" if make else "zz_g")
