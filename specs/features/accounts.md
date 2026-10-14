# Accounts

## 1. Scope

This specification governs **accounts**: named sets of credentials for one harness kind, kept by
**hmz** apart from the harness's own sign-in, so that two agents of one harness can run as two
accounts at once. It states how an account is named, stored, made, signed in and removed, which
ways in each harness kind offers, what a turn under an account is launched with, which machine's
credentials a harness reads, how a sign-in that refreshes itself is protected, what happens when a
credential is expired or refused, how an account's model catalogue is kept, and how one account
serves several harness kinds.

Out of scope:

- The harness kinds, agent specs, retries and fallback chains: `features/agents.md`.
- The LiteLLM gateway's lifecycle: `features/agents.md` §13.2.
- The layout of `<home>/providers/` and of the machine cache as files: `api/files/home.md` and
  `api/files/machine.md`.
- Where a harness runs relative to its env: `features/placements.md`.
- The account pages of the terminal and web frontends: `features/tui.md` and `features/web.md`.

## 2. Definitions

**2.1** **Account name**: a name of one or more letters, digits, dots, dashes and underscores,
starting with a letter or a digit.

**2.2** **Harness machine's own sign-in**: for each harness kind, the harness as the user has
signed it in on the harness machine, under no account and with the empty account name.

**2.3** **Way in**: one kind of account a harness kind offers, defined by the command it runs, the
variables it asks for, the variables it sets, and the arguments it appends to every turn.

**2.4** **Account variable**: a variable a harness reads an account, a credential or a model
endpoint from: every variable any way in of that harness kind asks for or sets, every other name
by which the harness reads the same credential (§6.1.4), and every other variable that harness
reads its sign-in or endpoint from.

**2.5** **Credential file**: a file the harness's own login writes its credentials to (§6.2.1).

**2.6** **Refreshing sign-in**: a credential file holding a refresh token that the vendor
replaces on each refresh and treats as stolen if presented again after replacement.

**2.7** **Gateway account**: an account that points a harness at an endpoint, other than the
vendor's own, that speaks that harness's protocol.

**2.8** **Routed account**: an account of a harness kind whose turns pass through a gateway, as
`features/agents.md` §13.2 defines it.

**2.9** **Model catalogue**: the list of models an account runs and the efforts each takes.

## 3. Identity

### 3.1 Naming

**3.1.1** An account MUST be identified by its harness kind and its account name, written
`<cli>/<name>`.

**3.1.2** hmz MUST accept every alias of a harness kind where an account is named, and MUST
record the account under the kind's name.

**3.1.3** hmz MUST refuse an account name that is not an account name per §2.1, where it is given,
with a message stating the permitted characters.

**3.1.4** hmz MUST refuse an account of a harness kind that is neither built in nor added.

**3.1.5** Accounts MUST be available for every built-in harness kind and for every ACP harness.

### 3.2 Choosing an account

**3.2.1** An agent MUST run as the account its agent spec names after `@`, and as the harness
machine's own sign-in where its agent spec names none, except as §7.1.2 states for harness
location standalone.

**3.2.2** An agent spec naming an account that does not exist MUST be refused before the epic
starts where it is given to `-a`, and otherwise before the agent's first turn, with a message
naming the agent, the harness kind and the account.

**3.2.3** hmz MUST NOT fall back to the harness machine's own sign-in for an agent whose account
does not exist.

### 3.3 The harness machine's own sign-in

**3.3.1** The harness machine's own sign-in MUST be offered for every harness kind, and MUST NOT
be listed among the accounts hmz made.

**3.3.2** hmz MUST hold no credentials for the harness machine's own sign-in, and MUST NOT make,
sign in, change or remove it.

**3.3.3** A turn under the harness machine's own sign-in MUST run with its environment as hmz found
it, with no account variable added or removed and no credential file substituted.

## 4. Storage

### 4.1 Layout

**4.1.1** Each account MUST be one directory `<home>/providers/<cli>/<name>/`, as
`api/files/home.md` states.

**4.1.2** The account's directory MUST hold a file `provider.json` stating the harness kind, the
account name, the way in it was made by, the variables a turn under it is given, the arguments
appended to its turns, and when it was made, and MUST hold the credential files the harness's own
login wrote under it.

