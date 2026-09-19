# Flows

## File Structure

```
.
├── __init__.py
├── agent.py
├── atlas.py
└── builtin
```

The whole of what a flow imports, and nothing else: what it drives, the mark that makes a
function a flow, the marks an atlas declares its graph with, and the vocabulary a turn is
described in. Nothing here finds a flow, reads one, runs one or compiles one -- all of that is
`hmz.runtime.flowing`, specified in [flowing.md](flowing.md), which is written against this and
which nothing here imports at the top of its file.

This MUST be the whole of what a flow imports. A flow is content -- somebody else's
repository, forked and edited -- and one that named `hmz.coganchor.agents` for the type of what it
drives and `hmz.coganchor.backends` for a fact about a CLI would be a flow that breaks whenever
humanize moves either. So the one import a flow writes MUST be `hmz.flows`, and whatever a
flow legitimately needs that is written down in another layer MUST be handed through from
here rather than reached for. What is handed through MUST be fetched when a flow names it
rather than imported with this module: this is also what a command line is routed through
before it knows whether it names a flow at all, and that MUST NOT pay for every coding agent
driver there is.

What MUST NOT be here is everything humanize does *to* a flow. A flow declares itself and
humanize does the reading, so a module that only ever reads, lists, checks, compiles or drives
a flow is a module no flow can name and therefore no flow can break on: it MUST live in
`hmz.runtime.flowing` instead. What is left here MUST be the interfaces, the marks and the
hand-through, and MUST hold as little implementation as saying that takes.

A flow MUST be a module, and there MUST be two shapes of one: a directory with an
`__init__.py` in it -- beside whatever it imports and a `skills/` of the skills it works by --
and a single `.py` file, which is what a flow that is one function still is. The directory MUST
win a name a file also uses, being the one that says most about itself.

Everything a flow needs MUST live inside its own directory, so that a flow can be copied,
forked and edited whole: a flow whose parts are elsewhere is a flow with a hole in it wherever
it is copied to. A flow that is a single file therefore brings no skills -- what is beside it
is the other flows, and none of it came with that one.

## `builtin/`

The flows humanize keeps in the package: a directory of flows and nothing else.

- Its flows MUST be read where they stand rather than from a `flows/` inside it. A fetched
  flowverse needs that directory to tell its flows from the repository around them; there is
  no repository around these, and a directory holding nothing else has nothing to tell them
  from.

- It MUST hold `chat` and nothing else. That is what humanize does before anything has been
  fetched, and a first run that had to clone before it could say hello is a first run that
  fails without a network. Everything else humanize offers MUST live in the official
  flowverse: a flow is content, and content that can change without a release is content that
  keeps up.

- It MUST NOT be a place of its own as far as anybody running a flow is concerned. Which of
  its two places a flow of humanize's is kept in is humanize's business, so this directory and
  the official flowverse MUST be listed, offered and resolved as the one place, `official`,
  and a flow moved from here to there MUST go on answering to the name it always had.

## `__init__.py`

```python
@dataclass(frozen=True, slots=True)
class Flow:
    name: str = ""
    about: str = ""
    skills: tuple[str, ...] = ()
    resumable: bool = False
    selectable: bool = True
    budget: Allowance | None = None


def flow[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
    budget: Allowance | None = None,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def __getattr__(name: str) -> object: ...
```

The mark that makes a function a flow, what that mark says, and the one door everything else a
flow writes is reached through.

- A flow MUST be a function marked with `flow`, and nothing else MUST be one: a flow is read by
  running its entry point, and which of the functions that leaves behind is a flow is the
  flow's to say rather than something to read off a name. One flow MAY hold several: `flow`
  with no name MUST be the one it holds under its directory's own name, and `flow(name=...)`
  MUST be one of its own, called `<flow>:<name>` -- so that three phases of one thing are one
  thing to write and three to run, each asking only for the agents it drives and only for the
  settings it takes.
- `flow` MUST mark rather than wrap. A flow is called the way it always was, and a decorator
  between the flow and whatever reads its arguments would be a decorator that has to answer for
  them. What it marks with MUST travel on the function, since a file is read by running it.
- A name MUST be what the mark was told and nothing else: a name written down where a flow is
  run -- a command line, a settings file, another flow asking for this one -- MUST NOT change
  under whoever renames the function. A file that marks two flows with one name MUST answer
  with the first of them, that being a file to correct rather than a choice to make at random.
- A flow MAY say that it can be picked up where the last run of it left off, which is what a
  loop meant to run for a week is: it is stopped and started, by a machine going down or by
  somebody pressing esc. Such a flow MUST be handed a dict as its last argument, holding what
  it wrote there last time -- so that what it is keeping track of is the flow's own handful of
  things rather than a second copy of the transcript, which the backends already keep.
