---
title: Notifications
description: Get told when an epic ends, a flow asks you something or a chat answers, and choose which of these you hear about.
---

# Notifications

Humanize notifies you when an epic or chat you are not viewing ends, asks a question or waits for you. You choose which events you hear about on each interface.

![A chat is answered while another view is open: its row gets a dot, and the dot goes when the chat is opened](/shots/user-notifications-unread.svg)

## What raises a notice

The daemon creates notices for every epic and chat it holds, regardless of which interface started it (`hmz exec` included). There are five kinds.

| Kind | When |
| --- | --- |
| **Done** | An epic finished. |
| **Failed** | An epic failed, crashed, ran out of budget or was refused. |
| **Stopped** | An epic was stopped. |
| **Questions** | A flow asks you something. See [Answer a flow's questions](/user/questions). |
| **Waiting** | A flow waits for what you say next. |

A finished chat turn counts as **Waiting** in the app and as **Done** in the terminal.

You get no notice for the epic or chat you are looking at. One that is open but out of sight still notifies: in the app when the window is not focused, in `hmz` when a menu covers it. Events from before the daemon started (in the terminal, before `hmz` opened) raise nothing.

## In the app

Humanize Desktop and the browser page work the same way. They listen to every reachable daemon, not only the one shown.

A notice does two things:

- Marks the chat or epic unread with a dot on its sidebar row, and on its folder when folded. Open the row to clear the dot, or use **Mark as unread** and **Mark as read** in the row menu. See [Organise chats](/user/manage-chats).
- Shows a system notification titled with the kind and daemon (such as `Done · Local`) and showing the flow (for a chat, its first message) and the first line of text. Click it to focus that chat or epic, or the running epic where a question waits.

The page has no notification bell, count or list of its own.

### Choose what you hear about

1. Click **Settings** (the gear) in the sidebar.
2. Under **App**, click **Notifications**.
3. Under **Kinds**, untick the events you want to mute. Muted kinds neither mark rows unread nor show notifications.
4. Under **System**, untick **On** to keep unread dots without system notifications.

Changes save at once. All options start on.

![The Notifications page of Settings in Humanize Desktop: the five kinds ticked, System on, shown by macOS](/shots/user-notifications-settings.svg)

### Allow notifications

Humanize Desktop shows `Shown by macOS.` or `Shown by Windows.` and needs no setup. On macOS, click **Allow** the first time the app sends a notification.

In a browser, look next to **System** for `Not asked`, `Allowed` or `Blocked`. Click **Allow** and accept the browser prompt. If it shows `Blocked`, enable notifications for the site in your browser settings. Browsers without notification support show `Unsupported`.

![In a browser, Allow is clicked on the Notifications page and the state changes from Not asked to Allowed](/shots/user-notifications-allow.svg)

## In the terminal

`hmz` notifies you about epics and chats on the local machine. A notice briefly shows a corner card titled `Done`, `Failed`, `Stopped`, `Question` or `Waiting` with the flow, folder and text. In `/epics`, the epic's row shows `●` until you open it.

![In a menu of the terminal interface, an epic ends: a Done card appears in the corner, then /epics shows a dot on the epic's row](/shots/user-notifications-terminal-card.svg)

When **System** is on, `hmz` also rings the terminal bell and sends a desktop notification. iTerm2, Ghostty, WezTerm, kitty and Windows Terminal display it; other terminals ignore it.

To configure notifications, run `/settings notifications`. Press <kbd>enter</kbd> on a row, select `on` or `off`, and choose **Save**.

![The Notifications page of /settings in the terminal: Done, Failed, Stopped, Questions, Waiting and System, each on](/shots/user-notifications-terminal-settings.svg)

| Row | Off means |
| --- | --- |
| **Done**, **Failed**, **Stopped**, **Questions**, **Waiting** | No card, bell or dot for that kind. |
| **System** | A card in `hmz` alone: no bell, no system notification. |

`hmz` saves these settings under `notifications` in `settings.yaml`. See [settings.yaml](/reference/settings).

## Good to know

- The app and terminal store settings separately, although the terminal page's heading mentions the web interface. App settings live in the browser or Humanize Desktop rather than the daemon, so each device has its own, and clearing site data resets them.
- The app skips system notifications for notices received more than ten minutes late (for example, while the page was closed), but still marks the row unread.
- Terminal cards and dots last only while `hmz` stays open. Chats have no row in `/epics`, so they show a card but no dot.
- `hmz exec` and `hmz chat` do not show notifications of their own.
- If system notifications do not appear, check **System Settings → Notifications → Humanize Desktop** on macOS, or **Settings → System → Notifications** on Windows.
- Programs can read the same notices. See [Events and records](/reference/events).
