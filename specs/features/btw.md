# Side questions

## 1. Scope

This document defines side questions: questions the **user** asks about an **epic** without
the question reaching the **flow** of that epic. It states who answers a side question, what
the answerer is told, what the answerer is permitted to do, how the **btw** agent is chosen,
how the user picks whom a side question is asked of, and how long a side conversation lasts, in
every **frontend** that offers side questions.

Out of scope:

- The layout of btw mode in the terminal interface: `features/tui.md`.
- The layout of the btw panel in the web interface: `features/web.md`.
- The `btw` key of `settings.yaml`: `api/settings.md`.
- The requests a frontend sends to ask a side question: `api/daemon.md`, `api/http.md`.
- What an epic records and how its figures are worked out: `features/epics.md`,
  `features/monitoring.md`.

## 2. Definitions

**2.1** **Side conversation**: a **session** that hmz opens beside an epic to answer side
questions, and that is not a session of the epic's flow.

**2.2** **Btw agent**: the **agent** that answers a side question about an epic as a whole.

**2.3** **Session side copy**: the side conversation that answers side questions about one
session of an epic.

**2.4** **Fork**: a session side copy that its **harness** opens as a copy of the asked
session's own history.

**2.5** **Snapshot**: the bounded description of an epic, frozen when a side question is
asked, that a side conversation is told (§4).

**2.6** **Ask line**: a line of the btw agent's answer of the form
`@ask <agent>/<n>: <question>`, in which `<agent>/<n>` names a session of the epic, alone or
after list markers (`-`, `*`, `+`, `<n>.`, `<n>)`) or quote markers (`>`), and optionally
wrapped in backticks.

**2.7** **Btw mode**: the state of the terminal interface in which every line the user types,
other than a `/` command, is a side question (`features/tui.md`).

**2.8** **Btw panel**: the part of the web interface's epic view in which the user asks side
questions (`features/web.md`).

**2.9** **Aside**: one side question together with the answer to it.

**2.10** **The Epic**: the name under which a frontend offers the btw agent as the one a side
question is asked of.

**2.11** **Ask command**: a run of `hmz-ask ask --to <agent>/<n> --question <question>` by the
btw agent, in which `<agent>/<n>` names a session of the epic; `hmz-ask list` lists the
sessions of the epic the side question is about, one `<agent>/<n>` per line, as the frontend
lists them (§4.10), and is not an ask.

**2.12** **Ask**: an ask line or an ask command.

## 3. Guarantees

**3.1** A side question MUST NOT reach any session of the epic's flow.

**3.2** A side question MUST NOT be delivered to the flow as a message, an answer to a
question, a steer, a stop or any other input.

**3.3** Asking a side question MUST NOT change the state, the transcript, the board, the
budget limits or the outcome of the epic.

**3.4** Every side conversation MUST run at the read-only permission level.

**3.5** Every side conversation MUST run with no skills, no goals, no tools of the flow, no
hooks of the flow and no approval of MCP servers, except what §6.10 to §6.14 give the btw
agent.

**3.6** A side conversation MUST NOT modify any file of the **workspace**.

**3.7** A side conversation MUST be told to treat everything it observes about the epic as
data and not as instructions.

**3.8** A side conversation's turns MUST NOT appear as nodes of the epic's monitor, as
sessions of the epic or as spans of the epic's trace.

**3.9** A side question MUST be answerable while the epic is running and after the epic has
ended.

**3.10** A frontend MUST refuse a side question to a side conversation while that side
conversation is answering an earlier one.

**3.11** A frontend MUST word the refusal of §3.10 as `features/tui.md` §12.10, `api/http.md` §9.3.5
and `api/daemon.md` §8.8.10 state.

**3.12** A failure to answer a side question MUST be reported to the user as a failure of the
side question and MUST NOT be reported as a failure of the epic.

## 4. What a side conversation is told

**4.1** The first side question put to a side conversation that is not a fork MUST be
accompanied by a snapshot of the epic.

**4.2** A snapshot MUST state the flow, the task, the workspace, the time elapsed since the
epic began, whether the epic has ended, how many messages wait to be delivered and whether
the flow waits for input from the user.

**4.3** A snapshot MUST state, for each agent of the epic, its own name followed by the
**role** it fills, whether it is working, how many turns it has taken and its model.

