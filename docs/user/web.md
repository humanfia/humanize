---
title: The browser page
description: "Serve Humanize to a browser with hmz web, and find your way around the page: its sidebar, shortcuts, dialogs, menus and panels."
---

# The browser page

`hmz web` serves Humanize in your browser, showing every chat and epic in every folder on this machine. [Humanize Desktop](/user/desktop) shows the same page in its own window, so everything here applies to the desktop app too.

![The page in a browser: the sidebar on the left lists the chats and epics of the shop folder, and a chat is open beside it](/shots/user-web-page.svg)

## Start the page

Run this command in a terminal:

```sh
hmz web
```

This starts the daemon if none is running, prints the page address, and opens it in your browser. Press <kbd>ctrl+c</kbd>, or close the terminal, to stop serving the page. Stopping `hmz web` does not stop any chats or epics.

![hmz web --port 8420 --no-open prints the address of the page, which ends in a key](/shots/user-web-serve.svg)

| Option | What it does |
| --- | --- |
| `--port PORT` | Listen on this port. `0` picks any free port. Without this option, `hmz web` reuses the last port, or picks a free one the first time or if that port is taken. |
| `--no-open` | Print the address without opening a browser. |
| `--attached` | Also stop when standard input closes. Use this when a program starts `hmz web` and must not leave it running. |

`hmz web` opens a browser only on macOS or on Linux with a desktop. Over SSH, it only prints the address.

The folder where you run `hmz web` is the folder offered first for new chats and epics.

### Sign in with the key

The page listens on the local machine only (`127.0.0.1`), at an address ending in a secret key. Open the full address once to set a browser cookie. After that, the plain address, such as `http://127.0.0.1:8420/`, works in that browser until you quit it.

![The browser opens the address with its key and is handed a cookie; hmz web passes everything you do to the daemon, which holds the chats and epics](/diagrams/user-web-1.svg)

A browser without the cookie shows an access message instead of the page:

![A browser that did not open the address with the key is told: This browser is not let in.](/shots/user-web-not-let-in.svg)

`hmz web` generates a new key each time it starts. After a restart, open the newly printed address.

::: warning
Anyone with the keyed address can use the page while `hmz web` runs. Do not share it where others can read it.
:::

## Navigate the layout

The page has four parts:

- The **sidebar** on the left holds navigation and the list of chats and epics.
- The **view** beside it shows a new chat, a new epic, an open chat or epic, or the flows.
- **Dialogs** open over the view: Search, Settings, Download, and Delete chat.
- A **side panel** opens on the right of some views, alongside [Ai-chan](/user/ai-chan)'s drawer.

Every view and dialog has its own URL hash after the `#`. Bookmark it, reopen it, or step through your history with the browser's back and forward buttons.

| Address | Opens |
| --- | --- |
| `#/new/chat` | A new chat (also the default when no view is in the address) |
| `#/new` | A new epic |
| `#/chats/<id>` | A chat |
| `#/epics/<name>` | An epic |
| `#/flows` | Flows |
| `#/search` | The Search dialog |
| `#/settings/<page>` | A Settings page |
| `#/@<daemon>/…` | Any of the above on another daemon |

See [Page addresses and shortcuts](/reference/web) for the full list.

## Use the sidebar

From top to bottom, the sidebar contains:

- The top row: the Humanize mark (opens a new chat), **Hide sidebar**, **Back**, and **Forward**.
- Action links: **New chat**, **New epic**, **Search**, and **Flows**. **Flows** shows a badge count when installed flows have a newer release.
- Your chats and epics. Click a row to open it, or point at it to see its full task, state, and start time. An epic row displays its state, flow, and age; click its arrow to list its agents and their sessions. An idle chat row shows only its title. It adds `Running` during an open turn, `Failed` when a turn failed, was refused, or crashed, and a dot when waiting for you. Point at a dot to see `Awaiting input` for a waiting chat or `Unread` for a row updated since you last opened it. See [Organise chats](/user/manage-chats) and [History and search](/user/history) for row actions.
- The active daemon at the foot: its name, machine, and state. An online daemon shows `idle` or the count of running epics, such as `2 live`. Otherwise it shows `connecting`, `installing`, `failed`, or `not connected`. Click it to switch daemons or open **Settings** or **Usage**. When a newer `hmz` is out, it shows an arrow badge and its menu adds **Update**, which copies `hmz update`. Click the gear beside it to open [Settings](/user/settings). To add daemons, see [Connect to other machines](/user/daemons).

