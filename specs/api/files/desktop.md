# Desktop App Files

## 1. Scope

This document specifies every file and directory the app of **hmz** for macOS and for Windows
creates, reads or leaves on the computer it runs on and, on Windows, in WSL: its data directory,
its log, its window state, its single-instance socket, the installation of `hmz` it makes, the
files it saves for the **user**, and the files of **hmz** it reads.

Out of scope:

- The definitions and rules common to `api/files/`: `api/files/home.md` §2 and §3, and
  `api/files/machine.md` §2.
- The behaviour of the app: `features/desktop.md`.
- The files the web **frontend** and the **daemon** the app starts create:
  `api/files/machine.md` and `api/files/home.md`.

## 2. Definitions

**2.1** **App**: the macOS application bundle `Humanize Desktop.app`, whose bundle identifier is
`ai.humanfia.humanize`, or on Windows the program `humanize.exe` of the identifier
`ai.humanfia.humanize`.

**2.2** **Data directory**: `~/Library/Application Support/ai.humanfia.humanize/` on macOS, and
`%APPDATA%\ai.humanfia.humanize\` on Windows.

**2.3** **Log directory**: `~/Library/Logs/ai.humanfia.humanize/` on macOS, and
`%LOCALAPPDATA%\ai.humanfia.humanize\logs\` on Windows.

**2.4** **WSL**: the default distribution of the Windows Subsystem for Linux of the Windows user
the **app** runs as (`features/desktop.md` §2.7), which is **this machine** of the **app** on
Windows.

## 3. The data directory

**3.1** The **app** MUST create the data directory and every missing parent when it first writes
a file in it.

**3.2** `port` in the data directory MUST hold the TCP port the web **frontend** the **app**
started last listened on, as decimal digits without a line feed; the **app** MUST write it only
when that port changes.

**3.3** The **app** MUST read a `port` that does not hold a valid port as no port.

**3.4** On macOS, `uv/uv` in the data directory MUST be the `uv` executable the **app** downloads
where it finds no `uv` of the **user**, with mode `0755`; the **app** MUST write it into
`uv/.uv.<pid>.new` and rename it into place only after its SHA-256 digest matches the digest the
**app** pins, and MUST remove `uv/.uv.<pid>.new` where that fails.

**3.5** `.window-state.json` in the data directory MUST hold the size, position and maximised
state of the window of the **app**, which the **app** restores when it starts.

**3.6** The **app** MUST NOT create in the data directory any entry other than those of §3.

**3.7** The **user** MAY delete the data directory while the **app** is not running; the **app**
then starts its web **frontend** on any port, downloads `uv` again on macOS where it needs it, and
opens its window at its default size and position.

## 4. The log

**4.1** `Humanize Desktop.log` in the log directory MUST receive, appended, the log of the **app** at
level info and above: each line the web **frontend** writes to its standard error, each line
`uv` writes while it installs `hmz`, the start, exit and stop of the web **frontend**, the
decisions of the **app** about installing `hmz`, and the results of looking for updates.

**4.2** The **app** MUST name the address of the web **frontend** in its log by its origin alone,
and MUST NOT write the access key of that address into any file.

**4.3** The **app** MUST replace `Humanize Desktop.log` with an empty file when it exceeds 40,000 bytes,
and MUST NOT keep the replaced content.

**4.4** The **user** MAY delete the log directory at any time.

## 5. Other files the app creates

**5.1** On macOS, the **app** MUST hold, while it runs, the Unix-domain socket
`/tmp/ai_humanfia_humanize_si.sock` through which a second copy of the **app** hands over to
the first.

**5.2** The **app** MUST save each file the web **frontend** downloads into the Downloads folder of
the **user** -- `~/Downloads/` on macOS, the Downloads known folder on Windows -- under the name
the page gives it, and where that name is taken, under the name with ` (<n>)` inserted
before its extension, `<n>` the smallest positive integer that makes it free; the **app** MUST
NOT overwrite a file there.

**5.3** On macOS, while it installs an update of itself, the **app** MUST use temporary
directories whose names begin with `tauri_current_app` and `tauri_updated_app`, in the temporary
directory or beside the **app**, and MUST remove them when the installation ends.

**5.4** On macOS, the **app** MUST NOT download an update to a file; it MUST hold a downloaded
update in memory until it installs it.

**5.5** The web view of the **app** MAY create the data stores macOS gives a web view of the
bundle identifier `ai.humanfia.humanize`, in which the web **frontend** keeps what it stores in
the browser.

**5.6** On Windows, the **app** MUST hand a second copy of itself over to the first through objects
of the Windows session that end with it, and MUST create no file for it.

**5.7** On Windows, the installer of the **app** MUST install it, for the **user** alone, into
`%LOCALAPPDATA%\Humanize Desktop\`, and MUST remove that directory when it uninstalls the **app**.

**5.8** On Windows, the **app** MAY write the installer of an update of itself into a directory
under the temporary directory of Windows while it installs that update.

**5.9** On Windows, the web view of the **app** MAY create the data stores WebView2 keeps for it
under `%LOCALAPPDATA%\ai.humanfia.humanize\`, in which the web **frontend** keeps what it stores
in the browser.

## 6. Installing hmz

**6.1** The **app** MUST install `hmz` by running
`uv tool install --force --python '>=3.12' --refresh-package hmz hmz[<extras>]==<version>` in
`$HOME`, where `<version>` is the version of the **app** and `<extras>` the extras the
installed `hmz` was installed with, read from its `uv-receipt.toml`.

**6.2** The **app** MUST NOT install `hmz` where its version is `0.0.0` or where the environment
variable `HUMANIZE_HMZ` is set.

**6.3** The **app** MUST NOT create, modify or remove any shell profile of the **user**.

**6.4** The **app** MUST NOT install `hmz` while the process `daemon.json` names in the machine
directory (`api/files/machine.md` §6) runs.

**6.5** The **app** MUST NOT write into the **home**, the machine directory or the cache
directory of **hmz** except through the `hmz` processes it starts.

**6.6** On Windows, the **app** MUST install `hmz` in WSL, running every command of §6 there
through `wsl.exe`, with `$HOME` the home directory of the **user** in WSL.

**6.7** On Windows, `~/.local/bin/uv` in WSL MUST be the `uv` executable the **app** downloads
where WSL has no `uv`, with mode `0755`; the **app** MUST write it there only after its SHA-256
digest matches the digest the **app** pins, and MUST leave nothing there where that fails.

## 7. Files the app reads

**7.1** The **app** MUST read `daemon.json` at
`${TMPDIR:-<temporary directory>}/humanize-<uid>/daemon.json` to learn whether the **daemon**
runs.

**7.2** The **app** MUST open, as their viewer and owner, files with the extension `.hmzepic` and
the media type `application/vnd.hmz.epic+gzip`, declaring the type identifier
`ai.humanfia.humanize.epic`, conforming to `public.data`.

**7.3** The **app** MUST NOT modify a `.hmzepic` file it opens.

**7.4** On Windows, the **app** MUST read the `daemon.json` of §7.1 in WSL, with the temporary
directory and the uid of WSL.

**7.5** On Windows, the installer of the **app** MUST register the **app**, for the **user** alone,
as the program that opens files with the extension `.hmzepic`.
