"""Refs, and the modules they are loaded from.

Every form a ref takes, relative and not; the bare-ref rule; a flow directory imported as a
module with what it keeps beside it importable by a plain name; one import per run however
often a ref is loaded; two checkouts of one name refused while a run uses one of them; and a
flow edited between two runs being the flow the second one runs. `git+` refs need git, and
are the integration tier's.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz.flows import (
    AgentCollection,
    EnvCollection,
    FlowContext,
    FlowDefinitionError,
    FlowLoadConflict,
    FlowNotFound,
    FlowParams,
    FlowRefError,
    HarnessKind,
    flow,
    load,
)
from hmz.runtime.flowing import loading
from hmz.runtime.flowing.engine import FlowImpl, load_flow
from hmz.runtime.flowing.fakes import FakeAgentDriver, run_fake
from hmz.runtime.flowing.loading import parse
from tests.flows.kit import flowverse

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _nobody_s_flows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Looks for flows nowhere but under the test's own directory."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)


# ------------------------------------------------------------------------------ refs


@pytest.mark.parametrize(
    ("ref", "url", "rev", "where", "sub"),
    [
        (":review", None, None, "", "review"),
        ("humanize1", None, None, "humanize1", ""),
        ("humanize1:gen-plan", None, None, "humanize1", "gen-plan"),
        ("official/rlar", None, None, "official/rlar", ""),
        ("local/scheduler:inner", None, None, "local/scheduler", "inner"),
        ("./flows/x", None, None, "./flows/x", ""),
        ("/abs/flows/x:y", None, None, "/abs/flows/x", "y"),
        ("C:/odd/path", None, None, "C:/odd/path", ""),
        (
            "git+https://github.com/humanfia/flowverse@main#humanize1:rlcr",
            "https://github.com/humanfia/flowverse",
            "main",
            "humanize1",
            "rlcr",
        ),
        (
            "git+ssh://git@github.com/humanfia/flowverse.git@v1.2#humanize1",
            "ssh://git@github.com/humanfia/flowverse.git",
            "v1.2",
            "humanize1",
            "",
        ),
        (
            "git+file:///tmp/repo#flow:sub",
            "file:///tmp/repo",
            None,
            "flow",
            "sub",
        ),
    ],
)
def test_a_ref_is_read(
    ref: str, url: str | None, rev: str | None, where: str, sub: str
) -> None:
    said = parse(ref)
    assert (said.url, said.rev, said.where, said.sub) == (url, rev, where, sub)
    assert repr(said).startswith("Ref(")


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "   ",
        ":",
        ":has space",
        "flow:",
        "flow:has space",
        ":a:b",
        "https://github.com/x/y#flow",
        "git+https://github.com/x/y#",
        "git+https://github.com/x/y#:sub",
        "git+https://github.com/x/y#flow:",
        "git+ftp://host/x#flow",
        "git+https:///#flow",
        "git+git@github.com:x/y#flow",
        3,
    ],
    ids=repr,
)
def test_what_is_no_ref_is_refused(ref: Any) -> None:
    with pytest.raises(FlowRefError) as raised:
        parse(ref)
    assert isinstance(raised.value, ValueError)


def test_a_relative_ref_with_no_flow_asking_is_refused() -> None:
    with pytest.raises(FlowRefError, match="no flow is asking"):
        load_flow(":anything", caller_globals={"__name__": "elsewhere"})


# -------------------------------------------------------------------------- flowverses

ALPHA = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow, load
from _alpha import helper


class Params(FlowParams):
    n: int = 0


@flow(agents=AgentCollection, envs=EnvCollection, params=Params)
async def alpha(task, *, agents, envs, params, ctx):
    said = [helper(task)]
    said.append(await load(":inner")(task, agents={}, envs={}, params=Params()))
    said.append(await load("beta")(task, agents={}, envs={}, params={}))
    said.append(await load("beta:second")(task, agents={}, envs={}, params={}))
    return said


@flow(agents=AgentCollection, envs=EnvCollection, params=Params, hidden=True)
async def inner(task, *, agents, envs, params, ctx):
    from _alpha import deeper
    return deeper(task) + " " + ctx.flow.ref
"""

ALPHA_HELPER = """
def helper(task):
    return f"helped {task}"


def deeper(task):
    return f"inner {task}"
"""

BETA = """
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def first(task, *, agents, envs, params, ctx):
    return "beta's only visible flow"


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, name="second", hidden=True)
async def second_flow(task, *, agents, envs, params, ctx):
    return "beta:second"
"""


