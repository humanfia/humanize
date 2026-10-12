# `desktop`

The macOS app in `desktop/`: one window on the page `hmz web` serves, which it starts as its own
child and stops as it quits. It is a frame around that page and nothing more: it draws nothing
of humanize's but how it is getting there and what went wrong, and is answerable only for
having the `hmz` of its own release installed, starting it, showing its page and what it
notifies, leaving nothing running behind it, and keeping itself up to date.

## API

```text
humanize.app      ai.humanfia.humanize, macOS 11 or later, on Apple silicon and Intel
  runs            hmz web --no-open --attached --port <the port it had last, or 0>
  in              $HOME, with the environment a login shell gives this account
  says            WKWebView's user agent, then humanize-desktop/<version>
  installs        uv tool install --force --python '>=3.12' --refresh-package hmz
                  hmz[<its extras>]==<its version>
                  with the first uv that answers `uv tool dir --bin` of $PATH, ~/.local/bin,
                  ~/.cargo/bin, /opt/homebrew/bin and its own, downloaded where none does
  runs hmz from   `uv tool dir --bin`; $HUMANIZE_HMZ alone where it is set, and in a
                  development build, $PATH, then ~/.local/bin, $UV_TOOL_BIN_DIR,
                  /opt/homebrew/bin, /usr/local/bin, /usr/bin and /bin
  opens           .hmzepic, application/vnd.hmz.epic+gzip, as ai.humanfia.humanize.epic,
                  which it exports, conforming to public.data: its viewer and owner
  keeps           ~/Library/Application Support/ai.humanfia.humanize/port
                  ~/Library/Application Support/ai.humanfia.humanize/uv/uv
                  ~/Library/Logs/ai.humanfia.humanize/humanize.log
  updates from    https://github.com/humanfia/humanize/releases/latest/download/latest.json
```

```js
// What its own page asks of it.
invoke('status', {after})  // once it is not starting, and not `after`, the status drawn last:
  // {state: 'running' | 'missing' | 'outdated'}
  // {state: 'installing', detail: {updating, step: 'uv' | 'python' | 'hmz', line}}
  // {state: 'waiting', detail: the version of the hmz holding running epics}
  // {state: 'install-failed', detail: {updating, said, keep: whether Continue can be offered}}
  // {state: 'failed' | 'stopped', detail: what it said on stderr}
invoke('retry')       // starts again, where it failed, stopped or found no hmz
invoke('keep')        // starts the hmz there, where installing its own failed and `keep` was said
invoke('update_now')  // installs its own now, where it is waiting

// What `hmz web`'s page asks of it, and nothing else.
invoke('notify', {title, body, address})  // a notification; clicked, the page opens `address`
```

`HUMANIZE_HMZ` is for development and tests: it names the `hmz` to run, nothing else is looked
for while it is set, and nothing is installed. A development build, `0.0.0`, installs nothing
either: it runs the first `hmz` it finds.

## Requirements

### Starting

- MUST open its window on its own page at once, a splash in humanize's colours light or dark as
  the system is -- `--paper` and `--ink` of `hmz web`'s page -- and MUST draw the window in that
  paper before any page is drawn, so it never flashes white.
- MUST ask the login shell for its environment once a launch, while the splash shows, and give
  up on it after 5 seconds for its own; MUST put `~/.local/bin`, `$UV_TOOL_BIN_DIR`,
  `/opt/homebrew/bin`, `/usr/local/bin` and the system's `/usr/bin` and `/bin` after `PATH`,
  each it lacks, either way; and MUST start `hmz web` in `$HOME` with that environment, since
  the daemon it starts runs the agents in it.
- MUST start it on the port it had last, so that what its page keeps in the browser, which is
  kept by origin, is there again; where that port cannot be served, MUST start it once more on
  any port, and keep that one.
- MUST open the window on the address `hmz web` prints once it prints it, within 30 seconds, as
  a top-level page and never a frame, and MUST NOT write that address's key anywhere: a log
  names the origin alone.
