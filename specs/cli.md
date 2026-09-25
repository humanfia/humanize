# `cli`

`hmz` -- the whole command line, over layers that have none of their own. One command anybody types,
one door onto what humanize spawns for itself, and naming no command at all opens the terminal
interface. It reads a line, routes it and settles who is reading; it decides nothing a layer under it
decides.

## API

```shell
hmz [<command> [<args>...]] | hmz --version | hmz --help   # no command: the terminal interface
hmz exec -f|--flow <ref> [-a|--agents <agent>[,<agent>...]]... [-e|--envs <env>[,<env>...]]...
         [-p|--params <key>=<value>[,...]]... [-b|--budget <limit>[,<limit>...]]...
         [--resume] [--json] <task>
<ref>    := [<flowverse>/]<flow>[:<name>] | <path> | git+<url>[@<rev>]#<flow>[:<name>]
<agent>  := <role>=<cli>[@<provider>]/<model>:<effort>
<env>    := <role>=<backend>@<provider>/<workdir>
<limit>  := duration=<duration> | cost=<usd> | output_tokens=<count> | graceful=<bool>
hmz internal <command> [<args>...]
hmz internal anchor [<options>] <agent> [<args>...]
hmz internal anchor serve --export <virtual>[:<real>] [--export ...]
    (--stdio | --listen [<host>:]<port> | --peer <ticket>@<host>:<port>)
    [--token <secret>] [--log-level debug|info|warning|error]
hmz internal anchor rendezvous [--listen [<host>:]<port>] [--punching <seconds>]
    [--log-level debug|info|warning|error]
hmz internal cred --map <from>=<to> [--map ...] -- <command> [<args>...]
hmz internal tools --at <socket>
hmz internal hook --at <socket>
```

```python
# __init__.py
APART = "HUMANIZE_DAEMON"   # `off`, `0` or `no`: keep the run with the terminal
COMMANDS: dict[str, tuple[Callable[[list[str]], int], str]]  # exec, internal
INTERNAL: dict[str, tuple[Callable[[list[str]], int], str]]  # anchor, cred, hook, tools
def main(argv: list[str] | None = None) -> int: ...
def opens() -> int: ...
def apart(session: Held) -> None: ...
def many(count: int | str, thing: str) -> str: ...
# output.py -- who is reading, asked once rather than command by command
def terminal(stream: IO[str] | None = None) -> bool: ...
def colours(stream: IO[str] | None = None) -> bool: ...
class Out:    # a run written for a person, or as NDJSON for a program; a context manager
    def __init__(self, *, as_json: bool = False) -> None: ...
    @property
    def as_json(self) -> bool: ...
    def record(self, **fields: Any) -> None: ...
    def row(self, said: str, /, **fields: Any) -> None: ...
    def note(self, said: str) -> None: ...
    def aside(self, said: str) -> None: ...
    def line(self, *parts: tuple[str, str]) -> None: ...
    def answer(self, said: str) -> None: ...
    def spins(self, says: Callable[[], str] | None) -> None: ...
    @property
    def console(self) -> Console: ...

class Shown:    # the agents' own events, drawn as one run; a context manager
    def __init__(self, out: Out) -> None: ...
    def heard(  # handed to `Run.watch`, which every session of a run is watched through
        self, agent: AgentBase, session: SessionBase | None, event: Event
    ) -> None: ...

# anchor.py, cred.py, hook.py, tools.py -- one command apiece
def anchor(argv: list[str]) -> int: ...
def cred(argv: list[str]) -> int: ...
def hook(argv: list[str]) -> int: ...
def tools(argv: list[str]) -> int: ...
```

## Requirements

- MUST offer exactly one command to a person -- `hmz exec` -- and MUST leave everything else humanize
  keeps to the prompt or to `sdk`.
- MUST gather every line humanize spawns for itself under `hmz internal`, MUST show both commands in
  the listing, MUST leave nothing it routes out of it, and MUST have each of those lines say in its
  own help that it is not one to type.
