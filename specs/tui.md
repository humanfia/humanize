# `tui`

The terminal interface `hmz` opens with no command: one prompt over everything humanize does,
drawn as a transcript, a multi-line editor and a status line. It runs flows and reads them
back; it defines no flows, drives no agents and keeps no store of its own.

## API

```python
# __init__.py
class Humanize(App[None]):
    def __init__(
        self,
        flow: str = "",
        agents: Mapping[str, Runs] | None = None,  # by role
        params: BaseModel | None = None,  # the flow's params
        session: Session | None = None,
    ) -> None: ...
    def reattached(self) -> None: ...
    def action_quit(self) -> None: ...
    def said(self) -> dict[str, Any]: ...  # the flow, its budget and usage, as JSON
```

Textual's `run()` opens it; the other three are what a run held elsewhere calls to redraw, stop,
or say what it is running.

## Requirements

- MUST open ready to talk to one agent, so that a typed line is enough to start — on what this
  workspace last ran where it has run anything, and as its arguments say where it was given one.
- MUST draw in the terminal's own colours, asking it nothing; failures in red, warnings in yellow.
- MUST stay responsive throughout — asking backends what they run, fetching, exporting — and MUST
  NOT start a CLI or reach the network on a sheet's drawing path.
- MUST NOT fetch a flowverse a running flow could be reading, or one written into here.
- MUST say why a flow will not load: a flowverse unfetched, a module missing, a file broken, no
  flow named in it.
- MUST read `/name` as a command, `$name [prompt]` as a flow and what to say to it, and any
  other line as said to the conversation being read, reaching a turn already under way.
- MUST run a `$` line at once where that flow is already set up here, otherwise open the flow
  menu inside it holding the line and run it once saved, saying nothing was started if that menu
  is walked out of.
- MUST treat `$` as prose where no flow-shaped name follows it and while an agent waits on an
  answer, and MUST refuse it while a flow runs, leaving that run untouched.
- MUST offer a half-typed command or flow what it could become, reconsidered as the cursor moves
  as well as the text, offer nothing against a whole word, and keep focus in the editor.
- MUST keep what was typed for walking back to, per directory, and fixed for the session.
- MUST keep one transcript per agent and one more they all appear on, open on the latter and
  return to it when a run starts, and bound what is kept without dropping either of those two.
- MUST show which agent is read, how many conversations it holds, whether it is working and
  whether it has something unread — nothing unread while the shared transcript is read.
- MUST send a typed line to the agent being read, to whichever of its conversations has a turn
  open and holding it for the next turn otherwise, and keep it against the agent that took it.
- MUST name what is running as the flow started and whatever it called, innermost last.
- MUST offer exactly these commands, each doing what it says: `/flow`, `/btw`, `/flowverses`,
  `/providers`, `/fallback`, `/epics`, `/resume`, `/settings`, `/monitor`, `/clear`, `/details`,
  `/afk`, `/stop`, `/exit`. `/btw` MUST be answered from a snapshot, not by asking the flow.
- MUST carry the last run of this directory of a flow that can be picked up on for `/resume` —
  its flow, roles, params, budget and task, picking up its journal, saying which — say why there
  is none to carry on, and refuse it, as it refuses picking any run up, while a flow is running
  or stopping.
- MUST let a flow's agents be set up whatever is happening, but offer a flow choice only when idle.
- MUST read the flows a place at a time — every flowverse fetched or not, then this project's own
  — showing which place is read, and letting a flow be copied here whole and under its name.
- MUST set a flow up by its roles: one row per agent role and one per environment role the flow
  declares, leaving out the ones the runtime fills -- an `Outworlder`, a `LocalEnv` -- then its
  params, asked with the flow's own params model, and what a run may spend. A saved menu MUST take
  effect from the next run, and MUST refuse to save a flow whose agent role names no model, or --
  for every flow but `chat` -- one that has no budget.
- MUST let what a run may spend -- a duration, a cost, output tokens, and whether a turn is let
  finish -- be set and read on the page its roles are on.
- MUST make an agent a CLI, an account, a model and an effort and nothing else, offering only
  CLIs installed here whose harness is the one the role names and serves what the role asks,
  this machine's own account as `as local`, models known runnable as the chosen account, and
  efforts that model takes -- and letting an account be made where one is asked for. An
  environment role MUST take a spec as `-e` spells one.
- MUST be whoever is outside a run: a question a flow puts to its outworlder MUST be asked at
  the prompt and answered with the next line typed, and `/afk` MUST make the outworlder away.
- MUST offer, per place flows come from, what it holds, adding one, fetching it again and taking
  one away, against the same store the flows are read from, with any credential in a URL hidden.
- MUST list every account under its CLI and offer correcting, re-signing, what it falls back to
  and taking it away, never drawing a secret back onto the screen.
- MUST answer both scales of falling back — which agent takes over from which, and which account
  a failing one falls back to — refusing anything that falls back to itself.
- MUST list the runs of this directory newest first with when each began, its flow, its task, how
  it went and how many sessions it opened, marking which can be picked up, readable while one runs.
- MUST offer per run where it is written down, carrying it on where its flow says so, and
  exporting it; an export MUST carry a trace of that run's own sessions and no transcript, say
  where it landed and how big it is, and replace that run's last export rather than pile up.
- MUST draw the run on `/monitor` as a box per agent in the flow's order with the handovers
  between them — only agents that have taken a turn, marked as working or as having something
  unread — never refused while a flow runs, redrawn as the run moves, every clock stopping where
  the run stopped, and any box readable from there whether or not it is working.
- MUST report spend per model, by kind of token and never as one total over the kinds, in an
  order that does not change, money beside tokens where known and tokens alone where not, marking
  a figure that is only a floor, and the rate as output tokens a second.
- MUST draw the board a flow and a person share under the diagram, applying changes at once while
  the flow runs and refusing, where the key was pressed, to edit a line the flow owns.
- MUST make `/settings` two pages, this machine and this directory, and forget this one alone.
- MUST ask once, at a first start and only with somebody there, whether humanize may report its
  own failures — what would be sent and what never would — unanswered if it is walked away from.
- MUST hold what a menu changes until it is left and saving is confirmed, asking on the way out
  of one holding changes; anything that runs an external command or writes to the board MUST
  apply at once instead.
- MUST answer a sheet once however many times its key is pressed, and ask twice on the same key
  before anything is taken away by one, putting that question down when the cursor moves.
- MUST keep a sheet's keys on the screen in one place, make a search asked for rather than what
  typing does, and bind no sheet key to a chord except saving.
- MUST give a selection back as the text written rather than the rows it was drawn on, let one go
  when what it was made against changes, and never scroll the transcript out from under a reader.

## Keys

| Key | Where | What it does |
| --- | --- | --- |
| `enter` | editor, sheets | send the line or take the offer; open the row under the cursor |
| `shift+enter`, `ctrl+j` | editor, menus | break the line; save the menu |
| `tab`, `shift+tab` | app, sheets | round the shared transcript and working agents; turn pages |
| `esc` | app, sheets | open `/monitor`; one step back, out of a search first |
| `ctrl+c` | app | take back the nearest thing; twice stops the flow |
| `ctrl+q` | app | what `/exit` does |
| `←`, `→` | sheets | step an adjustable row's value, or step between lists |
| `space` | sheets | the next value, coming round at the end |
| `s`, `a` | lists | search; add one |
| `r` | flowverses, models | fetch or ask again |
| `d` | board | take a line away |
| `f`, `v` | flows | copy the flow here; where flows come from |
