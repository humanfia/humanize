# Running a relay

In this guide you run `hmz relay serve` on a machine that both a daemon and your devices can
reach, and put TLS in front of it.

Reach for a relay when the daemon you want to use cannot be dialled: it sits behind a NAT, on
a laptop that moves between networks, or on a network that lets nothing in. Both ends dial out
to the relay instead, and the relay joins them.

::: info Before you start
- A machine with an address both ends can reach, such as a small cloud VM, with Humanize
  [installed](/user/installation).
- For `wss://`, a TLS proxy on it, such as [Caddy](https://caddyserver.com/), and a domain name
  that points at it.
:::

## Try it

```console
$ hmz relay serve
hmz relay: listening on ws://127.0.0.1:8765
```

The relay runs until you press <kbd>Ctrl</kbd>+<kbd>C</kbd> or send it `SIGTERM`, and then
exits with status `0`. To listen somewhere else, give `--listen`:

```console
$ hmz relay serve --listen 0.0.0.0:9000
hmz relay: listening on ws://0.0.0.0:9000
```

`--listen 127.0.0.1:0` takes any free port and prints the one it got.

## How it works

A daemon keeps one WebSocket open to the relay, under its daemon id. Before the relay gives it
that id's room, the daemon signs a fresh random nonce with its device key, and the relay checks
that the key is the one the id was made of. Nobody else can take a daemon's room.

A device then asks the relay for that daemon id:

- **A native client** (the terminal interface, the CLI, the desktop app) is joined by a byte
  splice. The daemon opens a second WebSocket for that one client, and the relay carries every
  binary message of each to the other, unchanged. What crosses is mutual TLS between the two
  ends, which the relay has no key to.
- **A browser** is joined by signals. The relay passes the WebRTC offer, answer and candidates
  between the browser and the daemon; the data channel they open goes directly between them
  where the network allows, and the daemon signs its side of it with its device key. A daemon
  that will not answer says why, and the relay tells the browser and closes its connection.
  Where the network allows no direct path, the two need STUN or TURN servers: the browser's are
  [set daemon by daemon](/user/web#webrtc-servers) in **Settings → Daemons**, and the daemon's
  are its machine's `ice_servers` setting.

The relay keeps nothing on disk and reads nothing of the machine it runs on: no settings, no
home, no identity. A room goes when its daemon disconnects.

## Put TLS in front of it

The relay itself speaks plain WebSockets. For a `wss://` URL, leave it on loopback and put a
TLS proxy in front. With Caddy, a `Caddyfile` of:

```text
relay.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

serves the relay at `wss://relay.example.com`, on any path. TLS here protects who connects to
whom from the network between you and the relay; it does not make the relay trusted. Sessions
are secured end to end either way.

## What the relay sees

The relay learns which daemon ids register, which addresses join them, when, and how many bytes
cross. It never sees what a session says, and it keeps none of what it learns.

## Limits

| Limit | Value |
| --- | --- |
| Longest text message | 65 536 bytes; a longer one closes the connection |
| Longest binary message | 1 048 576 bytes; a longer one closes the connection |
| Keepalive | a ping every 30 seconds; a connection that has not answered one within 60 seconds is closed |
| A native join the daemon does not answer | refused after 10 seconds: `The daemon did not answer.` |
| A connection that sends nothing, or a daemon that does not answer its challenge | closed after 10 seconds: `Nothing was said in time.` |

## Troubleshooting

| You see | Do this |
| --- | --- |
| `hmz: the relay cannot listen: … address already in use` | Another program holds that port. Pick another with `--listen`. |
| A client is told `No daemon <id> is here.` | The daemon is not connected to this relay. Check that it runs, and that it names this relay's URL. |
| A daemon is told `That daemon id is not proven.` | Its signature did not match its id. Its device key and certificate do not belong together. |

The full command line is in the [CLI reference](/reference/cli#hmz-relay).
