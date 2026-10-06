from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.policy import Layout, Router, answered, head, parents

if TYPE_CHECKING:
    from pathlib import Path


def on(platform: str) -> Router:
    """A router over one mirror at `/srv/mirror`, answering for a target on `platform`."""
    return Router(
        layouts=(Layout.create("/srv/mirror", "/work"),),
        platform=lambda: platform,
    )


# -------------------------------------------------------------------------------- head


@pytest.mark.parametrize(
    ("named", "said"),
    [("/a/b", "/a/b"), ("/a/state_*.db", "/a/state_"), ("/a/*/x", "/a/"), ("", "")],
)
def test_head_is_everything_up_to_the_first_wildcard(named: str, said: str) -> None:
    assert head(named) == said


# ---------------------------------------------------------------------------- answered


@pytest.mark.parametrize(
    ("path", "answer"),
    [
        ("/h/c.json", "/p/c.json"),
        ("/h/c.json.tmp", "/p/c.json.tmp"),
        ("/h/c.json/inside", "/p/c.json/inside"),
        ("/h/c.jsonl", None),
        ("/h/other", None),
    ],
)
def test_a_path_answers_itself_what_is_inside_and_what_is_beside_it(
    path: str, answer: str | None
) -> None:
    assert answered("/h/c.json", "/p/c.json", path) == answer


@pytest.mark.parametrize(
    ("named", "instead", "path", "answer"),
    [
        ("/h/state_*.db", "/p/state_*.db", "/h/state_5.db", "/p/state_5.db"),
        ("/h/state_*.db", "/p/state_*.db", "/h/state_5.db/x", "/p/state_5.db/x"),
        ("/h/state_*.db", "/p/state_*.db", "/h/other.db", None),
        (
            "/h/projects/*/chats",
            "/s/projects/*/chats",
            "/h/projects/a/chats/1",
            "/s/projects/a/chats/1",
        ),
        ("/h/projects/*/chats", "/s/projects/*/chats", "/h/projects", None),
        ("/h/projects/*/chats", "/s/projects/*/chats", "/h/projects/a/logs", None),
    ],
)
def test_a_pattern_answers_every_path_whose_names_match(
    named: str, instead: str, path: str, answer: str | None
) -> None:
    assert answered(named, instead, path) == answer


# ----------------------------------------------------------------------------- parents


def test_parents_makes_the_directory_a_path_is_in_once(tmp_path: Path) -> None:
    made: set[str] = set()
    path = tmp_path / "a" / "b" / "file"

    parents(str(path), made)

    assert path.parent.is_dir()
    assert made == {str(path.parent)}


def test_parents_does_not_ask_again_for_what_it_made(tmp_path: Path) -> None:
    gone = tmp_path / "gone"
    made = {str(gone)}

    parents(str(gone / "file"), made)

    assert not gone.exists()


