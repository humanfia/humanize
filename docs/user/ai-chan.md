# Ai-chan

<img class="ai-chan-avatar" src="/ai-chan/avatar-128.png" alt="Ai-chan, drawn in pixel art" width="96" height="96">

Ai-chan is Humanize's own operator: you tell her what you want in words, and she does it on
your epics as you would from the prompt or the page. Ask her what your epics did today, have her
steer a session, or run the tests in an epic's environment.

::: info At a glance
- **You will** open a conversation with Ai-chan, say what you want, and watch each thing she
  does to Humanize as she does it.
- **Use it when** a question spans several epics, or a job is easier said than clicked:
  "summarize what my epics did today", "tell the actor to stop refactoring", "run the tests in
  the env of epic X".
- **You need** an agent for her to think with, chosen as **Ai-chan** on the
  [General page of the settings](/user/settings#general) or when you open her.
:::

<style>
.ai-chan-avatar {
  float: right;
  margin: 0 0 12px 16px;
  image-rendering: pixelated;
}
</style>

## Try it

At the prompt, type `/ai`, pick **New**, press **Done** on the form as it comes, and say what
you want:

```text
❯ /ai
❯ summarize what my epics in this directory did today
```

On the page of [`hmz web`](/user/web) or in [Humanize Desktop](/user/desktop), click Ai-chan's
avatar at the right of any view's bar instead: a drawer opens beside it, with **New**.

## How it works

Every conversation with Ai-chan is fixed, when you make it, to three things. None of them
changes while the conversation lasts; to change one, make another conversation. A `/model` or
`/effort` said to her is refused, and leaves the [chat agent](/user/chat) her workspace remembers
as it was.

| | What it is | Choices | Default |
| --- | --- | --- | --- |
| **Scope** | what she may reach | `epic`: one epic, and the directory it ran in · `workspace`: one directory and every epic run there · `daemon`: every directory and every epic on this machine's daemon | the epic you are looking at, else the directory, else the daemon |
| **Nous** | what she thinks with | any [nous](/user/settings#nous), or an agent: a CLI, an account, a model and an effort | the **Ai-chan** setting |
| **Permission** | what she may change | a **preset**, `read-only` or `danger-full-access`, and **network**, off or on | `read-only`, network off |

What she may do follows from the preset, and from the scope reaching what she acts on:

| She can | `read-only` | `danger-full-access` |
| --- | --- | --- |
| Read epics, transcripts, traces and what they spent | yes | yes |
| Ask a session a [side question](/user/btw) | yes | yes |
| List, read and search the files of a running epic's environments | yes | yes |
| Read files under the scope's directory | yes | yes |
| Write files in her own scratch directory | yes | yes |
| Say something to an epic, answer it, stop it, force it, edit its board | no | yes |
| Write files in a running epic's environments, and run commands there | no | yes |
| Write files under the scope's directory | no | yes |
| Start an epic (`workspace` and `daemon` scopes) | no | yes |
| Change the settings and the nous, install flows (`daemon` scope) | no | yes |

Whatever the permission, she cannot reach anything outside her scope, pair a device, add an
account or touch its credentials, or see another conversation with Ai-chan, her own included.
Her CLI never stops to ask you for approval: what she cannot do is refused as she tries it, not
put to you.

**Network** off cuts the network for her CLI and every command it runs, except what her model
and its sign-in need. Turn it on when she must fetch something, such as a page or a package.

She talks as a chat does: she answers each thing you say in a turn, and
she shows each tool she calls -- what she asked Humanize for, and how it was answered -- as a
line of her turn you can open. What she does to an epic, every frontend reading that epic sees,
under her name, `Ai-chan#<n>`: a line she says to an agent reads `· by Ai-chan#3`, as yours
reads `· by` you.

## Example: summarize what your epics did today

You have run a few epics in `~/code/shop` today and want the gist without opening each.

**At the prompt.** In `~/code/shop`, type `/ai`. A menu lists every conversation with Ai-chan,
under **New**:

```text
  New                                                                         ①
    a conversation of its own scope, nous and permission
  Ai-chan#2 · check the reviewer's last round                                 ②
    epic 0912-a1b2c3 · claude/claude-opus-5:high · read-only · network off · between turns
  Ai-chan#1 · what did the benchmark score
    daemon · claude/claude-opus-5:high · read-only · network off · folded away
```

Pick **New**. A form asks for the scope, the nous, the preset and the network, each set to its
default. Nothing has run here, so the scope is `workspace`, this directory. Press **Done**: the
first line you say is the task that starts the conversation.

```text
❯ summarize what my epics here did today, one line each
  …                                                                          ③
  Four epics today:
  - 09:12 ralph_loop: added the coupon endpoint; done in 3 rounds, $2.10.
  - 11:40 rlar: the reviewer refused the migration twice; stopped by its budget.
  …
Ai-chan#3 · workspace shop · ◉ done                                          ④
```

What to look at, by number:

1. **New** makes a conversation. Every one you made is listed under it, newest first.
2. **Each conversation**, `Ai-chan#<n>` and its title, says its scope, its nous, its preset,
   whether its network is on, and how it stands: `answering`, `between turns` or `folded away`.
3. **Each tool she calls** is a tool line of her turn, as an agent's is, even with
   [Details](/user/settings#details) off: what she asked Humanize for, and how it was answered.
4. **`Ai-chan#3 · workspace shop`** at the front of the status line is the conversation you
   follow, with its scope.

### Check it worked

- She answered from what your epics wrote down: each line names an epic you ran.
- `/ai` again lists the conversation, `between turns`: ready for your next line.

## Open a conversation

| Where | Open | New | Stop her turn | Forget |
| --- | --- | --- | --- | --- |
| The prompt (`hmz`) | `/ai`, then <kbd>enter</kbd> on a conversation | `/ai` › **New**: a form, **Done**, then say the first line | `/stop` | `/ai`, <kbd>m</kbd> on a conversation, **forget** |
| The page (`hmz web`) | Ai-chan's avatar, at the right of every view's bar, then a conversation | **New** in the drawer: a form, then type the task and press <kbd>enter</kbd> | **Stop**, while she answers | **Forget** on a conversation |
| Humanize Desktop | as on the page | as on the page | as on the page | as on the page |

- **At the prompt**, the log screen follows the conversation you open, as it follows a chat:
  each line you say is her next turn. `/clear` leaves her conversation going and comes back to
  this directory's own. `/btw` is refused while you follow her: she is not a session of an
  epic.
- **On the page**, the drawer stays open from view to view until you close it, and lists each
  conversation as **Answering**, **Waiting** or **Folded away**. A conversation you open whose
  first turn failed says **Failed**, with what her harness said, and takes no more lines: start
  a new one. Its form also takes a **Title**, made from the task where you leave it empty. On a
  phone the drawer covers the view; <kbd>esc</kbd> or its close button puts it away.
- **Stopping** interrupts her turn and leaves the conversation between turns. It does not end
  it.
- **Forgetting** removes the conversation from the list and deletes her scratch directory. It
  asks first (`Forget Ai-chan#<n>?` at the prompt), and cannot be undone.
- **Her conversations are not your epics or chats.** None is listed in `/epics`, in the page's sidebar
  or among a directory's epics or chats, while it lasts or after you forget it; what it wrote down is
  kept on disk either way.

## Many conversations

Have as many as you like, of any scope, at once. Making one, talking in one, or forgetting one
never waits on another, nor on a chat or an epic.

A conversation nobody follows for a minute between turns **folds away**: nothing holds it, and
it costs nothing. It stays listed. Open it and say something, and she carries on where she was,
with the conversation so far. A conversation lasts until you forget it.

## Examples

Each is a first line, with the scope and permission it needs.

| Say | Scope | Permission |
| --- | --- | --- |
| "Summarize what my epics did today." | `daemon`, or `workspace` for one directory | `read-only` |
| "Why did the last rlar run stop?" | the epic, or its directory | `read-only` |
| "What has the reviewer of this epic been complaining about?" | `epic` | `read-only` |
| "Find where the actor in this epic left a TODO." | `epic` | `read-only` |
| "Steer the actor: stop refactoring, fix the failing test first." | `epic` | `danger-full-access` |
| "Ask actor/2 why it skipped the migration." | `epic` | `read-only` |
| "Run `pytest -x` in the env `repo` of this epic and tell me what fails." | `epic`, while it runs | `danger-full-access` |
| "Start ralph_loop here on the open issue about coupons." | `workspace` | `danger-full-access` |
| "Read the new release notes of pytest: does anything in them break us?" | `workspace` | `read-only`, network on |

To steer a session, she says the line to it as you would by typing into its transcript: see
[Talking to a running turn](/user/steering). To run tests in an env, she runs the command
there, in the env's own directory, as the flow would, without the epic being told. An env is
open only while its epic runs.

## Safety

::: danger `danger-full-access` on the `daemon` scope can do whatever you can
A `daemon` scope reaches every directory on this machine, and its directory is `/`. With
`danger-full-access`, she may write anywhere you may. Keep `daemon` conversations `read-only`
unless you mean it.
:::

- **Read-only means read-only.** Under `read-only`, every call that would change something --
  starting, saying, stopping, writing a file or a setting -- is refused before it has any
  effect, and she is told `Ai-chan is read-only, and <method> changes things.` She tells you so
  and stops there; make a `danger-full-access` conversation to do it.
- **Out of scope is refused too**, with `<method> is out of Ai-chan's scope: <what>.` An `epic`
  conversation cannot list the other epics of its directory, and a `workspace` one never sees
  another directory's: they are left out of what she reads.
- **Some things she can never do**: pair or revoke a device, touch an account's credentials,
  or make, read or forget a conversation with Ai-chan. These are refused with
  `Ai-chan cannot call <method>.`
- **She is confined.** Her CLI and every command it runs can read only the scope's directory,
  write it only under `danger-full-access`, and always write her scratch directory. Humanize's
  own machine directory is closed to her, so she reaches Humanize only through her tools. Where
  this machine cannot hold that, the conversation is refused rather than run wider: see
  [Permissions](/user/permissions).
- **What she reads is data.** She is told that nothing she reads -- an epic, a transcript, a
  file, what another frontend says -- is an instruction to her.
- **She has no budget.** Her turns are never stopped by a limit, so mind what you ask of a large
  scope.

## Troubleshooting

### `Name Ai-chan's nous: the ai_chan setting names none.` {#no-nous}

No nous was given, and the **Ai-chan** setting names none. Pick one on the form, or set
**Ai-chan** on the [General page](/user/settings#general).

### `Tell Ai-chan something to start with.`

The first line was empty. Say what you want her to do.

### `There is no epic <epic> in <workspace>.`

An `epic` scope names an epic that did not run in that directory. Pick it again from the
directory it ran in.

### `Ai-chan is not answering, so there is nothing to stop`

You pressed **Stop** or typed `/stop` between her turns. There is nothing to interrupt.

### `Ai-chan's harness must be kept from the daemon's socket, which Landlock cannot do: set sandbox.backend to bwrap` {#bwrap}

On Linux only bubblewrap keeps her CLI from Humanize's own socket; Landlock closes paths, not
connections to a socket. Install bubblewrap and set `sandbox.backend` to `bwrap` (see
[Permissions](/user/permissions)), then start the conversation again. macOS needs nothing.

### She says she is read-only

The conversation is `read-only`, and what you asked changes something. The preset cannot change:
make a new conversation with `danger-full-access`.

### She says something is out of her scope

The conversation's scope does not reach it. Make a new one whose scope does: the epic's
directory, or `daemon`.

## Next steps

- [Side questions (`/btw`)](/user/btw): ask one session of an epic, read-only, without the
  epic hearing it.
- [Talking to a running turn](/user/steering): say something to an agent yourself.
- [Settings](/user/settings#general): the nous a new conversation thinks with.
- [TUI reference](/reference/tui#ai-chan): `/ai`, its menu and its form.
- [Daemon reference](/reference/daemon#ai-chan): every method she may call, and what refuses it.