- A flow MUST NOT hold itself to a budget of its own. What a run may spend MUST be held to
  once, centrally, off the meters every backend already feeds -- a cap a flow implements is a
  cap only that flow has, reading only the tokens that flow happened to count, and one nobody
  can set from the menu they set everything else with. A flow MAY say what a run of it is
  worth by default, which is `budget=`, and MUST be overridable by whoever starts the run.
- That default MUST have three states and not two, because the third is what keeps a flow
  that is meant to run unbounded from being asked about it every time. Saying nothing MUST be
  a flow with no opinion, which runs under whatever the workspace was set up with; an
  `Allowance` with something in it MUST be the flow's own default; and an `Allowance()`
  written out MUST be a flow claiming in its own file that it is meant to run under nothing at
  all. Whatever asks somebody to confirm an unbounded run MUST read that claim rather than
  name a flow, so that the exemption is one reviewable line in the flow's file and MUST NOT be
  a list of names kept in the interface, the command line and the settings alike.
- What a flow says about itself MUST be the first line of its docstring where the decorator was
  not told one, and for a file that is one flow MUST fall back to the file's own docstring: a
  file that is one flow is documented as that flow.
- A flow MAY say it is not to be offered in a list of them. A flow reached only by another
  flow -- one phase of a thing, an engine two flows share -- is a flow to call by name and not
  a flow to start, and one that appeared in the picker would be a line nobody can act on.
- This module MUST be everything a flow imports, which is the interfaces beside it, the marks
  an atlas is written with, the mark itself, and what is written down in another layer handed
  through: the vocabulary a turn is described in, the facts about the CLIs and what each of
  them runs, where humanize keeps what outlives a run, and what it takes for one flow to run
  another. What is handed through MUST be the same object the layer it is written in holds, so
  that a flow and humanize are talking about one thing.
- What is handed through MUST be fetched when it is asked for, by name and never by import.
  Importing this module MUST cost no more than reading a directory: a menu of flows is drawn
  from it, and a command line is routed through it before it knows whether it names a flow at
  all.
- Some of what is handed through is written in the layer *above* -- `load`, which is one flow
  running another, is a run and runs are the runtime's. That MUST be handed through the same
  way as everything else and MUST NOT be imported: a flow that never calls another flow MUST
  NOT pay for the runtime by writing `@flow`, and the arrow between the two layers MUST go on
  pointing one way whenever anything is actually running.

## `agent.py`

```python
class Session(Protocol): ...


class Agent(Protocol): ...


class Driven(Agent, Protocol): ...


class Person(Agent, Protocol): ...
```

What a flow drives, written as interfaces and nothing else.

- What a flow may ask of an agent MUST be written down here and MUST be the whole of what a
  flow is written against. A flow that named the class behind it would be a flow written
  against which CLI is being driven, how a turn is spelled to that CLI and where its logs go,
  none of which is a flow's business and all of which moves.
- It MUST hold what a flow asks of an agent, and what whoever hands an agent to a flow settles
  on it: a turn, a session, a goal, a batch, what the run has cost, what is hung on the moments
  of a turn, what the agent is configured with, the run it is part of, and where its turns
  land. Nothing about starting a process, reading a stream or falling back to another account
  MUST be here, being how an agent is driven rather than what a flow drives -- and nothing here
  MUST be reachable only through the class, since a flow that called another hands over what it
  was given and the called flow is handed the same thing.
- The two MUST be two interfaces. What an agent *is* -- what it runs, where its turns land,
  what it is called, which of a flow's skills it carries -- is an answer somebody already
  gave, at a prompt or on a command line or in a settings file, and a flow that could change
  one of them would be a flow rewriting the choice its run was started with. So `Agent` MUST
  be what a flow may ask and MUST NOT include the settling, and `Driven` MUST be `Agent` plus
  it: whoever hands an agent over holds one of those, and a flow declares the other. What is
  written down here MUST be the whole of both, and the drivers MUST answer to both.
- A flow that wants an agent set up differently MUST make one, which MUST be `Agent.clone`:
  it says what is to differ and there MUST be nowhere to say it again. What it answers MUST be
  another agent rather than this one changed -- its own name where none was given, having
  opened nothing, spent nothing, watched by nobody, hooked to nothing and written down
  nowhere -- since two agents at two efforts are two agents, and a trace that read them as one
  would read a comparison as one agent changing its mind. Everything the call does not name
  MUST be the agent it came from, the skills it carries included.
- A flow that wants two ways out of one conversation MUST be able to branch it, which MUST be
  `Session.fork`: a second conversation carrying this one's history, going its own way from
  the moment it was made. It is the other half of `Agent.clone` and MUST NOT share its word --
  an agent is structure, so its clone knows nothing; a session is history, so its fork knows
  everything this one knows, and two things sharing one name is a flow author having to be
  told which is meant. What the child costs MUST be the child's: its own id, its own spending,
  its own line in the run's record, and nothing spent on the one it came from counted twice. A
  backend with no fork of its own MUST refuse it where it is asked rather than hand back a
  second handle on the one conversation, and MUST say beforehand whether it can, so that a
  flow may ask rather than catch.