def test_parents_says_nothing_of_a_directory_it_cannot_make(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    made: set[str] = set()

    parents(str(blocker / "below" / "x"), made)

    assert made == set()


# ------------------------------------------------------------------------------ Layout


def test_a_layout_with_no_target_path_is_the_mirror_itself() -> None:
    layout = Layout.create("/srv/mirror/", None)

    assert layout == Layout("/srv/mirror", "/srv/mirror")
    assert layout.to_virtual("/srv/mirror/a") == "/srv/mirror/a"


def test_a_layout_names_a_path_as_the_target_does() -> None:
    layout = Layout.create("/srv/mirror", "/work")

    assert layout.to_virtual("/srv/mirror") == "/work"
    assert layout.to_virtual("/srv/mirror/src/x.py") == "/work/src/x.py"
    assert layout.to_virtual("/SRV/Mirror/src") == "/work/src"


@pytest.mark.parametrize(
    ("path", "inside"),
    [
        ("/srv/mirror", True),
        ("/srv/mirror/a", True),
        ("/srv/mirrored", False),
        ("/srv", False),
    ],
)
def test_a_layout_holds_what_lies_under_its_root(path: str, inside: bool) -> None:
    assert Layout.create("/srv/mirror", "/work").contains(path) is inside


def test_a_layout_compares_case_only_when_asked() -> None:
    layout = Layout.create("/srv/mirror", "/work")

    assert not layout.contains("/SRV/MIRROR/a")
    assert layout.contains("/SRV/MIRROR/a", insensitive=True)
    assert layout.below("/SRV/MIRROR/a", insensitive=True) == "a"


def test_a_path_outside_a_layout_has_no_name_on_the_target() -> None:
    with pytest.raises(ValueError, match="is not inside"):
        Layout.create("/srv/mirror", "/work").to_virtual("/etc/passwd")


# ------------------------------------------------------------------------------ Router


def test_paths_in_the_mirror_are_the_targets_and_the_rest_are_local() -> None:
    router = on("linux")

    assert router.is_remote_path("/srv/mirror/a")
    assert not router.is_remote_path("/home/me/.ssh")
    assert router.to_virtual("/srv/mirror/a") == "/work/a"
    with pytest.raises(ValueError, match="not inside a remote layout"):
        router.to_virtual("/home/me")


def test_a_working_directory_outside_every_layout_is_left_alone() -> None:
    router = on("linux")

    assert router.virtual_cwd("/srv/mirror/sub") == "/work/sub"
    assert router.virtual_cwd("/home/me") == "/home/me"


def test_nested_layouts_prefer_the_longest_root() -> None:
    router = Router(
        layouts=(Layout.create("/m", "/w"), Layout.create("/m/inner", "/elsewhere")),
    )

    assert router.to_virtual("/m/inner/a") == "/elsewhere/a"
    assert router.to_virtual("/m/other") == "/w/other"


def test_local_paths_carve_holes_in_the_mirror() -> None:
    router = Router(
        layouts=(Layout.create("/m", "/w"),),
        local_paths=("/m/.state",),
    )

    assert router.layout_for("/m/.state/x") is None
    assert router.layout_for("/m/src") is not None


def test_a_mirror_inside_a_local_path_is_still_the_targets() -> None:
    router = Router(
        layouts=(Layout.create("/home/me/.hmz/mirror", "/w"),),
        local_paths=("/home/me/.hmz",),
    )

    assert router.is_remote_path("/home/me/.hmz/mirror/a")
    assert not router.is_remote_path("/home/me/.hmz/other")


def test_a_hole_is_carved_in_whatever_case_the_target_ignores() -> None:
    router = Router(
        layouts=(Layout.create("/m", "/w"),),
        local_paths=("/m/.state",),
        platform=lambda: "darwin",
    )

    assert router.layout_for("/m/.STATE/x") is None


def test_programs_run_on_the_target_unless_kept_here() -> None:
    router = Router(
        layouts=(Layout.create("/m", "/w"),),
        local_programs=("/opt/agent",),
    )

    assert router.runs_locally("/opt/agent/bin/node")
    assert not router.runs_locally("/usr/bin/git")
    assert not router.runs_locally("/opt/agentx")


def test_rewriting_is_a_no_op_where_the_mirror_is_at_the_targets_path() -> None:
    router = Router(layouts=(Layout.create("/m", None),))

    assert router.rewrite("grep -r x /m/src") == "grep -r x /m/src"


def test_rewriting_names_the_mirror_as_the_target_does() -> None:
    router = on("linux")

    assert router.rewrite("grep -r x /srv/mirror/src") == "grep -r x /work/src"
    assert router.rewrite("echo hello/srv/mirror") == "echo hello/srv/mirror"


def test_rewriting_matches_any_case_only_for_a_target_that_ignores_it() -> None:
    assert on("linux").rewrite("cat /SRV/MIRROR/a") == "cat /SRV/MIRROR/a"
    assert on("darwin").rewrite("cat /SRV/MIRROR/a") == "cat /work/a"


def test_rewriting_knows_the_mirror_by_its_other_name() -> None:
    router = Router(layouts=(Layout.create("/tmp/m", "/w"),))

    assert router.rewrite("ls /private/tmp/m/x") == "ls /w/x"


def test_a_redirect_answers_by_the_entry_that_says_most() -> None:
    router = Router(
        layouts=(),
        redirects=(("/h/.c", "/p/all"), ("/h/.c/creds.json", "/p/creds.json")),
    )

    assert router.swap("/h/.c/creds.json") == "/p/creds.json"
    assert router.swap("/h/.c/other") == "/p/all/other"
    assert router.swap("/h/elsewhere") is None


def test_a_target_not_yet_reached_is_no_mac() -> None:
    router = Router(layouts=(Layout.create("/m", "/w"),))

    assert not router.insensitive
    assert not router.settles


def test_a_mac_is_insensitive_to_case() -> None:
    assert on("darwin").insensitive
    assert not on("linux").insensitive


def test_a_session_with_one_spelling_for_everything_has_nothing_to_settle() -> None:
    router = on("linux")

    assert not router.settles
    assert router.canonical("/SRV/MIRROR/a") == "/SRV/MIRROR/a"


def test_what_settles_is_asked_again_until_the_target_answers() -> None:
    said = [""]
    router = Router(layouts=(Layout.create("/m", "/w"),), platform=lambda: said[0])

    assert not router.settles
    said[0] = "darwin"
    assert router.settles
    said[0] = "linux"
    assert router.settles


@pytest.mark.parametrize(
    ("path", "settled"),
    [
        ("/SRV/Mirror/a/B", "/srv/mirror/a/B"),
        ("/srv/mirror", "/srv/mirror"),
        ("/SRV/MIRROR", "/srv/mirror"),
        ("/Elsewhere/X", "/Elsewhere/X"),
    ],
)
def test_a_mac_settles_a_path_onto_the_mirrors_own_spelling(
    path: str, settled: str
) -> None:
    assert on("darwin").canonical(path) == settled


def test_a_path_named_through_private_is_settled_onto_the_mirror() -> None:
    router = Router(layouts=(Layout.create("/tmp/m", "/w"),), platform=lambda: "linux")

    assert router.settles
    assert router.canonical("/private/tmp/m/a") == "/tmp/m/a"
    assert router.canonical("/private/var/x") == "/private/var/x"


def test_the_workspace_named_by_its_own_path_is_settled_onto_the_mirror() -> None:
    router = Router(
        layouts=(Layout.create("/srv/mirror", "/work"),),
        aliases=(("/work", "/srv/mirror"),),
        platform=lambda: "linux",
    )

    assert router.canonical("/work/a") == "/srv/mirror/a"
    assert router.canonical("/work") == "/srv/mirror"
    assert router.canonical("/workshop") == "/workshop"


def test_an_alias_keeps_the_holes_and_programs_named_under_it() -> None:
    router = Router(
        layouts=(Layout.create("/srv/mirror", "/work"),),
        local_paths=("/work/.state",),
        local_programs=("/work/bin/agent",),
        aliases=(("/work", "/srv/mirror"),),
    )

    assert router.layout_for("/srv/mirror/.state/x") is None
    assert router.runs_locally("/srv/mirror/bin/agent")


def test_an_argument_naming_the_mirror_by_an_alias_is_rewritten() -> None:
    router = Router(
        layouts=(Layout.create("/srv/mirror", "/work"),),
        aliases=(("/home/me/proj", "/srv/mirror"),),
    )

    assert router.rewrite("cat /home/me/proj/a") == "cat /work/a"