**4.1.3** The directory, not the contents of `provider.json`, MUST decide which harness kind and
name an account has.

**4.1.4** A directory whose `provider.json` is missing or is not a JSON object MUST NOT be listed
as an account.

**4.1.5** A `fallback` key in `provider.json` MUST be ignored, and MUST be removed the next time
the account is written.

### 4.2 Protection

**4.2.1** Every directory hmz creates on the way to an account's directory and to each credential
file's parent MUST be readable and writable only by the user from the moment it exists.

**4.2.2** Every file hmz writes into an account MUST be readable and writable only by the user
from the moment it exists, and MUST be replaced whole, never left partly written.

**4.2.3** Removing an account MUST delete its directory, credential files included, and its model
catalogue.

## 5. Ways in

### 5.1 General

**5.1.1** hmz MUST offer, for each harness kind, its own ways in, in the order §5.2 lists them;
then, where LiteLLM's proxy can be started on this machine and the harness kind supports a
gateway, every way in of `litellm` as a routed way named `litellm-<way>`; then the way `env`,
except for `dsh` and `litellm`.

**5.1.2** Where the harness kind supports a gateway and LiteLLM is not installed, hmz MUST show,
in place of the routed ways, the command that installs it.

**5.1.3** A way in that runs a command MUST run the harness's own login command on the user's
terminal, with the account's credential files in place of the harness's own (§6.2), so that what
the login writes lands in the account.

**5.1.4** A way in that asks for a secret MUST NOT show the secret back, and a secret a login
command takes on standard input MUST be written to its standard input and MUST NOT appear on any
command line.

**5.1.5** A question with a default MUST take that default where the user leaves it blank.

**5.1.6** Making an account MUST replace the account's way, variables and arguments with those
given, and MUST leave credential files already in the account unchanged.

**5.1.7** A login command that exits non-zero MUST be reported with its exit status, and a login
command whose harness is not installed MUST be reported as not installed.

### 5.2 Ways by harness kind

**5.2.1** `claude` MUST offer: `login` (runs `claude auth login`); `console` (runs
`claude auth login --console`); `token` (asks `CLAUDE_CODE_OAUTH_TOKEN`); `key` (asks
`ANTHROPIC_API_KEY`); `wif` (workload identity federation); `anthropic-gateway`,
`bedrock-gateway` and `vertex-gateway` (a base URL and `ANTHROPIC_AUTH_TOKEN`); `bedrock`,
`bedrock-key`, `mantle`, `vertex`, `foundry`, `aws` and `google-cloud` (the cloud's own
credentials and region).

