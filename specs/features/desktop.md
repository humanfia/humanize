# Desktop

## 1. Scope

This document specifies the macOS app of hmz: how it is released and installed, how it installs and
starts hmz, what its window shows while it starts and when something goes wrong, how its window
behaves, how it opens exported epics and saves downloads, how it shows notifications, how it quits,
and how it updates itself. The app is a window on the page `hmz web` serves, and draws nothing of
hmz's own but its splash and its errors.

Out of scope:

- The page the window shows: `features/web.md`.
- The command line of `hmz web`: `api/cli.md`.
- The files the app keeps, and their locations: `api/files/desktop.md`.
- The daemon, and epics outliving the app: `features/daemons.md`.
- `hmz update` and the release check of hmz: `features/updates.md`.

## 2. Definitions

**2.1** The **app** is the macOS application named `humanize`, with the bundle identifier
`ai.humanfia.humanize`.

**2.2** The **app's version** is the release of hmz the app was built for.

**2.3** The **app's hmz** is hmz of the app's version, installed for the user as a uv tool.

**2.4** The **splash** is the app's own page: what the window shows before the page of `hmz web`,
and in its place when `hmz web` cannot be shown.

**2.5** A **development build** is a build of the app whose version is `0.0.0`.

**2.6** The **server** is the `hmz web` process the app started.

## 3. Releases

**3.1** Every release of hmz MUST be published with one disk image of the app for Apple silicon and
Intel together, named `humanize-<version>-macos-universal.dmg`, attached to the GitHub release.

**3.2** The disk image MUST lay the app out to be dragged into Applications, on a background that
shows how, and, where the app is signed ad hoc, how to open it the first time.

**3.3** The disk image MUST be under 15 MB.

**3.4** The app MUST be signed with an Apple Developer ID and notarized where the repository holds
one, and MUST be signed ad hoc otherwise.

**3.5** Where the repository holds the updater's key, every release MUST also publish the app's
update, `humanize-<version>-macos-universal.app.tar.gz`, signed with that key, and `latest.json`,
which offers it to both architectures. Where the key is not held, the release MUST be published
without them.

**3.6** The disk image and the update MUST be attested as built by the release workflow of the
repository.

**3.7** The GitHub release MUST NOT carry the wheel or the sdist of hmz, which PyPI carries.

**3.8** The app MUST run on macOS 11 or later, on Apple silicon and on Intel.

**3.9** The app's version MUST be the release's tag; a pre-release MUST still give macOS a bundle
version of numbers alone.

## 4. Installing hmz

**4.1** A release of the app MUST run the app's hmz and no other hmz; the version `0.5.0-rc.1` of
the app MUST run hmz `0.5.0rc1`.

**4.2** The app's hmz MUST be the hmz a terminal finds in `~/.local/bin`; the app MUST ignore any
other hmz on `PATH`.

**4.3** The app MUST learn the version of the hmz installed by asking it, and MUST install nothing
where that version is the app's version.

**4.4** Where no hmz is installed, or one of another version, older or newer, the app MUST install
the app's hmz, replacing the other and keeping the extras it was installed with.

**4.5** After installing, the app MUST check that the hmz installed says the app's version.

**4.6** The app MUST use the user's uv where one is found on `PATH`, in `~/.local/bin`,
`~/.cargo/bin` or `/opt/homebrew/bin`.

**4.7** Where the user has no uv, the app MUST download the uv release it pins for this Mac's
architecture over HTTPS, through the proxy the login shell sets and trusting what macOS trusts, MUST
refuse it unless its checksum is the one pinned, and MUST keep it in its own data directory alone.

**4.8** The app MUST NOT change any shell profile.

**4.9** The app MUST leave no uv and no hmz half written, however it ends.

**4.10** While it installs, the splash MUST show `Installing humanize` where no hmz was there and
`Updating humanize` where it replaces one, with the step -- `Getting uv`, `Getting Python` or
`Installing hmz` -- and the last line uv said.

**4.11** The app MUST NOT replace an hmz while this machine's daemon is running. While it runs, the
app MUST run the hmz there, and MUST install the app's hmz on a later launch once the daemon has
gone.

**4.12** Where the hmz there is too old to serve the app and the daemon is running, the splash MUST
show `Update waiting` with that hmz's version, MUST look again every 2 seconds, MUST install the
app's hmz once the daemon has gone, and MUST offer `Update now`, which installs it at once.

**4.13** Where an install fails, the splash MUST show `Install failed` or `Update failed` with what
uv said, `Retry`, the documentation, and, where an hmz that can serve the app is there, `Continue`,
which runs that hmz.

**4.14** Where `HUMANIZE_HMZ` is set, the app MUST run the hmz it names, MUST look for no other and
MUST install nothing.

**4.15** A development build MUST install nothing, and MUST run the first hmz it finds on `PATH`,
then in `~/.local/bin`, `$UV_TOOL_BIN_DIR`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and
`/bin`.

## 5. Starting `hmz web`

**5.1** The app MUST open its window on the splash at once, drawn in humanize's colours, light or
dark as the system is, and MUST draw the window in the page's background colour before any page is
drawn.

**5.2** The app MUST ask the login shell for its environment once per launch, and MUST use its own
where the shell does not answer within 5 seconds.