### Fold and resize the sidebar

Click **Hide sidebar**, or press <kbd>ctrl+.</kbd> (<kbd>cmd+.</kbd> on a Mac), to fold the sidebar away. A **Show sidebar** button then appears on the left of the view's top bar.

Drag the sidebar's right edge to resize it between 200 and 480 pixels. Double-click the edge to reset it to 275 pixels. With the keyboard, focus the edge and press <kbd>left</kbd> or <kbd>right</kbd> to move it by 16 pixels, <kbd>home</kbd> for the narrowest width, or <kbd>end</kbd> for the widest.

### Group and sort the list

Point at any group heading to reveal its **Group and sort** button (always visible on touch screens).

![The Group and sort menu is opened on the shop heading, Group by is set to Date, and the list regroups under Today with the folders listed last](/shots/user-web-group-sort.svg)

| Menu | Choices | Default |
| --- | --- | --- |
| **Group by** | **Folder**, **Date**, **None** | **Folder** |
| **Sort by** | **Last updated**, **Created** | **Last updated** |
| **Show** | **Chats**, **Epics** | Both |

**Date** groups items into `Today`, `Yesterday`, `Last 7 days`, `Last 30 days`, and `Older`. **None** puts everything into one `All` group. Pinned rows always appear first under `Pinned`. When you do not group by folder, folders appear at the bottom under `Folders`; click one to start a new chat in it, or click its **More options** button for the folder menu. Each group shows up to 20 rows before a **Show {n} more** button. Click **Reset to defaults** to restore all three settings.

The sidebar loads 60 chats and 60 epics at a time. When the daemon holds more, click **Show more** at the bottom of the list to load the next 60. Running epics sort as the most recently updated, and folders with a running epic appear first.

### Manage folder groups

When grouped by folder, each folder is a heading, and chats without a folder appear under `No folder`. Click a folder name to collapse or expand its rows. Click **+** on the heading beside **Group and sort** to start a new chat in that folder, or right-click the heading to open the folder menu.

![The menu of the shop folder: its path, then New chat here, New epic here, Search here, Copy path, Collapse, Settings and Usage](/shots/user-web-folder-menu.svg)

| Item | What it does |
| --- | --- |
| **New chat here**, **New epic here** | Start a chat or epic in this folder |
| **Search here** | Open Search filtered to this folder |
| **Copy path** | Copy the folder path |
| **Collapse** / **Expand** | Fold or unfold the group's rows |
| **Settings**, **Usage** | Open this folder's settings or usage in Settings |
| **Forget** | Remove the folder from the list (only available when it has no chats or epics) |

If a folder's directory is deleted on disk, it is tagged `missing`. Its existing rows remain, but you cannot start new runs in it.

Right-click empty space in the list, between its groups, and choose **Import** to load an exported epic. See [Export and import a run](/user/export).

## Keyboard shortcuts

On a Mac, press <kbd>cmd</kbd> instead of <kbd>ctrl</kbd>. The sidebar shows the first two shortcuts beside **Search** and **New chat**.

| Keys | What it does |
| --- | --- |
| <kbd>ctrl+k</kbd> | Open Search |
| <kbd>ctrl+shift+o</kbd> | Open a new chat |
| <kbd>ctrl+.</kbd> | Hide or show the sidebar |
| <kbd>esc</kbd> | Close the open menu, or else the open dialog. On a narrow window, closes the sidebar drawer next, then the side panel. |

## Use dialogs

![Search opens over a chat when cmd+k is pressed, and esc closes it and shows the chat again](/shots/user-web-search.svg)

Close a dialog by pressing <kbd>esc</kbd>, clicking its **Close** button, or clicking the dimmed backdrop. Closing returns you to the underlying view and leaves your browser history as if the dialog never opened. While a dialog is open, <kbd>tab</kbd> stays inside it. Opening a dialog address directly, such as `#/search`, opens it over a new chat.

## Use menus

Click chips and buttons to open menus, or right-click a row, heading, transcript line, or chat title for its context menu. Text fields and selected text keep the native browser menu. Only one menu stays open at a time.

Inside a menu, press <kbd>up</kbd>, <kbd>down</kbd>, <kbd>home</kbd>, and <kbd>end</kbd> to move through items. Press <kbd>right</kbd> to open a submenu and <kbd>left</kbd> to close it. Click elsewhere, press <kbd>esc</kbd>, scroll, or switch views to close the menu.

