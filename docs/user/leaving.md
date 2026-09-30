<script setup>
import Term from '../.vitepress/theme/components/user-prompt/Term.vue'
import TermScreen from '../.vitepress/theme/components/user-running/TermScreen.vue'

const back = [
  {
    label: 'hmz, later',
    lines: [
      '[dim]❯[/] Fix the bug in calc.py. [m]· by you@tui[/][n]1[/]',
      '[dim]── agent[/]',
      '[dim]● agent is working[/]',
      '[g]●[/] Found the bug: add() subtracts. Fixing it now.',
      '[dim]✻ Worked for 7s · agent[/]',
      '[dim]● agent is working · conversation 2 of 2[/][n]2[/]',
      '',
      { r: '[m]agent · claude/claude-haiku-4-5-20251001:high · ● 2[/]' },
      { r: '[m]$0.05 · 151 out/s[/]' },
      { rule: true },
      { prompt: '' },
      { rule: true },
      {
        l: '[c]·/·[/] agent… [m](24s · ctrl+c twice to stop)[/][n]3[/]',
        keys: '/ commands · shift+enter newline · ← monitor · ctrl+c stop',
      },
    ],
    caption:
      'A new interface on the same run, read from the top. Everything the run did while you were away is here.',
  },
]
</script>

# Leaving it running

A run does not need your terminal. Close the window, lose the ssh connection, or `/exit` and
choose `detach and exit`: the flow goes on taking its turns. Run `hmz` in the same directory
and you are back in it.

::: info At a glance
- **You will** walk away from a long run and come back to it later, from the same terminal or
  another one.
- **Use it when** a run will take longer than you want to sit and watch it, or your
  connection to the machine may drop.
- **You need** a flow running in `hmz`, started as in [Your first run](/user/first-run).
:::

## Try it

While a flow runs, type `/exit`, choose `detach and exit`, and later, in the same directory:

```sh
hmz
```

## How it works

The run is not held by the `hmz` you are looking at. It is held on this machine, apart from the
terminal, one run per directory, and `hmz` is a window onto it. Closing the window, on purpose
or because the connection dropped, leaves the run where it was. Running `hmz` again in the same
directory opens a new window onto the same run, and reads it from the top.

That has three consequences:

- **One run per directory.** `hmz` in a directory always opens that directory's run. Another
  project has its own.
- **Several windows at once.** A second terminal, or an ssh session from elsewhere, can open
  the same run while you still have it open. Each is a whole interface of its own. See
  [Several people on one run](/features/daemon#several-people-on-one-run).
- **The run lives on this machine.** Your laptop can close; the machine running `hmz` cannot. A
  reboot ends the run.

## Example: detach, then come back

Start a flow, as in [Your first run](/user/first-run). Then type `/exit`, or press
<kbd>ctrl+q</kbd>, which asks the same thing:

<Term title="/exit">

<pre><span class="p b">A flow is running.</span>

<span class="p">❯</span> <span class="d">1.</span> <span class="p">stop the flow and exit</span>
  <span class="d">2.</span> <span class="p">detach and exit</span>           <span class="m">run `hmz` here to reattach</span><span class="n">1</span>

<span class="d">enter choose · esc stay</span></pre>

</Term>

1. **`detach and exit`** is only offered where the run can outlive the terminal. Where it
   cannot, the answer in its place is `cancel`; see [below](#when-it-cant-be-left-running).

Press <kbd>↓</kbd> and <kbd>enter</kbd> on `detach and exit`. Your shell comes back, and the
flow is still going.

Later, from any terminal on the same machine:

```sh
cd ~/tmp/humanize-demo
hmz
```

<TermScreen title="hmz · ralph_loop" :frames="back" />

What to look at, by number:

1. **Your task, marked `· by you@tui`.** The new window reads the run from its first line, so
   everything said to it is there. A line typed in another window, the one you left included,
   is marked with who typed it.
2. **The rounds you missed.** A Ralph loop kept opening a conversation a round. Here it is on
   its second, and the first one's work is above it.
3. **The status line.** Still running, with the clock of the turn in progress, and
   `ctrl+c stop` as the last key: this window can stop the run as well as the one you left.

### Check it worked

- After `detach and exit`, the shell prompt comes back at once, with no `stopping` line.
- `hmz` in the same directory opens on the flow, still working, and not on a fresh `chat`.
- The transcript holds turns that happened while you were gone.

## Before you walk away

- **Say you are away.** A flow that asks you something waits for an answer. Type `/afk on`
  before you go, and it is answered with nothing instead: away stays said after you have left.
  A role you [claimed](/reference/tui#several-people-on-one-run) is anybody's to answer once
  you leave. See [Being away](/user/afk).
- **Give it a budget you can live with.** Nobody is watching the spend. See
  [Every run has a budget](/features/allowances).
- **Know how to stop it later.** Open it with `hmz`, then press <kbd>ctrl+c</kbd> twice or type
  `/stop`. That stops it for everybody reading it. <kbd>ctrl+c</kbd> never leaves a run
  behind. See [Stopping](/user/stopping).

## Variations

- **Just close the window.** Closing the terminal or losing the connection does what
  `detach and exit` does. `/exit` only asks so that you choose on purpose.
- **Watch from two places.** Leave one `hmz` open and run another in the same directory, over
  ssh for example. Leaving one leaves the others reading it.
- **Nobody watching at all.** A run with no one at any window belongs on a command line: see
  [Run it unattended](/user/unattended).

## When it can't be left running {#when-it-cant-be-left-running}

Then the interface holds the run in its own process, and closing the terminal ends the run.
`/exit` offers `cancel` in place of `detach and exit`. That happens when:

- **stdin or stdout is not a terminal**: output redirected to a file, or input from a pipe;
- **`HUMANIZE_DAEMON` is `off`**, `0` or `no`, for a machine where a run should end with its
  window:

  ```sh
  HUMANIZE_DAEMON=off hmz
  ```

- **humanize could not set it up**, which it says as it opens:
  `hmz: runs cannot be detached from the terminal (…), so they will run in this process
  instead`.

## Troubleshooting

### `hmz` opened on an idle prompt, not on my run

You are in another directory. A run belongs to the directory it was started in: `cd` there and
run `hmz` again.

### The run was gone when I came back

The machine was restarted, or the run ended by itself: its budget was spent, or the flow
finished. `/epics` lists it with how it ended. A flow that can be picked up carries on with
`/resume`; see [Picking a run up](/user/resuming).

### It was waiting for me the whole time

A question was put to you and nobody answered. Turn [`/afk`](/user/afk) on before you leave.

### `/exit` offers `cancel` instead of `detach and exit`

The run cannot outlive this terminal. See
[When it can't be left running](#when-it-cant-be-left-running).

## Next steps

- [Being away (`/afk`)](/user/afk): keep a run you left from waiting on you.
- [Stopping](/user/stopping): end it when you are back.
- [Picking a run up](/user/resuming): carry on after a reboot or a stop.
- [The terminal can leave](/features/daemon): how a run outlives its terminal, drawn.
- [Daemon reference](/reference/daemon): the details.