def _verse(at: Path) -> Path:
    return flowverse(
        at,
        {
            "alpha": {"__init__.py": ALPHA, "_alpha/__init__.py": ALPHA_HELPER},
            "beta": BETA,
        },
    )


async def test_every_relative_form_resolves_inside_a_flowverse(tmp_path: Path) -> None:
    flows = _verse(tmp_path)
    said = await run_fake(str(flows / "alpha"), "t")
    assert said == [
        "helped t",
        "inner t alpha:inner",
        "beta's only visible flow",
        "beta:second",
    ]


async def test_a_flowverse_of_this_project_is_found_by_name(tmp_path: Path) -> None:
    _verse(tmp_path / ".humanize")
    assert await run_fake("beta:second") == "beta:second"
    assert await run_fake("local/beta:second") == "beta:second"
    assert (await run_fake("alpha", "t"))[0] == "helped t"
    with pytest.raises(FlowNotFound, match="no flow is called"):
        await run_fake("gamma")
    with pytest.raises(FlowNotFound, match="no flow called 'third'"):
        await run_fake("beta:third")


def test_a_bare_ref_is_the_flow_named_after_its_directory(tmp_path: Path) -> None:
    flows = _verse(tmp_path)
    alpha: Any = load(str(flows / "alpha"))
    assert alpha.name == "alpha"
    assert alpha.ref == "alpha:alpha"
    beta: Any = load(str(flows / "beta"))
    assert beta.name == "first"


def test_a_bare_ref_to_a_module_of_many_visible_flows_names_them(
    tmp_path: Path,
) -> None:
    flows = flowverse(
        tmp_path,
        {
            "many": """
            from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
            async def one(task, *, agents, envs, params, ctx): ...

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
            async def two(task, *, agents, envs, params, ctx): ...
            """,
            "none": "x = 1\n",
        },
    )
    with pytest.raises(FlowNotFound, match="one, two"):
        load(str(flows / "many"))
    assert load(f"{flows / 'many'}:two").description is None
    with pytest.raises(FlowNotFound, match="defines no flow"):
        load(str(flows / "none"))


def test_a_flow_file_is_a_flow_too(tmp_path: Path) -> None:
    alone = tmp_path / "alone.py"
    alone.write_text(
        "from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow\n"
        "@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)\n"
        "async def alone(task, *, agents, envs, params, ctx):\n"
        "    return 'alone'\n",
        encoding="utf-8",
    )
    found: Any = load(str(alone))
    assert found.name == "alone"
    assert load(str(tmp_path / "alone")) is found


def test_a_flow_imported_from_elsewhere_is_not_a_subflow(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "own": """
            from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow
            from theirs_helpers import borrowed

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
            async def own(task, *, agents, envs, params, ctx): ...
            """,
        },
    )
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "theirs_helpers.py").write_text(
        "from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow\n"
        "@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)\n"
        "async def borrowed(task, *, agents, envs, params, ctx): ...\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path / "lib"))
    try:
        with pytest.raises(FlowNotFound, match="holds no flow called 'borrowed'"):
            load(f"{flows / 'own'}:borrowed")
    finally:
        sys.path.remove(str(tmp_path / "lib"))
        sys.modules.pop("theirs_helpers", None)


def test_two_flows_of_one_name_in_one_module_are_refused(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "twice": """
            from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, name="x")
            async def a(task, *, agents, envs, params, ctx): ...

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams, name="x")
            async def b(task, *, agents, envs, params, ctx): ...
            """,
        },
    )
    with pytest.raises(FlowDefinitionError, match="two flows"):
        load(f"{flows / 'twice'}:x")


def test_a_flow_that_will_not_import_is_written_wrong(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "broken": "raise RuntimeError('no')\n",
            "syntax": "def (:\n",
            "bad_decl": """
            from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

            @flow(agents=dict, envs=EnvCollection, params=FlowParams)
            async def bad_decl(task, *, agents, envs, params, ctx): ...
            """,
        },
    )
    with pytest.raises(FlowDefinitionError, match="failed") as raised:
        load(str(flows / "broken"))
    assert isinstance(raised.value.__cause__, RuntimeError)
    with pytest.raises(FlowDefinitionError):
        load(str(flows / "syntax"))
    with pytest.raises(FlowDefinitionError, match="AgentCollection"):
        load(str(flows / "bad_decl"))
    assert "broken" not in sys.modules
    assert str(flows / "broken") not in sys.path


# --------------------------------------------------------------------- the module cache

