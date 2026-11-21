# Humanize Desktop

Humanize Desktop is the page of [`hmz web`](/user/web) in a window of its own, on macOS and on
Windows: the same page, every epic of every daemon you reach, with no terminal to keep open and
no browser tab to find. The page is built into the app, and the app serves it itself: no
`hmz web` runs.

To install it, see [Installation](/user/installation#desktop).

::: info At a glance
- **You will** know what the app does for you, how it reaches your daemons, how it keeps itself
  and `hmz` up to date, and what to do when it does not start.
- **Use it when** you would rather open an app than run `hmz web` and keep its terminal.
- **You need** macOS 11 or newer (Apple silicon or Intel), with `hmz`
  [installed](/user/installation#cli); or Windows 10 or 11 on x64 with WSL 2.
:::

## How it works

The app is a window, not a second Humanize. It holds no epic: every epic is held by a
[daemon](/user/leaving), and the page in the window speaks to each daemon it shows, as the page
in a browser does.

- **The page comes with the app.** It is the page of the same release, and the app shows it at
  once; nothing is started to serve it.
- **Local is this machine's daemon.** On macOS, the app reaches it by running
  `hmz daemon connect --stdio` -- the `hmz` your login shell finds, `~/.local/bin` included --
  which starts the daemon where it is not running. Where there is no `hmz`, the page still opens,
  and says Local cannot be reached until you [install it](/user/installation#cli). On Windows,
  Local is the daemon in WSL, and the app installs `hmz` there: see [On Windows](#windows).
- **Other machines too.** The [daemons](/user/web#daemons) the page reaches -- your ssh hosts
  and EasyTier daemons -- are reached from the app itself: ssh with your ssh config, WSL's
  [on Windows](#windows), and every route but ssh and Local inside mutual TLS, as the app's own
  device, paired as a browser is.
- **It uses your login shell's environment**, so `hmz` and the coding agent CLIs are found as a
  terminal finds them.
- **Closing the window is not quitting.** On macOS the app stays in the Dock; on Windows, in
  the tray. Clicking the icon brings the window back. Quitting -- <kbd>cmd+q</kbd> on macOS,
  **Quit** in the tray icon's menu on Windows -- closes the app's connections to its daemons.
- **Your epics outlive it**: they are held by the daemons, so quitting the app leaves an epic
  going. See [Leaving it running](/user/leaving), and on Windows,
  [Your epics and WSL](#your-epics-and-wsl).
- **The page is the whole window**, up to its top edge. On macOS the traffic lights stand in
  the page's top row, which is one row across the sidebar and the view. Drag the window by any
  empty part of the top row, and double-click it to zoom or maximize -- also while Settings,
  another dialog or a drawer is open over the page: a dialog stands under that row, never over
  it, so the whole row still moves the window.
- **Ai-chan is in the window too**: her avatar, at the right of every view's bar, opens the
  [drawer](/user/web#ai-chan) of your conversations with [Ai-chan](/user/ai-chan).
- **Links to elsewhere open in your browser**, and an export is saved to **Downloads** and shown
  in the Finder or Explorer.

## On Windows: WSL {#windows}

Humanize needs Linux or macOS, so on Windows `hmz` runs in
[WSL](https://learn.microsoft.com/windows/wsl/), in your default distribution. That
distribution is **Local**: your epics, your repositories, uv, `hmz` and the coding agent CLIs
all live there. The window, the tray icon, notifications and downloads stay on Windows. The app
reaches Local by running `hmz daemon connect --stdio` through `wsl.exe`.

- **It installs `hmz` in WSL for you, at its own version.** Humanize Desktop 0.5.0 runs Humanize
  CLI 0.5.0, since both come from the same release. Where there is none, or one of another
  version, it runs `uv tool install --force hmz==<its version>` in WSL, keeping any extras you
  installed with, and says **Installing Humanize CLI** or **Updating Humanize CLI** while it does.
  That is the same `~/.local/bin/hmz` a terminal in WSL finds, so the `hmz` you type there is the
  app's version too.
- **It brings uv only where you have none.** It uses WSL's -- on your `PATH`, or in
  `~/.local/bin` or `~/.cargo/bin` -- and otherwise downloads uv into `~/.local/bin`, checked
  against a checksum it carries. uv gets Python where it needs to. Your shell profile is never
  touched.
- **It never updates under running epics.** While WSL's daemon runs, the `hmz` there keeps
  running it, and the app updates it on a later launch, once the daemon has gone. See
  [`Update waiting`](#update-waiting).
- **Local is your WSL distribution.** The sidebar and **Settings → Daemons** name Local's host
  as `<distro> (WSL)`, `Ubuntu (WSL)` say.
- **Coding agent CLIs go in WSL.** The daemon finds what a login shell in WSL finds; a CLI
  installed on Windows is not seen.
- **Your ssh hosts are WSL's.** The hosts **New daemon** offers are those of `~/.ssh/config` in
  WSL, and the app reaches an [SSH daemon](/user/web#daemons) with WSL's `ssh`, run through
  `wsl.exe`: its config, its keys and its `known_hosts`, as `ssh <host>` in a WSL terminal
  uses them. An identity file is a path in WSL. What Windows' own `ssh` has in
  `%UserProfile%\.ssh` is not read. That `ssh` asks for no passphrase and is not started by
  your login shell, so an ssh agent your shell's startup files set is not seen: name its
  socket with `IdentityAgent` in `~/.ssh/config`, or use a key without a passphrase.
- **Keep your repositories in WSL**, under your Linux home -- `~/src/project`, not
  `/mnt/c/Users/you/project`. Files on a Windows drive are reached from WSL through a slow
  share, and locks and permissions there do not behave as Linux's do, which Humanize relies on.
  From Windows, Explorer reaches your WSL files under **Linux** in its sidebar, or at
  `\\wsl.localhost\<distro>`.

On macOS the app installs nothing: install `hmz` as [Installation](/user/installation#cli) says,
and update it with `uv tool upgrade hmz`.

### Your epics and WSL {#your-epics-and-wsl}

An epic is held in WSL, not by the app, so quitting the app leaves it going -- but only while
WSL keeps your distribution running. While the app is open, its connection to Local keeps the
distribution running. Once you quit, WSL may shut the distribution down when it is idle, and
whatever runs there stops with it, your epics included. `wsl --shutdown`, or a restart of
Windows, stops them too.

How long WSL waits is `instanceIdleTimeout`, in the `[general]` section of
`%UserProfile%\.wslconfig`: 15000 milliseconds by default, and `-1` turns the shutdown off. To
leave epics running after you quit the app:

```ini
[general]
instanceIdleTimeout=-1
```

Then, with nothing running in WSL, run `wsl --shutdown` once so that WSL reads the file again.
Microsoft's [WSL configuration](https://learn.microsoft.com/windows/wsl/wsl-config) has the
rest. Otherwise, keep the app open, minimized or in the tray, while epics run.

## Opening a `.hmzepic` {#opening-a-hmzepic}

The app is what a `.hmzepic` -- an [exported epic](/user/export) -- opens with. Double-click one
in the Finder or Explorer, choose **Open With → Humanize Desktop**, or drop one on the window:
the page reads it from the app and imports it into the daemon it shows, as **Import** on the
page does, and opens it on its [Exomyth](/user/web#exomyth). Opened while the app is still
starting, it is imported once the page is there. Of several opened or dropped at once, the last
is imported; anything but a `.hmzepic` is left alone. The page can read only a file you opened
with the app this way.

One you already have is refused, with **Open** to go to it; one that cannot be picked up on this
machine says why on its own page, as any [imported epic](/user/web#importing-an-epic) does.

## Notifications {#notifications}

The page's [notifications](/user/web#notifications) -- an epic done, failed or stopped, a question
for you, a [chat](/user/chat) waiting for your next line, on any daemon -- show as system
notifications from Humanize Desktop, unless the window is in front and on that chat or epic.
Click one: the window comes to the front, on the epic or chat it is about.

The kinds that appear are set in **Settings → Notifications**; the app needs no permission asked
there, as a browser does. On macOS, the first one asks whether Humanize Desktop may send them:
choose **Allow**. After that, the system's own settings decide how they are shown, or silence
them: **System Settings → Notifications → Humanize Desktop** on macOS, **Settings → System →
Notifications → Humanize Desktop** on Windows.

## Updates {#updates}

The app looks for a new release a few seconds after it opens, and every 6 hours after. It
downloads one in the background, checks that it was signed by Humanize's release, and then asks
once, naming the version:

- **Restart** installs it, and opens Humanize Desktop again on it.
- **Later** leaves it until you quit Humanize Desktop, which installs it then.

To look now, choose **Check for Updates…** -- from the **Humanize** menu on macOS, from
the tray icon's menu on Windows. (The app's own menus and these windows are in English, whatever
[language](/user/web#language) the page is written in.) A small window shows it looking, then how far the download is.
Then it offers the new release, or says Humanize Desktop is up to date, or why it could not
look. Only releases are offered, never a pre-release, unless the app you run is a pre-release
itself: then the newest release or pre-release is.

On Windows, once the new app opens, it updates `hmz` in WSL to its own version too, as it would
at any launch: at once where WSL's daemon is not running, and otherwise once it has gone.

## Troubleshooting {#troubleshooting}

### Local cannot be reached

The page opened, but says Local cannot be reached. On macOS, `hmz` is not installed, or not where
your login shell finds it: [install it](/user/installation#cli), then reconnect from **Settings →
Daemons**. Either way, the app's log has what `hmz daemon connect` said:

::: code-group

```sh [macOS]
open ~/Library/Logs/ai.humanfia.humanize/"Humanize Desktop.log"
```

```powershell [Windows]
notepad "$env:LOCALAPPDATA\ai.humanfia.humanize\logs\Humanize Desktop.log"
```

:::

### `Install failed` or `Update failed`

Windows only. uv could not install `hmz` in WSL: most often you are offline, or a proxy is in
the way. The window shows what uv said; press **Retry** once you are connected. Where an `hmz`
of another version is already installed and can serve the app, **Continue** opens the page with
it as it is, and the app tries again next time. uv takes the proxy and index your WSL login
shell sets (`HTTPS_PROXY`, `UV_INDEX_URL`).

### `Update waiting` {#update-waiting}

Windows only. Epics are running in an `hmz` too old for the app to use, and updating it now
could stop them. The app waits, and updates as soon as WSL's daemon has gone. **Update now**
updates at once, if you would rather not wait.

### `WSL missing`

Windows only. Windows has no WSL, or WSL has no distribution. Run `wsl --install` in PowerShell,
restart if it asks, open the distribution once to make your Linux user, then **Retry**.
`wsl --list --verbose` shows what you have; the app uses the default one, marked `*`.

### My epics stopped after I quit the app

Windows only. WSL shut the distribution down: see [Your epics and WSL](#your-epics-and-wsl).

### No system notifications

None comes of the chat or epic the window is in front on. Check that **Settings →
Notifications** in the app has them switched on, and that the system's notification settings
allow Humanize Desktop.

### Using an `hmz` of your own

To have the app run another `hmz` for Local -- a checkout you are working on, say -- name it in
`HUMANIZE_HMZ` and open the app from that shell. It then installs nothing. On Windows it is a
path in WSL, set in Windows:

::: code-group

```sh [macOS]
HUMANIZE_HMZ=~/src/humanize/.venv/bin/hmz "/Applications/Humanize Desktop.app/Contents/MacOS/humanize"
```

```powershell [Windows]
$env:HUMANIZE_HMZ = '/home/you/src/humanize/.venv/bin/hmz'
& "$env:LOCALAPPDATA\Humanize Desktop\humanize.exe"
```

:::

## Uninstall

Quit Humanize Desktop first.

- **macOS:** move it from Applications to the Trash. To forget what it kept as well -- its
  device identity and window, what the page remembers, and its log:

  ```sh
  rm -rf ~/Library/{Application\ Support,WebKit,Caches,Logs}/ai.humanfia.humanize
  ```

- **Windows:** remove it in **Settings → Apps → Installed apps**. Its own data is in
  `%APPDATA%\ai.humanfia.humanize` and `%LOCALAPPDATA%\ai.humanfia.humanize`; delete both to
  forget it.

Forgetting its device identity means pairing the app again with every daemon it reached
inside mutual TLS. `hmz`, and your epics, stay as they are; `uv tool uninstall hmz` -- in WSL,
on Windows -- removes `hmz` too.

## Next steps

- [In a browser (`hmz web`)](/user/web): the page itself, and what it refuses.
- [Leaving it running](/user/leaving): what goes on after the window closes.
- [Installation](/user/installation): the app, `hmz`, and the coding agent CLIs it drives.
