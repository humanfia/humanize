---
title: Find and install flows
description: Install flows from a flowverse, keep them up to date, add your own, and start one from a chat line.
---

# Find and install flows

Humanize ships with no flows. Install flows from a flowverse (a git repository that lists flows and their releases) or keep your own in a local folder.

![Where flows come from and what each is called](/diagrams/user-flows-1.svg)

## Where flows come from

| Source | What it is | Name of a flow in it |
| --- | --- | --- |
| `official` | The official flowverse, `humanfia/flowverse`. Always listed and cannot be removed. Browse its catalogue at [humanfia.ai/flows](https://humanfia.ai/flows/). | `goal` |
| A flowverse you add | Any other index repository under a name you choose. | `@team/review` |
| `local` | Flows in `.hmz/flows/` of the project. | `@local/review` |
| `user` | Flows in `~/.local/share/humanize/flows/`. | `@user/review` |

Humanize looks up bare names like `review` in the project first, then your home folder, then `official`, and then other flowverses in alphabetical order. A project flow overrides an official flow of the same name.

Chat requires no flow. See [Chat with an agent](/user/chat).

## In the app

Click **Flows** in the sidebar to see the **Installed** and **Flowverses** tabs.

### Install a flow

1. Open the **Flowverses** tab. It opens on the **Official** flowverse.
2. Pick a release next to the flow. The list defaults to the newest stable release and marks pre-releases with `(pre)`.
3. Click **Install**. Humanize installs the release and its dependencies, then shows the installed version on the row.

![The Flowverses tab: Install is clicked on rlar, which then shows on the Installed tab](/shots/user-flows-install.svg)

Installed flows appear as cards on the **Installed** tab. Click a card to view its description, ref, resumability, agent roles, environments, and params. Click **New epic** to run it; see [Start an epic](/user/epics).

When no flows are installed, the tab shows `No flows installed yet.` with a **Browse Flowverses** button.

### Update, switch release or uninstall

When a flowverse lists a newer release for an installed flow, the sidebar **Flows** item shows a badge, the page shows `1 update`, and the flow card shows `0.2.0 out`.

![The Installed tab with a flow open and the Update button](/shots/user-flows-installed.svg)

| To | Do this |
| --- | --- |
| Update | Open the card and click **Update to 0.2.0**, or right-click the card and select it from the menu. |
| Switch to another release | On the **Flowverses** tab, select the release next to the flow and click **Switch**. A `✓` marks the installed release. |
| Uninstall | Click **Uninstall** on the open card or on the **Flowverses** tab, then confirm. |
| Copy a flow's name | Right-click the card and select **Copy name**. The menu also offers **New epic** and **Show**. |

![A flowverse's tab: the release list, Switch, Uninstall, Fetch and Remove](/shots/user-flows-flowverse.svg)

### Add, fetch or remove a flowverse

1. On the **Flowverses** tab, click **Add flowverse** (the plus icon next to the tabs).
2. Enter the repository in **URL** as `owner/repo` for GitHub or as a full URL. Leave **Name** blank to use the repository name, or type your own.
3. Click **Add**. A new tab appears listing the flowverse's flows.

![A flowverse is added by its repository and lists its flow](/shots/user-flows-add.svg)

Click **Fetch** (the round arrow next to the flowverse name) to reload the index and check for new releases. Click **Remove** and confirm to delete the flowverse and uninstall all flows from it. Right-click a flowverse tab for **Open**, **Fetch**, and **Copy URL**.

An unfetched flowverse displays `Not fetched yet.` with a **Fetch** button. If the index contains invalid entries, expand the `skipped` line to see each entry and why it failed.

## In the terminal

Type `/flow` and press <kbd>enter</kbd>. The menu opens on **Installed**, grouping ready-to-run flows by source and marking available updates with `↑`. Press <kbd>enter</kbd> to open a row, <kbd>tab</kbd> to focus buttons, <kbd>/</kbd> to search, <kbd>m</kbd> to open the row menu (open, update, uninstall, copy here and copy name for a flow; open, fetch, remove and copy URL for a flowverse), and <kbd>esc</kbd> to go back.

### Install a flow

1. Press <kbd>tab</kbd>, then press <kbd>enter</kbd> on **Install more…** to list flowverses.
2. Press <kbd>enter</kbd> on a flowverse, then on a flow. Releases appear newest first with their tag, commit, and licence.
3. Press <kbd>enter</kbd> on a release to install it and its dependencies immediately.

![The terminal: /flow, Install more, the official flowverse, rlar's releases, installed](/shots/user-flows-terminal.svg)

Press <kbd>enter</kbd> on a different release of an installed flow to switch versions.

### Update, uninstall or copy

Select a flow on the **Installed** screen and use the action buttons.

| Button | What it does |
| --- | --- |
| **Install more…** | Opens the flowverse list. |
| **Update** | Installs the newest available release, if one exists. |
| **Uninstall** | Removes the installed flow. |
| **Copy here** | Copies the flow into the project's `.hmz/flows/` folder for editing. Disabled for project flows, and refused if the project already has a flow of that name. |
| **Search…** | Filters the list. |

![The Installed page in the terminal with a newer release marked](/shots/user-flows-terminal-installed.svg)

Use **Copy here** to customize an installed flow without losing your changes on the next update. Because project flows take precedence, the bare name now resolves to your local copy.

![rlar copied into the project and listed as @local/rlar](/shots/user-flows-terminal-copied.svg)

### Add, fetch or remove a flowverse

Open **Install more…** to manage flowverses. **Add flowverse…** prompts for `repository` and `name`. **Fetch again** reloads the index for the selected flowverse. **Remove** prompts `Remove <name>?` and deletes the flowverse along with any flows installed from it.

All flow and flowverse actions take effect immediately. **Save** only saves the role configuration for the flow you are setting up to run.

## Add your own flows

Place a Python file or folder in `.hmz/flows/` to use it in the current project, or in `~/.local/share/humanize/flows/` to use it everywhere. Humanize loads these flows directly and reloads them whenever you save changes. To build one, see [Write your first flow](/tutorials/first-flow) and [Anatomy of a flow](/builder/flow).

In the app, the **Flows** page lists installed flows and those in `~/.local/share/humanize/flows/`, but not a project's. Select project flows from the **New epic** page.

## Start a flow from a chat line

Type `$` followed by a flow name and a task in the chat input to start a flow. Type `$` by itself to autocomplete flow names.

```text
$ralph_loop Add a discount code to checkout
```

![The app's message box offering flows after $r](/shots/user-flows-dollar.svg)

![The terminal prompt offering flows after $r](/shots/user-flows-terminal-dollar.svg)

- In the terminal, the flow starts immediately if it is already configured for this folder. Otherwise, `/flow` opens on its roles and starts the epic when you save. If you omit the task, nothing starts: the flow is set up and the terminal tells you to give it a task with `/flow <name> <task>`.
- In the app, the flow starts using the folder's last setup for that flow. If you omit the task, the **New epic** page opens with the flow selected.
- Typing `/flow ralph_loop` followed by a task works the same way in both interfaces.

If a skill shares a name with a flow, the chat preference determines which one `$` runs. See [Commands, skills and files in a chat](/user/chat-input).

## From the command line

Run `hmz exec -f` to execute an installed flow by name. `hmz exec` never installs flows; if a flow is available in a flowverse but not installed, the command fails and tells you which flowverse provides it. `-f` also takes a path to a flow file or folder, starting with `.`, `/` or `~`.

![hmz exec refuses rlar because it is not installed](/shots/user-flows-exec-refused.svg)

Install flows using the app, the terminal, `hmz flowverses install`, or [The Python SDK](/builder/sdk). For all `hmz exec` flags, see [The command line](/user/command-line).

### Manage flows and flowverses

`hmz flows` and `hmz flowverses` do what the **Flows** page does.

```bash
hmz flowverses list                          # flowverses, installed flows, newer releases
hmz flowverses add acme/flows --name team    # add a flowverse
hmz flowverses show team                     # its flows and every release
hmz flowverses install @team/review          # install, or update to the newest release
hmz flowverses install @team/review --version 1.2.0   # switch release
hmz flowverses uninstall @team/review        # asks first; -y skips the question
hmz flowverses fetch team                    # check for new releases
hmz flowverses remove team                   # asks first; -y skips the question
```

To start a flow, read what it needs, then check the line before you run it:

```bash
hmz flows list                # the flows on offer in this folder
hmz flows show ralph_loop     # roles, params, and an hmz exec line to fill in
hmz flows backends            # every harness, account and model, written as -a takes it
hmz flows check ralph_loop -a coder=claude/claude-opus-5:high -p budget.cost=5
```

`hmz flows setup` takes the same options as `check` and saves them for the folder, so a new epic of that flow opens with them filled in. `hmz flows fork ralph_loop` copies a flow into `.hmz/flows/` of the folder so you can edit it.

Every command takes `--json` and prints its full help with `-h`. See [Command-line reference](/reference/cli#hmz-flows).

### Manage folders

```bash
hmz workspaces list              # every folder Humanize knows, the current one first
hmz workspaces add ~/code/app    # add a folder before anything runs in it
hmz workspaces forget ~/code/old # forget a folder's settings and flow set-ups
hmz workspaces browse ~/code     # list folders on the daemon's machine
hmz workspaces complete '~/co'   # complete a partly typed path
```

## Good to know

- Flows are Python code, and Humanize loads the code of every installed flow to list it. Only install flows from repositories you trust.
- Fetching updates the list of available releases without changing your installed flows, and overwrites any local changes in the index cache.
- You cannot uninstall a flow while another installed flow depends on it. Uninstall the dependent flow first.
- In the app and from `hmz flowverses`, installing, switching, uninstalling and removing a flowverse are refused while an epic is running on the machine: `An epic is running: flows change once none is.`
- A flowverse name starts with a letter or digit, uses letters, digits, `.`, `-` and `_`, and cannot be `official`, `local` or `user`.
- While a flow is running in the terminal, `/flow` only opens that flow's roles, and `$` returns `hmz: cannot choose a flow while one is running`.
- Opening the terminal fetches all flowverses in the background without installing updates, skipping any index you have edited by hand. When updates are available, the status line shows `1 flow update`.
- Flows that fail to load appear in red in the terminal along with the error message.
- To publish your own flows or host a flowverse, see [Publish and version a flow](/builder/publishing).