COUNTED = """
import builtins
from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow, load

builtins.hmz_imported = getattr(builtins, "hmz_imported", 0) + 1
VERSION = {version!r}


class Params(FlowParams):
    left: int = 0


@flow(agents=AgentCollection, envs=EnvCollection, params=Params)
async def counted(task, *, agents, envs, params, ctx):
    if params.left:
        below = Params(left=params.left - 1)
        return await load(":counted")(task, agents={{}}, envs={{}}, params=below)
    return VERSION
"""


@pytest.fixture
def imports() -> Any:
    import builtins

    builtins.hmz_imported = 0  # pyright: ignore[reportAttributeAccessIssue]
    yield builtins
    del builtins.hmz_imported  # pyright: ignore[reportAttributeAccessIssue]


async def test_a_run_imports_a_flow_once_however_often_it_is_loaded(
    tmp_path: Path, imports: Any
) -> None:
    flows = flowverse(tmp_path, {"counted": COUNTED.format(version="one")})
    assert await run_fake(str(flows / "counted"), params={"left": 50}) == "one"
    assert imports.hmz_imported == 1


async def test_a_flow_edited_between_runs_is_the_flow_the_next_run_runs(
    tmp_path: Path, imports: Any
) -> None:
    flows = flowverse(tmp_path, {"counted": COUNTED.format(version="one")})
    assert await run_fake(str(flows / "counted")) == "one"
    assert await run_fake(str(flows / "counted")) == "one"
    assert imports.hmz_imported == 1
    entry = flows / "counted" / "__init__.py"
    entry.write_text(COUNTED.format(version="a longer two"), encoding="utf-8")
    assert await run_fake(str(flows / "counted")) == "a longer two"
    assert imports.hmz_imported == 2


async def test_a_flow_runs_as_it_was_loaded_even_if_edited_since(
    tmp_path: Path, imports: Any
) -> None:
    flows = flowverse(tmp_path, {"counted": COUNTED.format(version="one")})
    loaded = load(str(flows / "counted"))
    entry = flows / "counted" / "__init__.py"
    entry.write_text(COUNTED.format(version="a longer two"), encoding="utf-8")
    assert await run_fake(loaded, params={"left": 3}) == "one"
    assert imports.hmz_imported == 1
    assert await run_fake(str(flows / "counted"), params={"left": 3}) == "a longer two"
    assert imports.hmz_imported == 2


def test_modules_are_let_go_only_when_nobody_runs_them(tmp_path: Path) -> None:
    flows = flowverse(tmp_path, {"counted": COUNTED.format(version="one")})
    load(str(flows / "counted"))
    assert "counted" in sys.modules
    assert str(flows / "counted") in sys.path
    [held] = [one for one in loading.modules() if one.name == "counted"]
    held.pins += 1
    try:
        loading.forget()
        assert "counted" in sys.modules
    finally:
        held.pins -= 1
    loading.forget()
    assert "counted" not in sys.modules
    assert str(flows / "counted") not in sys.path


def test_forgetting_one_flowverse_leaves_every_other_flow_as_it_was(
    tmp_path: Path,
) -> None:
    mine = flowverse(tmp_path / "mine", {"counted": COUNTED.format(version="one")})
    theirs = flowverse(tmp_path / "theirs", {"kept": COUNTED.format(version="two")})
    load(str(mine / "counted"))
    load(str(theirs / "kept"))
    kept = sys.modules["kept"]
    loading.forget(mine)
    assert "counted" not in sys.modules
    assert str(mine / "counted") not in sys.path
    assert sys.modules["kept"] is kept
    assert str(theirs / "kept") in sys.path