**5.3** The app MUST append to `PATH` each of `~/.local/bin`, `$UV_TOOL_BIN_DIR`,
`/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and `/bin` that it lacks.

**5.4** The app MUST start the server as `hmz web --no-open --attached --port <port>` in the user's
home directory, with that environment.

**5.5** The app MUST start the server on the port it had last, and, where that port cannot be
served, MUST start it once more on any free port and keep that port.

**5.6** The app MUST open the window on the address the server prints, within 30 seconds of starting
it, as a top-level page.

**5.7** The app MUST NOT write the key of that address anywhere; its log MUST name the origin alone.

**5.8** The app MUST hold the server's standard input open while it runs, so that the server stops
however the app ends.

**5.9** The app MUST start every process with the signals interrupt, terminate and hangup at their
defaults, whatever the app was started with.

## 6. The splash and errors

**6.1** The splash MUST show the humanize mark and `Starting` while the server starts.

**6.2** Where the server exits before it listens, the splash MUST show `Failed` with what it said on
standard error, and `Retry`.

**6.3** Where the server exits after it listens, the splash MUST show `Stopped` with what it said on
standard error, and `Restart`.

**6.4** Where no hmz is found, the splash MUST show `Not found` with `Retry`.

**6.5** Where the hmz found refuses `web` or `--attached`, the splash MUST show `Outdated` with
`Retry`.

**6.6** Every error the splash shows MUST offer the documentation.

**6.7** The splash MUST NOT ask the user to run a command.

**6.8** Every heading and button of the splash MUST be a word or a short phrase.

## 7. The window

**7.1** The app MUST have one window.

**7.2** The window MUST load nothing but the splash and the origin of the server; every other
address, a new window included, MUST open in the default browser, and only where its scheme is
`http`, `https` or `mailto`.

**7.3** The window MUST have no title bar of its own: the page MUST run to the window's top edge,
with the window controls over its top row.

**7.4** The window MUST be moved by dragging any part of that top row that is not a control, and
MUST zoom on a double click there, on the splash and on the page alike.

**7.5** The app MUST say in its user agent that it is the app, as `humanize-desktop/<version>`, so
that the page draws its top row around the window controls from its first frame.

**7.6** The app MUST tell the page whether the window is full screen.

**7.7** The window's title MUST be the page's title.

**7.8** The app MUST keep the window's size and position from one launch to the next.

**7.9** The app MUST have the menus of a Mac app: the app menu, with `About humanize` and `Check for
Updates…`; `Edit`, with undo, redo, cut, copy, paste and select all; `View`, with `Reload`, `Actual
Size`, `Zoom In`, `Zoom Out` and full screen; `Window`; and `Help`, with the documentation.

**7.10** The menus MUST NOT take a shortcut the page binds: Cmd+K, Cmd+Shift+O and Cmd+. MUST reach
the page.

**7.11** The app MUST NOT give the page any power of the app's but showing a notification, moving
and zooming the window, and learning whether the window is full screen.

**7.12** Closing the window MUST hide it and leave the app and the server running; clicking the Dock
icon, or opening the app again, MUST show it again.

**7.13** Opening the app while it runs MUST bring the running app's window forward, and MUST NOT
start a second app.

## 8. Files

**8.1** The app MUST be the viewer and owner of `.hmzepic` files.

**8.2** A `.hmzepic` file opened with the app -- double clicked, or by `Open With` -- or dropped on
its window MUST be imported by the page as `features/web.md` §6.8 specifies, which opens its
Exomyth.

**8.3** A `.hmzepic` file opened before the server listens MUST be imported once it does.

**8.4** Of several files opened or dropped at once, the app MUST import the last `.hmzepic`, and
MUST ignore every file that is not a `.hmzepic`.

**8.5** A download MUST be saved in `~/Downloads` under the name the page gave it, numbered where
that name is taken, never over another file, and MUST be shown in the Finder once saved.

## 9. Notifications

**9.1** The app MUST show each notification the page hands it as a macOS notification, its title and
body as text.

**9.2** The app MUST ask macOS for leave to notify the first time it notifies.

**9.3** A click on a notification MUST bring the window forward and open the address the
notification carries, only where that address is of the server's own origin.

## 10. Quitting

**10.1** Quitting MUST interrupt every process the app started and has not seen end -- the server,
whether it listens yet or not, an install, and every hmz or uv asked something.

**10.2** Quitting MUST kill each such process that has not stopped within 3 seconds of its
interrupt, so that no process of the app outlives it.

**10.3** Once quitting has begun, the app MUST start no process.

**10.4** Quitting the app MUST NOT stop any epic.

## 11. Updating itself

**11.1** The app MUST look for a newer release 5 seconds after it starts, and every 6 hours after by
the wall clock, whether or not the Mac slept between.

**11.2** The app MUST look only at the latest release's `latest.json`, over HTTPS, and MUST take
only a version newer than its own, and a pre-release only where its own version is one.

**11.3** A development build MUST never look.

**11.4** The app MUST download what it finds in the background, and MUST take it only where it is
signed with the updater's key.

**11.5** The app MUST NOT download an update where it could not install one: run from its disk
image, moved aside by Gatekeeper, or where only an administrator could replace it.

**11.6** Once an update is downloaded, the app MUST ask once, in an alert titled with the new
version: `Restart` MUST install it and start the app again, through a quit that stops the server;
`Later`, or quitting while the alert shows, MUST install it as the app quits.

**11.7** The alert MUST NOT hold up a quit.

**11.8** `Check for Updates…` MUST look at once and say what it found -- the update, that the app is
up to date, or why it could not look -- or, where an update is already downloaded, MUST ask again.

**11.9** A look the app takes by itself MUST tell the user nothing, and MUST write what it found to
the app's log alone.

**11.10** Once an updated app starts, it MUST install its own hmz as §4 specifies.