- MUST say, in words and never a sentence for a heading or a button, what went wrong: what
  `hmz web` said on stderr with Retry where it exits before it listens; and, where nothing is
  installed, `Not found` where no `hmz` is found and `Outdated` where it refuses `web` or
  `--attached`, with Retry. It MUST offer the documentation wherever something went wrong, and
  MUST NOT ask anybody to run a command.
- MUST show what it said and offer Restart where `hmz web` exits on its own once it listens.

### Installing `hmz`

- A release MUST run `hmz` of its own version and no other -- `0.5.0-rc.1` runs `0.5.0rc1` --
  as `uv tool` installs it for this account, the `hmz` a terminal finds in `~/.local/bin`; it
  MUST ignore any other `hmz` on `PATH`.
- MUST tell the version there by what `hmz --version` says, and MUST NOT install anything where
  it is the app's: then all it adds to a launch MUST be that and `uv tool dir --bin`.
- MUST install it where there is none, and replace one of any other version, older or newer,
  with `uv tool install --force`, keeping the extras it was installed with; MUST check that what
  it installed says the app's version; and MUST say how that goes while it does, as `Installing
  humanize` or `Updating humanize`, the step -- `Getting uv`, `Getting Python`, `Installing hmz`
  -- and the last line uv said.
- MUST use the user's uv where one answers `uv tool dir --bin`; where none does, MUST download
  the uv release pinned in the app for this Mac's architecture from astral-sh/uv's GitHub
  release over HTTPS, through the login shell's proxy and trusting what macOS trusts, saying how
  much has come; MUST refuse it unless its sha256 is the one pinned beside it; and MUST keep it
  in its own data directory alone, written whole and then moved into place. It MUST NOT touch a
  shell profile.
- MUST NOT replace an `hmz` while this machine's daemon is running -- the epics it holds would
  have their files taken from under them -- telling so by the process `daemon.json` names in
  `humanize-<uid>` of the temporary directory. It MUST run the `hmz` there instead while they
  run, and install its own on a later launch once the daemon has gone, which it does once its
  hosts hold nothing running and nobody reading. Where the `hmz` there is too old to serve it,
  MUST say `Update waiting` with its version, look again every 2 seconds and install its own
  once the daemon has gone, and offer `Update now` for the user to install it at once.
- Where an install fails, MUST say `Install failed` or `Update failed` with what uv said, Retry
  and the documentation, and `Continue` with the `hmz` there where it takes `web --attached`.
- MUST leave no uv and no install half-written however it ends: the uv it downloads is put in
  place whole or not at all, and uv's own install is.

### The window

- MUST load nothing but its own page and `http://127.0.0.1:<port>` of the `hmz web` it started;
  anything else, a new window included, MUST open in the default browser, and only where it is
  `http`, `https` or `mailto`.
- MUST import a `.hmzepic` opened with it -- double-clicked, or `Open With` -- or dropped on
  its window, by opening `#/epics/import?path=<its path>` on `hmz web`'s page, which opens its
  Exomyth; one opened before `hmz web` listens MUST be imported once it does. Of several at once,
  MUST import the last; MUST ignore any other file.
- MUST put a download in `~/Downloads`, under the name the page gave it -- numbered where that
  is taken, never over another file -- and show it in the Finder once it is saved.
- MUST keep its size and place from one launch to the next, and MUST keep its title the page's.
- MUST draw no title bar of its own: the page runs to the window's top edge, with the traffic
  lights over its top row, centred on it; the window MUST be dragged by any of that row that is
  not clicked, and zoomed where it is double-clicked, on its own page and on `hmz web`'s.
- MUST say it is the app in its user agent, so that the page draws its top row around the
  traffic lights from its first frame, and MUST tell the page whether the window is full
  screen, where they are gone.
