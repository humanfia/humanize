---
title: Back up to git
description: Keep a copy of every epic and chat in a git repository of your own, pick which repositories an epic goes to, and download an epic or chat back onto any machine.
---

# Back up to git

A backup target is a git repository of your own where Humanize copies epics and chats. One repository can hold epics from every machine and project, so losing a machine or a container does not lose your runs.

![Two machines push their epics to one git repository, each epic in a directory named by machine, workspace and epic](/diagrams/user-backups-1.svg)

Humanize pushes using your machine's `git` and its configured credentials, such as an SSH key. It never prompts for a password, so the repository must accept pushes without asking. An empty repository works: the first backup creates the branch.

## Target settings

Targets belong to your home directory, not to a workspace.

| Field | What it is | Default |
| --- | --- | --- |
| Name | Up to 32 letters, digits, `-`, and `_`, starting with a letter or digit. Epics reference targets by name, and the app does not let you change it later. | |
| Repository | The git URL. | |
| Branch | The branch epics are committed to. | `main` |
| When | The automatic backup policies below. If none are ticked, the target backs up only on demand. | none |
| Default | Send new epics to this target unless you pick others. Chats always go to the default targets. | off |

Policies trigger backups automatically:

| Policy | In the settings file | Backs up |
| --- | --- | --- |
| **On session close** | `session` | Each time one of the epic's sessions closes. |
| **Every N minutes** | `interval` | Every N minutes while the epic runs. N is at least 1 and defaults to 30. |
| **On epic end** | `end` | Once when the epic finishes, fails, or stops. |

Backups run in the background without slowing the epic down. If a backup fails, the epic records the failure and does not fail itself.

## In the app

### Add a target

1. Open **Settings**, then **Backup**.
2. Under **New target**, fill in **Name** and **Repository**. Change **Branch** if needed.
3. Under **When**, tick the policies you want.
4. Click **Save**. The target appears in the **Targets** table.
5. Tick **Default** on its row to send new epics there automatically.

![Adding a target in Humanize Desktop: the name lab and a repository are typed, On epic end is ticked, Save adds the row, and Default is ticked](/shots/user-backups-add.svg)

Click **Edit** on a row to load the target into the form. Click **Remove**, then confirm, to delete it. Click **Batch apply** to copy your targets to your other daemons.

![Settings, Backup in Humanize Desktop: the targets lab, backed up to on epic end and a default, and offsite, manual](/shots/user-backups-settings.svg)

### Choose where an epic goes

On the **New epic** page, the **Backup** section shows a checkbox for each configured target. Default targets start ticked. Untick all of them to skip backing up the epic. Humanize remembers your choice for that flow in that folder.

![The New epic page with a Backup group: lab is ticked and offsite is not](/shots/user-backups-new-epic.svg)

### Back up now

Click the **Upload** arrow at the top of an epic, or choose **Upload** from the menu of an epic or chat in the sidebar. The page shows `Uploading to lab` and returns immediately. The upload goes to the epic's assigned targets, or to the default targets if none were assigned. Hover over **Upload** to see the status of the last backup to each target.

![Upload is clicked at the top of an epic, and the page says Uploading to lab](/shots/user-backups-upload.svg)

### Download from a target

1. Open **Settings**, then **Backup**, and click **Download**.
2. If you have multiple targets, pick one from the list at the top of the dialog.
3. The dialog lists every epic and chat in the target, grouped by machine and folder, newest first. Items already on this machine are marked **Here** with an **Open** button.
4. Click **Download** on a row to copy the epic or chat to this machine and open it.

![Download is opened from Settings, Backup; it lists an epic of studio marked Here and one of gpu-box; Download brings that one here and opens it](/shots/user-backups-download.svg)

## In the terminal

Type `/settings backup` to list each target with its URL, branch, and policies. A `✔` marks a default target. Press <kbd>enter</kbd> on a target to edit it, or choose **Add target**. On the form, **Every N minutes** offers 5, 10, 15, 30, 60, or 120 minutes, and **Remove** deletes the target. Choose **Done** on the form, then **Save** on the page to write your changes.

![/settings backup in the terminal interface lists lab and offsite; enter on lab opens its form with name, URL, branch, the three policies and Default](/shots/user-backups-tui.svg)

