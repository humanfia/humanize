# The Humanize Protocol: Desktop Application

## Abstract

This document specifies the Humanize desktop application for macOS and Windows: how it is released,
how it installs and starts hmz, its window, and the files it keeps. The application shows the page
that [WEB] specifies; this document states only what the application adds to it or changes in it.

## Status of This Document

This document is one of the documents of the Humanize Protocol, which Section 2.2.4 of [CORE] lists.
It is normative. It is cited by the tag [DESKTOP].

## Table of Contents

- [1. Introduction](#1-introduction)
- [2. Conventions and Terminology](#2-conventions-and-terminology)
- [3. The Application](#3-the-application)
  - [3.1. Scope](#31-scope)
  - [3.2. Terminology](#32-terminology)
  - [3.3. Releases](#33-releases)
  - [3.4. Installing hmz](#34-installing-hmz)
  - [3.5. Starting `hmz web`](#35-starting-hmz-web)
  - [3.6. The splash and errors](#36-the-splash-and-errors)
  - [3.7. The window](#37-the-window)
  - [3.8. Files](#38-files)
  - [3.9. Notifications](#39-notifications)
  - [3.10. Quitting](#310-quitting)
  - [3.11. Updating itself](#311-updating-itself)
- [4. Files of the Application](#4-files-of-the-application)
  - [4.1. Scope](#41-scope)
  - [4.2. Terminology](#42-terminology)
  - [4.3. The data directory](#43-the-data-directory)
  - [4.4. The log](#44-the-log)
  - [4.5. Other files the app creates](#45-other-files-the-app-creates)
  - [4.6. Installing hmz](#46-installing-hmz)
  - [4.7. Files the app reads](#47-files-the-app-reads)
- [5. Security Considerations](#5-security-considerations)
- [6. References](#6-references)
  - [6.1. Normative References](#61-normative-references)

## 1. Introduction

This document specifies the Humanize desktop application for macOS and Windows: how it is released,
how it installs and starts hmz, its window, and the files it keeps. The application shows the page
that [WEB] specifies; this document states only what the application adds to it or changes in it.

This document is organised as follows:

- Section 3: The Application.
- Section 4: Files of the Application.

## 2. Conventions and Terminology

The key words "MUST", "MUST NOT" and "MAY" in this document are to be interpreted as described in
BCP 14 [RFC2119] [RFC8174] when, and only when, they appear in all capitals, as shown here.

The conventions for numbering and citation, and every term of the shared glossary, are those of
Section 2 of [CORE].

## 3. The Application

### 3.1. Scope

Section 3 specifies the app of hmz for macOS and for Windows: how it is released and installed,
how it installs and starts hmz, what its window shows while it starts and when something goes wrong,
how its window behaves, how it opens exported epics and saves downloads, how it shows notifications,
how it quits, and how it updates itself. The app is a window on the page `hmz web` serves, and draws
nothing of hmz's own but its splash and its errors. On Windows, hmz runs in WSL, while the window,
its notifications and its files are of Windows.

Out of scope:

- The page the window shows: Section 3 of [WEB].
- The command line of `hmz web`: Section 8 of [CLI].
- The files the app keeps, and their locations: Section 4.
- The daemon, and epics outliving the app: Section 3 of [DAEMON].
- `hmz update` and the release check of hmz: Section 13 of [CORE].

### 3.2. Terminology

**3.2.1** The **app** is the application named `Humanize Desktop`, for macOS and for Windows, with
the identifier `ai.humanfia.humanize`.

**3.2.2** The **app's version** is the release of hmz the app was built for.

**3.2.3** The **app's hmz** is hmz of the app's version, installed for the user as a uv tool.

**3.2.4** The **splash** is the app's own page: what the window shows before the page of `hmz web`,
and in its place when `hmz web` cannot be shown.

**3.2.5** A **development build** is a build of the app whose version is `0.0.0`.

**3.2.6** The **server** is the `hmz web` process the app started.

**3.2.7** **WSL** is the default distribution of the Windows Subsystem for Linux of the Windows user
the app runs as: the one `wsl.exe` runs where it is given none.

**3.2.8** The **installer** is the program that installs the app on Windows.

### 3.3. Releases

**3.3.1** Every release of hmz MUST be published with one disk image of the app for Apple silicon
and Intel together, named `humanize-<version>-macos-universal.dmg`, attached to the GitHub release.

**3.3.2** The disk image MUST lay the app out to be dragged into Applications, on a background that
shows how, and, where the app is signed ad hoc, how to open it the first time.

**3.3.3** The disk image MUST be under 15 MB.

**3.3.4** The app MUST be signed with an Apple Developer ID and notarized where the repository holds
one, and MUST be signed ad hoc otherwise.

**3.3.5** Where the repository holds the updater's key, every release MUST also publish the app's
update, `humanize-<version>-macos-universal.app.tar.gz`, signed with that key, and `latest.json`,
which offers it to both architectures. Where the key is not held, the release MUST be published
without them.

**3.3.6** The disk image and the update MUST be attested as built by the release workflow of the
repository.

**3.3.7** The GitHub release MUST NOT carry the wheel or the sdist of hmz, which PyPI carries.

**3.3.8** The app MUST run on macOS 11 or later, on Apple silicon and on Intel.

**3.3.9** The app's version MUST be the release's tag; a pre-release MUST still give macOS a bundle
version of numbers alone.

**3.3.10** Every release of hmz MUST also be published with the installer for Windows on x64, named
`humanize-<version>-windows-x64-setup.exe`, attached to the GitHub release.

**3.3.11** The installer MUST install the app for the Windows user who runs it alone, and MUST NOT
ask for an administrator.

**3.3.12** Where the repository holds the updater's key, every release MUST also publish the
installer's signature with that key, `humanize-<version>-windows-x64-setup.exe.sig`, and its
`latest.json` MUST offer the installer as the update of `windows-x86_64`. Where the key is not held,
the release MUST be published without them.

**3.3.13** The installer MUST be attested as built by the release workflow of the repository.

**3.3.14** The app MUST run on Windows 10 or later, on x64, with WSL of version 2.

**3.3.15** The installer MUST put the app in the Start menu, and MUST put it on the desktop only
where whoever installs it ticks to; an update MUST keep a desktop shortcut that is there and add
none.

**3.3.16** The installer MUST show the Humanize mark as its icon and on each of its pages.

### 3.4. Installing hmz

**3.4.1** A release of the app MUST run the app's hmz and no other hmz; the version `0.5.0-rc.1` of
the app MUST run hmz `0.5.0rc1`.

**3.4.2** The app's hmz MUST be the hmz a terminal finds in `~/.local/bin`; the app MUST ignore any
other hmz on `PATH`.

**3.4.3** The app MUST learn the version of the hmz installed by asking it, and MUST install nothing
where that version is the app's version.

**3.4.4** Where no hmz is installed, or one of another version, older or newer, the app MUST install
the app's hmz, replacing the other and keeping the extras it was installed with.

**3.4.5** After installing, the app MUST check that the hmz installed says the app's version.

**3.4.6** The app MUST use the user's uv where one is found on `PATH`, in `~/.local/bin`,
`~/.cargo/bin` or `/opt/homebrew/bin`.

**3.4.7** On macOS, where the user has no uv, the app MUST download the uv release it pins for this
Mac's architecture over HTTPS, through the proxy the login shell sets and trusting what macOS
trusts, MUST refuse it unless its checksum is the one pinned, and MUST keep it in its own data
directory alone.

**3.4.8** The app MUST NOT change any shell profile.

**3.4.9** The app MUST leave no uv and no hmz half written, however it ends.

**3.4.10** While it installs, the splash MUST show `Installing Humanize CLI` where no hmz was there
and `Updating Humanize CLI` where it replaces one, with the step -- `Getting uv`, `Getting Python`
or `Installing hmz` -- and the last line uv said.

**3.4.11** The app MUST NOT replace an hmz while this machine's daemon is running. While it runs,
the app MUST run the hmz there, and MUST install the app's hmz on a later launch once the daemon has
gone.

**3.4.12** Where the hmz there is too old to serve the app and the daemon is running, the splash
MUST show `Update waiting` with that hmz's version, MUST look again every 2 seconds, MUST install
the app's hmz once the daemon has gone, and MUST offer `Update now`, which installs it at once.

**3.4.13** Where an install fails, the splash MUST show `Install failed` or `Update failed` with
what uv said, `Retry`, the documentation, and, where an hmz that can serve the app is there,
`Continue`, which runs that hmz.

**3.4.14** Where `HUMANIZE_HMZ` is set, the app MUST run the hmz it names, MUST look for no other
and MUST install nothing.

**3.4.15** A development build MUST install nothing, and MUST run the first hmz it finds on `PATH`,
then in `~/.local/bin`, `$UV_TOOL_BIN_DIR`, `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and
`/bin`.

**3.4.16** On Windows, the app MUST run every hmz and uv of Section 3.4 in WSL, through `wsl.exe`,
and MUST read every path Section 3.4 names, the one `HUMANIZE_HMZ` names included, as a path of WSL.

**3.4.17** On Windows, where WSL has no uv, the app MUST download the uv release it pins for Linux
on WSL's architecture over HTTPS, MUST refuse it unless its checksum is the one pinned, and MUST put
it in WSL's `~/.local/bin`.

### 3.5. Starting `hmz web`

**3.5.1** The app MUST open its window on the splash at once, drawn in Humanize's colours, light or
dark as the system is, and MUST draw the window in the page's background colour before any page is
drawn.

**3.5.2** The app MUST ask the login shell for its environment once per launch, and MUST use its own
where the shell does not answer within 5 seconds.

**3.5.3** The app MUST append to `PATH` each of `~/.local/bin`, `$UV_TOOL_BIN_DIR`,
`/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and `/bin` that it lacks.

**3.5.4** The app MUST start the server as `hmz web --no-open --attached --port <port>` in the
user's home directory, with that environment.

**3.5.5** The app MUST start the server on the port it had last, and, where that port cannot be
served, MUST start it once more on any free port and keep that port.

**3.5.6** The app MUST open the window on the address the server prints (Section 4.2.4 of [WEB]),
within 30 seconds of starting it, as a top-level page.

**3.5.7** The app MUST NOT write the key of that address (Section 4.2.3 of [WEB]) anywhere; its log
MUST name the origin alone.

**3.5.8** The app MUST hold the server's standard input open while the app runs.

> Informative: the server stops when its standard input ends (Section 8.2.6 of [CLI]), so it stops however the app ends.

**3.5.9** The app MUST start every process with the signals interrupt, terminate and hangup at their
defaults, whatever the app was started with.

**3.5.10** On Windows, the app MUST ask WSL's login shell for its environment, MUST use the one WSL
gives a process where that shell does not answer within the time of Section 3.5.2, and MUST start
the server and every other process of Section 3.5 in WSL, through `wsl.exe`, from the user's home
directory there, reading every path Section 3.5 names as a path of WSL.

### 3.6. The splash and errors

**3.6.1** The splash MUST show the Humanize mark and `Starting` while the server starts.

**3.6.2** Where the server exits before it listens, the splash MUST show `Failed` with what it said
on standard error, and `Retry`.

**3.6.3** Where the server exits after it listens, the splash MUST show `Stopped` with what it said
on standard error, and `Restart`.

**3.6.4** Where no hmz is found, the splash MUST show `Not found` with `Retry`.

**3.6.5** Where the hmz found refuses `web` or `--attached`, the splash MUST show `Outdated` with
`Retry`.

**3.6.6** Every error the splash shows MUST offer the documentation.

**3.6.7** The splash MUST NOT ask the user to run a command.

**3.6.8** Every heading and button of the splash MUST be a word or a short phrase.

**3.6.9** On Windows, where `wsl.exe` or WSL is missing, the splash MUST show `WSL missing` with
`Retry`.

### 3.7. The window

**3.7.1** The app MUST have one window.

**3.7.2** The window MUST load nothing but the splash and the origin of the server; every other
address, a new window included, MUST open in the default browser, and only where its scheme is
`http`, `https` or `mailto`.

**3.7.3** The window MUST have no title bar of its own: the page MUST run to the window's top edge,
with the window controls over its top row.

**3.7.4** The window MUST be moved by dragging any part of that top row that is not a control, and
MUST zoom on a double click there, on the splash and on the page alike.

**3.7.5** The app MUST say in its user agent that it is the app, as `humanize-desktop/<version>`,
and the page MUST then draw its top row around the window controls from its first frame.

**3.7.6** The app MUST tell the page whether the window is full screen.

**3.7.7** The window's title MUST be the page's title.

**3.7.8** The app MUST keep the window's size and position from one launch to the next.

**3.7.9** On macOS, the app MUST have the menus of a Mac app: the app menu, with `About Humanize
Desktop` and `Check for Updates…`; `Edit`, with undo, redo, cut, copy, paste and select all; `View`,
with `Reload`, `Actual Size`, `Zoom In`, `Zoom Out` and full screen; `Window`; and `Help`, with the
documentation.

**3.7.10** On macOS, the menus MUST NOT take a shortcut the page binds: the shortcuts of Section
3.4.3.1 of [WEB] to Section 3.4.3.3 of [WEB] MUST reach the page.

**3.7.11** The app MUST NOT give the page any power of the app's but showing a notification, moving
and zooming the window, and learning whether the window is full screen.

**3.7.12** Closing the window MUST hide it and leave the app and the server running; clicking the
Dock icon on macOS or the tray icon on Windows, or opening the app again, MUST show it again.

**3.7.13** Opening the app while it runs MUST bring the running app's window forward, and MUST NOT
start a second app.

**3.7.14** On Windows, the window controls MUST be minimize, maximize and close, taking together 138
by 32 pixels at the window's top right, with the snap layouts of Windows on maximize.

**3.7.15** On Windows, the user agent MUST be the one of WebView2 followed by `
humanize-desktop/<version>`.

**3.7.16** On Windows, the app MUST have no menu bar, and the window MUST keep the keys WebView2
gives it to reload and to zoom.

**3.7.17** On Windows, the shortcuts of Section 3.4.3.1 of [WEB] to Section 3.4.3.3 of [WEB] MUST
reach the page.

**3.7.18** On Windows, the app MAY give the page the power to minimize, maximize, restore and close
the window, besides those of Section 3.7.11.

**3.7.19** On Windows, while it runs, the app MUST show a tray icon in the notification area of the
taskbar, whose menu MUST hold `Show Humanize Desktop`, `Check for Updates…`, `Documentation` and
`Quit`.

### 3.8. Files

**3.8.1** The app MUST be the viewer and owner of `.hmzepic` files.

**3.8.2** A `.hmzepic` file opened with the app -- double clicked, or by `Open With` -- or dropped
on its window MUST be imported by the page as Section 3.6.8 of [WEB] specifies.

**3.8.3** A `.hmzepic` file opened before the server listens MUST be imported once it does.

**3.8.4** Of several files opened or dropped at once, the app MUST import the last `.hmzepic`, and
MUST ignore every file that is not a `.hmzepic`.

**3.8.5** A download MUST be saved in the user's Downloads folder -- `~/Downloads` on macOS, the
Downloads folder of Windows on Windows -- under the name the page gave it (Section 4.5.3.4 of
[WEB]), numbered where that name is taken, never over another file, and MUST be shown in the Finder
on macOS or in File Explorer on Windows once saved.

**3.8.6** On Windows, the app MUST hand the page the Windows path of a `.hmzepic` file, unchanged;
Section 3.6.8.1 of [WEB] specifies how that path is read.

### 3.9. Notifications

**3.9.1** The app MUST show each notification the page hands it (Section 3.15.3.1 of [WEB]) as a
macOS notification on macOS and as a Windows toast notification on Windows, its title and body as
text; a toast MUST show the Humanize mark beside them.

**3.9.2** On macOS, the app MUST ask macOS for leave to notify the first time it notifies.

**3.9.3** A click on a notification MUST bring the window forward, and MUST open the address the
notification carries (Section 3.15.3.2 of [WEB]) only where that address is of the server's own
origin.

### 3.10. Quitting

**3.10.1** Quitting MUST interrupt every process the app started and has not seen end -- the server,
whether it listens yet or not, an install, and every hmz or uv asked something.

**3.10.2** Quitting MUST kill each such process that has not stopped within 3 seconds of its
interrupt, so that no process of the app outlives it.

**3.10.3** Once quitting has begun, the app MUST start no process.

**3.10.4** Quitting the app MUST stop no more than stopping `hmz web` stops, as Section 3.3.8 of
[WEB] specifies.

**3.10.5** On Windows, quitting MUST interrupt each process of Section 3.10.1 by closing its
standard input.

**3.10.6** On Windows, `Quit` in the menu of the tray icon MUST quit the app.

### 3.11. Updating itself

**3.11.1** The app MUST look for a newer release 5 seconds after it starts, and every 6 hours after
by the wall clock, whether or not the computer slept between.

**3.11.2** The app MUST look only at the latest release's `latest.json`, over HTTPS, and MUST take
only a version newer than its own, and a pre-release only where its own version is one.

**3.11.3** A development build MUST NOT look for a newer release.

**3.11.4** The app MUST download what it finds in the background, and MUST take it only where it is
signed with the updater's key.

**3.11.5** The app MUST NOT download an update where it could not install one: run from its disk
image, moved aside by Gatekeeper, or where only an administrator could replace it.

**3.11.6** Once an update is downloaded, the app MUST ask once, in an alert titled with the new
version: `Restart` MUST install it and start the app again, through a quit that stops the server;
`Later`, or quitting while the alert shows, MUST install it as the app quits.

**3.11.7** The alert MUST NOT hold up a quit.

**3.11.8** `Check for Updates…` MUST look at once and say what it found -- the update, that the app
is up to date, or why it could not look -- or, where an update is already downloaded, MUST ask
again. While it looks, a small window apart from the one of Section 3.7.1 MUST show that it is
looking, then how far the download is, and `Check for Updates…` MUST be off and read `Checking for
Updates…`; the window MUST close before the app says what it found. Once `Restart` is chosen, the
window MUST show the install until the app starts again.

**3.11.9** A look the app takes by itself MUST tell the user nothing, and MUST write what it found
to the app's log alone.

**3.11.10** Once an updated app starts, it MUST install its own hmz as Section 3.4 specifies.

**3.11.11** On Windows, the app MUST NOT download an update where it does not run from where the
installer put it for the user alone.

**3.11.12** On Windows, the app MUST install an update by running the installer it downloaded,
asking the user nothing.

## 4. Files of the Application

### 4.1. Scope

Section 4 specifies every file and directory the app of **hmz** for macOS and for Windows
creates, reads or leaves on the computer it runs on and, on Windows, in WSL: its data directory, its
log, its window state, its single-instance socket, the installation of `hmz` it makes, the files it
saves for the **user**, and the files of **hmz** it reads.

Out of scope:

- The definitions and rules common to Section 4 to Section 9 of [FILES]: Section 4.2 of [FILES]
  and Section 4.3 of [FILES], and Section 7.2 of [FILES].
- The behaviour of the app: Section 3.
- The files the web **frontend** and the **daemon** the app starts create: Section 7 of [FILES] and
  Section 4 of [FILES].

### 4.2. Terminology

**4.2.1** **App**: the macOS application bundle `Humanize Desktop.app`, whose bundle identifier is
`ai.humanfia.humanize`, or on Windows the program `humanize.exe` of the identifier
`ai.humanfia.humanize`.

**4.2.2** **Data directory**: `~/Library/Application Support/ai.humanfia.humanize/` on macOS, and
`%APPDATA%\ai.humanfia.humanize\` on Windows.

**4.2.3** **Log directory**: `~/Library/Logs/ai.humanfia.humanize/` on macOS, and
`%LOCALAPPDATA%\ai.humanfia.humanize\logs\` on Windows.

**4.2.4** **WSL**: the default distribution of the Windows Subsystem for Linux of the Windows user
the **app** runs as (Section 3.2.7), which is **this machine** of the **app** on Windows.

### 4.3. The data directory

**4.3.1** The **app** MUST create the data directory and every missing parent when it first writes a
file in it.

**4.3.2** `port` in the data directory MUST hold the TCP port the web **frontend** the **app**
started last listened on, as decimal digits without a line feed; the **app** MUST write it only when
that port changes.

**4.3.3** The **app** MUST read a `port` that does not hold a valid port as no port.

**4.3.4** On macOS, `uv/uv` in the data directory MUST be the `uv` executable the **app** downloads
where it finds no `uv` of the **user**, with mode `0755`; the **app** MUST write it into
`uv/.uv.<pid>.new` and rename it into place only after its SHA-256 digest matches the digest the
**app** pins, and MUST remove `uv/.uv.<pid>.new` where that fails.

**4.3.5** `.window-state.json` in the data directory MUST hold the size, position and maximised
state of the window of the **app**, which the **app** restores when it starts.

**4.3.6** The **app** MUST NOT create in the data directory any entry other than those of Section
4.3.

**4.3.7** The **user** MAY delete the data directory while the **app** is not running; the **app**
MUST then start its web **frontend** on any port, download `uv` again on macOS where it needs it,
and open its window at its default size and position.

### 4.4. The log

**4.4.1** `Humanize Desktop.log` in the log directory MUST receive, appended, the log of the **app**
at level info and above: each line the web **frontend** writes to its standard error, each line `uv`
writes while it installs `hmz`, the start, exit and stop of the web **frontend**, the decisions of
the **app** about installing `hmz`, and the results of looking for updates.

**4.4.2** The **app** MUST name the address of the web **frontend** in its log by its origin alone,
and MUST NOT write the key of that address (Section 4.2.3 of [WEB]) into any file.

**4.4.3** The **app** MUST replace `Humanize Desktop.log` with an empty file when it exceeds 40,000
bytes, and MUST NOT keep the replaced content.

**4.4.4** The **user** MAY delete the log directory at any time.

### 4.5. Other files the app creates

**4.5.1** On macOS, the **app** MUST hold, while it runs, the Unix-domain socket
`/tmp/ai_humanfia_humanize_si.sock` through which a second copy of the **app** hands over to the
first.

**4.5.2** The **app** MUST save each file the web **frontend** downloads into the Downloads folder
of the **user** -- `~/Downloads/` on macOS, the Downloads known folder on Windows -- under the name
the page gives it, and where that name is taken, under the name with ` (<n>)` inserted before its
extension, `<n>` the smallest positive integer that makes it free; the **app** MUST NOT overwrite a
file there.

**4.5.3** On macOS, while it installs an update of itself, the **app** MUST use temporary
directories whose names begin with `tauri_current_app` and `tauri_updated_app`, in the temporary
directory or beside the **app**, and MUST remove them when the installation ends.

**4.5.4** On macOS, the **app** MUST NOT download an update of itself to a file.

**4.5.5** The web view of the **app** MAY create the data stores macOS gives a web view of the
bundle identifier `ai.humanfia.humanize`, in which the web **frontend** keeps what it stores in the
browser.

**4.5.6** On Windows, the **app** MUST hand a second copy of itself over to the first through
objects of the Windows session that end with it, and MUST create no file for it.

**4.5.7** On Windows, the installer of the **app** MUST install it, for the **user** alone, into
`%LOCALAPPDATA%\Humanize Desktop\`, and MUST remove that directory when it uninstalls the **app**.

**4.5.8** On Windows, the **app** MAY write the installer of an update of itself into a directory
under the temporary directory of Windows while it installs that update.

**4.5.9** On Windows, the web view of the **app** MAY create the data stores WebView2 keeps for it
under `%LOCALAPPDATA%\ai.humanfia.humanize\`, in which the web **frontend** keeps what it stores in
the browser.

### 4.6. Installing hmz

**4.6.1** The **app** MUST install `hmz` by running `uv tool install --force --python '>=3.12'
--refresh-package hmz hmz[<extras>]==<version>` in `$HOME`, where `<version>` is the version of the
**app** and `<extras>` the extras the installed `hmz` was installed with, read from its
`uv-receipt.toml`.

**4.6.2** The **app** MUST NOT install `hmz` where its version is `0.0.0` or where the environment
variable `HUMANIZE_HMZ` is set.

**4.6.3** The **app** MUST NOT create, modify or remove any shell profile of the **user**.

**4.6.4** The **app** MUST NOT install `hmz` while the process `daemon.json` names in the machine
directory (Section 7.6 of [FILES]) runs.

**4.6.5** The **app** MUST NOT write into the **home**, the machine directory or the cache directory
of **hmz** except through the `hmz` processes it starts.

**4.6.6** On Windows, the **app** MUST install `hmz` in WSL, running every command of Section 4.6
there through `wsl.exe`, with `$HOME` the home directory of the **user** in WSL.

**4.6.7** On Windows, `~/.local/bin/uv` in WSL MUST be the `uv` executable the **app** downloads
where WSL has no `uv`, with mode `0755`; the **app** MUST write it there only after its SHA-256
digest matches the digest the **app** pins, and MUST leave nothing there where that fails.

### 4.7. Files the app reads

**4.7.1** The **app** MUST read `daemon.json` at `${TMPDIR:-<temporary
directory>}/humanize-<uid>/daemon.json` to learn whether the **daemon** runs.

**4.7.2** The **app** MUST open, as their viewer and owner, files with the extension `.hmzepic` and
the media type `application/vnd.hmz.epic+gzip`, declaring the type identifier
`ai.humanfia.humanize.epic`, conforming to `public.data`.

**4.7.3** The **app** MUST NOT modify a `.hmzepic` file it opens.

**4.7.4** On Windows, the **app** MUST read the `daemon.json` of Section 4.7.1 in WSL, with the
temporary directory and the uid of WSL.

**4.7.5** On Windows, the installer of the **app** MUST register the **app**, for the **user**
alone, as the program that opens files with the extension `.hmzepic`.

## 5. Security Considerations

This section summarises the security-relevant properties this document states. It states no
requirement of its own.

What the app downloads, and how it is checked:

- hmz itself is installed by `uv tool install`, which fetches it, as one pinned version, the
  app's version (Section 3.4.1, Section 3.4.4 and Section 4.6.1); the app checks afterwards that
  the hmz installed says that version (Section 3.4.5).
- Where no `uv` is found, the app downloads the `uv` release it pins over HTTPS and refuses it
  unless its SHA-256 digest is the one pinned (Section 3.4.7, Section 3.4.17, Section 4.3.4 and
  Section 4.6.7). It leaves no `uv` and no hmz half written (Section 3.4.9).
- The app reads only the latest release's `latest.json`, over HTTPS, and takes an update of itself
  only where it is newer and signed with the updater's key (Section 3.11.2 and Section 3.11.4).
  Releases without that key carry no update (Section 3.3.5 and Section 3.3.12). Release artefacts
  are attested as built by the release workflow (Section 3.3.6 and Section 3.3.13), and the macOS
  app is notarized only where a Developer ID is held, and signed ad hoc otherwise (Section 3.3.4).

What the app runs:

- The app runs `hmz`, `uv`, the login shell and, on Windows, `wsl.exe` and the installer of an
  update (Section 3.4, Section 3.5, Section 3.11.12 and Section 4.6). The hmz it runs is the one
  in `~/.local/bin`, never another on `PATH` (Section 3.4.2), except where `HUMANIZE_HMZ` names one
  or the build is a development build (Section 3.4.14 and Section 3.4.15): whoever sets that
  variable, or the `PATH` of a development build, chooses the program run.
- The environment of the server is that of the user's login shell (Section 3.5.2 and Section
  3.5.10). No process of the app outlives it (Section 3.5.8 and Section 3.10).
- Neither the app nor its installer asks for an administrator, and both install for one user alone
  (Section 3.3.11, Section 3.11.5, Section 3.11.11 and Section 4.5.7). The app changes no shell
  profile (Section 3.4.8 and Section 4.6.3) and writes hmz's own directories only through hmz
  (Section 4.6.5).

What the window shows and may do:

- The window loads only the splash and the origin of the server; every other address opens in the
  default browser, and only with the scheme `http`, `https` or `mailto` (Section 3.7.2). A click
  on a notification opens only an address of the server's origin (Section 3.9.3).
- The page holds no power of the app but those of Section 3.7.11 and Section 3.7.18.
- The key that admits a browser to the server (Section 4.4 of [WEB]) is written to no file, and the
  log names the server by its origin alone (Section 3.5.7 and Section 4.4.2). The log does hold
  what the server and `uv` write to standard error (Section 4.4.1).
- A download never overwrites a file (Section 3.8.5 and Section 4.5.2), and an opened `.hmzepic`
  is never modified (Section 4.7.3); importing one is subject to Section 3.6.8 of [WEB].

Fixed, predictable paths the app relies on are the single-instance socket
`/tmp/ai_humanfia_humanize_si.sock` on macOS (Section 4.5.1) and `daemon.json` under the temporary
directory (Section 4.7.1).

## 6. References

### 6.1. Normative References

- **[RFC2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", BCP 14, RFC
  2119, March 1997, <https://www.rfc-editor.org/info/rfc2119>.
- **[RFC8174]** Leiba, B., "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", BCP 14, RFC
  8174, May 2017, <https://www.rfc-editor.org/info/rfc8174>.
- **[CORE]** "The Humanize Protocol: Core Concepts and Functional Behaviour", [`core.md`](core.md).
- **[CLI]** "The Humanize Protocol: Command-Line Interface", [`cli.md`](cli.md).
- **[DAEMON]** "The Humanize Protocol: Daemon", [`daemon.md`](daemon.md).
- **[WEB]** "The Humanize Protocol: Web Interface", [`web.md`](web.md).
- **[FILES]** "The Humanize Protocol: Settings, Environment Variables and Files", [`files.md`](files.md).
