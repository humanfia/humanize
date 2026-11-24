---
title: Use Humanize from a browser and your phone
description: Serve the Humanize page with hmz web, open it in a browser and on your phone, turn on notifications, and add a second machine with a pairing code.
---

# Use Humanize from a browser and your phone

Serve the Humanize page from your computer, open it in a browser and on your phone, turn on notifications, and connect a second machine.

![A chat open in the page on a phone-sized screen](/shots/tutorials-browser-and-phone-phone.svg)

## What you need

- A computer with `hmz` installed and one coding agent signed in. See [Install and update](/user/install) and [Finish your first task in the terminal](/tutorials/first-task-terminal).
- A project directory. This page uses `~/shop`.
- A phone and a private network to reach your computer. This page uses Tailscale on both.
- For step 6 only: a second machine with `hmz` installed, called `devbox`.

## 1. Serve the page

Start the web server in your project on a port you choose:

```sh
cd ~/shop
hmz web --port 8420 --no-open
```

The command prints an address and stays running. Without `--no-open`, `hmz web` opens the address in your default browser. Press <kbd>ctrl+c</kbd> to stop the server; active chats and epics keep running.

![hmz web prints the address of the page, with its key](/shots/tutorials-browser-and-phone-serve.svg)

The string after `key=` is a secret token that grants access. Every run of `hmz web` generates a new key.

## 2. Open it in a browser

Open the printed address in a browser on your computer. You see the same interface as Humanize Desktop. Type a message and press <kbd>enter</kbd> to start a chat.

![A chat is typed and answered in the browser](/shots/tutorials-browser-and-phone-chat.svg)

The browser stores the key in a cookie and strips it from the address bar.

## 3. Open the page on your phone

`hmz web` only accepts connections from its own computer. Forward a port on your computer to it, so your phone's traffic arrives as a local connection.

![The phone reaches hmz web through a port forwarded on the computer; the computer's browser reaches it directly](/diagrams/tutorials-browser-and-phone-1.svg)

In a second terminal on your computer, forward the port with Tailscale:

```sh
tailscale serve --bg --tcp 8420 tcp://localhost:8420
```

On your phone, open the address from step 1 with `127.0.0.1` replaced by your computer's Tailscale name or address. For example, if `hmz web` printed `http://127.0.0.1:8420/?key=abc` and your computer is `studio`, open `http://studio:8420/?key=abc`.

Any port forward works if it runs on the same computer as `hmz web` and keeps the address `http://`. Behind an HTTPS proxy, such as `tailscale serve --bg 8420`, Chrome cannot connect to the daemon.

::: warning
Anyone who can reach the forwarded port and has the key can run agents on your computer. Keep the port on a private network, and do not share the address.
:::

## 4. Navigate on a small screen

Tap **Show sidebar** at the top left to open the navigation drawer, which appears on screens 860 pixels wide or narrower. Tap a chat to open it, or tap the dimmed area to close the drawer.

![On a phone: Show sidebar opens the drawer, and a chat is picked from it](/shots/tutorials-browser-and-phone-drawer.svg)

Tap **More options** at the end of a chat's row for its actions. Over a plain `http://` address the copy actions answer `Copy failed`, because the phone's browser withholds its clipboard.

![The menu of a chat in the drawer: Open, Pin, Rename, Fork, Archive, Delete and more](/shots/tutorials-browser-and-phone-menu.svg)

Both browsers talk to the same daemon, so messages sync live. On your phone, search and settings fill the screen, and a panel opens as a sheet from the bottom.

## 5. Turn on notifications

Start a chat and switch to another view. When the agent replies, a dot appears next to the chat in the sidebar. Open the chat to clear the dot.

![The drawer with a dot beside a chat that was answered](/shots/tutorials-browser-and-phone-unread.svg)

To get system notifications in the browser on your computer, click the gear (**Settings**) at the bottom of the sidebar, then **Notifications**. Click **Allow** and accept the browser prompt.

![Settings, Notifications: the kinds, the System switch and Allow](/shots/tutorials-browser-and-phone-notifications.svg)

Under **Kinds**, pick what triggers an alert: an epic that is **Done**, **Failed** or **Stopped**, **Questions** from a flow, and **Waiting** when a chat turn ends. Each browser saves its own settings.

Keep the tab open to receive notifications. Phone browsers rarely show them: if you see **Unsupported** instead of **Allow**, the browser cannot. Unread dots in the sidebar work everywhere.

## 6. Add a second machine

Connect your page to a daemon on a second machine, `devbox`.

### On devbox

Add a TCP listener to `~/.config/humanize/settings.toml` on `devbox`:

```toml
listen = ["tcp://0.0.0.0:41817"]
```

Generate a one-time pairing code:

```sh
hmz daemon pair
```

![hmz daemon pair prints a pairing code and when it expires](/shots/tutorials-browser-and-phone-pair.svg)

Copy the line starting with `hmz-pair:`. The code works once and expires after 10 minutes.

### In the page

Open **Settings**, then **Daemons**. Under **New daemon**, tap **TCP**. Enter `devbox` in **Name**, paste the code into **Pairing code**, and tap **Add**. The code uses the hostname of `devbox`; if your computer cannot resolve that name, also enter the IP and port in **Address**, such as `tcp://192.0.2.10:41817`.

![The New daemon form: TCP chosen, a name and a pairing code](/shots/tutorials-browser-and-phone-add.svg)

`devbox` appears in the daemon list. If its state is not `up`, tap **Connect**.

![The line of devbox in the list of daemons: TCP, its address, up](/shots/tutorials-browser-and-phone-daemons.svg)

To switch machines, open the sidebar and tap the daemon bar at the bottom. Tap **Daemon**, then `devbox`. Tap **Local** in the same menu to switch back.

![The daemon bar's menu switches the page from Local to devbox](/shots/tutorials-browser-and-phone-switch.svg)

The computer running `hmz web` connects to `devbox`, not your phone, so `devbox` must be reachable from that computer on port 41817. Each browser stores its own list of daemons.

## What you did

- Served the web interface with `hmz web` and signed in with its key.
- Reached the page from your phone through a forwarded port.
- Navigated with the sidebar drawer on a small screen.
- Allowed system notifications and saw the dot that marks an unread chat.
- Paired a second machine with `hmz daemon pair` and switched between daemons.

## Next

- [The browser page](/user/web): everything the page does.
- [Connect to other machines](/user/daemons): SSH, EasyTier and routes.
- [Relays and WebRTC](/user/relay): reach a daemon that has no open port.
- [Notifications](/user/notifications): every kind and where it shows.
