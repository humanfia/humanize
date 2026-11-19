"""protocol/openrpc.json is an OpenRPC document, and says what the protocol's text says.

The two meta-schemas beside this file are `@open-rpc/meta-schema` 1.14.9 and the
`@json-schema-tools/meta-schema` 1.8.3 it refers to for every schema, as published, so the test
reads nothing off the network. The second is a draft 7 schema under an `$id` of its own.
"""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, cast

import pytest
from jsonschema import Draft7Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "protocol"
DOCUMENT = PROTOCOL / "openrpc.json"
META = Path(__file__).with_name("openrpc-meta-schema.json")
SCHEMA_META = Path(__file__).with_name("json-schema-meta-schema.json")

# The namespaces of Section 4 of daemon.md; a backticked `<namespace>.<name>` in the text names a
# method or a notification, but for the files the text also names that way.
NAMESPACES = (
    "accounts|aichan|backups|btw|devices|easytier|env|epic|files|flows|flowverses|hosts"
    "|notices|nous|pair|paths|rpc|runs|runtimes|session|settings|workspaces"
)
NAMED = re.compile(rf"`((?:{NAMESPACES})\.[a-z_]+)`")
NOT_METHODS = re.compile(r"\.(md|json|jsonl|yaml|yml|py)$")


def load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return load(DOCUMENT)


def names(document: dict[str, Any]) -> list[str]:
    methods = cast("list[dict[str, Any]]", document["methods"])
    told = cast("list[dict[str, Any]]", document["x-notifications"])
    return [m["name"] for m in methods] + [n["name"] for n in told]


def text() -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(PROTOCOL.glob("*.md"))
    )


class Validates(Protocol):
    """What of a jsonschema validator the tests use, typed."""

    def iter_errors(self, instance: object) -> Iterator[ValidationError]: ...
    def is_valid(self, instance: object) -> bool: ...


def validator() -> Validates:
    tools: Resource[Any] = DRAFT7.create_resource(load(SCHEMA_META))
    known = [
        ("https://meta.json-schema.tools", tools),
        ("https://meta.json-schema.tools/", tools),
    ]
    registry: Registry[Any] = Registry[Any]().with_resources(known)
    return cast("Validates", Draft7Validator(load(META), registry=registry))


def test_the_document_is_valid_openrpc(document: dict[str, Any]) -> None:
    errors = sorted(
        validator().iter_errors(document), key=lambda e: list(e.absolute_path)
    )
    assert not errors, "\n".join(
        f"{list(e.absolute_path)}: {e.message}" for e in errors
    )


def test_the_meta_schema_refuses_what_is_not_openrpc(document: dict[str, Any]) -> None:
    method = cast("list[dict[str, Any]]", document["methods"])[0]
    broken = {**document, "methods": [{**method, "params": [{"schema": {"type": 5}}]}]}
    assert not validator().is_valid(broken)


def test_every_schema_in_it_is_a_schema(document: dict[str, Any]) -> None:
    schemas = cast("dict[str, Any]", document["components"]["schemas"])
    for schema in schemas.values():
        Draft7Validator.check_schema(schema)
    told = cast("list[dict[str, Any]]", document["x-notifications"])
    for method in cast("list[dict[str, Any]]", document["methods"]) + told:
        for param in method["params"]:
            Draft7Validator.check_schema(param["schema"])
        if "result" in method:
            Draft7Validator.check_schema(method["result"]["schema"])


# What every method answers whatever it is (Section 6.11.3 of wire.md), and the three an unpaired
# session may call.
EVERY = {-32600, -32602, -32603, -32800, 413}
UNPAIRED = {"session.hello", "pair.claim", "rpc.discover"}


def test_every_method_lists_the_errors_every_method_answers(
    document: dict[str, Any],
) -> None:
    errors = cast("dict[str, dict[str, Any]]", document["components"]["errors"])
    for method in cast("list[dict[str, Any]]", document["methods"]):
        if method.get("x-notification"):
            assert "result" not in method, method["name"]
            assert "errors" not in method, method["name"]
            continue
        refs = [e["$ref"].rsplit("/", 1)[1] for e in method["errors"]]
        codes = {errors[name]["code"] for name in refs}
        wanted = EVERY if method["name"] in UNPAIRED else EVERY | {401}
        assert wanted <= codes, method["name"]
        assert "result" in method, method["name"]


def test_every_reference_in_it_resolves(document: dict[str, Any]) -> None:
    refs = re.findall(
        r'"\$ref": "#/components/(\w+)/(\w+)"', DOCUMENT.read_text("utf-8")
    )
    missing = {
        f"{kind}/{name}"
        for kind, name in refs
        if name not in document["components"][kind]
    }
    assert not missing


def test_methods_are_by_name_and_named_once(document: dict[str, Any]) -> None:
    every = names(document)
    assert len(every) == len(set(every))
    for method in cast("list[dict[str, Any]]", document["methods"]):
        assert method["paramStructure"] == "by-name", method["name"]


def test_every_method_is_in_the_protocol_text(document: dict[str, Any]) -> None:
    written = text()
    missing = [name for name in names(document) if f"`{name}`" not in written]
    assert not missing


def test_every_method_the_text_names_is_in_the_document(
    document: dict[str, Any],
) -> None:
    listed = set(names(document))
    named = {n for n in NAMED.findall(text()) if not NOT_METHODS.search(n)}
    assert named - listed == set()


# The scopes of `x-hmz-reach` and the parameters it may name (Section 4.21.2 of daemon.md).
SCOPES = {"any", "daemon", "workspace", "epic", "never"}
NAMES = {"workspace", "slot", "epic", "sub"}


def test_every_method_says_its_reach_and_whether_it_writes(
    document: dict[str, Any],
) -> None:
    for method in cast("list[dict[str, Any]]", document["methods"]):
        reach = cast("dict[str, str]", method["x-hmz-reach"])
        takes = {p["name"] for p in method["params"]}
        assert reach["scope"] in SCOPES, method["name"]
        named = set(reach) - {"scope"}
        assert named <= NAMES, method["name"]
        assert {reach[n] for n in named} <= takes, method["name"]
        assert isinstance(method["x-hmz-writes"], bool), method["name"]
        if "idem" in takes:
            assert method["x-hmz-writes"], method["name"]


def test_a_slot_of_any_host_may_be_one_of_ai_chan(document: dict[str, Any]) -> None:
    # A slot names a chat's host, an Ai-chan conversation's or an exec's (Section 4.2.6 of
    # daemon.md): a parameter taking the first and the last takes the one between them too.
    schemas = cast("dict[str, Any]", document["components"]["schemas"])
    for method in cast("list[dict[str, Any]]", document["methods"]):
        for param in method["params"]:
            if param["name"] != "slot":
                continue
            schema = cast("dict[str, Any]", param["schema"])
            if "$ref" in schema:
                schema = schemas[schema["$ref"].rsplit("/", 1)[1]]
            takes = cast("Validates", Draft7Validator(schema)).is_valid
            if takes("chat:01") and takes("exec:01"):
                assert takes("ai:01"), method["name"]
                assert takes(""), method["name"]
