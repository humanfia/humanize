---
title: Humanize Desktop
description: Know what the desktop app adds to the page, how its window, menus, files and notifications behave, and what to do when it does not start.
---

# Humanize Desktop

Humanize Desktop runs the `hmz web` page in its own window on macOS and Windows. It works the same way as [the browser page](/user/web); this guide covers only what the app adds. To install or update it, see [Install and update](/user/install).

![Humanize Desktop on macOS: a chat is open, and the window's close, minimize and full-screen lights sit in the page's top row beside the sidebar buttons](/shots/user-desktop-window.svg)

## What the app adds

The app bundles the page from its release. It runs no `hmz web` server and holds no epics itself.

![Humanize Desktop reaches the Local daemon by running hmz daemon connect --stdio, and daemons on other machines over ssh, tcp, ws, a relay or EasyTier; quitting the app leaves the daemons and their epics running](/diagrams/user-desktop-1.svg)

**Local** is this machine's daemon. The app connects to it by running `hmz daemon connect --stdio`, which starts the daemon if needed. On macOS, it uses the `hmz` from your login shell. On Windows, it uses the `hmz` installed in the default WSL distribution.

The app connects directly to daemons on other machines without `hmz web` in between. See [Connect to other machines](/user/daemons).

When an SSH machine has no `hmz`, the app installs nothing there until you agree. It asks `hmz is not installed on <name>. Install it?`: **Install** installs `hmz` on that machine and connects; **Not now** leaves the machine untouched and the daemon `failed` until you click **Connect** again. A machine that has another release of `hmz` is not asked about.

On Windows, the app reaches an SSH daemon with the `ssh` inside the default WSL distribution. The **Host** list under **Settings → Daemons → New daemon** comes from WSL's `~/.ssh/config`, and keys, `known_hosts`, and any **Identity file** are WSL paths; the app does not read `%UserProfile%\.ssh`.

The app stores your preferences and daemon list in its own storage, separate from any browser. Its menus, launch window, and update windows are always in English, regardless of the page language.

## Manage the window

The window has no title bar; the page extends to the top edge.

| | macOS | Windows |
| --- | --- | --- |
| Window controls | Three lights at the top left of the page | **Minimize**, **Maximize** (or **Restore Down**), and **Close** at the top right |
| Move the window | Drag an empty part of the top row | Same |
| Zoom or maximize | Double-click an empty part of the top row | Same |
| Close | The red light or <kbd>⌘W</kbd> hides the window; the app stays in the Dock | Hides the window; the app stays in the tray |
| Reopen | Click the Dock icon or open the app again | Click the tray icon or open the app again |

Only one instance and one window run at a time. Opening the app again brings the existing window forward. Closing the window stops nothing: the app, its connections, and all epics keep running. In full screen, the window controls are hidden.

The app remembers its size, position, and maximized state between launches. It first opens at 1280 by 820, and its minimum size is 640 by 480. While loading, the window matches your system's light or dark appearance; once loaded, the page's theme applies. See [Themes and language](/user/themes).

## Use the menus

### macOS menu bar

| Menu | Items |
| --- | --- |
| **Humanize** | **About Humanize**, **Check for Updates…**, **Hide Humanize**, **Hide Others**, **Show All**, **Quit Humanize** |
| **Edit** | **Undo**, **Redo**, **Cut**, **Copy**, **Paste**, **Select All** |
| **View** | **Reload**, **Actual Size**, **Zoom In**, **Zoom Out**, full screen |
| **Window** | **Minimize**, **Zoom**, **Close Window** |
| **Help** | **Documentation** |

The menus do not capture page shortcuts, so keys like <kbd>⌘K</kbd> go straight to the page.

### Windows tray icon

Windows has no menu bar. Left-click the tray icon to show the window, or right-click it for the menu:

| Item | Action |
| --- | --- |
| **Show Humanize Desktop** | Brings the window forward |
| **Check for Updates…** | Checks for a newer release (see [Install and update](/user/install)) |
| **Documentation** | Opens the documentation in your browser |
| **Quit** | Quits the app |

## Reload and zoom the page

On macOS, use the **View** menu:

| Item | Key | Action |
| --- | --- | --- |
| **Reload** | <kbd>⌘R</kbd> | Reloads the page, closing and reconnecting all connections |
| **Zoom In** | <kbd>⌘=</kbd> | Scales the page by 1.1x, up to 300% |
| **Zoom Out** | <kbd>⌘-</kbd> | Scales the page down by 1.1x, down to 50% |
| **Actual Size** | <kbd>⌘0</kbd> | Resets zoom to 100% |

Zoom resets when you quit. On Windows, use the standard WebView2 shortcuts: <kbd>ctrl+r</kbd> or <kbd>F5</kbd> to reload, and <kbd>ctrl+=</kbd>, <kbd>ctrl+-</kbd>, and <kbd>ctrl+0</kbd> to zoom.

## Open links, files, and downloads

A link that leads outside the page opens in your default browser, and only if it is an `http`, `https`, or `mailto` link.

Double-click a `.hmzepic` file, choose **Open With**, or drop it onto the window to import and open it in the current daemon. If you open multiple files at once, the app imports only the last one. Opening a file does not modify it. See [Export and import a run](/user/export).