Point at truncated text to see the full text in a tooltip. Brief corner messages, such as `Link copied`, confirm your actions.

### Confirm an action

Click a permanent action button, such as **Remove**, **Delete**, **Uninstall**, **Revoke**, or **Forget**, to reveal a question beside it with **Cancel** and the confirming answer. No dialog opens.

![The Forget button in a folder's settings asks its question beside itself, with Cancel and Forget as answers](/shots/user-web-confirm.svg)

Only one question stays open at a time. Press <kbd>esc</kbd>, click elsewhere, move focus away, open a menu or dialog, or leave the view to cancel.

## Use the side panel

Chats and epics have a right-hand side panel for details, files, changes, a terminal, and side questions. See [Files, changes and terminal](/user/environment-panels) and [Ask a side question](/user/side-questions).

Click a pane's button in the top bar to open or close it. The browser remembers whether you left the panel open or shut. Opening a second panel closes the first only if the central view would shrink below 480 pixels.

## Use on narrow windows and touch screens

In windows 860 pixels wide or narrower, such as on a phone, the layout adapts:

![On a phone-sized window, Show sidebar opens the sidebar as a drawer over the page, which is dimmed behind it](/shots/user-web-narrow.svg)

Click **Show sidebar** in the top bar to open the sidebar as an overlay drawer. Select an item, tap the dimmed backdrop, or press <kbd>esc</kbd> to close it. Side panels cover the view, only one overlay stays open at a time, and dialogs fill the window.

Touch devices hide tooltips and always show the age on chat rows.

## What the browser remembers

Each browser (and Humanize Desktop) stores its own interface state locally, separate from the daemon:

- Sidebar fold state and width.
- **Group and sort** choices, collapsed groups, and which epics are opened out in the list.
- Whether an epic shows its sessions as a graph or a list.
- Pinned rows and unread marks.
- Open panels.
- Theme and language (see [Themes and language](/user/themes)).
- Notification settings (see [Notifications](/user/notifications)).
- Other daemons you added (see [Connect to other machines](/user/daemons)).

`hmz web` reuses the same port each time so your browser keeps this state. Clearing site data in the browser resets these preferences without affecting your chats, epics, or daemon settings. A browser that cannot store anything works the same and forgets them.

## Behind a reverse proxy

`hmz web` can sit behind an HTTP or HTTPS reverse proxy such as nginx or Caddy. The proxy must run on the same machine, or reach `hmz web` through a port forwarded to that machine's loopback, because `hmz web` answers loopback connections only. It must also pass WebSocket upgrades for `/rpc` and `/dial`.

- **The proxy keeps `Host`.** Nothing else is needed. The page's requests are accepted when the browser's `Origin` is `http` or `https` and names the same host and port as `Host`; a missing port counts as 443 for `https` and 80 for `http`. In nginx this is `proxy_set_header Host $http_host;`. Caddy keeps `Host` by default.
- **The proxy rewrites `Host`.** Tell `hmz web` the public origin: `hmz web --origin https://hmz.example.com`. Requests whose `Origin` is exactly that origin are accepted too. Without `--origin` the page loads but its connection to the daemon is refused with 403.

Open the printed address with the proxy's origin in place of `http://127.0.0.1:<port>`, keeping `/?key=<key>`, for example `https://hmz.example.com/?key=<key>`. The key lets that browser in under that name.

A request from any other site is still refused, and `hmz web` never reads `X-Forwarded-Host`, `X-Forwarded-Proto` or `Forwarded`. Anyone who can reach the proxy and has the key acts as you on this machine, so put the proxy's own sign-in in front of it when it is reachable from a network.

## Good to know

- `hmz web` accepts connections from the local machine only. To reach it from another computer, forward the port over SSH (for example, `ssh -L 8420:127.0.0.1:8420 you@server`) and open the printed address locally. To serve it under a name of your own over HTTPS, see [Behind a reverse proxy](#behind-a-reverse-proxy). For phones or machines without SSH, see [Use Humanize from a browser and your phone](/tutorials/browser-and-phone).
- If the port passed to `--port` is taken, `hmz web` exits with `hmz: the web interface cannot be served:` and the reason. It also exits with a message if a daemon from an older, incompatible Humanize is running on this machine.
- Scripts can read the address from standard output: `hmz web --no-open` prints a single line, `hmz web: <address>`. See [CLI](/reference/cli).
- The browser tab title is `Humanize · ` followed by the machine's name.
