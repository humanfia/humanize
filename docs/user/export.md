---
title: Export and import a run
description: Pack an epic into one .hmzepic file with credentials removed, send it, and read it back in on any machine.
---

# Export and import a run

Export an epic to pack it into a single `.hmzepic` file for sharing. Import that file on any machine to read the epic back in.

![An epic is exported as one .hmzepic archive with secrets redacted, and imported as an epic on any machine](/diagrams/user-export-1.svg)

## What the archive contains

The `<epic name>.hmzepic` file is a gzip-compressed tar archive. It holds:

- `manifest.json`: the flow, task, outcome, agents, workspace path, git commit, Humanize version, and the version and SHA-256 of each coding agent CLI.
- `epic.jsonl`: the run record, plus one record for each flow it called.
- `sessions/<session>/`: every session log file.
- `traces/`: the epic's traces.
- The flow state of a resumable flow and any profiles.

The archive keeps prompts and agent output intact, and removes credentials.

## What is scrubbed

Humanize scrubs every file in the archive and replaces recognized secrets with `[redacted]`.

| What | Examples |
| --- | --- |
| Account variable values 8 characters or longer | an API key, a private gateway address |
| Keys in vendor formats | `sk-`, `pk-`, `ghp_`, `github_pat_`, `glpat-`, `xai-`, `xoxb-`, `hf_`, `AIza` |
| JSON Web Tokens and bearer tokens | `Bearer` followed by a token |
| URL credentials | `https://user:password@host` |
| Secret field and query parameter values | `token`, `api_key`, `secret`, `password`, `credential`, `signature` |

Humanize never removes token counts, costs, or model names. `manifest.json` lists the kinds of credential that are scrubbed under `redacted`.

::: warning
Scrubbing removes credentials only. Your task, prompts, and agent output remain in the file. Read [Security](/user/security) before attaching an export to a public issue.
:::

## Export an epic

### In the app

Open the epic and click **Export** in its bar. The app offers **Export** for any epic that is not running, and never for a chat.

![An ended epic in Humanize Desktop with the pointer on the Export button in the epic's bar](/shots/user-export-app.svg)

You can also right-click the epic's row in the sidebar or right-click its title and choose **Export**.

![The menu of an epic's row in the sidebar, with Copy link, Export and Upload](/shots/user-export-menu.svg)

Humanize Desktop saves the file to your Downloads folder and reveals it in Finder or File Explorer. Re-exporting the same epic saves `<epic name> (1).hmzepic` without overwriting the existing file. In a browser, the archive downloads like any other file.

### In the terminal

1. Type `/epics` and press <kbd>enter</kbd>.
2. Select the epic and press <kbd>enter</kbd>.
3. Choose `export epic`.
4. Enter a file or directory path, or keep the default `~/Downloads/`. Press <kbd>enter</kbd> to confirm the path, then press <kbd>enter</kbd> on `Done`.

![In hmz: /epics, an epic's menu with export epic chosen, the form that asks where the archive goes, and the line that says where it was written](/shots/user-export-terminal.svg)

The terminal first gathers a fresh trace of the epic into the archive; **Export** in the app packs the traces the epic already has. The list shows the archive path, its size, and its trace contents. Exporting to an existing archive path overwrites the file. Humanize sets the file permissions to mode `0600` (readable only by you).

To export an epic from a remote daemon, run `/epics @<daemon name>`, press <kbd>enter</kbd> on an epic that is not running, and choose `export`. The same form asks where the archive goes, and Humanize downloads it to that path on your local machine.

## Import an epic

### In the app

Drag and drop a `.hmzepic` file anywhere onto the window. The app imports the epic into the current daemon and opens it: a browser opens the epic's page, and Humanize Desktop opens its trace in Exomyth.

![A .hmzepic file is dragged over the page in a browser, which outlines itself; once dropped, the epic is in the sidebar and open](/shots/user-export-drop.svg)

You can also import a file in three other ways:

- Click **Search**, select **Import** under **Actions**, and pick the file.
- Right-click empty space in the sidebar list and choose **Import**.
- Double-click a `.hmzepic` file or open it with Humanize Desktop from your file manager. The app imports the epic and opens its trace in Exomyth.

In a browser, you can import a file already on the daemon's machine by navigating to `#/epics/import?path=<file>` with its full path. Click **Import** at the prompt to confirm. The page then opens the epic's trace in Exomyth.

![The browser page at the import address: the path of the file, an Import button and Cancel](/shots/user-export-address.svg)

If the epic already exists on the machine, Humanize refuses the import, names the existing epic, and shows an **Open** link.

![The notice of a refused import: the epic is already here, with an Open link](/shots/user-export-already.svg)

### In the terminal

1. Type `/epics` and press <kbd>enter</kbd>.
2. Press <kbd>i</kbd> or choose `Import…`.
3. Enter the file path. The form starts at `~/Downloads/`. Press <kbd>tab</kbd> to complete paths, or drop a file into the terminal to paste its path. Press <kbd>enter</kbd> to keep the path, then press <kbd>enter</kbd> on `Done`.

![The Import epic form in hmz, with the path of a .hmzepic file in Downloads typed](/shots/user-export-terminal-import.svg)

The list selects the imported epic and displays its target directory. If the epic already exists on the machine, the list says so and selects the existing epic.

![The list of epics in hmz after an import: the imported epic is selected, and the line under the list says imported into ~/shop](/shots/user-export-terminal-imported.svg)

### The Export and Import pages

The terminal also has an Export page and an Import page, opened from an epic's row menu in the navigator. Export lists every epic recorded on this machine; press <kbd>enter</kbd> on one and say where the archive goes. Import asks for the `.hmzepic`; <kbd>tab</kbd> finishes the path. Both show a moving bar while the archive is written or read, and you can press <kbd>esc</kbd> to leave: the transfer goes on, and the page shows what came of it when you open it again.

## Use an imported epic

An imported epic works like any local epic. Humanize files it under its original workspace path, even if that directory does not exist on your machine. See [History and search](/user/history) and [Trace a run with Exomyth](/user/tracing) to inspect it.

You can resume an imported epic only if the workspace exists at the same path on your machine and, for a git repository, contains the original commit (it does not need to be checked out). Otherwise, the app shows `Imported · not resumable here:` with the reason. See [Resume a run](/user/resuming).

## Copy a link to an epic

Click **Copy link** in an epic's bar or menu to copy its page address. The link contains no run data and works only for users who can reach the same daemon. A link copied in Humanize Desktop is the app's own address and does not open in a browser; copy it from the browser page to send it. Export the epic to share it with someone who cannot reach your daemon.

## From Python

Call `Hmz().epics.bundled(epic, output=...)` to write an archive and return its path and manifest. Call `Hmz().epics.imported(archive)` to import an archive and return the epic's location. See [The Python SDK](/builder/sdk).

## Good to know

- The web app uploads imports in chunks and refuses files over 2 GiB.
- Humanize refuses files that do not end in `.hmzepic`, archives containing multiple epics or symbolic links, and archives missing `manifest.json`.
- The harnesses `opencode`, `mimo` and `cursor-agent` keep their sessions in their own storage, so the archive holds no log files for their sessions. `manifest.json` says so for each such session.
- Imports are atomic: Humanize imports the entire epic or nothing, and never modifies the `.hmzepic` file.
- If you open or drop multiple files on Humanize Desktop at once, it imports only the last `.hmzepic` file.
- To store epics in a git repository instead of sending files, see [Back up to git](/user/backups).