Files you download from the page, such as exported epics, save to your Downloads folder and are then shown in Finder or File Explorer. Downloads never overwrite existing files: `epic.hmzepic` becomes `epic (1).hmzepic`.

## Receive notifications

Notifications appear as native macOS notifications or Windows toasts. Click a notification to bring the window forward to that chat or epic.

macOS asks once for permission to show notifications. Choose which events notify you in **Settings → Notifications**, where the page displays `Shown by macOS.` or `Shown by Windows.` See [Notifications](/user/notifications).

![Settings, Notifications in Humanize Desktop: the kinds Done, Failed, Stopped, Questions and Waiting, and under System the switch On with the line Shown by macOS](/shots/user-desktop-notifications.svg)

## Quit the app

| | How |
| --- | --- |
| macOS | **Humanize → Quit Humanize**, or <kbd>⌘Q</kbd> |
| Windows | Right-click the tray icon, then click **Quit** |

Quitting closes all connections and stops any processes the app started, killing any that remain after 3 seconds. Epics keep running in their daemons. See [Leave it running and come back](/user/leaving).

::: warning
On Windows, epics run in WSL. After you quit the app, WSL may shut down an idle distribution and stop your epics. To keep the distribution running, set `instanceIdleTimeout` to `-1` under `[general]` in `%UserProfile%\.wslconfig`.
:::

## Start the app

The window opens showing `Starting`. On macOS, the page loads right away.

On Windows, the app checks the default WSL distribution for a matching `hmz` version and installs or updates it if needed. The window shows `Installing Humanize CLI` or `Updating Humanize CLI`, the current step (`Getting uv`, `Getting Python`, `Installing hmz`), and the latest line of installer output before opening the page.

![The launch window on Windows: Starting, then Installing Humanize CLI with a progress bar through Getting uv, Getting Python and Installing hmz](/shots/user-desktop-install.svg)

## Troubleshooting {#troubleshooting}

### Launch errors on Windows

Every error screen includes a **Documentation** button that opens this page.

| Heading | Cause | Fix |
| --- | --- | --- |
| `WSL missing` | WSL or a Linux distribution is not installed, or WSL did not start within 60 seconds. | Run `wsl --install` in PowerShell, then click **Retry**. |
| `Install failed` or `Update failed` | The installation failed. The window shows the last 12 lines of output. | Check your connection and click **Retry**. If a compatible `hmz` is already installed, click **Continue** to use it. |
| `Update waiting` | Epics are running in an older, incompatible `hmz`. | Wait for the epics to finish so the app can update, or click **Update now** to update immediately (this may stop them). |
| `Not found` | The app installs no `hmz` (a development build, or `HUMANIZE_HMZ` is set) and found none to run in WSL. | Install `hmz` in WSL, or point `HUMANIZE_HMZ` at one that exists, then click **Retry**. |

![The launch window saying WSL missing, with the installer's reason and the buttons Retry and Documentation](/shots/user-desktop-wsl-missing.svg)

![The launch window saying Update failed, with what the installer said and the buttons Retry, Continue and Documentation](/shots/user-desktop-update-failed.svg)

![The launch window saying Update waiting, with the buttons Update now and Documentation](/shots/user-desktop-update-waiting.svg)

![The launch window saying Not found, with the buttons Retry and Documentation](/shots/user-desktop-not-found.svg)

### Local cannot be reached on macOS

On macOS, the app does not install `hmz`. If your login shell cannot find `hmz`, the page opens and shows `Local is unavailable, failed: hmz is not installed on this machine.` [Install the CLI](/user/install), then quit the app and open it again.

### Read the log

Open `Humanize Desktop.log` to see connection events, installer output, and update checks. The log contains no secrets and resets when it exceeds 40,000 bytes.

macOS:

```sh
open ~/Library/Logs/ai.humanfia.humanize/"Humanize Desktop.log"
```

Windows (PowerShell):

```powershell
notepad "$env:LOCALAPPDATA\ai.humanfia.humanize\logs\Humanize Desktop.log"
```

### Use a custom `hmz` binary

Set `HUMANIZE_HMZ` to run a specific `hmz` binary for Local. The app then skips looking for or installing any other `hmz`. On Windows, provide a path inside WSL.

macOS:

```sh
HUMANIZE_HMZ=~/src/humanize/.venv/bin/hmz "/Applications/Humanize Desktop.app/Contents/MacOS/humanize"
```

Windows (PowerShell):

```powershell
$env:HUMANIZE_HMZ = '/home/you/src/humanize/.venv/bin/hmz'
& "$env:LOCALAPPDATA\Humanize Desktop\humanize.exe"
```

For more fixes, see [Troubleshooting](/user/troubleshooting).

## Good to know

- On Windows, clicking a notification opens its chat or epic only if it arrived since the app started. On macOS, older notifications work too.
- The app suppresses notifications for the chat or epic currently shown in a focused window.
- If you open a `.hmzepic` file before the page finishes loading, the app imports it once the page is ready.
- On Windows, store your repositories inside the WSL Linux home directory, not under `/mnt/c`.
- For file paths, commands, and environment variables, see the [Desktop app reference](/reference/desktop).
