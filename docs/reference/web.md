---
pageClass: hmz-ref
---

<script setup>
import '../.vitepress/theme/components/ref-cli/ref.css'
</script>

# Web reference

The web interface `hmz web` serves: a workspace's runs drawn in a browser on the same machine,
as one more [frontend](/reference/daemon#hosting) of the runs a host holds there. Its command
line, how a browser is let in, what is refused, the page's addresses, every route the page
calls, and the stream it follows. Package `hmz.web`. Notation:
[Conventions](/reference/#conventions). The task-by-task guide is
[In a browser](/user/web).

The server is the standard library's `http.server`, and the page is plain ES modules served as
they are: `hmz web` installs nothing beyond `hmz` and builds nothing.

## Command line {#command-line}

```text
hmz web [--port <port>] [--no-open]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--port <port>` | `0` | The port to listen on, on `127.0.0.1`. `0` picks any free one. |
| `--no-open` | off | Print the address and open no browser. |

Once listening it prints one line to stdout, flushed, then opens that address with Python's
`webbrowser` unless `--no-open` was given, and serves until `SIGINT`:

```text
hmz web: http://127.0.0.1:<port>/?key=<key>
```

### Where the runs are held {#where-runs-are-held}

| Condition | Runs |
| --- | --- |
| `HUMANIZE_DAEMON` stripped and lower-cased is `off`, `0` or `no` | Held in this process; `hmz web` stopping closes them. |
| anything else | Held by this workspace's host process, found or started through [`hmz.daemon.attach`](/reference/daemon#module), tried **3** times **0.5 s** apart. They outlive `hmz web`. |

`hmz web` attaches as one frontend, named `browser` (`#2`, `#3`… beside another of that name),
of `kind` `web`. Whenever the host lets it go, it attaches again **2 s** later, for as long as it
is served; a page following the stream is then told to [start over](#stream).

### Exit statuses {#exit-statuses}

| Status | stderr | When |
| --- | --- | --- |
| `0` | — | Interrupted (`SIGINT`) after it was serving. |
| `1` | `hmz: the runs in <dir> are held by an older humanize (pid <n>); stop it with that version` (or `on this machine`) | An older humanize holds the runs. |
| `1` | `hmz: the web interface cannot be served: <OSError>` | The runs could not be reached, or the port could not be listened on. |
| `2` | argparse's usage error | The line was wrong. |

## Letting a browser in {#sign-in}

| Step | What happens |
| --- | --- |
| The key | 32 random bytes, URL-safe base64 (43 characters), made afresh each time `hmz web` starts, and only ever printed in the address. |
| `GET /?key=<key>` | `303` to `/`, setting `hmz-<port>=<key>; HttpOnly; SameSite=Strict; Path=/`. A key that is not this server's: `403`. |
| Every request under `/api/` | Answered only where the cookie carries the key; otherwise `401`, and the page says `This browser is not let in.` |
| The page's own files | Served without the cookie; they hold nothing of the runs. |

## What is refused {#refused}

Every refusal is JSON, `{"error": "<one sentence>"}`, with the status below. They are checked in
this order.

| Status | Condition | `error` |
| --- | --- | --- |
| `403` | `Host` is not `127.0.0.1`, `localhost` or `[::1]`, on any port | `Open the address hmz web printed, on the machine it runs on.` |
| `401` | `/api/…` without the key's cookie | `Open the address hmz web printed to let this browser in.` |
| `403` | `POST` whose `Origin` is not `http://<Host>` | `Use this server's own page to make this request.` |
| `415` | `POST` whose `Content-Type` is not `application/json` | `Send JSON.` |
| `411` | `POST` whose `Content-Length` is not a number | `Say how long what is sent is.` |
| `413` | `POST` body over **1 MiB** | `That is more than a request here may send.` |
| `400` | Body not a JSON object | `Send JSON.` or `Send a JSON object.` |
| `404` / `405` | No route of that path / none for that method | `There is nothing here by that name.` |
| `405` | A method other than `GET` outside `/api/` | `Only the page's own files are here.` |
| `400` | A field a request does not take, or of another type | e.g. `start takes no rounds.`, `say takes text as text.` |
| `409` | The runs refused the request | Their own sentence, as [`Refused`](/reference/sdk#refused) gives it. |
| `503` | The runs could not be asked | `The runs could not be asked: <why>` |
| `500` | Anything else, with a traceback on `hmz web`'s stderr | `Something went wrong here: <why>` |

A `Host` naming another machine is refused before anything else is read: a web page elsewhere
that points a name of its own at `127.0.0.1` reaches nothing. A port forwarded from another
machine still names the loopback, so it is let in.

## The page {#page}

The files under `hmz/web/static/` are served as they are, `/` being `index.html`. Every answer
carries `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and
`X-Frame-Options: DENY`, a weak `ETag` and `Cache-Control: no-cache` (`304` when it has not
changed). The page itself carries:

```text
Content-Security-Policy: default-src 'self'; img-src 'self' data:; style-src 'self';
  script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none';
  form-action 'self'
```

Each view is an address after `#`, so it can be kept and opened again:

| Address | View |
| --- | --- |
| `#/runs[?status=&flow=&q=&offset=]` | Every run of the workspace. `status`: how it went, `running` or `unfinished`. |
| `#/live` | The run going, or the last one. |
| `#/runs/<name>` | One run written down, by its epic's name; live where it is the run going. |
| `#/start[?flow=&resume=<name>]` | Starting a flow, or picking the run named up. |
| `#/flows[?flow=]` | The flows on offer, one opened. |
| `#/usage[?days=]` | What the runs spent over the last `days` (7, 30, 90 or 365; default 30), by UTC day. |
| `#/settings/<page>` | `general`, `accounts`, `fallback`, `runtimes` or `workspace`. |

The colours chosen in the bar are kept in the browser's `localStorage` as `hmz-theme` (`light`,
`dark`, or absent for the system's).

## API {#api}

JSON in and out. A `POST` takes a JSON object, `{}` where nothing is sent.

### The runs held {#api-held}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/held` | | `workspace`, `version`, `me` (this frontend's client id), `gone` (why the runs let it go, or `""`), `run` (the latest [`run` snapshot](/reference/daemon#snapshots), or `null`) |
| `GET /api/held/stream` | `Last-Event-ID` header, or `?last=` | [The stream](#stream) |
| `POST /api/held/start` | `flow`, `task` (both required); `agents`, `envs` (`{role: spec}`); `params`, `budget` (object or `null`); `profile` (bool); `resume` (bool, or an epic) | The host's answer: `run` |
| `POST /api/held/say` | `text`; `to` (`""`, a role, `<role>/<n>`, or `outworlder:<role>`, routed as [`say` routes it](/reference/daemon#say-routing)) | The host's answer |
| `POST /api/held/answer` | `question`, `text` | The host's answer |
| `POST /api/held/stop`, `/force` | | The host's answer |
| `POST /api/held/afk` | `on` (bool); `role` | The host's answer |
| `POST /api/held/claim` | `role`; `take` (bool) | The host's answer |
| `POST /api/held/release` | `role` | The host's answer |
| `POST /api/held/board` | `key`; `value` (`""` removes the line) | The host's answer |
| `POST /api/btw` | `question`; `to` (`""` the btw agent, or `<role>/<n>`) | `answer`, and `asked`: `[{to, question}]`, each session the btw agent asked on the way |
| `POST /api/btw/leave` | `to`, or nothing for every side conversation | `{"ok": true}` |

Each `POST /api/held/<do>` is the [request](/reference/daemon#requests) of that name, sent down
this frontend's link as given. A side question is asked as [`/btw`](/reference/tui#btw-command)
asks one, through the same side conversations: a second question to one still answering is
`409`, and a run starting closes them.

### The runs written down {#api-runs}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/runs` | `status`, `flow`, `q` (in its task, flow or name), `offset` (`0`), `limit` (`50`, at most `200`) | `runs` (rows, newest first), `total`, `offset`, `limit`, `counts` (`{how: n}` over every run), `flows` |
| `GET /api/runs/<name>` | | The row, and `at`, the whole `task`, `ref`, `agents` (`role`, `runs`, `backend`, `model`, `effort`, `provider`), `sessions`, `envs`, `used`, `params`, `budget`, `picked_up`, `profile`, `picks_up` (whether it can be picked up), `calls` (the tree of flows it called) |
| `GET /api/runs/<name>/trace` | | `sessions`: each with its `key`, `agent` and `actions` (`category`, `name`, `at`, `start`, `seconds`, `args`), read out of the run's logs as [tracing](/reference/tracing) reads them; kept until the run's journal changes |
| `GET /api/runs/<name>/bundle` | | The run's [export](/reference/tracing), as a download |
| `GET /api/usage` | `days` (`30`; 1 to 365) | `days` (per UTC day, oldest first), `flows` (costliest first), `ended` (`{how: n}`), `whole`: each with `runs`, `cost`, `output_tokens`, `seconds`, and `money`, `tokens`, `worked` as the terminal interface says them |

A row is `name`, `flow`, `task` (its first line, cut at 240 characters), `began`, `ended`,
`how` (as the run ended; `running` for the run going, `unfinished` for one that never said),
`agents` (`[{role, runs}]`), `sessions` (a count), `resumable`, `held` (whether it is the run
going) and `spent`: what its budget counted as it ended, or `null`. A run of no such name is
`404`.

### Flows {#api-flows}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/flows` | | `flows` (`[{whose, name, about}]`), `flow` (the one this workspace opens on), `running` (the flows going, `[{ref, name, depth, since, task}]`) |
| `GET /api/flow` | `name` | What it declares: `ref`, `description`, `resumable`, `resumes`, `agents` (`name`, `required`, `auto`, `harness`, `permission`, `skills`), `envs`, `params` (its JSON schema), and `remembered` (what this workspace last set it up with). `404` for one that will not load. |
| `GET /api/backends` | | `installed` and `installable`: `{cli: [{name, efforts}]}` |

### Settings {#api-settings}

| Method and path | Takes | Answers |
| --- | --- | --- |
| `GET /api/settings` | | `workspace`, `flow`, `btw`, `details`, `reports` (`null` where never answered), `flows` (set up here) |
| `POST /api/settings` | any of `btw` (text), `details`, `reports` (bool) | As `GET` |
| `POST /api/settings/forget` | | `forgot` (whether there was anything), and as `GET` |
| `GET /api/accounts` | | `accounts` (`cli`, `name`, `way`, `sets`, `made`, `models`, `asked`, `serves`) and `backends` (each CLI's `ways`: `name`, `about`, `terminal`, `asks`) |
| `POST /api/accounts` | `cli`, `name`, `way`; `answers` (`{variable: value}`) | As `GET`. A way whose `terminal` is true is refused: it runs the CLI's own sign-in. |
| `POST /api/accounts/remove` | `cli`, `name` | As `GET` |
| `POST /api/accounts/models` | `cli`; `name` (`""` for this machine's own) | As `GET`, once the CLI has said what it runs |
| `POST /api/accounts/copy` | `cli`, `name`, `into` | As `GET` |
| `GET /api/fallbacks` | | `steps` (`spec`, `to`, `tries`, `policy`, `timeout`), `policies`, `default`, `places` |
| `POST /api/fallbacks` | `spec`; `to` (places, in order); `tries`; `policy`; `timeout` (seconds, `0` none) | As `GET` |
| `POST /api/fallbacks/clear` | `spec` | As `GET` |
| `GET /api/runtimes` | | `runtimes` (each as it is written down) and `blanks` (each backend's fields, as a new one holds them) |
| `POST /api/runtimes` | `backend`, `name`, `fields`; `replace` (bool) | As `GET` |
| `POST /api/runtimes/remove` | `backend`, `name` | As `GET` |
| `POST /api/runtimes/check` | `backend`, `name` | What it said: `reached`, `said`, `home`, `cpus`, `memory`, `gpus`, `usable`, `gpu_memory`, `runtimes`, `version`, `short`, `nodes` |
| `GET /api/runtimes/hosts` | | `hosts` your ssh config names (`alias`, `host`, `user`, `port`, `identity_files`, `proxy_jump`, `saved`) |
| `POST /api/runtimes/import` | `names`; `update` (bool) | As `GET /api/runtimes` |

An account is listed by the names of the variables it sets (`sets`), never by a value.

## The stream {#stream}

`GET /api/held/stream` answers `text/event-stream`, starting with `retry: 2000`. Each event is
named, its data one JSON object:

| Event | `id` | Data |
| --- | --- | --- |
| `hello` | | `epoch` (this link's), `me` |
| `record` | `<epoch>:<seq>` | One [history record](/reference/daemon#history-records), in order |
| `standing` | | One [snapshot](/reference/daemon#snapshots), each time it changes |
| `figures` | | What the run has done and cost, worked out by `hmz.runtime.watching`, at most once a second |
| `gone` | | `why`: the runs let this link go. The stream ends. |
| `again` | | `{}`: the link changed, or the server is stopping. Start over. |

A stream starts with every record kept (the latest **20,000**) after the one named by
`Last-Event-ID`, or `?last=`, where that names this link's epoch, and from the first kept
otherwise; then how everything stands; then each as it comes. A comment, `: quiet`, is sent
after **15 s** of nothing.

`figures` holds `run`, `elapsed` and `lasting` (the clock), `ended`, `agents` and `sessions`
(each `name`, `turns`, `working`, `since`, `lasting`, `used`, `tokens`, `under`), `handovers`
(`[{from, to, count}]`), `latest`, `spending` (per model: `tokens`, `rate`, `dollars`, `money`,
`kinds`), `reckoning` (per kind: `tokens`, `whole`) and `tally`: the two lines the terminal
interface draws under a run.

## Module `hmz.web` {#module}

```python
@contextlib.contextmanager
def listening(*, port: int = 0, apart: bool = True) -> Generator[Site]: ...
def serve(*, port: int = 0, apart: bool = True, shown: Callable[[str], object] = print,
          opened: Callable[[str], object] | None = None) -> None: ...
```

`listening` attaches to the runs and listens, answering nothing until `Site.serve_forever` is
called; leaving the block lets go of the runs, and closes them where they were held in this
process. `serve` is both, until `KeyboardInterrupt`, telling `shown` the address once it
listens and handing it to `opened`. `Site.address` is the address with its key; `Site.port` the
port.
