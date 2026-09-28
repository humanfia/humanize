"""The hosts an ssh config names, and importing them as environment providers.

Read off files the test writes, never the user's own `~/.ssh`: `HOME` is a directory of the
test's, so that the one config read without being named is one it wrote. What a host resolves
to is `ssh -G`'s to say, which is a program, and is checked in the integration and system tiers.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.machines import sshconfig, store
from hmz.coganchor.machines.store import IMPORTED, SSHProvider

if TYPE_CHECKING:
    from pathlib import Path


#: A home no user has, which `Path.expanduser` raises for.
_NOBODY = "~hmz-no-such-user"


@pytest.fixture(autouse=True)
def user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home of the test's own, with an `.ssh` in it and nothing else."""
    at = tmp_path / "home"
    (at / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(at))
    return at


def test_every_host_is_listed_once_in_the_order_it_is_written(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text(
        "# a note\n"
        "Host builder gpu\n"
        "  HostName 10.0.0.2\n"
        "\n"
        "Host *\n"
        "  ForwardAgent yes\n"
        "Host web-? !not-this\n"
        "Host builder\n"  # said twice, listed once
        "host lowercase\n"
        'Host = "equals"\n'
        "Match host other\n"
        "Host\n"
    )

    assert sshconfig.aliases(config) == ["builder", "gpu", "lowercase", "equals"]


def test_an_include_is_followed_where_it_is_written(tmp_path: Path) -> None:
    (tmp_path / "conf.d").mkdir()
    (tmp_path / "conf.d" / "b.conf").write_text("Host from-b\n")
    (tmp_path / "conf.d" / "a.conf").write_text(
        f"Host from-a\n  Include {tmp_path / 'deeper'}\n"
    )
    (tmp_path / "deeper").write_text("Host deepest\n")
    config = tmp_path / "config"
    config.write_text(
        f"Host first\nInclude {tmp_path / 'conf.d'}/*.conf {tmp_path / 'missing'}\n"
        "Host last\n"
    )

    assert sshconfig.aliases(config) == ["first", "from-a", "deepest", "from-b", "last"]


def test_an_include_that_is_not_absolute_is_under_the_users_ssh(
    user_home: Path, tmp_path: Path
) -> None:
    (user_home / ".ssh" / "extra").write_text("Host extra\n")
    config = tmp_path / "config"
    config.write_text("Include extra\nHost mine\n")

    assert sshconfig.aliases(config) == ["extra", "mine"]


def test_an_include_under_no_home_there_is_includes_nothing(tmp_path: Path) -> None:
    """`~somebody` nobody is, as ssh reads it: a file that is not there, not a crash."""
    config = tmp_path / "config"
    config.write_text(f"Include {_NOBODY}/config\nHost mine\n")

    assert sshconfig.aliases(config) == ["mine"]
    assert sshconfig.aliases(f"{_NOBODY}/config") == []


def test_a_config_that_includes_itself_ends(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text(f"Host again\nInclude {config}\n")

    assert sshconfig.aliases(config) == ["again"]


def test_the_users_own_config_is_read_when_none_is_named(user_home: Path) -> None:
    (user_home / ".ssh" / "config").write_text("Host mine\n")

    assert sshconfig.default() == user_home / ".ssh" / "config"
    assert sshconfig.aliases() == ["mine"]


def test_no_config_names_no_host(tmp_path: Path) -> None:
    assert sshconfig.aliases() == []
    assert sshconfig.aliases(tmp_path / "missing") == []


def test_importing_writes_a_provider_per_host_naming_the_alias(
    user_home: Path, tmp_path: Path
) -> None:
    (user_home / ".ssh" / "config").write_text("Host gpu builder\n")
    config = tmp_path / "config"
    config.write_text("Host elsewhere odd:name\n")

    own = store.imports()
    theirs = store.imports(config)

    assert own == [
        SSHProvider(name="gpu", alias="gpu", made=IMPORTED),
        SSHProvider(name="builder", alias="builder", made=IMPORTED),
    ]
    assert theirs == [
        SSHProvider(
            name="elsewhere", alias="elsewhere", config=str(config), made=IMPORTED
        ),
    ]
    assert [one.name for one in store.providers("ssh")] == [
        "builder",
        "elsewhere",
        "gpu",
    ]
    assert store.imports(user_home / ".ssh" / "config", update=True)[0].config == ""


def test_importing_leaves_one_already_there_unless_told_to_update(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu\nHost other\n")
    (gpu,) = store.imports(config, ["gpu"])
    store.write(dataclasses.replace(gpu, alias="elsewhere", workdir="/srv"))

    assert [one.name for one in store.imports(config)] == ["other"]
    assert store.find("ssh", "gpu") == dataclasses.replace(
        gpu, alias="elsewhere", workdir="/srv"
    )
    (updated,) = store.imports(config, ["gpu"], update=True)
    assert updated == SSHProvider(
        name="gpu", alias="gpu", config=str(config), workdir="/srv", made=IMPORTED
    )


def test_one_typed_in_is_never_written_over_by_an_import(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu\nHost other\n")
    typed = SSHProvider(name="gpu", host="10.0.0.2", user="me", port=2222)
    store.add(typed)

    assert [one.name for one in store.imports(config, update=True)] == ["other"]
    with pytest.raises(ValueError, match="gpu was typed in"):
        store.imports(config, ["other", "gpu"], update=True)
    assert store.find("ssh", "gpu") == typed


def test_two_hosts_one_name_are_not_both_imported(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host a+b a-b\n")

    with pytest.raises(
        ValueError, match="a-b cannot be imported: a\\+b is imported as a-b"
    ):
        store.imports(config, ["a+b", "a-b"])
    assert store.providers() == []
    assert [one.alias for one in store.imports(config)] == ["a+b"]


def test_a_host_that_is_no_name_is_imported_under_one(tmp_path: Path) -> None:
    """And one `ssh` could never be handed as a destination is not imported at all."""
    config = tmp_path / "config"
    config.write_text("Host me@box _under box%1\n")

    written = store.imports(config)

    assert [(one.name, one.alias) for one in written] == [
        ("under", "_under"),
        ("box-1", "box%1"),
    ]
    with pytest.raises(ValueError, match="invalid ssh alias"):
        store.imports(config, ["me@box"])


def test_importing_a_host_the_config_does_not_name_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Host gpu\n")

    with pytest.raises(ValueError, match="ssh config has no host ghost"):
        store.imports(config, ["gpu", "ghost"])
    assert store.providers() == []