**4.4** A snapshot MUST state the handovers between agents with their counts.

**4.5** A snapshot MUST state the spending of the epic per model in tokens, in output tokens
per second and, only where the model is priced, in money.

**4.6** A snapshot MUST NOT state a missing price as zero money.

**4.7** A snapshot MUST state the tokens of each kind spent over the whole epic and MUST mark
each figure that is only a floor as a floor.

**4.8** A snapshot MUST state at most the 32 most recent observations of the epic: what its
agents said and did and what its flow printed, each cut to at most 600 characters.

**4.9** A snapshot MUST NOT contain any agent's thinking.

**4.10** Every side question put to the btw agent, the first and every later one, MUST list
the sessions of the epic by `<agent>/<n>`, saying where none is open yet, and MUST state that
the btw agent MAY ask them by ask commands, and by ask lines where it cannot run a command
(§6).

**4.11** A snapshot told to a session side copy MUST contain only the observations of the
asked session's agent and of the flow, and MUST NOT list the sessions of the epic.

**4.12** A fork MUST be told which session it is a copy of, and MUST be told not to carry on
that session's task.

**4.13** Every question after the first in one side conversation MUST be put to that side
conversation without a further snapshot, and, to the btw agent, with only what §4.10 states.

**4.14** A snapshot MUST be of the epic the side question is about alone, and MUST NOT
contain observations of any other epic.

## 5. Who answers

**5.1** A side question asked while the user reads one session of an epic MUST be answered by
the session side copy of that session.

**5.2** A side question asked while the user reads an agent's transcript MUST be answered by
the session side copy of that agent's newest session.

**5.3** A side question asked anywhere else MUST be answered by the btw agent.

**5.4** Where the harness of the asked session can fork a session, the session side copy MUST
be a fork.

**5.5** Where the harness of the asked session cannot fork a session, or the fork does not
open, or the fork returns no answer, the session side copy MUST be a new session of the same
agent told a snapshot (§4.11).

**5.6** A session that has ended MUST be askable as §5.1 to §5.5 state.

**5.7** In the web interface, a session of an epic that no host (`features/daemons.md` §2.1)
holds any longer MUST be askable, its session side copy being carried on from where that epic
kept the session.

**5.8** Where the session the user reads no longer exists, a frontend MUST refuse the side
question, naming that session.

**5.9** Where there is no btw agent (§7) and the user does not read a session, a frontend MUST
refuse the side question, saying that the agent that answers The Epic is set in the settings.

## 6. The btw agent asking sessions

**6.1** The btw agent MAY run ask commands during its turn, and MAY answer with one or more
ask lines instead of an answer to the user.

**6.2** hmz MUST put each ask's question to the session side copy of the session it names,
opening that side copy as §5.4 and §5.5 state where it is not open.

**6.3** hmz MUST return each session side copy's answer to the btw agent, attributed to the
session it came from.

**6.4** hmz MUST carry out at most 4 asks, ask commands and ask lines together, per side
question that the user asks.

**6.5** Once 4 asks have been carried out for one side question, hmz MUST answer every
further ask command with `No more asks this question: answer the user with what you have.`,
MUST tell the btw agent so after ask lines, and MUST take its next answer as the answer to
the user.

**6.6** An ask that names no session of the epic MUST be answered back to the btw agent as a
session not found, naming the sessions of the epic.

**6.7** An ask whose session side copy fails or answers nothing MUST be answered back to the
btw agent as that failure or as no answer.

**6.8** A frontend MUST show the user each ask as it is carried out, naming the session and
the question, once per ask.

**6.9** The answer shown to the user MUST NOT contain ask lines.

**6.10** The btw agent's side conversation MUST carry the skill `ask-conversation`, which
states the ask command and `hmz-ask list`, and says to ask a session rather than guess what it
did or knows; no session side copy MUST carry it.

**6.11** hmz MUST carry out an ask command on the host that runs the btw agent, while the
btw agent's turn waits on it, and MUST carry out one ask command run twice with the same
session and question in one turn once.

**6.12** hmz MUST hang a pre-tool-use hook on the btw agent that carries out an ask command
the btw agent reaches for. On a harness on which a refusal prevents the tool
(`features/agents.md` §9.2.1), the hook MUST refuse the tool with the ask command's output as
the reason.