**5.2.2** `agy` MUST offer: `login` (runs `agy`); `key` (asks `GEMINI_API_KEY`);
`gemini-gateway` and `openai-gateway` (its enterprise LLM gateway's URL and key); and `adc`
(asks `GOOGLE_APPLICATION_CREDENTIALS`).

**5.2.3** `codex` MUST offer: `login` (runs `codex login`); `device` (runs
`codex login --device-auth`); `key` and `token` (run `codex login` with the key or token on
standard input); `workload` (workload identity federation); `openai-gateway` (asks
`CODEX_PROVIDER_URL` and `CODEX_PROVIDER_KEY`); `azure`; `bedrock`; `bedrock-key`; `ollama`; and
`lmstudio`.

**5.2.4** `cursor-agent` MUST offer: `login` (runs `cursor-agent login`); `key` (asks
`CURSOR_API_KEY`); and `cursor-gateway` (asks `CURSOR_API_ENDPOINT` and `CURSOR_API_KEY`).

**5.2.5** `dsh` MUST offer: `key` (asks `DEEPSEEK_API_KEY`); and `openai-gateway`,
`anthropic-gateway` and `gemini-gateway` (ask `DEEPSEEK_BASE_URL` and `DEEPSEEK_API_KEY`).

**5.2.6** `litellm` MUST offer: `openai-key`, `anthropic-key`, `gemini-key`, `xai-key`,
`openrouter-key`, `deepseek-key`, `groq-key` and `mistral-key` (each the vendor's own key
variable); `openai-gateway` and `anthropic-gateway` (ask `LITELLM_GATEWAY_URL` and
`LITELLM_GATEWAY_KEY`); `bedrock`; `vertex`; and `azure`.

**5.2.7** `grok` MUST offer: `login` (runs `grok login`); `device` (runs
`grok login --device-auth`); `oidc`; `provider-command`; `key` (asks `XAI_API_KEY`); and
`openai-gateway` and `anthropic-gateway` (ask `GROK_XAI_API_BASE_URL` and `XAI_API_KEY`).

**5.2.8** `kimi` MUST offer: `login` (runs `kimi login` for the region asked); `kimi-key`; and
`openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask `KIMI_MODEL_BASE_URL`,
`KIMI_MODEL_API_KEY` and `KIMI_MODEL_NAME`).

**5.2.9** `mcode` MUST offer: `login` (runs `mcode login` for the region asked); `key` (runs
`mcode provider set-minimax-key`); and `openai-gateway` and `anthropic-gateway` (run
`mcode provider add` for the gateway asked).

**5.2.10** `mimo` MUST offer: `login` (runs `mimo auth login`); `key` (asks `XIAOMI_API_KEY`);
`anthropic-key`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key` and `deepseek-key`;
`openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask `MIMO_GATEWAY_URL`,
`MIMO_GATEWAY_KEY` and `MIMO_GATEWAY_MODEL`); `vertex`; `bedrock`; and `azure`.

**5.2.11** `omp` MUST offer: `anthropic-key`, `anthropic-token`, `openai-key`, `gemini-key`,
`xai-key`, `openrouter-key`, `deepseek-key`, `groq-key` and `mistral-key`; `bedrock`; and
`vertex`.

**5.2.12** `omp` MUST offer no `login`.

**5.2.13** `opencode` MUST offer: `login` (runs `opencode auth login`); `wellknown`; `zen` (asks
`OPENCODE_API_KEY`); `anthropic-key`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key`,
`deepseek-key` and `mistral-key`; `openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask
`OPENCODE_GATEWAY_URL`, `OPENCODE_GATEWAY_KEY` and `OPENCODE_GATEWAY_MODEL`); `bedrock`;
`vertex`; and `azure`.

**5.2.14** `pi` MUST offer: `login` (runs `pi` for its `/login`); `anthropic-key`,
`anthropic-token`, `openai-key`, `gemini-key`, `xai-key`, `openrouter-key`, `deepseek-key`,
`groq-key` and `mistral-key`; `openai-gateway`, `anthropic-gateway` and `gemini-gateway` (ask
`PI_GATEWAY_URL`, `PI_GATEWAY_KEY` and `PI_GATEWAY_MODEL`); `bedrock`; `vertex`; and `azure`.

**5.2.15** `qwen` MUST offer: `coding-plan` and `token-plan` (ask `OPENAI_BASE_URL` and
`OPENAI_API_KEY`); `gemini-key`; `openai-gateway`; `anthropic-gateway`; `gemini-gateway`;
`vertex`; and `vertex-key`.

**5.2.16** `qwen` MUST offer no `login`.

**5.2.17** An ACP harness MUST offer only `env`.

> Informative: the variables each way asks for, their defaults and the arguments each appends are
> listed in `docs/reference/providers.md`.

### 5.3 The `env` way

**5.3.1** The `env` way MUST read `NAME=VALUE` lines, stripping surrounding whitespace, skipping
blank lines and lines starting with `#`, and permitting `=` within a value.

**5.3.2** A non-empty line with no `=`, or with an empty name, MUST be refused with a message
naming the line.

**5.3.3** The `env` way MUST keep every variable given, whatever its name.

## 6. A turn under an account

### 6.1 Variables and arguments

**6.1.1** A turn under an account MUST run with the account's variables added to its environment.

**6.1.2** A turn under an account MUST run without every account variable of its harness kind
that the account does not set, so that no variable of the user's shell overrides the account.

**6.1.3** A turn under an account MUST have the account's arguments appended to the harness's
command line.

**6.1.4** The following names MUST be treated as one credential each, so that setting any one
removes the others: `CLAUDE_CODE_OAUTH_TOKEN` and `ANTHROPIC_OAUTH_TOKEN`; `GEMINI_API_KEY` and
`GOOGLE_API_KEY`; `MOONSHOT_API_KEY` and `KIMI_API_KEY`; `OPENAI_BASE_URL` and
`OPENAI_API_BASE`; `XAI_API_KEY` and `GROK_CODE_XAI_API_KEY`.

**6.1.5** An account's variables MUST reach the harness as its environment and MUST NOT be
written on any command line.

**6.1.6** On `litellm`, the account MUST be passed on the call.

**6.1.7** On `litellm`, hmz MUST NOT remove any variable from this process's environment for an
account.

### 6.2 Credential files

**6.2.1** The credential files of each harness kind MUST be those `api/files/harness-homes.md` §4.5
lists, and an ACP harness MUST have none.

**6.2.2** A turn under an account MUST read and write the account's copy of each credential file
wherever the harness reads or writes its own, and MUST NOT read or write the harness's own.

**6.2.3** A credential file the harness writes during a turn under an account MUST be written to
the account, so that a refreshed credential persists.

**6.2.4** A credential path hmz cannot substitute MUST fail the harness's access to it, and MUST
NOT fall through to the harness's own file.

**6.2.5** A turn that needs credential files substituted on a machine where hmz cannot substitute
them MUST be refused rather than run with the harness's own credentials.

**6.2.6** A copy of a credential file that hmz makes for a harness to read MUST be used for reads
alone, as `api/files/harness-homes.md` §4 states, and MUST be removed when the turn
ends, whatever became of it.

**6.2.7** A credential that is not a file (a system keychain entry) and a credential stored in
the same database as the harness's sessions MUST NOT be held by an account.

**6.2.8** Where a harness is launched with a virtual config home (`features/agents.md` §5.2),
its credential files MUST be the account's, or for the harness machine's own sign-in the user's
real ones, and MUST NOT be copies discarded at exit.

### 6.3 Gateway accounts

**6.3.1** A gateway account MUST point the harness at its endpoint by the harness's own variables
or arguments, and hmz MUST NOT write the endpoint or its key into any configuration file of the
user.

**6.3.2** Where an endpoint's key is needed by a harness that reads it from configuration, the
configuration MUST name the variable holding the key, and the key itself MUST NOT be written to
any file or command line.

**6.3.3** A gateway account MUST run the models its endpoint serves, under the model ids the
endpoint lists.

### 6.4 Routed accounts

**6.4.1** A routed way MUST ask for and set what `litellm`'s way of the same name asks for and
sets.

**6.4.2** A turn under a routed account MUST be launched as `features/agents.md` §13.2 states,
with the account's own variables withheld from the harness.

**6.4.3** The models of a routed account MUST be those behind the gateway, never those the
harness lists of its own.

**6.4.4** `claude`, `agy`, `codex`, `dsh`, `grok`, `kimi`, `pi`, `qwen`, `opencode`, `mimo` and
`mcode` MUST support routed accounts.

**6.4.5** Every harness kind not listed in §6.4.4 MUST NOT offer routed accounts.

## 7. Which machine's credentials a harness reads

### 7.1 The harness machine

**7.1.1** An agent with no account MUST run as the harness's own sign-in on the harness machine,
and hmz MUST NOT carry any sign-in of this machine to another machine for it.

**7.1.2** An agent with an account MUST run as that account wherever its harness runs, with the
account's variables and credential files made available to the harness on the harness machine
for each turn, except under harness location standalone, where the agent MUST run as the harness
machine's own sign-in (`features/placements.md` §5.3.3).

**7.1.3** Where a harness runs under harness location env, the account's credential
files MUST be placed there in a directory only the harness machine's user can enter, unreadable
by anyone else from the moment it exists, and MUST be removed when the turn ends, whatever became
of it.

**7.1.4** Where a harness under harness location env has no way of reading credential files from a
location hmz names, a turn needing them MUST be refused.

**7.1.5** Commands the agent runs on an env machine other than the harness machine MUST NOT
receive the account's variables.

### 7.2 Refreshing sign-ins

**7.2.1** hmz MUST treat a credential file holding `refresh_token`, `refreshToken` or a `refresh`
key as a refreshing sign-in.

**7.2.2** A refreshing sign-in MUST never be refreshed in two places independently.

**7.2.3** Turns whose harness runs on this machine MUST use a refreshing sign-in in place, and
any number of them MUST be permitted to do so at once.

**7.2.4** A turn whose harness runs under harness location env MUST be lent a copy of a refreshing
sign-in only while no other turn uses it, and no other turn MUST use it until the copy is returned.

**7.2.5** A turn that finds a refreshing sign-in held the other way MUST be refused at once with
the fault class `contended`, and MUST NOT wait for it.

**7.2.6** When a lent turn ends, hmz MUST write the refreshed copy back over the account's file,
unless the account's file changed meanwhile, in which case hmz MUST say so and MUST NOT write over
it.

**7.2.7** Where the file system of an account's directory does not let hmz hold a refreshing
sign-in against other processes, hmz MUST log that it cannot hold the sign-in.

**7.2.8** Where §7.2.7 applies, hmz MUST run the turn without holding the sign-in.

## 8. Model catalogues

### 8.1 Keeping and asking

**8.1.1** hmz MUST keep each account's model catalogue in this machine's cache, as
`api/files/machine.md` states, and never in the home.

**8.1.2** The catalogue of the harness machine's own sign-in MUST be kept under a name no account
can take.

**8.1.3** hmz MUST ask for a catalogue when the user asks for it.

**8.1.4** A frontend MUST ask for an account's catalogue when the user picks an account whose
catalogue was never asked for.

**8.1.5** The terminal frontend MUST ask again at start-up, without blocking, for the catalogue of
the harness machine's own sign-in of each installed harness kind where that catalogue is missing or
stale.

**8.1.6** A catalogue asked for more than 7 days ago, or never asked for, MUST be stale.

**8.1.7** Where the account sets its harness's endpoint variable, the catalogue MUST be the
endpoint's model list, asked under the account's secret, following a redirect only to the same
host and never from `https` to `http`; otherwise the catalogue MUST be what the harness lists
when asked under the account.

**8.1.8** An endpoint that does not answer MUST leave a catalogue already read from it in place.

**8.1.9** Reading a catalogue MUST cost one file read and no network; a catalogue never asked for
MUST read as empty and MUST NOT be guessed.

## 9. Expired and refused credentials

### 9.1 Refusal

**9.1.1** A turn whose credential the provider refuses (expired, revoked, invalid, or not signed
in) MUST fail with the fault class `refused`, MUST NOT be retried at its place, and MUST be
carried to the next place of its fallback chain where one is configured, as
`features/agents.md` §11 states.

**9.1.2** A turn that fails as `refused` after its fallback chain is exhausted MUST raise
`HarnessRefused` in the flow, whose message MUST say that the account needs signing in again.

**9.1.3** hmz MUST NOT attempt to sign an account in again without the user.

**9.1.4** hmz MUST let the user sign an account in again from the account pages of the
frontends.

**9.1.5** Signing an account in again MUST run the account's way in again over the same account.

**9.1.6** A turn refused because a model is not the account's to run MUST fail with the fault
class `unlisted` and MUST NOT be reported as a credential failure.

## 10. One account, several harness kinds

### 10.1 Copying

**10.1.1** hmz MUST offer to copy an account of one harness kind to every other harness kind that
reads every one of its variables under the same or an equivalent name (§6.1.4).

**10.1.2** An account whose credentials are files and not variables MUST NOT be offered for
copying.

**10.1.3** A copy MUST rename each variable to the name the target harness kind reads, MUST be
recorded under the first way in of the target that asks for and sets exactly those variables and
runs no command, else under `env`, and MUST replace an account of the same name there.

**10.1.4** Copying an account to a harness kind that cannot run as it MUST be refused, naming the
account and the harness kind.

## 11. Secrecy

### 11.1 Secrets

**11.1.1** hmz MUST NOT print, display or log the value of any account variable; where an account
is shown, hmz MUST show its harness kind, its name, its way in and the names of its variables.

**11.1.2** hmz MUST NOT send any account's credentials to a frontend page.

**11.1.3** A turn under one account MUST NOT read or write the credentials of another account.
