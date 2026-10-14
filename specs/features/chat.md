# Chat

## 1. Scope

This document defines the chat: the built-in **flow** named `chat`, in which the **user** talks
to one **agent**, one turn at a time, in one conversation. It states how a chat starts, takes
turns, reports its status, runs beside other **epics**, folds away, is carried on and ends,
and what every **frontend** draws and refuses for it.

Out of scope:

- The flow API that `chat` is written against: `api/flows.md`.
- How hosts are started, linked and let go: `features/daemons.md`, `api/daemon.md`.
- The terminal interface's layout outside a chat: `features/tui.md`.
- The web interface's layout outside a chat: `features/web.md`.
- Side questions asked about a chat: `features/btw.md`.
- Notices of chat turns: `features/monitoring.md`.
- What an epic records: `features/epics.md`, `api/files/epics.md`.

## 2. Definitions

**2.1** **Chat**: an epic of the flow `chat`, where a flow is `chat` when its name is `chat` or
when it is named by a path or reference whose last part is `chat`.

**2.2** **Assistant**: the one agent **role** of `chat`, and the agent that fills it.

**2.3** **Conversation**: the one **session** of the assistant in a chat.

**2.4** **Turn**: the assistant's answer to one message from the user, from the moment the
message is delivered to the moment the answer is complete.

**2.5** **Between turns**: the state of a chat whose assistant has completed a turn and waits
for the user's next message.

**2.6** **Folding away**: the end of the **host** that holds a chat, while the chat is between
turns, leaving its epic recorded so that it MAY be carried on.

**2.7** **Carrying on**: resuming a chat in its own epic with its own conversation.

## 3. The flow

**3.1** `chat` MUST declare exactly one agent role, `assistant`, one outworlder role, `human`,
which is the user, and one environment role, `workspace`, which is the **workspace** on this
machine.

**3.2** `chat` MUST take no params.

**3.3** `chat` MUST NOT require a budget, and a chat MUST run with no limit on its spending.

**3.4** The assistant MUST have every capability that its **harness** offers, the web
included.

**3.5** `chat` MUST be resumable.

**3.6** `chat` MUST be the flow the terminal interface opens on in a workspace for which no flow
is remembered.

## 4. Turns

**4.1** The task of a chat MUST be the first message of its conversation.

**4.2** Each answer of the assistant MUST be shown to the user as the assistant's line of the
conversation.

**4.3** The next message the user says in a chat that is between turns MUST be the next turn of
the same conversation.

**4.4** A message the user says while a turn is open MUST be delivered to that turn where the
harness accepts a message mid-turn, and MUST otherwise be held for the next turn.

**4.5** A frontend MUST NOT draw the chat's wait for the next message as a question to the
user.

**4.6** A question the assistant asks the user mid-turn MUST be shown in the conversation with
the options it offers, and the user's next message MUST answer it.

**4.7** An empty next message MUST end the chat.

**4.8** Where the **outworlder** `human` is away, the chat MUST take its first turn and then end,
the next message being empty.

**4.9** Where the first turn of a chat that is not carried on fails, the epic MUST end failed
with what the harness said.

**4.10** Where a later turn fails, the chat MUST say in the conversation that the turn could
not be taken and why, and MUST go on between turns.

## 5. Status

**5.1** A chat MUST be reported as `running` while a turn is open.

**5.2** A chat MUST be reported as `done` while it is between turns.

**5.3** A chat that has ended MUST be reported as `done`, or as `failed` where §4.9 applies.

**5.4** A frontend MUST NOT offer a way to stop a chat or to force it to stop.

**5.5** A frontend MUST refuse a request to stop a chat, saying that a chat is not stopped.

## 6. Many chats

**6.1** Each chat MUST be an epic of its own on a host of its own.

**6.2** Any number of chats MUST be able to run in one workspace at once, beside the
workspace's own flow.

**6.3** Starting a chat MUST NOT end, stop or wait on any other chat or any flow.

**6.4** Starting or resuming a flow in a workspace MUST NOT end, stop or wait on any chat of
that workspace.

**6.5** A frontend MUST list every chat among the epics of its workspace, with its status as §5
states it.

## 7. Folding away and carrying on

**7.1** A chat MUST fold away once it is between turns and no frontend has followed it for the
period `features/daemons.md` states.

**7.2** A chat MUST NOT fold away while a turn is open.

**7.3** A chat that a host holds MUST, when opened from a list of epics, be followed where it is,
its conversation drawn from its first message.

**7.4** A chat that has folded away MUST, when opened from a list of epics, be drawn with what
was said in it, and the next message the user says in it MUST carry it on.

**7.5** Carrying on a chat MUST continue the same epic, MUST continue the same conversation,
and MUST take the message that carried it on as the next turn.

**7.6** Where the conversation of a chat cannot be carried on, the chat MUST say so in the
conversation with the reason, MUST start a new conversation in the same epic, and MUST answer
the message that carried it on in that new conversation.

**7.7** A chat of another workspace, or one that cannot be carried on here, MUST be refused,
saying that the chat cannot be continued here.

**7.8** A chat MUST NOT be carried on by `/resume` or by resuming the workspace's last epic;
it MUST be carried on only from a list of epics or by saying something in it.

## 8. Drawing a chat

**8.1** Every frontend MUST draw a chat as its conversation alone: the user's messages and the
assistant's answers, in order.

**8.2** A frontend MUST NOT draw for a chat a monitor, a graph or list of agents, a tree of
agents or sessions, a transcript of several sessions, a list of outworlders or a timeline in
Exomyth.

**8.3** A frontend MUST NOT offer for a chat a way to stop it, to force it, or to round its
views.

**8.4** The terminal interface MUST end the chat on the screen by `/clear`, which starts a new
chat and leaves the previous one going on its own host (`features/tui.md`).

**8.5** The web interface MUST end the chat on the screen by starting a new epic, which leaves
the previous chat going on its own host (`features/web.md`).

**8.6** Leaving a frontend while a chat is on the screen MUST NOT ask the user anything, and
MUST leave a chat that a host holds to that host.

**8.7** Every behaviour of a chat that the web interface offers MUST be offered by the terminal
interface by keys and commands, and every behaviour of a chat that the terminal interface
offers MUST be offered by the web interface.
