---
title: Relays and WebRTC
description: Reach a daemon that has no open port, from a terminal or a browser anywhere, through a relay you run.
---

# Relays and WebRTC

A relay connects your devices to a daemon with no open port, such as a laptop behind NAT. Both the daemon and your device dial out to the relay. Browsers can also use the relay to set up a direct WebRTC connection.

![A daemon with no open port registers at a relay; the terminal and Desktop join through the relay inside mutual TLS, and a browser page sends only signals through it and then opens a data channel to the daemon](/diagrams/user-relay-1.svg)

A relay supports two routes:

| Route | Who opens it | What the relay carries |
| --- | --- | --- |
| `relay:<ws-url>` | `hmz` in a terminal, Humanize Desktop, and `hmz web` for its page | Every byte of the session, as mutual TLS it cannot read. |
| `webrtc:<ws-url>` | The page itself, in a browser or in Desktop | Only the signals that set the connection up. The data channel then goes straight between browser and daemon where the network allows. |

Both routes are encrypted end to end and pinned to the daemon's ID. The relay holds no keys.

## Run a relay

On a machine both ends can reach, such as a cloud server, start the relay:

```sh
hmz relay serve
```

![hmz relay serve in a terminal, printing: hmz relay: listening on ws://127.0.0.1:8765](/shots/user-relay-serve.svg)

The relay runs until you press <kbd>ctrl+c</kbd> or send `SIGTERM`, then exits with status `0`. It reads no settings and writes nothing to disk.

| Option | Meaning |
| --- | --- |
| `--listen HOST:PORT` | The address to listen on. Default `127.0.0.1:8765`. Write an IPv6 host in brackets. Port `0` takes any free port and prints it. |

The relay speaks plain WebSockets. To serve it at a `wss://` address, keep it on loopback and put a TLS proxy in front. This Caddy `Caddyfile` serves it at `wss://relay.example.com` on any path:

```text
relay.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

## Register a daemon at the relay

On the daemon's machine, add listeners to `~/.hmz/settings.yaml`. The daemon opens them as soon as you save the file.

```yaml
listen:
  - relay:wss://relay.example.com
  - webrtc:wss://relay.example.com
```

`relay:` accepts connections from terminals and Desktop. `webrtc:` accepts browsers. Both share one registration at the relay. A daemon with a listener stays running when idle. To start it automatically after a reboot, install it as a login service (see [The daemon](/user/daemon)).

To test without editing settings, run the daemon in the foreground. If a daemon is already running, the command refuses with `hmz: a daemon is already running (pid …)`.

```sh
hmz daemon serve --listen relay:wss://relay.example.com --listen webrtc:wss://relay.example.com
```

![hmz daemon serve with a relay and a webrtc listener, printing that it listens on both at wss://relay.example.com](/shots/user-relay-register.svg)

To answer WebRTC connections, install the WebRTC extra on the daemon's machine:

```sh
uv tool install 'hmz[webrtc]'
```

Next, generate a pairing code on the daemon's machine. The code includes the daemon's ID and both routes, works once, and expires after 10 minutes.

```sh
hmz daemon pair
```

## Add the daemon on your device

### In the app

1. Open **Settings**, then **Daemons**.
2. Under **New daemon**, select **WebRTC**, or select **Relay** to connect through `hmz web` or Desktop over a `relay:` route.
3. Enter a **Name** and paste the **Pairing code**.
4. Click **Add**.

![The New daemon form with WebRTC picked: Name devbox, a pairing code, the Address webrtc:wss://relay.example.com, and one STUN server](/shots/user-relay-add.svg)

| Field | Meaning |
| --- | --- |
| **Name** | What this page calls the daemon. |
| **Pairing code** | The `hmz-pair:…` code made on the other machine. |
| **Address** | Optional. The route to try first: `webrtc:wss://…` under **WebRTC**, `relay:wss://…` under **Relay**. Left empty, the routes the code carries are tried. |
| **STUN and TURN** | WebRTC only. Servers to claim the code with; see below. |

The app claims the code right away. The daemon appears in your list as **up**, and your device appears under its **Devices**.

![The Daemons list: Local, and devbox of kind WebRTC at webrtc:wss://relay.example.com, state up, with the device studio and its WebRTC servers](/shots/user-relay-daemons.svg)

See [Connect to other machines](/user/daemons) for other ways to add a daemon, route order, and device management.

### In the terminal

`hmz` connects over the `relay:` route and never opens a `webrtc:` route.

1. Run `/settings daemons`.
2. Select **Add daemon** and set `mode` to `Pairing code`.
3. Fill in `name` and `code`.
4. Press <kbd>enter</kbd> on the new daemon and select `connect`.

![The Daemons page of /settings in the terminal: Local, and devbox reached at relay:wss://relay.example.com, up](/shots/user-relay-terminal.svg)

## Configure STUN and TURN servers

Simple networks need no extra servers. When the browser and daemon cannot connect directly, a STUN server discovers a path, and a TURN server relays traffic if no direct path exists. Humanize provides neither; use your own or a provider's. You configure each side separately.

**In the browser**, configure servers per daemon. Open **Settings**, then **Daemons**, and expand **WebRTC servers** under the daemon's row (it opens by default when the daemon has a `webrtc:` route). Enter one server per line in **STUN and TURN**—the URL, followed by the username and credential for TURN—and click **Save**.

```text
stun:stun.example.com:3478
turn:turn.example.com:3478 alex not-a-real-key
```

Join multiple URLs for one server with commas. A URL starts with `stun:`, `stuns:`, `turn:`, or `turns:`. Saved credentials appear as `••••` and stay unchanged unless you edit them. Saving reconnects the daemon with the new servers.

**On the daemon**, add `ice_servers` to `~/.hmz/settings.yaml`:

```yaml
ice_servers:
  - urls: stun:stun.example.com:3478
  - urls: turn:turn.example.com:3478
    username: alex
    credential: not-a-real-key
```

## Use shared EasyTier nodes

EasyTier is another way to reach a machine with no open port. Both machines join a private network and meet on shared nodes without a relay of your own. See [Connect to other machines](/user/daemons) for setup and editing. The form's **Nodes** field lists ready-made nodes.

![The Nodes field of the EasyTier form: listed shared nodes, each up or down with its uptime over 24 hours, two public nodes, and one node added by hand and ticked](/shots/user-relay-nodes.svg)

The list loads from the EasyTier community status page and shows whether each node is **up** along with its 24-hour uptime. To read the `easytier` status page of another Uptime Kuma server, set `HUMANIZE_EASYTIER_NODES` to that server's URL. Two public nodes, `tcp://public.easytier.top:11010` and `tcp://easytier.public.kkrainbow.top:11010`, are always available even if the status page is unreachable.

To add your own node, type `tcp://host:port` (or `udp`, `ws`, `wss`, `quic`, or `wg`) and press **Add node** or <kbd>enter</kbd>. Tick at least one node that the other machine also uses.

## Troubleshoot connections

| You see | Do this |
| --- | --- |
| `hmz: the relay cannot listen: …` | Another program holds the port. Pick another with `--listen`. |
| `No daemon <id> is here.` | The daemon is not registered at this relay. Check that it runs and that its `listen` names this relay's address. |
| `The daemon did not answer.` | The daemon did not accept the join within 10 seconds. Try again. |
| `This daemon cannot answer WebRTC.` | Install `hmz[webrtc]` on the daemon's machine. |
| `This daemon takes native joins alone here.` | Add the `webrtc:` listener beside the `relay:` one. |
| `This daemon answers WebRTC alone here.` | Add the `relay:` listener beside the `webrtc:` one. |

## Good to know

- The relay sees which daemon IDs register, which addresses join them, timestamps, and byte counts, but never session contents. Anyone who can reach a relay can connect to it, though only paired devices can pass the daemon's check.
- A browser's WebRTC identity is stored in its site data. Clearing site data makes the browser a new device that you must pair again.
- If a daemon loses its connection to the relay, it retries after 1 second, doubling up to 60 seconds, while its other listeners keep working.
- The relay enforces a 65 536-byte limit on text messages, a 1 048 576-byte limit on binary messages, a 30-second ping interval (a ping unanswered for 60 seconds closes the connection), and a 10-second timeout for a daemon to answer a join.

See the [daemon reference](/reference/daemon) for all routes and listeners, [settings.yaml](/reference/settings) for configuration keys, and the [CLI reference](/reference/cli) for commands.