- The drivers MUST answer to it structurally, and `hmz.coganchor.agents` MUST NOT import it. The
  arrow points one way -- a flow names what it drives, and a driver is written without ever naming a
  flow -- and a driver that inherited from this would be the layer below reaching up. That they
  answer MUST be stated once, where a type checker reads it, so that a driver which stops answering
  reads as a driver to correct rather than as a flow that fails on its first turn.
- A flow MUST declare the places it drives with these, and what it writes beside one -- a
  moment, a `Goal`, a `Remote`, an `Isolated`, an `AgentDefaults`, a `Needs` -- MUST go on
  meaning what it means. What is annotated is which interface, not which class.
- What one turn of a conversation may spend before it is cut off MUST be sayable here, as a
  value rather than as arguments: a flow that wants a shorter round says what it may cost and
  when a cap takes hold, and a dimension added to the answer MUST NOT be a change to every
  place a turn can be asked for. It MUST be the session's to say as well as the agent's, and
  MUST be sayable again while the conversation runs, for the reason the skills it carries are:
  a loop watching what a round is costing decides between two rounds, not before the first.
- A flow MUST be able to cut off the turn now running, which is not the same as stopping the
  agent: stopping prevents its *next* turn, and a turn already gone wrong is minutes of a run
  nobody can get back. What a turn cut off answers with MUST still be one answer, holding what
  the agent got as far as saying -- a flow reading a stream that stopped mid-sentence would be
  waiting for an answer nobody is going to give.
- What an agent may do, whether it has goals and whether it may search the web MUST be among
  what a place declares, and MUST NOT be sayable anywhere else: they are things about the work
  rather than about the agent, so the person who wrote the flow settles them and the person
  who chose the agent is not asked. A flow MUST NOT be able to change them once it is running
  either -- they are on `Driven` and not on `Agent`, like everything else somebody already
  answered -- so a flow that wants an agent allowed less makes another with `Agent.clone`.
- What a place declares MUST only ever tighten what the agent filling it already carries, and
  MUST NOT loosen it. A place that declares nothing declares the loosest of each -- nothing at
  all about what the agent may do, goals on, nothing at all about the web -- so a flow that says
  nothing MUST run its agents at exactly what they came with rather than resetting them to
  those. Otherwise a run somebody started at `read-only` would be back at whatever its CLI does
  unasked the moment it called a flow that mentioned nothing, and calling a flow they did not
  write would be how their `read-only` gets undone. Saying nothing MUST therefore be looser than
  every rung there is, which is what keeps the rule one rule: a declaration always tightens, and
  the thing it tightens from when nobody has declared anything is the whole of what that CLI
  would do on its own.
- A called flow's declaration MUST hold for the length of the call and no longer, and MUST be
  measured against what the calling flow settled rather than against what the agent was made
  with: tightening is the point of declaring, and loosening is a called flow handing itself
  more than its caller has. Two calls holding one agent at once MUST each get what it
  declared, and the agent MUST go back to what it was before any of them took it once the
  last lets go -- not to what the call that happened to end last saw.
- "Looser" MUST NOT be read as "sees less". At a declared `bypass` humanize answers each of
  Claude's permission requests itself, so a flow's `PERMISSION_REQUEST` hooks see every one; at
  `auto` Claude decides for itself and those hooks see nothing. A flow that tightens `bypass` to
  `auto` therefore gains restriction and loses visibility, and one written around watching what
  its agent asks for MUST say `bypass` and mean it. It MUST write the word: a place that declares
  nothing is not at `bypass`, humanize answers nothing for it, and those hooks see whatever the
  CLI itself asks humanize -- which on a Claude Code left to itself is nothing at all.
- A flow MUST be able to put callbacks of its own in front of an agent as tools it may reach
  for, said on the conversation and taking effect from its next turn -- which is where a flow
  is when it has something to offer. The callback MUST run in the process the flow is in, so
  that an agent reaching for one is the flow's own code running and may do whatever the flow
  may do, up to and including running another flow and waiting for it. A backend with no way of
  being given a tool it was not shipped with MUST refuse one where it is offered, and MUST say
  beforehand which it is, so that a flow may ask rather than catch. What that comes to is
  `hmz.coganchor.agents.tools`.
- Which of a flow's skills one conversation carries MUST be the session's own to say, and
  MUST be sayable again while the conversation runs: an agent is what it was made as, and a
  conversation is a thing that gets somewhere -- one that has finished reading and started
  writing wants the skill about writing and no longer wants the eight about reading. A session
  nobody has said anything about MUST carry every one the flow brought, which is what every
  session of every flow has always carried, and a name the flow does not bring MUST be ignored
  rather than refused: what a session may carry is the flow's to say, and a fork that dropped
  a skill is a session carrying the rest rather than a turn that will not run.
