---
title: Accounts
description: Give a coding agent a named set of credentials, keep several per CLI, and add, edit, copy or remove them in the app and the terminal.
---

# Accounts

An account is a named set of credentials for one coding agent CLI. Humanize isolates each account from the CLI's own sign-in and from other accounts, so two agents of the same CLI can run at the same time under different accounts.

![Three agents of one CLI: two run as the named accounts work and personal, kept under ~/.hmz/providers, and one runs as Local, the CLI's own sign-in](/diagrams/user-accounts-1.svg)

An agent without an account name runs as **Local**, using the CLI's existing sign-in on your machine. Humanize stores no credentials for Local, so you cannot edit or remove it.

## Use an account

Add `@` and the account name to the agent spec: `claude@work/MODEL`. Without `@`, the agent runs as Local. You can also pick the account in the app and terminal pickers; see [Coding agents](/user/agents) and [Nous](/user/nous).

Humanize refuses unknown account names before anything runs:

![hmz chat with -a claude@staging is refused: the chat names no claude account called staging](/shots/user-accounts-cli.svg)

Account changes take effect on the agent's next session. Running sessions keep the account they started with.

## In the app

Open **Settings**, then **Accounts**. The table lists each account by CLI, showing its name, sign-in method, the variable names it sets under **Sets**, and the model count and last check time under **Models**. Secret values are never shown. **Local** is listed under each CLI that has at least one named account. With no account at all, the page says **No account yet.** and **Add account** jumps to the form.

![Settings, Accounts in Humanize Desktop: Claude Code has the accounts personal and work, and Local, the sign-in made outside Humanize](/shots/user-accounts-list.svg)

Accounts belong to the daemon selected at the top of Settings. **Batch apply** is disabled on this page and displays **Secrets stay put** because accounts cannot be copied across daemons. To use an account on another daemon, select that daemon and create the account there.

### Add an account

1. Under **New account**, select the **CLI** and a **Sign-in method**.
2. Type a **Name**, such as `work`.
3. Fill in the fields for that method. Empty fields with defaults show the default value they will use.
4. Click **Create**. The page displays `Made claude@work.` and adds the account to the table.

![The New account form: the sign-in method key is picked, the account is named work, the key is pasted, and Create adds it to the table](/shots/user-accounts-new.svg)

Methods marked `(at a terminal)` run the CLI's own sign-in. You cannot create them in the app, and **Create** is disabled. Create them in the terminal instead.

### Edit, refresh, copy, remove

Click **Edit** on a row to update its fields. Leave a field empty (**Unchanged**) to keep its current value, then click **Save**. To update an account created with the CLI's own sign-in, sign in again in the terminal.

![The edit form of the account work: one field, ANTHROPIC_API_KEY, showing Unchanged, with Save and Cancel](/shots/user-accounts-edit.svg)

Click **More options** on a row, or right-click it, for more actions:

| Item | What it does |
| --- | --- |
| **Refresh models** | Asks the CLI which models it can run with this account. |
| **Copy to** a CLI | Creates an account with the same name and credentials for another compatible CLI, replacing any existing account of that name. |
| **Remove** | Prompts for confirmation, then deletes the account and its credentials. |

![The More options menu of the account work: Refresh models, Copy to for each other CLI the key can run, and Remove](/shots/user-accounts-menu.svg)

**Copy to** appears only for CLIs that accept the same credentials; for example, an Anthropic API key also works with Pi or OpenCode. Subscription sign-ins live in a single CLI's store and cannot be copied. The **Local** row offers only **Refresh models**.

## In the terminal

Type `/settings accounts`. Accounts appear under a heading for each CLI, with `as local` listed last in each group. Press <kbd>/</kbd> to search the list.

![The Accounts page of the terminal interface: under claude, the accounts personal and work with their method and variable, then as local](/shots/user-accounts-terminal.svg)

### Add an account

1. Press <kbd>tab</kbd> and choose **Add an account**.
2. Set `cli` and `way` (the sign-in method), and type a `name`.
3. Fill in the rows the method adds. Secrets appear as dots.
4. Toggle each `also for` row to copy the account to other compatible CLIs. Installed CLIs start on, and a row warns `overwrites <cli>/<name>` when the copy would replace an account.
5. Choose **Done**. The line above **Done** previews the changes.

![The Add an account form in the terminal: the list of ways is opened, key is picked, the name and the key are answered, and the line over Done says it adds claude/work](/shots/user-accounts-terminal-add.svg)

The account is created immediately. If the method uses the CLI's own sign-in, that flow takes over the terminal until it finishes. Humanize then queries the CLI for the models available to the new account.

### Edit, sign in again, remove

Press <kbd>enter</kbd> on an account to open its menu.

| Item | What it does |
| --- | --- |
| `edit settings` | Prompts for the setup fields again. Leave a secret blank to keep its current value. The `also for` rows update the copies for other CLIs. |
| `sign in again` | For an account made by the CLI's own sign-in: runs that sign-in immediately, taking over the terminal until it finishes. Other accounts have no command to run; edit their settings instead. |
| **Remove** | Marks the account and its credentials for deletion. Choose **Cancel removal** to undo. |

![An account's menu in the terminal: edit settings and sign in again, then Remove, which marks the row as will be removed](/shots/user-accounts-terminal-menu.svg)

Edits and removals take effect when you choose **Save**. Until then, the row displays `edited` or `will be removed`.

Choose **Add a custom CLI** on the same page to register your own ACP-compatible CLI; see [Gateways, LiteLLM and custom CLIs](/user/gateways).

### Pick an account for an agent

1. Open the agent sheet from `/settings workspace` and **Chat agent**, or from a role in `/flow`.
2. Set `cli` first, then press <kbd>enter</kbd> on the `account` row.

The **Select the account to run as** list opens. It starts with `as local`, followed by each account for that CLI, its sign-in method, and the variables it sets. If the CLI has no accounts, the list shows `<cli> has no saved accounts yet`.

![The list Select the account to run as in the terminal: as local is ticked, then personal and work, with the buttons Add an account and Search](/shots/user-accounts-terminal-pick.svg)

To create an account from here, press <kbd>tab</kbd> and choose **Add an account**. The form is for that CLI, so it has no `cli` row, and it selects the new account for the agent as soon as you choose **Done**.

## Sign-in methods

Each CLI offers its own list of sign-in methods. The main kinds:

| Kind | Examples | What the account holds |
| --- | --- | --- |
| The CLI's own sign-in | `login`, `console`, `device` | The files the CLI writes when you sign in. Terminal only. |
| API key or token | `key`, `token`, `openai-key` | One secret, usually kept as an environment variable. Codex and MiniMax Code hand it to their own sign-in, so theirs are terminal only. |
| Gateway | `anthropic-gateway`, `openai-gateway`, `gemini-gateway` | The address and key of an endpoint that speaks a vendor's API. |
| Cloud | `bedrock`, `vertex`, `azure`, `foundry` | The profile, project, region or key of your cloud account. |
| Variables of your own | `env` | Any variables, typed as `NAME=VALUE` lines in the terminal form. The app's form asks nothing for this kind, so an account made there sets no variables. |
| Through LiteLLM | `litellm-openai-key` and others | Credentials for a local LiteLLM gateway that the CLI is pointed at. |

See [Agents and harnesses](/reference/agents) for the methods each CLI supports, and [Gateways, LiteLLM and custom CLIs](/user/gateways) for gateway and LiteLLM setup.

## Good to know

- Account names must start with a letter or digit and contain only letters, digits, `.`, `-`, and `_`. Names must be unique within each CLI.
- Accounts are stored in `~/.hmz/providers/<cli>/<name>/`.
- Running under an account swaps only the credentials. The CLI keeps its sessions, settings, and skills.
- During a turn under an account, Humanize unsets other credential variables from your shell, such as a stray `ANTHROPIC_API_KEY`.
- You can add a key account before installing its CLI. The account works once you install the CLI.
- On macOS, a turn or a sign-in under a named account fails for a CLI that stores credential files, which is every built-in CLI except `dsh`, `omp`, `qwen` and `litellm`. The error is `hmz internal cred: nothing could supervise it: the tracer needs Linux`. Use Local on macOS, or run on Linux.
- To manage accounts from Python, see [The Python SDK](/builder/sdk).