To choose targets for a flow, type `/flow`, press <kbd>enter</kbd> on the flow, and press <kbd>enter</kbd> on the `backup` row. A sheet opens with a switch for each target.

![The Backup sheet of the flow goal in the terminal interface: a switch per target, lab on and offsite off](/shots/user-backups-tui-flow.svg)

To back up an epic now, open `/epics`, press <kbd>enter</kbd> on the epic, and choose `upload`, which is listed once a target exists. For a chat, type `/resume` inside a chat, press <kbd>m</kbd> on the chat, and choose `upload`.

To download, choose **Download…** on `/settings backup`, then press <kbd>enter</kbd> on an epic or chat. Choose **Fetch** to re-read the repository, **Target…** to switch targets, or **Search…** to filter by flow, task, directory, or machine.

![Download from lab in the terminal interface: an epic of studio marked here, and one of gpu-box under /srv/shop](/shots/user-backups-tui-download.svg)

## From the command line

Pass `--backup` when starting an epic to pick its targets. Repeat `--backup` for multiple targets, or pass `--backup none` to disable backups. Without the flag, the epic uses the default targets.

```console
$ hmz exec -f goal -a worker=claude/claude-haiku-4-5 -p budget.cost=1 --backup lab --backup offsite "add a discount code to checkout"
```

When the epic ends, `hmz exec` waits up to 60 seconds for its backups to finish.

Use `hmz backup` to back up, list, and download runs:

| Command | What it does |
| --- | --- |
| `hmz backup EPIC` | Backs up one epic or chat now and waits. `EPIC` is an epic name in this directory, a chat id, or a path. |
| `hmz backup --list` | Lists the epics and chats held by every target. |
| `hmz backup --pull EPIC` | Downloads an epic or chat from the first target that holds it and prints its local path. |
| `--to NAME` | Restricts the command to this target. Repeatable. Works with all three commands. |

![hmz backup with an epic name answers lab: backed up to the repository; --list shows two epics and a chat by machine, workspace, name, ending and task; --pull prints the path of the downloaded epic](/shots/user-backups-cli.svg)

Without `--to`, `hmz backup EPIC` uses the targets the epic started with, or the defaults. If two machines backed up an epic with the same name, `--pull` lists both. Specify the one you want as `<machine>/<workspace>/<epic>`.

| Exit status | Meaning |
| --- | --- |
| 0 | Every target succeeded. |
| 1 | A target failed, or the epic to download is already on this machine. |
| 2 | No such epic, no such target, or no targets configured. |

You can also configure targets in `~/.hmz/settings.yaml`. See [settings.yaml](/reference/settings) for all keys.

```yaml
backup:
  targets:
    - name: lab
      url: git@github.com:you/epics.git
      branch: main
      policies: [end]
      every: 30
  defaults: [lab]
```

## Repository layout

Each epic is stored as plain files at `<machine>/<workspace>/<epic>/` on the target's branch. `<machine>` is the short hostname, and `<workspace>` is the flattened path of the folder where the epic ran. The directory contains the same files as an [exported run](/user/export): `epic.jsonl`, `manifest.json`, and `sessions/`. Chats follow the same layout under their chat id.

Each backup creates one commit naming the epic and the trigger: `session`, `interval`, `end`, or `manual`. If the epic has not changed since the last backup, Humanize skips the commit. If git has no author identity configured, Humanize commits as `hmz <hmz@localhost>`.

Humanize replaces secrets with `[redacted]` before committing, matching the behavior of an export. See [Security](/user/security).

## Good to know

- A downloaded epic is treated as an import. It lands under the folder path where it originally ran, and its record notes which target it came from. You can [resume](/user/resuming) it only if that folder exists at the same path on this machine and, for a git repository, holds the commit the epic was on.
- Downloading an epic that already exists locally fails with `is already here`.
- A downloaded chat lands in this machine's chat list. Continue it with `/resume` in a chat.
- Starting an epic with an unknown target name fails immediately before the epic runs.
- Every git command times out after 120 seconds and never prompts. An error like `Permission denied (publickey)` means git could not authenticate; check that `git ls-remote` succeeds on the URL without prompting.
- If a backup is still running on exit, `hmz exec` waits up to 60 seconds and `hmz` waits up to 15 seconds. Run `hmz backup EPIC` to retry an interrupted backup.