- `Person` MUST be what a flow declares for the person at the prompt, and the class that
  answers to it MUST be read as the same place: a flow written before there was an interface
  named the class, and it is the same place either way. The class itself MUST be reachable
  too: a place is annotated with the interface, and a person is made rather than annotated.
- A `Person` MUST carry a board -- named lines the flow and the person both write on, which
  neither waits at. Saying something to them stops the turn until they answer, and that is
  right for a question and wrong for what there is to do next and how far through it is. Which
  lines are one side's alone MUST be sayable, and the other side MUST be refused where it
  writes. What that comes to is `hmz.coganchor.agents.board`.
- What is true of a backend rather than of one agent -- which moments it runs, whether it has
  a goal feature, whether it can be held to a shape, whether a turn of it can be talked to
  while it runs -- MUST be declared on the class. It is read off the class where a flow is
  checked against the agents it was given, before any of them has been made, so anything
  answering to this MUST say it the same way, annotation and all.
- Whether a turn already running can be steered MUST be one of those, as `Session.steers`, so
  that a flow meaning to put a word in asks rather than catching the refusal a backend handed
  its whole prompt up front raises. It is the same arrangement `fork` has and for the same
  reason: what a backend cannot do MUST be knowable before an hour of a run has been spent
  finding out.
- One vocabulary MUST name the capabilities, so that a flow author, the catalogue and a
  compiler ask for one under one word wherever they ask: `goal`, `steer`, `shape`, `tools`,
  `fork`, `search`, `swarm`, `resume` and `moment:<name>` of an agent; `remote`, `isolated`,
  `managed`, `linux` and `darwin` of where its turns land; and `anchor:<how>` of the way a
  turn's own commands are reached there. A second word for a capability that already has one
  is a generated flow asking for what nothing answers to.

## `atlas.py`

```python
type Kind = Literal["mind", "logic", "atlas"]


@dataclass(frozen=True, slots=True)
class Atlas:
    name: str = ""


@dataclass(frozen=True, slots=True)
class Marked:
    kind: Kind
    rerun: bool = True


@dataclass(frozen=True, slots=True)
class Sub:
    named: str


def atlas[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def mind[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def logic[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]: ...


def sub(named: str) -> Sub: ...
```

What an atlas is written in. A flow is a Python file that may branch any way it likes, and the
one thing nothing can ask it is what it is about to do; an atlas is the other bargain, whose
body is a declaration in a narrower Python and whose shape is therefore a graph that exists
before anything does. This MUST be the half of that an atlas author writes: the marks and
nothing else. What they compile *to* MUST be `hmz.runtime.flowing.prophecy`, and the compiling
itself `hmz.runtime.flowing.prophesying` -- neither of which an atlas names, and so neither of
which MUST be here.

- An atlas MUST be a flow. It MUST carry everything `flow` marks a flow with as well as its
  own mark, so that everything which already finds, lists, names, refuses and runs a flow goes
  on doing so, and only what compiles one has to know there are two kinds. `atlas` MUST mark
  rather than wrap, for the reason `flow` MUST.
- An atlas MUST always be able to be picked up where the last run of it left off, and MUST say
  so without being asked. A prophecy is a list of nodes with an answer apiece, so what a run of
  one has done is something the run itself writes down -- and an atlas therefore MUST NOT be
  handed a dict, and MUST NOT declare one: what an ordinary flow keeps by hand is what this
  keeps by being a graph.
- There MUST be two kinds of ordinary node and one that is a whole atlas. A `mind` MUST be a
  turn taken by an agent and MUST be handed the agent the call site names; a `logic` MUST be
  Python and MUST be handed no agent at all; an atlas reached by another atlas MUST be a
  supernode, which is one node from outside and one prophecy from within.
- A mind MUST have exactly one way out and a logic MAY have several. A branch is a decision,
  and a decision nothing but a model made is a decision no reading of the flow can state, so
  what a turn said MUST reach a branch by being read by a logic node.
- A node MAY say that a run picked up inside it steps past it rather than running it again.
  What a node says by saying nothing MUST be that it runs again: work cut off partway is work
  that was not done. One that says otherwise MUST answer with nothing, since a run stepping
  past it has no answer of its for what comes next to be missing.
- An atlas MUST reach another atlas by `sub` and MUST reach an ordinary flow by nothing at
  all. `load` answers with a flow that may be anything, and a prophecy with one of those in it
  would be a graph with a hole where a node should be -- which is the one thing a prophecy is
  for not having. What `sub` answers with MUST never be called: the body it is written in is
  read rather than run, and a call MUST say so rather than do something surprising.
