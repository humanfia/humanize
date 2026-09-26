<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const screen = (said, answer, mode) => [
  '',
  `[dim]❯[/] /afk ${said}`,
  { t: `[dim]${answer}[/]`, hl: true },
  '',
  { r: '[m]agent · claude/claude-opus-5:high[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: `${mode}[c]◉[/] ralph_loop[m] · ~/work/api[/]`,
    keys: '/ commands · shift+enter newline · esc monitor · ctrl+c exit',
    hl: mode !== '',
  },
]

const afk = [
  {
    label: '/afk off',
    lines: screen('off', 'here: an agent may stop and ask you', ''),
    caption: 'Where it starts: an agent that stops to ask waits for your answer.',
  },
  {
    label: '/afk on',
    lines: screen('on', 'away: an agent that wants to ask is told nobody is here', '[y]afk[/] · '),
    caption:
      'Away. The status line says <code>afk</code>, in yellow, in front of everything else, for as long as it is on.',
  },
]
</script>

# Being away — `/afk`

`/afk on` tells humanize that nobody is at the prompt. A question an agent or the flow asks you
is answered at once with nothing, and the run carries on instead of waiting for you. Turn it on
before you leave a long run alone.

## Try it

```
/afk          flips it
/afk on       you are away
/afk off      you are here   ← where it starts
```

<TermScreen title="hmz · ralph_loop" :frames="afk" />

It works before a run starts and during one. A question already waiting when you turn it on is
dropped, and the flow is told nobody answered. What an empty answer means for each kind of
question is on [Questions](/user/questions).

::: tip `/afk` is about questions, not approvals
A flow's agents never wait for approval, whether you are here or away. See
[Permissions](/user/permissions).
:::

## When to leave it off

Leave it off in [`chat`](/flows/chat), and in any flow built around talking to you. Every
reply there asks you for the next message, so an empty answer ends the conversation.

## Without the interface

`hmz exec` has nobody at a prompt, so it always runs as if `/afk` were on. A question an agent
asks is still printed, in yellow, so you can read afterwards what it wanted. See
[Run it unattended](/user/unattended).

A flow can check whether you are away. See [The person as an agent](/weaver/human-agent).

## See also

- [Questions](/user/questions)
- [Picking a run up](/user/resuming), for a run that stopped while you were away