- MUST have the menus a Mac app has -- the app's, Edit, View, Window and Help -- with Edit's
  undo, cut, copy, paste and select all, which the web view needs to have them at all; View's
  Reload, Actual Size, Zoom In, Zoom Out and Full Screen; and the documentation under Help. It
  MUST NOT take a shortcut the page binds: Cmd+K, Cmd+Shift+O and Cmd+. are the page's.
- MUST NOT put a script of its own into `hmz web`'s page but what says whether the window is
  full screen, nor grant it any of the app's commands but `notify`, nor anything but that and to
  drag and zoom the window.
- MUST show what `notify` is handed as a notification of macOS's own, its title and body as
  text, asking macOS for leave the first time; and a click on one MUST bring the window forward
  and open its address on `hmz web`'s page, only where it is a `#` address of that page's own
  origin.

### Leaving

- Closing the window MUST only hide it, with the app and `hmz web` left running; the Dock icon,
  or opening the app again, MUST bring it back. A second copy of the app MUST NOT start: it MUST
  bring the first one's window forward and exit.
- Quitting MUST interrupt every process the app started and has not seen end -- `hmz web`,
  whether it listens yet or not, uv installing, an `hmz` or a uv asked its version or
  directory -- as Ctrl+C would, kill each that has not stopped within 3 seconds, and reap it, so
  that no process of the app's outlives it, and MUST start none from then on; and MUST hold
  `hmz web`'s standard input open while it runs, so that `--attached` stops it however the
  app ends.
- MUST start every process with SIGINT, SIGTERM and SIGHUP as they are by default, whatever the
  app was handed: one ignored where the app was started would be ignored by `hmz web` too, and
  Quit would kill it rather than stop it.

### Updating itself

- MUST look for a newer release 5 seconds after it starts, so that the start is never slower
  for it, and every 6 hours after by the wall clock, asleep or not, at `latest.json` of the latest release over HTTPS -- never a
  pre-release's, so that a release is all it is offered -- and MUST take only a version newer
  than its own, and a pre-release only where its own is one. A development build, `0.0.0`, MUST
  never look.
- MUST download what it finds in the background, and MUST take it only signed with the key
  whose public half is in `tauri.conf.json`.
- MUST then ask once, in an alert titled with the new version: `Restart` installs it and starts
  the app again, through the quit that stops `hmz web`; `Later`, or a quit while it asks,
  installs it as the app quits. The alert MUST NOT hold up a quit, and MUST go with the app.
- MUST offer `Check for Updates…` in the app's menu, which looks at once and says what it
  found -- the update, that it is up to date, or why it could not look -- or, once one is
  downloaded, asks again. A look of its own MUST say nothing but to the log.
- MUST NOT download where it could not install: run from its disk image, moved aside by
  Gatekeeper, or where only an administrator could replace it.

### What it weighs

- MUST be Rust and the system's web view, with no frontend framework, no bundler, and no
  feature of Tauri it does not use; its own page MUST be plain HTML, CSS and JavaScript.
- MUST build its release optimised for size, linked whole and stripped, with a disk image under
  15 MB.

### The release

- MUST be built for every release as one disk image for both architectures,
  `humanize-<version>-macos-universal.dmg`, laid out to drag the app into Applications, attested
  as built by `publish.yml`, and attached to the GitHub release beside the wheel and the sdist.
- MUST be built for every release as its update too, where the repository holds the updater's
  key: `humanize-<version>-macos-universal.app.tar.gz`, signed with that key and attested, and
  `latest.json` offering it to both architectures, both attached to the release. Where the key
  is not held, the release MUST still be made, without them.
- MUST be signed ad hoc where the repository holds no Apple Developer ID, and signed with it and
  notarized where it does.
- MUST say its version only in `desktop/src-tauri/tauri.conf.json`, `0.0.0` on `main`, which a
  release sets to its tag; a pre-release MUST still give macOS a bundle version of numbers alone.