- MUST open the terminal interface for a line naming no command, MUST offer no command that opens it
  too, and MUST answer an unknown command with a usage error listing the commands. That line MUST say
  nothing about what to run: what was chosen at the prompt MUST be what the next line opens on.
- MUST pass everything after a command name to that command untouched, `--help` included, at both
  levels, and MUST cost no module of any other command to reach one. `python -m hmz` MUST be `hmz`.
- MUST open the interface on a run held apart from the terminal wherever there is a terminal on both
  ends, reading whichever run is already held here and starting one where none is; with no terminal on
  both ends it MUST open in this process. `APART` MUST refuse holding for a whole machine, and
  anything else that stops a run being held MUST be said and then done without.
- MUST settle whether escapes may be written in one place: `NO_COLOR` MUST win over everything, then
  `TERM=dumb`, then `FORCE_COLOR`, and otherwise whether a terminal is reading. `FORCE_COLOR` MUST NOT
  make a run believe somebody is watching it, and `rich` MUST NOT be reached until escapes are wanted.
- A piped or redirected run MUST be written with no escapes at all and MUST go on writing what a turn
  answered to stdout; anything that is not the answer MUST go to stderr.
- `--json` MUST be NDJSON -- one object a line, flushed as written, the same keys every time, stdout
  carrying objects alone -- and MUST NOT carry what only a terminal needed.
- MUST say nothing to a program that a line for a person would not: an account is its variable names
  and never their values, a flowverse its URL with any secret taken out.
- `hmz exec` MUST take every `-a`, `-e`, `-p` and `-b` on the line as one list apiece, however it
  was broken up, and two roles given one spelling MUST be two agents.
- Every `<agent>` and `<env>` MUST name the role it fills. A role the flow does not declare, one
  given twice, a required role left unfilled, a role the runtime fills -- an `Outworlder`, a
  `LocalEnv` -- named at all, a param the flow does not take or cannot read, a spec that cannot be
  read, an agent whose harness is not the one its role names or does not serve what its role asks,
  and a line with no `-b` -- for every flow but `chat`, which runs under `Budget(cost=inf)` -- MUST
  each be a usage error before any agent has started, as MUST a flow that is not there or will not
  load, and `--resume` of a flow that cannot be picked up or has no run to pick up.
- `--resume` MUST pick up the newest run of that flow in this workspace that can be picked up;
  without it every run MUST start from the top.
- MUST read `<cli>` from the front and `<effort>` from after the last colon so that a model's own
  punctuation stays the model's, and MUST NOT restate here which backends exist.
- A run started from a command line MUST have nobody outside it: its outworlder is away.
- MUST draw a run from the agents' own event stream rather than from each backend's own progress and
  MUST NOT show both, saying which agent is taking a turn and in which conversation, what it said,
  what it ran, what it started, and what a turn cost -- in money as well as tokens, and tokens alone
  for a model nobody prices -- with something going on moving while a terminal is reading.
- MUST say, without asking, when a cap cannot be read -- a cost cap over a model nobody prices -- and
  MUST say a run its budget stopped in a line rather than as a failure.
- `hmz internal anchor` MUST load `coganchor` and nothing else of humanize, the door included.
- `hmz internal cred` MUST exit with the program's own status, MUST refuse a line naming nothing to
  answer or no program to run, and MUST NOT fall back to running unsupervised.
- `hmz internal tools` MUST do nothing but carry lines, MUST carry both directions at once with the
  end of either ending the other, and MUST answer a socket that is not there with a status rather than
  a crash.
- `hmz internal hook` MUST do nothing but carry the one call, MUST exit zero whatever the flow said
  and whether or not it was there, MUST NOT exit with the status these CLIs read as the hook itself
  refusing, and MUST let the tool through when the flow has gone, saying so where only a person sees.
