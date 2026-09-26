<script setup>
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const screen = (lines, mode) => [
  ...lines,
  '',
  { r: '[m]actor · claude/claude-opus-5:high · ○ 1[/]' },
  { r: '[m]reviewer · codex/gpt-5.6-sol:high[/]' },
  { r: '[m]input 38.1k · output 4.2k · cache_read 612.0k · cache_write 29.4k[/]' },
  { r: '[m]$1.87 · 21 out/s[/]' },
  { rule: true },
  { prompt: '' },
  { rule: true },
  {
    l: `${mode}[c]·|·[/] rlar… [m](252s · ctrl+c twice to stop)[/]`,
    keys: '/ commands · shift+enter newline · esc monitor · ctrl+c stop',
    hl: mode !== '',
  },
]

const notice = [
  {
    label: 'notice',
    lines: [
      '[y]●[/] [dim]claude is rate-limited (this account has spent its quota; another one, or a wait, is what answers it); carrying on as work[/]',
    ],
  },
]

const turn = [
  {
    label: '/details off',
    lines: screen(
      [
        '[dim]── actor[/]',
        '',
        '[dim]● actor is working[/]',
        '',
        '[g]●[/] The three failing tests pass now. The retry in charge() ran before the lock was taken, so a second charge could slip in between.',
        '',
        '[dim]✻ Worked for 74s · actor[/]',
      ],
      '',
    ),
    caption: 'The default: who is working, what each turn said, and how long it took.',
  },
  {
    label: '/details on',
    lines: screen(
      [
        '[dim]── actor[/]',
        '',
        '[dim]● actor is working[/]',
        '',
        '[g]●[/] Read[dim](tests/test_pay.py)[/]',
        '[g]●[/] Grep[dim](def charge)[/]',
        '[g]●[/] Read[dim](src/pay.py)[/]',
        '',
        '[dim i]The retry runs before the lock is taken. A second call can get in there.[/]',
        '',
        '[g]●[/] Edit[dim](src/pay.py)[/]',
        '[g]●[/] Bash[dim](pytest -q tests/test_pay.py)[/]',
        '',
        '[g]●[/] The three failing tests pass now. The retry in charge() ran before the lock was taken, so a second charge could slip in between.',
        '',
        '[dim]✻ Worked for 74s · actor[/]',
      ],
      '[m]details[/] · ',
    ),
    caption:
      'Every tool call and every line of thinking, and <code>details</code> in front of the status line.',
  },
]
</script>

# Showing the working — `/details`

By default the screen shows what each turn said and nothing of how it got there. Turn
`/details` on to see every tool call, every line of thinking, and whatever a flow or backend
prints along the way. Reach for it when a turn is slow or does something you did not expect.

## Try it

```
/details          flips it
/details on       show the working
/details off      show only what each turn said   ← where it starts
```

Here is one turn of [`rlar`](/flows/rlar)'s actor, both ways:

<TermScreen title="hmz · rlar" :frames="turn" />

Turning it on shows what arrives from then on. What scrolled past while it was off stays
hidden, but the run's [trace](/user/tracing) has all of it.

## What it never hides

A yellow `●` line is humanize saying what it is doing about a turn: waiting out a rate limit,
carrying on as another account, cutting a turn off. It shows either way, because it is what
tells a turn that is waiting apart from one that has hung.

<TermScreen title="hmz · rlar" :frames="notice" />

## It changes only the screen

The agents are not told, and they do not work any differently. The run and its trace are the
same either way.

| Turn it on | Leave it off |
| --- | --- |
| The first time you run a flow, to see what its turns do | For a long run you only check on now and then |
| When a turn takes far longer than it should | When you want each answer without scrolling past its tools |

A flow can watch its agents' tool calls itself. See [Hooks](/weaver/hooks).

## See also

- [Watching a run](/user/monitor)
- [Cost and rate](/user/tally)
- [Tracing](/user/tracing), for all of it afterwards
