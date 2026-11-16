"""`hmz.trust.devices`: the devices paired with this machine's daemon."""

from __future__ import annotations

import stat

import pytest
import yaml

from hmz.trust import identity
from hmz.trust.devices import FILE, Device, Devices

A, B, C = "a" * 52, "b" * 52, "dtls:" + "c" * 52


class Clock:
    """A clock a test moves, from 2026-01-01T00:00:00Z."""

    def __init__(self) -> None:
        self.now = 1_767_225_600.0

    def __call__(self) -> float:
        return self.now


def test_the_file_is_beside_the_identity() -> None:
    assert Devices().at == identity.directory() / FILE


def test_devices_are_added_in_order_with_exactly_their_keys() -> None:
    clock = Clock()
    devices = Devices(clock=clock)
    assert devices.add("laptop", A) == "laptop"
    clock.now += 5
    assert devices.add("phone", C) == "phone"
    assert devices.listed() == [
        Device("laptop", A, "2026-01-01T00:00:00Z", None),
        Device("phone", C, "2026-01-01T00:00:05Z", None),
    ]
    written = yaml.safe_load(devices.at.read_text())
    assert written == [
        {
            "name": "laptop",
            "fingerprint": A,
            "added": "2026-01-01T00:00:00Z",
            "seen": None,
        },
        {
            "name": "phone",
            "fingerprint": C,
            "added": "2026-01-01T00:00:05Z",
            "seen": None,
        },
    ]
    assert stat.S_IMODE(devices.at.stat().st_mode) == 0o600
    assert stat.S_IMODE(devices.at.parent.stat().st_mode) == 0o700


def test_a_name_taken_is_made_unique() -> None:
    devices = Devices()
    assert devices.add("laptop", A) == "laptop"
    assert devices.add("laptop", B) == "laptop#2"
    assert devices.add("laptop", C) == "laptop#3"


def test_a_device_paired_again_keeps_its_name() -> None:
    devices = Devices()
    devices.add("laptop", A)
    assert devices.add("other", A) == "laptop"
    assert len(devices.listed()) == 1


@pytest.mark.parametrize("name", ["", "-x", ".x", "a b", "a#2", "local", "é"])
def test_a_name_out_of_the_grammar_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        Devices().add(name, A)


def test_named_says_whether_a_fingerprint_is_paired() -> None:
    devices = Devices()
    devices.add("laptop", A)
    assert devices.named(A) == "laptop"
    assert devices.named(B) is None


def test_revoking_removes_it_and_tells_whoever_watches() -> None:
    devices = Devices()
    devices.add("laptop", A)
    devices.add("phone", B)
    told: list[Device] = []
    unwatch = devices.watch(told.append)
    gone = devices.revoke("laptop")
    assert gone.fingerprint == A
    assert told == [gone]
    assert devices.named(A) is None
    assert devices.named(B) == "phone"
    unwatch()
    devices.revoke("phone")
    assert told == [gone]


def test_local_is_not_revoked_and_an_unknown_name_is_not_found() -> None:
    devices = Devices()
    with pytest.raises(ValueError, match="local"):
        devices.revoke("local")
    with pytest.raises(LookupError, match=r"^There is no device nobody\.$"):
        devices.revoke("nobody")


def test_seen_is_written_at_most_once_a_minute() -> None:
    clock = Clock()
    devices = Devices(clock=clock)
    devices.add("laptop", A)
    devices.seen(A)
    assert devices.listed()[0].seen == "2026-01-01T00:00:00Z"
    clock.now += 59
    devices.seen(A)
    assert devices.listed()[0].seen == "2026-01-01T00:00:00Z"
    clock.now += 1
    devices.seen(A)
    assert devices.listed()[0].seen == "2026-01-01T00:01:00Z"
    devices.seen(B)
    assert [one.fingerprint for one in devices.listed()] == [A]


def test_a_file_deleted_unpairs_every_device() -> None:
    devices = Devices()
    devices.add("laptop", A)
    devices.at.unlink()
    assert devices.listed() == []
    assert devices.named(A) is None


def test_entries_that_are_not_devices_are_left_out() -> None:
    devices = Devices()
    devices.at.parent.mkdir(parents=True)
    devices.at.write_text(
        yaml.safe_dump(
            [
                {
                    "name": "a",
                    "fingerprint": A,
                    "added": "2026-01-01T00:00:00Z",
                    "seen": None,
                },
                {"name": "b", "fingerprint": B, "added": "yesterday", "seen": None},
                {"name": "c", "fingerprint": B, "added": "2026-01-01T00:00:00Z"},
                "nope",
            ]
        )
    )
    assert [one.name for one in devices.listed()] == ["a"]


def test_timestamps_yaml_reads_as_dates_are_read_back() -> None:
    devices = Devices()
    devices.at.parent.mkdir(parents=True)
    devices.at.write_text(
        f"- name: a\n  fingerprint: {A}\n  added: 2026-01-01T00:00:00Z\n"
        "  seen: 2026-01-02T00:00:00Z\n"
    )
    assert devices.listed() == [
        Device("a", A, "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
    ]


def test_a_file_that_is_not_yaml_pairs_nothing() -> None:
    devices = Devices()
    devices.at.parent.mkdir(parents=True)
    devices.at.write_text("[: nope")
    assert devices.listed() == []


def test_a_file_that_cannot_be_read_is_not_written_over() -> None:
    devices = Devices()
    devices.at.parent.mkdir(parents=True)
    devices.at.write_text("[: nope")
    with pytest.raises(ValueError, match="not YAML"):
        devices.add("laptop", A)
    devices.seen(A)
    assert devices.at.read_text() == "[: nope"
    devices.at.write_text("name: laptop\n")
    with pytest.raises(TypeError):
        devices.revoke("laptop")


def test_an_entry_that_is_not_a_device_is_written_back_as_it_was() -> None:
    devices = Devices()
    devices.at.parent.mkdir(parents=True)
    devices.at.write_text(yaml.safe_dump([{"name": "odd", "extra": 1}]))
    devices.add("laptop", A)
    devices.seen(A)
    devices.revoke("laptop")
    assert yaml.safe_load(devices.at.read_text()) == [{"name": "odd", "extra": 1}]
