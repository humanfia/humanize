"""What an agent may touch: the three kinds in order, the four scopes, and the rule they nest by."""

from __future__ import annotations

import copy
import dataclasses
import itertools
import operator
import pickle

import pytest

from hmz.flows import Permission, PermissionKind

NONE, READ, ALL = PermissionKind.NONE, PermissionKind.READ, PermissionKind.ALL


def test_the_kinds_order_the_way_they_widen_rather_than_alphabetically() -> None:
    assert NONE < READ < ALL
    assert ALL > READ > NONE
    for kind in PermissionKind:
        assert operator.le(kind, kind)
        assert operator.ge(kind, kind)
    assert NONE <= READ <= ALL
    assert ALL >= READ >= NONE
    assert sorted([ALL, NONE, READ]) == [NONE, READ, ALL]
    assert max(NONE, ALL, READ) is ALL
    assert not ALL < READ


def test_a_kind_orders_against_its_own_spelling_and_refuses_any_other() -> None:
    assert READ < "all"
    assert READ >= "read"
    with pytest.raises(TypeError, match="not a permission kind"):
        _ = READ < "everything"


def test_a_kind_is_still_the_string_it_is_written_as() -> None:
    assert ALL == "all"
    table: dict[str, int] = {ALL: 1}
    assert table["all"] == 1
    assert [one.value for one in PermissionKind] == ["none", "read", "all"]


def test_the_default_is_the_workdir_whole_the_rest_read_and_no_network() -> None:
    granted = Permission()
    assert (granted.local, granted.user, granted.system, granted.online) == (
        ALL,
        READ,
        READ,
        NONE,
    )


@pytest.mark.parametrize(
    ("local", "user", "system"),
    [
        (local, user, system)
        for local, user, system in itertools.product(PermissionKind, repeat=3)
        if local >= user >= system
    ],
)
@pytest.mark.parametrize("online", [NONE, ALL])
def test_every_nesting_of_the_scopes_is_a_permission(
    local: PermissionKind,
    user: PermissionKind,
    system: PermissionKind,
    online: PermissionKind,
) -> None:
    granted = Permission(local=local, user=user, system=system, online=online)
    assert granted.covers(granted)


@pytest.mark.parametrize(
    ("local", "user", "system"),
    [
        (local, user, system)
        for local, user, system in itertools.product(PermissionKind, repeat=3)
        if not local >= user >= system
    ],
)
def test_a_wider_scope_granted_more_than_a_narrower_one_is_refused(
    local: PermissionKind, user: PermissionKind, system: PermissionKind
) -> None:
    with pytest.raises(ValueError, match="wider scope"):
        Permission(local=local, user=user, system=system)


def test_the_network_is_all_or_nothing() -> None:
    with pytest.raises(ValueError, match="all or nothing"):
        Permission(online=READ)


def test_a_kind_written_as_its_string_is_read_as_the_kind() -> None:
    granted = Permission(local="all", user="read", system="none", online="all")  # pyright: ignore[reportArgumentType]
    assert granted.system is NONE
    assert granted == Permission(system=NONE, online=ALL)


@pytest.mark.parametrize("said", ["write", 2, None, [], {"a": 1}])
def test_anything_else_is_not_a_kind(said: object) -> None:
    with pytest.raises(ValueError, match="not a permission kind"):
        Permission(local=said)  # pyright: ignore[reportArgumentType]


def test_covering_is_scope_by_scope() -> None:
    wide = Permission(local=ALL, user=ALL, system=READ, online=ALL)
    narrow = Permission(local=ALL, user=READ, system=NONE, online=NONE)
    assert wide.covers(narrow)
    assert not narrow.covers(wide)
    assert not Permission(online=NONE).covers(Permission(online=ALL))
    assert not Permission(system=NONE).covers(Permission(system=READ))
    sideways = Permission(local=ALL, user=ALL, system=NONE)
    assert not sideways.covers(Permission(local=ALL, user=READ, system=READ))
    assert not Permission(local=ALL, user=READ, system=READ).covers(sideways)


def test_a_permission_is_a_value() -> None:
    granted = Permission(user=NONE, system=NONE)
    with pytest.raises(dataclasses.FrozenInstanceError):
        granted.local = NONE  # pyright: ignore[reportAttributeAccessIssue]
    assert hash(granted) == hash(Permission(user=NONE, system=NONE))
    assert pickle.loads(pickle.dumps(granted)) == granted  # noqa: S301 -- its own
    assert copy.deepcopy(granted) == granted