async def test_two_checkouts_of_one_flow_conflict_while_one_is_running(
    tmp_path: Path,
) -> None:
    ours = _verse(tmp_path / "ours")
    theirs = _verse(tmp_path / "theirs")
    load(str(ours / "alpha"))

    @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
    async def both(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> Any:
        first: Any = load(str(ours / "alpha"))
        with pytest.raises(FlowLoadConflict):
            load(str(theirs / "alpha"))
        return first

    first = await run_fake(both)
    second: Any = load(str(theirs / "alpha"))
    assert first is not second
    assert second.fn.__code__.co_filename.startswith(str(theirs))


def test_a_flow_is_not_imported_over_a_module_that_is_no_flow(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {
            "json": """
            from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

            @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
            async def json(task, *, agents, envs, params, ctx): ...
            """,
            "clashing": {
                "__init__.py": """
                from hmz.flows import AgentCollection, EnvCollection, FlowParams, flow

                @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
                async def clashing(task, *, agents, envs, params, ctx): ...
                """,
                "pytest.py": "",
            },
        },
    )
    import json

    found: Any = load(str(flows / "json"))
    assert found.name == "json"
    assert found.ref == "json:json", "the ref followed the name it was imported as"
    assert sys.modules["json"] is json
    with pytest.raises(FlowLoadConflict, match="pytest"):
        load(str(flows / "clashing"))


async def test_a_flow_defined_in_a_test_finds_the_flows_beside_it() -> None:
    assert await run_fake(beside_me, "t") == "neighbour t"
    found: Any = load_flow(":neighbour", caller_globals=globals())
    assert found is neighbour


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def beside_me(
    task: str,
    *,
    agents: AgentCollection,
    envs: EnvCollection,
    params: FlowParams,
    ctx: FlowContext,
) -> Any:
    return await load(":neighbour")(task, agents={}, envs={}, params=params)


@flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
async def neighbour(
    task: str,
    *,
    agents: AgentCollection,
    envs: EnvCollection,
    params: FlowParams,
    ctx: FlowContext,
) -> str:
    return f"neighbour {task}"


async def test_flows_defined_in_one_function_find_each_other() -> None:
    @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
    async def first_one(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> str:
        return "first"

    @flow(agents=AgentCollection, envs=EnvCollection, params=FlowParams)
    async def second_one(
        task: str,
        *,
        agents: AgentCollection,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> str:
        return await load(":first_one")(task, agents={}, envs={}, params=params)

    assert await run_fake(second_one) == "first"
    del first_one


def test_a_relative_ref_from_a_module_holding_flows_resolves_among_them() -> None:
    found = load(":neighbour")
    assert found is neighbour
    assert type(found) is FlowImpl


# ------------------------------------------------------------------------------ skills

SKILLED = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, flow


class Reviewer(Agent):
    _skills = ({skill!r},)


class Agents(AgentCollection):
    reviewer: Reviewer


@flow(agents=Agents, envs=EnvCollection, params=FlowParams)
async def skilled(task, *, agents, envs, params, ctx):
    return agents["reviewer"].grant.skills
"""


async def test_a_role_s_skills_are_found_in_its_flow_s_own_skills(
    tmp_path: Path,
) -> None:
    flows = flowverse(
        tmp_path,
        {
            "skilled": {
                "__init__.py": SKILLED.format(skill="review"),
                "skills/review/SKILL.md": "how to review",
            },
            "unskilled": {"__init__.py": SKILLED.format(skill="missing")},
        },
    )
    assert await run_fake(str(flows / "skilled")) == ("review",)
    with pytest.raises(FlowDefinitionError, match="'missing'"):
        await run_fake(str(flows / "unskilled"))


FULL = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow
from hmz.runtime.flowing.engine import full_view


class Chatter(Agent):
    _skills = ("review",)


class Agents(AgentCollection):
    chatter: Chatter


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def chat(task, *, agents, envs, params, ctx):
    chatter = agents["chatter"]
    await chatter.spawn(env=envs["here"])
    return sorted(one.__name__ for one in chatter.grant.capabilities)


full_view(chat)
"""


async def test_a_full_view_flow_keeps_the_skills_its_roles_name(tmp_path: Path) -> None:
    flows = flowverse(
        tmp_path,
        {"chat": {"__init__.py": FULL, "skills/review/SKILL.md": "how to review"}},
    )
    driver = FakeAgentDriver(HarnessKind.PI)
    granted = await run_fake(str(flows / "chat"), agents={"chatter": driver})
    assert granted == ["AskUserHookAgentMixin", "SteeringAgentMixin"]
    assert [one.name for one in driver.sessions[0].skills] == ["review"]


async def test_concurrent_calls_share_one_fetch_of_their_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from hmz.runtime.flowing import engine

    fetched: list[str] = []
    real = engine._skills_for

    def counting(flow: Any, role: Any) -> Any:
        fetched.append(role.name)
        return real(flow, role)

    monkeypatch.setattr(engine, "_skills_for", counting)
    flows = flowverse(
        tmp_path,
        {
            "skilled": {
                "__init__.py": SKILLED.format(skill="review"),
                "skills/review/SKILL.md": "how to review",
            },
        },
    )
    skilled: Any = load(str(flows / "skilled"))

    from hmz.flows import Agent

    class Workers(AgentCollection):
        worker: Agent

    @flow(agents=Workers, envs=EnvCollection, params=FlowParams)
    async def many(
        task: str,
        *,
        agents: Workers,
        envs: EnvCollection,
        params: FlowParams,
        ctx: FlowContext,
    ) -> Any:
        worker = agents["worker"]
        return await asyncio.gather(
            *(
                skilled(task, agents={"reviewer": worker}, envs={}, params=params)
                for _ in range(20)
            )
        )

    said = await run_fake(many)
    assert fetched == ["reviewer"]
    assert said == [("review",)] * 20
