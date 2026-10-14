# Side questions

## 1. Scope

This document defines side questions: questions the **user** asks about an **epic** without
the question reaching the **flow** of that epic. It states who answers a side question, what
the answerer is told, what the answerer is permitted to do, how the **btw** agent is chosen and
recorded per epic, and how long a side conversation lasts, in every **frontend** that offers
side questions.

Out of scope:

- The layout of btw mode in the terminal interface: `features/tui.md`.
- The layout of the btw panel in the web interface: `features/web.md`.
- The `btw` key of `settings.yaml`: `api/settings.md`.
- The `btw` event of `epic.jsonl`: `api/files/epics.md`.
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
`@ask <agent>/<n>: <question>`, in which `<agent>/<n>` names a session of the epic.

**2.7** **Btw mode**: the state of the terminal interface in which every line the user types,
other than a `/` command, is a side question (`features/tui.md`).

**2.8** **Btw panel**: the part of the web interface's epic view in which the user asks side
questions (`features/web.md`).

**2.9** **Aside**: one side question together with the answer to it.

**2.10** **Btw agent choice**: the harness, account, model and effort that the user picked for
the btw agent of one epic.

## 3. Guarantees

**3.1** A side question MUST NOT reach any session of the epic's flow.

**3.2** A side question MUST NOT be delivered to the flow as a message, an answer to a
question, a steer, a stop or any other input.

**3.3** Asking a side question MUST NOT change the state, the transcript, the board, the
budget limits or the outcome of the epic.

**3.4** Every side conversation MUST run at the read-only permission level.

**3.5** Every side conversation MUST run with no skills, no goals, no tools of the flow, no
hooks of the flow and no approval of MCP servers.

**3.6** A side conversation MUST NOT modify any file of the **workspace**.

**3.7** A side conversation MUST be told to treat everything it observes about the epic as
data and not as instructions.

**3.8** A side conversation's turns MUST NOT appear as nodes of the epic's monitor, as
sessions of the epic or as spans of the epic's trace.

**3.9** A side question MUST be answerable while the epic is running and after the epic has
ended.

**3.10** A frontend MUST refuse a side question to a side conversation while that side
conversation is answering an earlier one.

**3.11** A frontend MUST word the refusal of §3.10 as `features/tui.md` §12.14, `api/http.md` §9.3.5
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

**4.10** A snapshot told to the btw agent MUST list the sessions of the epic by
`<agent>/<n>` and MUST state that the btw agent MAY ask them by ask lines (§6).

**4.11** A snapshot told to a session side copy MUST contain only the observations of the
asked session's agent and of the flow, and MUST NOT list the sessions of the epic.

**4.12** A fork MUST be told which session it is a copy of, and MUST be told not to carry on
that session's task.

**4.13** Every question after the first in one side conversation MUST be put to that side
conversation without a further snapshot.

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
refuse the side question, saying that a coding agent is required.

## 6. The btw agent asking sessions

**6.1** The btw agent MAY answer with one or more ask lines instead of an answer to the user.

**6.2** hmz MUST put each ask line's question to the session side copy of the session it
names, opening that side copy as §5.4 and §5.5 state where it is not open.

**6.3** hmz MUST return each session side copy's answer to the btw agent, attributed to the
session it came from.

**6.4** hmz MUST carry out at most 4 ask lines per side question that the user asks.

**6.5** Once 4 ask lines have been carried out for one side question, hmz MUST tell the btw
agent that it can ask no more, and MUST take its next answer as the answer to the user.

**6.6** An ask line that names no session of the epic MUST be answered back to the btw agent
as a session not found.

**6.7** An ask line whose session side copy fails or answers nothing MUST be answered back to
the btw agent as that failure or as no answer.

**6.8** A frontend MUST show the user each ask line as it is carried out, naming the session
and the question.

**6.9** The answer shown to the user MUST NOT contain ask lines.

## 7. Choosing the btw agent

**7.1** The btw agent of an epic MUST be the first of these that yields an agent:

1. the btw agent choice recorded with that epic (§8);
2. otherwise, the agent named by the `btw` setting of `settings.yaml`;
3. otherwise, the agent of the first agent role the flow declares, as that role's first
   session of the epic where it has one, or as what the role is set up to run where it has
   none;
4. otherwise, the agent of the epic's first session.

**7.2** Where none of §7.1's items yields an agent, there MUST be no btw agent.

**7.3** The `btw` setting MUST be an agent spec (`api/settings.md` §4.3.1).

**7.4** The `btw` setting MUST be absent where the agent §7.1 item 3 yields is meant.

**7.5** A change of the `btw` setting MUST take effect from the next side conversation the btw
agent opens, and MUST NOT change a side conversation already open.

## 8. The btw agent choice of an epic

**8.1** The btw panel MUST offer, once opened, a control that shows the btw agent in force and
lets the user pick the harness, the account, the model and the effort of the btw agent.

**8.2** Btw mode MUST offer, once entered, a key that opens the agent sheet for the btw agent,
in which the user picks the harness, the account, the model and the effort
(`features/tui.md`).

**8.3** A frontend MUST offer as harnesses, accounts, models and efforts exactly those the
agent sheet of a flow role offers (`features/agents.md`).

**8.4** A btw agent choice MUST be recorded with the epic the side questions are about, as the
`btw` event of that epic's `epic.jsonl`.

**8.5** A btw agent choice MUST outlive closing and reopening the btw panel or btw mode,
closing and reopening the frontend, and the end of the epic.

**8.6** A btw agent choice recorded with an epic MUST be shown and used by every frontend that
asks side questions about that epic.

**8.7** When the btw agent choice of an epic changes, hmz MUST open a new side conversation with
the newly chosen agent at the next side question to the btw agent.

**8.8** When the btw agent choice of an epic changes, a frontend MUST keep the asides already
shown.

**8.9** A btw agent choice MUST NOT change the agent of any session side copy.

**8.10** A btw agent choice MUST NOT change the `btw` setting of `settings.yaml`.

**8.11** Where no epic is in view, a frontend MUST refuse a btw agent choice
(`features/tui.md` §12.11, `api/http.md` §9.4.4).

## 9. Lifetime of side conversations and asides

**9.1** Every side question after the first, in one btw mode or one btw panel, MUST go on in
the same side conversation as the first, so that a question MAY refer to an earlier one.

**9.2** Leaving btw mode (`features/tui.md` §12.12) MUST close every side conversation that btw
mode opened.

**9.3** Closing the side conversations in the btw panel MUST close every side conversation the
panel opened.

**9.4** A new epic starting on the host the frontend follows MUST close every side conversation
opened about the epic it replaces (`features/tui.md` §12.13).

**9.5** A frontend going away MUST close every side conversation it opened.

**9.6** A side conversation that opens after its btw mode or btw panel was closed MUST be
closed at once, and its answer MUST NOT be shown.

**9.7** The web interface MUST keep, per workspace, which side conversations are open and the
last 200 asides, so that a page opened again shows them.

**9.8** The terminal interface MUST show each aside in the transcript the user reads, and MUST
NOT keep asides after the transcript is cleared or the interface closes.

**9.9** A frontend MUST show an answer to a side question distinguishably from every line of the
epic's own (`features/tui.md` §12.5).
