---
title: Security
description: Know what an agent may touch, where your credentials are kept, which devices reach your daemon, and what Humanize reports about itself.
---

# Security

Agents in Humanize act without asking for approval. Permissions limit what an agent can touch, the sandbox enforces those limits, and pairing controls which devices reach your daemon.

![A permission sets a fence around the coding agent; by default it writes the work folder, reads the rest of the machine and reaches the network](/diagrams/user-security-1.svg)

## What an agent may do

One of three permission presets limits each agent, in chats and in flows.

| In the app | Name in a flow | The agent may |
| --- | --- | --- |
| **Read only** | `read-only` | read files and run commands, and change no file |
| **Edit this folder** | `workspace-write` | change files in its work folder only, and read the rest. The default |
| **Full access** | `danger-full-access` | change files anywhere on the machine |

Chats always have network access. A flow sets the permission for each of its roles, and can turn the network off or add rules for single paths. You do not pick permissions when starting an epic, so check the flow first. See [Permissions](/user/permissions).

### In the app

Click the permission chip under the message box and pick a preset. The new preset applies on the next turn.

![The permission chip under the message box opens a menu of three presets, and Read only is picked](/shots/user-security-permission.svg)

A chat started in the terminal or with `hmz chat` uses **Edit this folder**.

## The sandbox

The operating system enforces the permission outside the agent across its entire process and every command it runs, using Seatbelt on macOS and Landlock or bubblewrap on Linux. If the machine cannot enforce a permission, Humanize refuses to start the session rather than run the agent with wider access.

When a flow turns the network off, the agent can reach only the hosts for its model and sign-in.

Work on a server or in a container is fenced the same way on the machine where the commands run. See [The sandbox](/user/sandbox) for details and settings.

## Credentials

- **Accounts.** An account is a named set of credentials for one coding agent, stored under `~/.local/share/humanize/providers/`. Humanize never displays saved values; the app and terminal list only the variable names an account sets. A turn running under an account ignores any other credentials for that agent in your environment. See [Accounts](/user/accounts).
- **Your agent's own settings.** An agent that rewrites its settings while it runs, or that Humanize adds settings to, starts in a settings directory of its own. The settings files there are copies, and Humanize drops the agent's changes to them when the process stops. The agent still uses your own sign-in and sessions.
- **Remote machines.** When an agent runs on another machine under an account, Humanize places the account's credentials there for the turn and removes them afterward.
- **Archives and backups.** Humanize scrubs every exported `.hmzepic` archive and every backup. It replaces every secret it finds with `[redacted]`, including account values, vendor keys, web and bearer tokens, URL credentials, and any field named as a token, key, secret, or password. It keeps your prompts and the agents' output. See [Export and import a run](/user/export) and [Back up to git](/user/backups).

## Other devices

![Another device pairs with the daemon: you carry a pairing code over, the device checks the daemon's key over TLS, and once paired it may call the daemon's methods](/diagrams/user-security-2.svg)

The app, terminal, and command line on your local machine reach the daemon directly and are trusted, as are connections over SSH and WSL. `hmz web` listens only on the local machine and admits only a browser that opens the printed address.

Every other device must pair first. A pairing code admits one device a single time and expires after 10 minutes, unless you pass `--seconds` with a value from 60 to 86400. TLS encrypts the connection, and each side proves itself with its own key: the device accepts only the daemon matching the key in the code, and the daemon knows each paired device by its key. There are no certificates to manage.

An unpaired device can only say hello, claim a pairing code, and list the daemon's methods. The daemon refuses any other request with `This device is not paired: claim a pairing code first.`

A paired device has the same access you do, except it cannot open a terminal in an environment. Set `envs.paired_terminals` to `true` in `settings.toml` to allow terminal access.

Revoking a device closes its sessions immediately, and it cannot reconnect without a new code. See [Connect to other machines](/user/daemons) to add a machine.

### In the app

1. Open **Settings**, then **Daemons**.
2. Find **Devices** under a running daemon to see paired devices.
3. Click **Revoke** and confirm.

![The Daemons page of Settings lists the device laptop under Local, with a Revoke button](/shots/user-security-devices.svg)

### In the terminal

1. Type `/settings`, open **Daemons**, and press <kbd>enter</kbd> on a daemon.
2. Choose `pair a device…` to generate a code, or `devices…` to list paired devices.
3. Press <kbd>enter</kbd> on a device and choose `revoke`.

### From the command line

```sh
hmz daemon pair
hmz daemon devices
hmz daemon devices revoke laptop
```

![hmz daemon devices lists one device with its fingerprint, then hmz daemon devices revoke laptop revokes it](/shots/user-security-revoke.svg)

## Error reports

Humanize sends failure reports to its developers only if you opt in.

A report includes the error and its location in Humanize, the flow and what each agent was set to run, installed coding agents, account names, active skill and flowverse names, that a run went five minutes without progress, and versions. It never includes your input, agent output, files, paths outside Humanize, keys, tokens, or credentials. See [Report a problem](/user/reporting).

### In the app

Open **Settings**, then **General**, and set **Error reports** to **On** or **Off**, and click **Save**.

![The General page of Settings, with Error reports not set](/shots/user-security-reports.svg)

### In the terminal

`hmz` prompts you once on first start. To change your choice later, type `/settings general`, switch **Error reports**, and save when you leave. Select **What is sent** to view both lists.

![The General settings page in the terminal, with What is sent opened and both lists shown below](/shots/user-security-terminal.svg)

### From the command line

`hmz exec`, the daemon, and `hmz web` never prompt you. Set `HUMANIZE_SENTRY=on` or `HUMANIZE_SENTRY=off` to configure reporting for a single process.

## Settings

Configure these keys in `settings.toml`. See [settings.toml](/reference/settings).

| Key | What it does |
| --- | --- |
| `sandbox.backend` | On Linux, which sandbox to use: `auto`, `landlock` or `bwrap` |
| `sandbox.native` | Lets Codex's own sandbox hold its permission instead |
| `envs.paired_terminals` | Lets paired devices open terminals. Off by default |
| `listen` | Where the daemon listens for other devices. Nothing by default |
| `enable_sentry` | Your answer about error reports |

## Good to know

- A flow is Python code that runs as your user outside the sandbox. Install only flows you trust.
- **Full access** imposes no file limits. Use it only when you accept the risk of losing files on the machine.
- The sandbox does not block access to Unix sockets such as Docker's, or to Mach services on macOS.
- When an agent runs on a different machine than its workspace, Humanize refuses the session if project settings such as hooks would execute programs on the agent's machine.
- [Ai-chan](/user/ai-chan) stays within the scope you assign her and cannot reach the daemon outside it.
- A daemon holds at most 16 unclaimed pairing codes in memory. Generating a 17th code drops the oldest one.
- A paired device runs all actions as the daemon's operating system user.
