"""`hmz.trust.pairing`: one-time codes, and claiming them."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import pytest

from hmz.trust import pairing
from hmz.trust.devices import Devices

if TYPE_CHECKING:
    from pathlib import Path

ID = "a" * 52


def admitted() -> str:
    return "admitted"


class Clock:
    """A clock a test moves."""

    def __init__(self) -> None:
        self.now = 1_000_000.5

    def __call__(self) -> float:
        return self.now


def decoded(text: str) -> dict[str, object]:
    body = text.removeprefix(pairing.PREFIX)
    assert "=" not in body
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def test_a_code_is_the_prefix_and_base64url_json_of_exactly_its_keys() -> None:
    clock = Clock()
    code = pairing.Codes(clock).make(ID, ["tcp://h:1", "relay:wss://r"])
    text = code.text()
    assert text.startswith("hmz-pair:")
    said = decoded(text)
    assert said == {
        "v": 1,
        "id": ID,
        "routes": ["tcp://h:1", "relay:wss://r"],
        "token": code.token,
        "expires": 1_000_600,
    }
    token = code.token
    assert "=" not in token
    assert len(base64.urlsafe_b64decode(token + "=")) == 32
    assert pairing.read(text) == code


def test_each_code_has_a_token_of_its_own() -> None:
    codes = pairing.Codes()
    assert codes.make(ID, ["tcp://h:1"]).token != codes.make(ID, ["tcp://h:1"]).token


@pytest.mark.parametrize("seconds", [59, 86_401, 0, True, 600.0])
def test_a_lifetime_out_of_bounds_is_refused(seconds: int) -> None:
    with pytest.raises(ValueError, match=r"^A code lives 60 to 86400 seconds\.$"):
        pairing.Codes().make(ID, ["tcp://h:1"], seconds)


@pytest.mark.parametrize("seconds", [60, 86_400])
def test_a_lifetime_in_bounds_is_kept(seconds: int) -> None:
    clock = Clock()
    assert (
        pairing.Codes(clock).make(ID, ["tcp://h:1"], seconds).expires
        == 1_000_000 + seconds
    )


def test_a_code_is_claimed_once() -> None:
    codes = pairing.Codes()
    code = codes.make(ID, ["tcp://h:1"])
    codes.claims(code.token, admitted)
    with pytest.raises(
        pairing.InvalidCodeError, match=r"^That pairing code is not valid"
    ):
        codes.claims(code.token, admitted)


def test_an_expired_code_is_refused() -> None:
    clock = Clock()
    codes = pairing.Codes(clock)
    code = codes.make(ID, ["tcp://h:1"], 60)
    clock.now = code.expires
    with pytest.raises(pairing.InvalidCodeError):
        codes.claims(code.token, admitted)


def test_a_code_just_before_it_expires_admits() -> None:
    clock = Clock()
    codes = pairing.Codes(clock)
    code = codes.make(ID, ["tcp://h:1"], 60)
    clock.now = code.expires - 0.5
    codes.claims(code.token, admitted)


def test_a_token_never_made_is_refused() -> None:
    codes = pairing.Codes()
    codes.make(ID, ["tcp://h:1"])
    with pytest.raises(pairing.InvalidCodeError):
        codes.claims("nope", admitted)


def test_at_most_sixteen_are_held_and_the_oldest_goes() -> None:
    codes = pairing.Codes()
    made = [codes.make(ID, ["tcp://h:1"]) for _ in range(pairing.HELD + 1)]
    with pytest.raises(pairing.InvalidCodeError):
        codes.claims(made[0].token, admitted)
    for code in made[1:]:
        codes.claims(code.token, admitted)


def text(said: object) -> str:
    return pairing.PREFIX + base64.urlsafe_b64encode(json.dumps(said).encode()).decode()


GOOD = {"v": 1, "id": ID, "routes": ["tcp://h:1"], "token": "t", "expires": 5}


@pytest.mark.parametrize(
    "said",
    [
        "hmz-pear:abc",
        "hmz-pair:!!!",
        "hmz-pair:" + base64.urlsafe_b64encode(b"[1]").decode(),
        text({**GOOD, "extra": 1}),
        text({k: v for k, v in GOOD.items() if k != "token"}),
        text({**GOOD, "v": 2}),
        text({**GOOD, "v": True}),
        text({**GOOD, "v": 1.0}),
        text({**GOOD, "id": "A" * 52}),
        text({**GOOD, "routes": "tcp://h:1"}),
        text({**GOOD, "routes": [1]}),
        text({**GOOD, "routes": []}),
        text({**GOOD, "token": 1}),
        text({**GOOD, "expires": "5"}),
        text({**GOOD, "expires": False}),
    ],
)
def test_what_is_not_a_code_is_refused(said: str) -> None:
    with pytest.raises(ValueError, match="not a pairing code"):
        pairing.read(said)


def test_a_code_is_read_with_white_space_around_it() -> None:
    assert pairing.read(f"  {text(GOOD)}\n").token == "t"


def test_an_unpaired_session_may_say_hello_claim_and_discover_alone() -> None:
    for method in ("session.hello", "pair.claim", "rpc.discover"):
        assert pairing.allows(method, paired=False)
    assert not pairing.allows("epic.attach", paired=False)
    assert not pairing.allows("pair.create", paired=False)
    assert pairing.allows("epic.attach", paired=True)
    assert (
        pairing.NOT_PAIRED == "This device is not paired: claim a pairing code first."
    )


def test_claiming_pairs_the_device_of_the_session(tmp_path: Path) -> None:
    codes = pairing.Codes()
    devices = Devices(tmp_path / "devices.yaml")
    code = codes.make(ID, ["tcp://h:1"])
    assert pairing.claim(codes, devices, code.token, "laptop", "f" * 52) == "laptop"
    assert devices.named("f" * 52) == "laptop"
    with pytest.raises(pairing.InvalidCodeError):
        pairing.claim(codes, devices, code.token, "laptop", "g" * 52)
    assert devices.named("g" * 52) is None


def test_a_claim_of_a_bad_name_leaves_the_code_held(tmp_path: Path) -> None:
    codes = pairing.Codes()
    devices = Devices(tmp_path / "devices.yaml")
    code = codes.make(ID, ["tcp://h:1"])
    with pytest.raises(ValueError, match="name"):
        pairing.claim(codes, devices, code.token, "-bad", "f" * 52)
    assert pairing.claim(codes, devices, code.token, "good", "f" * 52) == "good"


def test_a_claim_whose_device_cannot_be_written_leaves_the_code_held(
    tmp_path: Path,
) -> None:
    codes = pairing.Codes()
    code = codes.make(ID, ["tcp://h:1"])
    blocked = tmp_path / "file"
    blocked.write_text("")
    with pytest.raises(OSError, match=r"."):
        pairing.claim(
            codes, Devices(blocked / "devices.yaml"), code.token, "a", "f" * 52
        )
    devices = Devices(tmp_path / "devices.yaml")
    assert pairing.claim(codes, devices, code.token, "a", "f" * 52) == "a"
