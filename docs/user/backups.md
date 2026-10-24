# Backing epics up

Keep a copy of every epic in a git repository of your own, so that a machine you lose, or a
container you throw away, does not take its epics with it. Use this when epics run somewhere
other than your laptop, or when you want one place that holds the epics of every machine you
run on.

## Try it

Make an empty repository you can push to, say where it is in `~/.hmz/settings.yaml`, and run
an epic with it:

```yaml
backup:
  targets:
    - name: lab
      url: git@github.com:you/epics.git
      policies: [end]
  defaults: [lab]
```

```console
$ hmz exec -f chat -a assistant=claude/claude-haiku-4-5 "say hello"
did: say hello
hmz exec: backing the epic up
```

The repository now holds one commit, `Back up epic 20261012T091500.123Z-1a2b3c (end)`.

## Before you start

- A git repository you can push to from this machine, with no password prompt: an ssh key, or
  a credential helper. Humanize uses your own `git` and never asks for, or keeps, a password.
- `git` on `PATH`.

## What a backup is

A backup is the same files an [export](/user/export) holds, laid out as files instead of an
archive, with every credential struck out in the same way. Each epic goes into its own
directory:

```text
<machine>/<workspace>/<epic>/
    epic.jsonl            what happened, a line at a time
    manifest.json         what the epic was, and what each CLI was
    sessions/<session>/…  each agent's own log
```

`<machine>` is this machine's short host name and `<workspace>` the directory the epic ran in,
flattened, so one repository holds the epics of every machine and every project. Each backup is
one commit, naming the epic and why it was made, pushed to the target's branch; a backup of an
epic that has not changed since its last one makes no commit.

## When an epic is backed up

Each target says when, in `policies`. Tick any of them, or none:

| Policy | When |
| --- | --- |
| `session` | as each session of the epic closes |
| `interval` | every `every` minutes, while the epic runs |
| `end` | once the epic has ended: done, failed or stopped |
| none | only when you ask |

A backup never holds anything up. It runs behind the epic, one at a time per target, and a
target that cannot be reached is written down as a failed backup rather than an epic that
failed. `hmz exec` waits up to a minute for its last backups once it has printed its answer,
then leaves; `hmz` waits up to 15 seconds for the ones it started once you close it.

## Choosing the targets

`defaults` are the targets a new epic goes to. Choose others when you start it:

```console
$ hmz exec -f chat -a assistant=claude/claude-haiku-4-5 --backup lab --backup home "hi"
$ hmz exec -f chat -a assistant=claude/claude-haiku-4-5 --backup none "hi"
```

The epic remembers which targets it was started with. In `hmz`, the same targets are
written on the [Backup page](/user/settings#backup) of `/settings` -- `/settings backup`
-- and a flow's **backup** row on `/flow` switches on the ones its epics go to. In
[`hmz web`](/user/web), add and change targets under **Settings → Backup**, and pick an
epic's under **Options → Backup** as you start it. Either way the defaults are chosen until
you save or start the flow with others, and from then on what you chose for that flow in
that directory is.

## Backing an epic up by hand

```console
$ hmz backup 20261012T091500.123Z-1a2b3c
lab: backed up to git@github.com:you/epics.git
$ hmz backup 20261012T091500.123Z-1a2b3c --to home
```

Without `--to`, the epic goes to the targets it was started with, else to the defaults. An
epic [imported](/user/export) from another machine goes to the defaults: the targets it was
started with were that machine's, and so were its backups, which this machine does not show.
In a terminal a spinner says which targets it is backing up to until each has answered; so it
does for `--list` and `--pull` below.

In `hmz`, open the epic on `/epics` and choose **upload**, which does the same without waiting;
the epic then says how its last backup to each target went.

In [`hmz web`](/user/web), **Upload** in an epic's menu, or at the top of the epic, does the same
without waiting for it; hover it for how the last backup to each target went.

## Downloading an epic

A target holds the epics of every machine that backs up to it. List them, and download one into
this machine's epics, where it is an epic like any other:

```console
$ hmz backup --list --to lab
lab: 2 epics
  gpu-box  /home/you/code  20261012T091500.123Z-1a2b3c  done  fix the flaky test
  laptop  /Users/you/code  20261012T101500.456Z-4d5e6f  unfinished  write the docs
$ hmz backup --pull 20261012T091500.123Z-1a2b3c --to lab
/Users/you/.hmz/epics/-home-you-code/20261012T091500.123Z-1a2b3c
```

A download is an [import](/user/export#importing-a-run): it lands under the directory it ran in,
says which target and path it came from, and resumes only where that directory is here at the
same path, on the commit it was on. An epic you already have -- one this machine backed up and
still keeps, or one downloaded before -- is refused. Without `--to`, every target is looked in;
where two machines' epics share a name, name it as `<machine>/<workspace>/<epic>`.

In [`hmz web`](/user/web), **Download** on **Settings → Backup** lists what a
target holds by machine and then by directory, the ones already here marked **Here**; pick the
target where there is more than one. **Download** on an epic brings it here and opens it.
In `hmz`, **download…** on [`/settings backup`](/user/settings#backup) does the same with the
keys: <kbd>enter</kbd> on an epic brings it here, and `/epics` lists it.

From Python, `Hmz().backups.listed("lab")` lists them and
`Hmz().backups.pulled("lab", key)` downloads one; `listed` fetches first, so call it off any
thread a screen is drawn on.

## Check that it worked

```console
$ git clone git@github.com:you/epics.git && ls epics/*/*/
```

How each epic's last backup to each target went is written into the epic itself, so every
interface can show it.

## If it goes wrong

| What you see | Why | Do this |
| --- | --- | --- |
| `hmz exec: error: no backup target is named x` | `--backup x` names no target in settings | Add it, or name another. |
| `lab: failed: Permission denied (publickey)` | git could not sign in | Check `git ls-remote <url>` works without a prompt. |
| `hmz exec: a backup took longer than 60s and was left` | the remote is slow or unreachable | Run `hmz backup <epic>` once it answers. |
| `hmz backup: … is already here, at …` | the epic downloaded is one you have | Open it where it is. |

## Next steps

- [Settings reference](/reference/settings#backup) for every key.
- [CLI reference](/reference/cli#hmz-backup) for `hmz backup` and `--backup`.
- [Importing a run](/user/export#importing-a-run), which a download is.