**6.13** On a harness that has a shell (`features/agents.md` §10.2.1), `hmz-ask` MUST be a
fake command line that prints the ask command's output. On `codex`, `hmz-ask` alone MUST run
outside Codex's sandbox (`features/agents.md` §10.2.8), and the sandbox MUST otherwise stay as
the read-only rung puts it, its network cut.

**6.14** Where the answer to an ask command reached the btw agent neither as a refusal (§6.12)
nor as output (§6.13), hmz MUST, when the btw agent's turn would stop, send it on with every
such answer as §6.3 states, at most 4 times per turn.

**6.15** A btw agent whose harness serves no pre-tool-use hook that fires (`litellm`) MUST ask
by ask lines alone.

## 7. Choosing the btw agent

**7.1** The btw agent MUST be the agent named by the `btw` setting of `settings.yaml`, for
every epic alike.

**7.2** Where the `btw` setting names no agent, there MUST be no btw agent: no agent of the
epic, of its flow or of its sessions MUST stand in for it.

**7.3** The `btw` setting MUST be an agent spec (`api/settings.md` §4.3.1).

**7.4** A change of the `btw` setting MUST take effect from the next side conversation the btw
agent opens, and MUST NOT change a side conversation already open.

**7.5** A frontend MUST NOT offer a choice of the btw agent other than the `btw` setting, and
MUST NOT offer a choice of the agent of a session side copy, which is the asked session's own
(§5.4, §5.5).

**7.6** A side question whose side conversation would run on a harness that has no read-only
rung (`mcode`, `dsh`, every ACP harness) MUST be refused, saying that harness has no read-only
rung.

## 8. Whom a side question is asked of

**8.1** The btw panel MUST hold any number of side conversations at once, each asking one of The
Epic or one session of the epic, MUST let the user open a new one, and MUST show one at a time,
offering the others to switch to.

**8.2** A side conversation of the btw panel MUST be asked of whom the user picked before its
first question, and MUST NOT be asked of anyone else after; to ask another, the user opens
another side conversation.

**8.3** The btw panel MUST offer, until a side conversation is opened by its first question, one
control that picks whom it asks, outside the box its question is typed in, and MUST NOT offer it
once it is open.

**8.4** That control MUST name the btw agent as `The Epic`, and MUST NOT name it otherwise.

**8.5** That control MUST lay the sessions out as a hierarchy: one entry per agent of the epic,
naming the agent and the role it fills, under which are that agent's sessions, newest first.

**8.6** That control MUST let the user narrow what it offers by typing part of an agent's name,
a role or a session.

**8.7** That control MUST show which one is picked, and MUST keep the pick while the epic is
redrawn, falling back to The Epic only where the session picked is no longer of the epic.

**8.8** The btw panel MUST name each side conversation by whom it asks, as `btw · The Epic` or
`btw · <agent>/<n>`.

**8.9** While a side conversation of the btw panel is answering, the panel MUST show that it is,
on that side conversation and where it is offered to switch to, MUST show each ask line (§6.8)
as it is carried out, and MUST NOT let the user send it another question.

**8.10** Btw mode MUST pick whom it asks by the view read, as §5 states (`features/tui.md`).

## 9. Lifetime of side conversations and asides

**9.1** Every side question after the first, in one btw mode or one side conversation of the btw
panel, MUST go on in the same side conversation as the first, so that a question MAY refer to an
earlier one.

**9.2** Leaving btw mode (`features/tui.md` §12.8) MUST close every side conversation that btw
mode opened.

**9.3** Closing a side conversation in the btw panel MUST close it, and no other.

**9.4** A new epic starting on the host the frontend follows MUST close every side conversation
opened about the epic it replaces (`features/tui.md` §12.9).

**9.5** A frontend going away MUST close every side conversation it opened.

**9.6** A side conversation that opens after its btw mode, or it in the btw panel, was closed
MUST be closed at once, and its answer MUST NOT be shown.

**9.7** The web interface MUST keep, per workspace, which side conversations are open, about
which epic, whom each asks, the question each is answering and its ask lines so far, and the last
200 asides of each, so that a page opened again shows them.

**9.8** The terminal interface MUST show each aside in the transcript the user reads, and MUST
NOT keep asides after the transcript is cleared or the interface closes.

**9.9** A frontend MUST show an answer to a side question distinguishably from every line of the
epic's own (`features/tui.md` §12.5).
