---
pageClass: hmz-feature
---

<script setup>
import { withBase } from 'vitepress'
</script>

# Into its environments

<p class="hmz-tagline">Every machine a run works on, open beside it: its files, a shell, and what
changed.</p>

<div class="hmz-facts">

- **Every environment of the run.** Each role's environment, every worktree, scratch directory or
  copy a flow made of one, and a chat's own workspace, local or on another machine.
- **What it can do, not what the flow asked for.** Files are always there; a shell wherever the
  machine has one; changes wherever git is. What the flow declared only picks the panel you land
  on.
- **Written down.** Every file you write, every commit and every shell you open goes into the
  run's history under your name. What you type into a shell does not.
- **Gone when it goes.** An environment that closes stays on screen, read-only, saying so.

</div>

## In a browser

On a running epic, every environment in the **Epic** panel links to it; in a chat, open the
**Environment** panel beside the conversation, which is there for every chat however long ago
it was last said to: its folder is brought up as the panel opens. The Environments view lists every environment of
the run, grouped by role, with the ones a flow made nested under the one they came from.

<div class="hmz-facts">

- **Files.** A tree of the workdir, tabs, syntax highlighting, find and replace. You never save:
  a file is written 0.8 seconds after you stop typing, and when you leave it. If an agent changed
  it meanwhile, a banner offers **Compare**, **Keep mine** or **Reload**; a file you have not
  touched just follows what the agent writes. `Ctrl+P` opens any file by name, `Ctrl+Shift+F`
  searches them all. Drag the line between the tree and the editor, or move it with the arrow
  keys, to size the tree; a double click puts it back. The tree takes two fifths of the panel at
  the most, and in a panel narrower than 480 pixels it stands over the editor. Right-click an
  entry, or press the menu key on it, to make, rename, delete or copy its path.
- **Terminal.** A login shell in the workdir, as many as you like. Close the page and they keep
  running; open it again, or from another browser, and you see what they printed while you were
  away. A shell nobody has looked at for 10 minutes is closed, and every shell goes when its
  environment does.
- **Changes.** Like an editor's source control: merge conflicts, staged, changed and untracked
  files, a diff of each, stage, unstage, discard, commit, the last commits, and, where the run keeps
  them, the snapshots to rewind to. Rewinding waits until no agent is mid-turn there. What a
  file's buttons do is also in its menu, on a right click or the menu key, and `Delete` discards
  the one the keys are on, asking first. The line between the list and the diff sizes the list
  as the one in Files sizes the tree, between 200 pixels and two fifths of the panel.

</div>

## In the terminal

`/env` lists the same environments; `/env coder` opens the first of the role `coder`. **Files**
browses and edits with highlighting, or hands the file to `$VISUAL`/`$EDITOR` with `e`.
**Changes** stages, unstages, discards and commits. **Shell** gives the whole terminal to a shell
in the environment; type `~.` at the start of a line to come back, leaving it running.

## From another device

A device you paired, or one reaching this machine over EasyTier, reads and writes files and works
git like any other frontend, but cannot open a shell: a shell is the machine itself. To let it,
set this in [the settings file](/user/settings):

```yaml
envs:
  paired_terminals: true
```

::: warning Your user, on every machine the run reaches
Whatever you do in an environment you do as the user the daemon runs as, on the machine the
environment is on. Read [Security](/user/security).
:::

<div class="hmz-paths by-three">
  <a :href="withBase('/user/web')">
    <strong>In a browser</strong>
    <span>The page, its epics, and the panel these open from.</span>
  </a>
  <a :href="withBase('/user/remote-execution')">
    <strong>Where they are</strong>
    <span>Containers, SSH hosts and clusters a role can work on.</span>
  </a>
  <a :href="withBase('/reference/daemon')">
    <strong>How it is held</strong>
    <span>The host, its frontends, and doing it all from Python.</span>
  </a>
</div>
