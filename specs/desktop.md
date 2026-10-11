# `desktop`

The macOS app in `desktop/`: one window on the page `hmz web` serves, which it starts as its own
child and stops as it quits. It is a frame around that page and nothing more: it draws nothing
of humanize's but what to do while the page cannot be had, brings no Python and no `hmz` of its
own, and is answerable only for starting the one installed here, showing its page, and leaving
nothing running behind it.

## API

```text
humanize.app      ai.humanfia.humanize, macOS 11 or later, on Apple silicon and Intel
  runs            hmz web --no-open --attached --port <the port it had last, or 0>
  in              $HOME, with the environment a login shell gives this account
  finds hmz in    $HUMANIZE_HMZ alone where it is set, else $PATH, then ~/.local/bin,
                  $UV_TOOL_BIN_DIR, /opt/homebrew/bin, /usr/local/bin, /usr/bin and /bin
  keeps           ~/Library/Application Support/ai.humanfia.humanize/port
                  ~/Library/Logs/ai.humanfia.humanize/humanize.log
```

```js
// What its own page asks of it.
invoke('status')  // once hmz web is not starting: {state: 'running' | 'missing' | 'outdated'},
                  // or {state: 'failed' | 'stopped', detail: what it said on stderr}
invoke('retry')   // starts it again, where it is not starting or running
```

`HUMANIZE_HMZ` is for development and tests: it names the `hmz` to run, and nothing else is
looked for while it is set.

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
- MUST say, in words and never a sentence for a heading or a button: `Install humanize` with
  `uv tool install hmz` to copy, the documentation and Retry, where no `hmz` is found; `Update
  humanize` with `uv tool upgrade hmz` where it refuses `web` or `--attached`; and what it said on
  stderr with Retry where it exits before it listens for any other reason.
- MUST show what it said and offer Restart where `hmz web` exits on its own once it listens.

### The window

- MUST load nothing but its own page and `http://127.0.0.1:<port>` of the `hmz web` it started;
  anything else, a new window included, MUST open in the default browser, and only where it is
  `http`, `https` or `mailto`.
- MUST put a download in `~/Downloads`, under the name the page gave it -- numbered where that
  is taken, never over another file -- and show it in the Finder once it is saved.
- MUST keep its size and place from one launch to the next, and MUST keep its title the page's.
- MUST have the menus a Mac app has -- the app's, Edit, View, Window and Help -- with Edit's
  undo, cut, copy, paste and select all, which the web view needs to have them at all; View's
  Reload, Actual Size, Zoom In, Zoom Out and Full Screen; and the documentation under Help. It
  MUST NOT take a shortcut the page binds: Cmd+K, Cmd+Shift+O and Cmd+. are the page's.
- MUST NOT put a script of its own into `hmz web`'s page, nor grant it any of the app's commands.

### Leaving

- Closing the window MUST only hide it, with the app and `hmz web` left running; the Dock icon,
  or opening the app again, MUST bring it back. A second copy of the app MUST NOT start: it MUST
  bring the first one's window forward and exit.
- Quitting MUST interrupt `hmz web` as Ctrl+C would, kill it if it has not stopped within 3
  seconds, and reap it, so that no process of the app's outlives it; and MUST hold `hmz web`'s
  standard input open while it runs, so that `--attached` stops it however the app ends.
- MUST start `hmz web` with SIGINT, SIGTERM and SIGHUP as they are by default, whatever the app
  was handed: one ignored where the app was started would be ignored by `hmz web` too, and
  Quit would kill it rather than stop it.

### What it weighs

- MUST be Rust and the system's web view, with no frontend framework, no bundler, and no
  feature of Tauri it does not use; its own page MUST be plain HTML, CSS and JavaScript.
- MUST build its release optimised for size, linked whole and stripped, with a disk image under
  15 MB.

### The release

- MUST be built for every release as one disk image for both architectures,
  `humanize-<version>-macos-universal.dmg`, laid out to drag the app into Applications, attested
  as built by `publish.yml`, and attached to the GitHub release beside the wheel and the sdist.
- MUST be signed ad hoc where the repository holds no Apple Developer ID, and signed with it and
  notarized where it does.
- MUST say its version only in `desktop/src-tauri/tauri.conf.json`, `0.0.0` on `main`, which a
  release sets to its tag; a pre-release MUST still give macOS a bundle version of numbers alone.
