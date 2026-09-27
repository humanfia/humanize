# Leaving it running

A run does not need your terminal. Close the window, lose the ssh connection, or `/exit` and
choose to leave it running: the flow goes on taking its turns. Run `hmz` in the same directory
and you are back in it.

## Try it

Start a flow, as in [Your first run](/user/first-run). Then type `/exit`, or press
<kbd>ctrl+q</kbd>, which asks the same thing:

```text
A flow is running.

❯ 1. stop it, then leave
  2. leave it running             `hmz` here reads it again

enter choose · esc stay
```

Choose `leave it running`. Your shell comes back, and the flow is still going.

Later, from any terminal on the same machine:

```sh
cd ~/tmp/humanize-demo
hmz
```

A new interface opens on the run and reads it from the top: everything it has done so far,
what it asked and who answered, as if you had never left.

## What to know before you walk away

- **One run per directory.** `hmz` in a directory always opens that directory's run. Another
  project has its own.
- **Several interfaces at once.** Open `hmz` in the same directory from a second terminal, over
  ssh for example, and each is a whole interface of its own on the same run. Leaving one leaves
  the others reading it. See [Several people on one run](/features/daemon#several-people-on-one-run).
- **Questions wait for you.** A flow that asks you something waits for an answer. Type
  `/afk on` before you go, and it is answered with nothing instead: away stays said after you
  have left. A role you [claimed](/reference/tui#several-people-on-one-run) is anybody's to
  answer once you leave. See [Being away](/user/afk).
- **Stopping it later.** Open it with `hmz`, then press <kbd>ctrl+c</kbd> twice or type
  `/stop`. That stops it for everybody reading it. <kbd>ctrl+c</kbd> never leaves a run behind.
- **A reboot ends it.** The run lives on this machine. A flow that can be picked up carries on
  with `/resume`. See [Picking a run up](/user/resuming).

## When it can't be left running

Then the interface holds the run in its own process, and closing the terminal ends the run.
`/exit` offers `stay here` in place of `leave it running`. That happens when:

- **stdin or stdout is not a terminal**: output redirected to a file, or input from a pipe;
- **`HUMANIZE_DAEMON` is `off`**, `0` or `no`, for a machine where a run should end with its
  window:

  ```sh
  HUMANIZE_DAEMON=off hmz
  ```

- **humanize could not set it up**, which it says as it opens:
  `hmz: the runs here cannot be held apart from the terminal (…), so they are held in this
  process instead`.

A run nobody watches at all belongs on a command line: see [Run it
unattended](/user/unattended). How a run outlives its terminal is on [The terminal can
leave](/features/daemon), and the details are in the [Daemon reference](/reference/daemon).

<style scoped>
kbd {
  display: inline-block;
  padding: 0 6px;
  border: 1px solid var(--vp-c-divider);
  border-bottom-width: 2px;
  border-radius: 5px;
  background: var(--vp-c-bg-soft);
  font-family: var(--vp-font-family-mono);
  font-size: 0.85em;
  line-height: 1.6;
  white-space: nowrap;
}
</style>
