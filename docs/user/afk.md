<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const agent = { r: '[m]agent · claude/claude-opus-5-5:high · ● 3[/]' }
const running = (mode, n) => ({
  l: `${mode}[c]·|·[/] agent… [m](2m14s · ctrl+c twice to stop)[/]${n ? '[n]3[/]' : ''}`,
  keys: 'shift+tab switch view · / commands · shift+enter newline · ← monitor · ctrl+c stop',
  hl: mode !== '',
})

const afk = [
  {
    label: '1 · here',
    lines: [
      '[dim]● agent is working · conversation 3 of 3[/]',
      '',
      '[dim]❯[/] /afk off',
      '[dim]here: an agent may stop and ask you[/]',
      '',
      agent,
      { rule: true },
      { prompt: '/afk on[n]1[/]' },
      { rule: true },
      running(''),
    ],
    caption: 'Where it starts: an agent that stops to ask waits for your answer.',
  },
  {
    label: '2 · away',
    lines: [
      '[dim]● agent is working · conversation 3 of 3[/]',
      '',
      '[dim]❯[/] /afk on',
      { t: '[dim]away: agents that ask are told nobody is here[/][n]2[/]', hl: true },
      '',
      agent,
      { rule: true },
      { prompt: '' },
      { rule: true },
      running('[y]afk[/] · ', true),
    ],
    caption:
      'Away. The status line says <code>afk</code>, in yellow, in front of everything else, for as long as it is on.',
  },
]

const one = [
  {
    label: 'on an outworlder',
    lines: [
      '[dim]─ reading outworlder human ─[/]',
      '[g]●[/] Hey, what shall we build next?',
      '[dim]   type an answer, or /afk to stop being asked[/][n]1[/]',
      '[dim]❯[/] /afk on',
      { t: '[dim]away as human: agents that ask are told nobody is here[/][n]2[/]', hl: true },
      '[dim]— the flow is done —[/][n]3[/]',
      '',
      { r: '[m]assistant · claude/claude-opus-5-5:high · ○ 1[/]' },
      { rule: true },
      { prompt: '' },
      { rule: true },
      {
        l: '[y]afk human[/][n]4[/] · [c]◉[/] chat[m] · ~/work/api[/]',
        keys: '/ commands · shift+enter newline · ← monitor · ctrl+c exit',
        hl: true,
      },
    ],
    caption:
      'In <code>chat</code>, every reply asks you for the next message, so being away ends the conversation.',
  },
]
</script>

# Being away — `/afk`

`/afk on` tells humanize that nobody is at the prompt. A question an agent or the flow asks you
is answered at once with nothing, and the run carries on instead of waiting for you. Turn it on
before you leave a long run alone.

::: info At a glance
- **You will** stop a run from waiting on you, and turn that off again when you are back.
- **Use it when** you leave a run that might ask you something: overnight, over lunch, or
  before you [detach](/user/leaving).
- **You need** `hmz` open, with or without a run. [Your first run](/user/first-run) starts
  one.
:::

## Try it

```text
/afk          flips it
/afk on       you are away
/afk off      you are here   ← where it starts
```

## How it works

Some flows ask you things: a planner that needs a decision, an agent that asks which of two
approaches you want, a chat that waits for your next message. Each question is put by an
**outworlder**, the role in a flow that is you, and while you are here it waits for your
answer. See [Questions](/user/questions).

`/afk on` says you are away. From then on:

- a question already waiting is answered by nobody, at once;
- an agent that asks is shown asking, is told nobody answered, and carries on;
- a flow's question is answered with nothing, or with the flow's defaults. One with no
  default fails the flow with `nobody is there to answer …`, unless the flow handles that, and
  `chat` ends. [Questions](/user/questions#when-nobody-is-there) has the table.

Away belongs to the run rather than to your interface. It stays said after you
[leave](/user/leaving), and every interface reading the run shows it.

## Example: leave a Ralph loop for the evening

A [`ralph_loop`](https://humanfia.ai/flows/ralph-loop) is working through a refactor and will run for hours. You
want it to keep going even if an agent stops to ask something. Step through what the screen
does:

<TermScreen title="hmz · ralph_loop" :frames="afk" />

What to look at, by number:

1. **`/afk on`**, typed on the transcript of every agent, so it covers the whole run.
2. **`away: agents that ask are told nobody is here`.** The confirmation. `/afk off` answers
   `here: an agent may stop and ask you`, and on an outworlder's transcript
   `here as <role>: agents may stop and ask you`.
3. **`afk ·` on the status line**, in yellow, in front of everything else. It stays there until
   you turn it off, so you cannot come back and forget it.

### Check it worked

- The status line starts with `afk`.
- Above the editor, no outworlder's line says `asking`, as
  `human · outworlder · asking` does while a question waits on you.
- If the flow asks something while you are away, the run carries on rather than showing
  `waiting for you` on the status line.

## One outworlder at a time

A flow may have more than one outworlder, each with a transcript of its own that
<kbd>shift+tab</kbd> reaches. Where you type `/afk` decides whom it is about:

| Where | `/afk` sets |
| --- | --- |
| an outworlder's transcript | that outworlder alone; the status line names it, `afk human` |
| every agent's transcript, or the monitor | every outworlder at once, undoing what was set for one |
| one conversation's transcript | nothing: it is not offered there, and says where it works |

Here is `/afk on` typed on the outworlder's transcript of a [`chat`](https://humanfia.ai/flows/chat), recorded
from a real run:

<TermScreen title="hmz · chat" :frames="one" />

1. **`type an answer, or /afk to stop being asked`**: the question waiting on you.
2. **`away as human: …`**: the confirmation names the outworlder it is about.
3. **`— the flow is done —`**: an empty answer to a chat's question ends the chat. This is why
   `/afk` belongs off in a flow built around talking to you.
4. **`afk human`**: away for that outworlder alone.

Where somebody else has [claimed](/reference/tui#several-people-on-one-run) an outworlder,
`/afk` from every agent's transcript leaves theirs as they left it, and `/afk` on their
outworlder's transcript is refused, saying whose it is.

::: tip `/afk` is about questions, not approvals
A flow's agents never wait for approval, whether you are here or away. See
[Permissions](/user/permissions).
:::

## Variations

- **Before a run starts.** `/afk on` works with nothing running. The next run starts away.
- **Without the interface.** `hmz exec` has nobody at a prompt, so it always runs as if `/afk`
  were on. A question an agent asks is still printed, in yellow, so you can read afterwards
  what it wanted. See [Run it unattended](/user/unattended).
- **From a flow.** A flow can check whether you are away. See
  [The person as an agent](/weaver/human-agent).

## Troubleshooting

### `hmz: /afk is only available on the monitor, the all-agents transcript and an outworlder's transcript, not on one agent's transcript`

You are reading one conversation. Press <kbd>shift+tab</kbd> until you are on every agent's
transcript, or on the outworlder's, and type it again.

### The chat ended as soon as I turned it on

In [`chat`](https://humanfia.ai/flows/chat), every reply asks you for the next message, and an empty answer ends
the conversation. Leave `/afk` off in any flow built around talking to you.

### I came back and the run is waiting on me

`/afk` was off, or was set for another outworlder. Answer the question, or type `/afk on` on
every agent's transcript to cover them all.

### I came back and a decision was made without me

That is what away means: the question was answered with nothing, or with the flow's own
default. Turn `/afk off` while you are at the prompt. To carry on from before that point, see
[Picking a run up](/user/resuming).

## Next steps

- [Questions](/user/questions): what each kind of question does with an empty answer.
- [Leaving it running](/user/leaving): close the terminal and keep the run.
- [Picking a run up](/user/resuming): for a run that stopped while you were away.
