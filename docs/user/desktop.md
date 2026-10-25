# Humanize Desktop

Humanize Desktop is [`hmz web`](/user/web) in a window of its own, on macOS and on Windows: the
same page, every epic on this machine, with no terminal to keep open and no browser tab to
find. It starts `hmz web` when it opens and stops it when you quit.

To install it, see [Installation](/user/installation#desktop).

::: info At a glance
- **You will** know what the app does for you, how it keeps itself and `hmz` up to date, and
  what to do when it does not start.
- **Use it when** you would rather open an app than run `hmz web` and keep its terminal.
- **You need** macOS 11 or newer (Apple silicon or Intel), or Windows 10 or 11 on x64 with
  WSL 2.
:::

## How it works

The app is a window, not a second Humanize. It runs `hmz web --no-open --attached` and shows
the page it serves.

- **It installs `hmz` for you, at its own version.** Humanize Desktop 0.5.0 runs Humanize CLI
  0.5.0, since both come from the same release. Where there is none, or one of another version,
  it runs `uv tool install --force hmz==<its version>`, keeping any extras you installed with, and
  says **Installing Humanize CLI** or **Updating Humanize CLI** while it does. That is the same
  `~/.local/bin/hmz` a terminal finds, so the `hmz` you type is the app's version too; another
  `hmz` on your `PATH`, from pipx or pip, is left alone and not used.
- **It brings uv only where you have none.** It uses yours -- on your `PATH`, or in
  `~/.local/bin`, `~/.cargo/bin` or `/opt/homebrew/bin` -- and otherwise downloads uv, checked
  against a checksum it carries. uv gets Python where it needs to. Your shell profile is never
  touched.
- **It never updates under running epics.** While epics are running, the `hmz` there keeps
  running them and the app opens it as it is; it updates on a later launch, once they have
  ended. See [`Update waiting`](#update-waiting).
- **It starts in your home directory**, with the environment your login shell gives you, so
  `hmz` and the coding agent CLIs are found as a terminal finds them, and your home is the
  directory a new epic is offered first. Pick **No workspace** for an epic that should work in
  a new directory of its own, in the temporary directory, rather than in one of yours.
- **It keeps its port.** `hmz web` listens on the port it had last time, so the page opens as
  you left it, in the [theme](/user/web#themes) you chose. A theme made in a browser is brought
  into the app by exporting it there and importing it here.
- **Closing the window is not quitting.** On macOS the app stays in the Dock; on Windows, in
  the tray. `hmz web` keeps serving, and clicking the icon brings the window back. Quitting --
  <kbd>cmd+q</kbd> on macOS, **Quit** in the tray icon's menu on Windows -- stops `hmz web` too.
- **Your epics outlive it**, as they outlive `hmz web`: quitting the app leaves an epic going.
  See [Leaving it running](/user/leaving), and on Windows,
  [Your epics and WSL](#your-epics-and-wsl).
- **The page is the whole window**, up to its top edge. Drag the window by any empty part of
  the top row, and double-click it to zoom or maximize.
- **Links to elsewhere open in your browser**, and an export is saved to **Downloads** and shown
  in the Finder or Explorer.
- **Other machines too.** The [daemons](/user/web#daemons) the page reaches -- your ssh hosts
  -- are reached from the app as from a browser, with your ssh config, and switched between at
  the foot of the sidebar.

## On Windows: WSL {#windows}

Humanize needs Linux or macOS, so on Windows `hmz` runs in
[WSL](https://learn.microsoft.com/windows/wsl/), in your default distribution. That
distribution is **Local**: your epics, your repositories, uv, `hmz` and the coding agent CLIs
all live there. The window, the tray icon, notifications and downloads stay on Windows. The app
runs `hmz web` through `wsl.exe`, and Windows reaches its page on `127.0.0.1` by WSL's
localhost forwarding.

- **Local is your WSL distribution.** The sidebar and **Settings → Daemons** name Local's host
  as `<distro> (WSL)`, `Ubuntu (WSL)` say.
- **Coding agent CLIs go in WSL.** The app finds what a login shell in WSL finds; a CLI
  installed on Windows is not seen.
- **Keep your repositories in WSL**, under your Linux home -- `~/src/project`, not
  `/mnt/c/Users/you/project`. Files on a Windows drive are reached from WSL through a slow
  share, and locks and permissions there do not behave as Linux's do, which Humanize relies on.
  From Windows, Explorer reaches your WSL files under **Linux** in its sidebar, or at
  `\\wsl.localhost\<distro>`.

### Your epics and WSL {#your-epics-and-wsl}

An epic is held in WSL, not by the app, so quitting the app leaves it going -- but only while
WSL keeps your distribution running. While the app is open, its `hmz web` keeps the
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
in the Finder or Explorer, choose **Open With → Humanize Desktop**, or, on macOS, drop one on
the window: the app imports it, as **Import** on the page does, and opens it on its
[Exomyth](/user/web#exomyth). Opened while the app is still starting, it is imported once the
page is there. Of several opened or dropped at once, the last is imported; anything but a
`.hmzepic` is left alone. On Windows, a file on a Windows drive, or one in WSL reached as
`\\wsl.localhost\<distro>\…`, is found in WSL at the path it has there.

One you already have is refused, with **Open** to go to it; one that cannot be picked up on this
machine says why on its own page, as any [imported epic](/user/web#importing-an-epic) does.

## Notifications {#notifications}

The page's [notifications](/user/web#notifications) -- an epic done, failed or stopped, a question
for you, a `chat` waiting for your next line, on any daemon -- show in the window's bell and toasts
as in a browser, and, while the window is hidden or not in front, as system notifications from
Humanize Desktop. Click one: the window comes to the front, on the epic it is about.

The kinds that appear are set in **Settings → Notifications**; the app needs no permission asked
there, as a browser does. On macOS, the first one asks whether Humanize Desktop may send them:
choose **Allow**. After that, the system's own settings decide how they are shown, or silence
them: **System Settings → Notifications → Humanize Desktop** on macOS, **Settings → System →
Notifications → Humanize Desktop** on Windows.

## Updates {#updates}

The app looks for a new release a few seconds after it opens, and every 6 hours after. It
downloads one in the background, checks that it was signed by Humanize's release, and then asks
once, naming the version:

- **Restart** installs it, and opens Humanize Desktop again on it, `hmz web` stopped and started
  with it.
- **Later** leaves it until you quit Humanize Desktop, which installs it then.

To look now, choose **Check for Updates…** -- from the **Humanize Desktop** menu on macOS, from
the tray icon's menu on Windows. A small window shows it looking, then how far the download is.
Then it offers the new release, or says Humanize Desktop is up to date, or why it could not
look. Only releases are offered, never a pre-release, unless the app you run is a pre-release
itself: then the newest release or pre-release is.

Once the new app opens, it updates `hmz` to its own version too, as it would at any launch: at
once where no epics are running, and otherwise once they have ended.

## Troubleshooting {#troubleshooting}

### `Install failed` or `Update failed`

uv could not install `hmz`: most often you are offline, or a proxy is in the way. The window
shows what uv said; press **Retry** once you are connected. Where an `hmz` of another version is
already installed and can serve the app, **Continue** opens it as it is, and the app tries again
next time. uv takes the proxy and index your login shell sets (`HTTPS_PROXY`, `UV_INDEX_URL`) --
on Windows, your WSL login shell.

### `Update waiting` {#update-waiting}

Epics are running in an `hmz` too old for the app to open, and updating it now could stop them.
The app waits, and updates as soon as they have ended. **Update now** updates at once, if you
would rather not wait.

### `WSL missing`

Windows only. Windows has no WSL, or WSL has no distribution. Run `wsl --install` in PowerShell,
restart if it asks, open the distribution once to make your Linux user, then **Retry**.
`wsl --list --verbose` shows what you have; the app uses the default one, marked `*`.

### The window stays on its mark, or says the page cannot be reached

Windows only. `hmz web` is serving in WSL, but Windows cannot reach it on `127.0.0.1`. WSL
forwards localhost unless `%UserProfile%\.wslconfig` turns it off: remove
`localhostForwarding=false` from its `[wsl2]` section, or use mirrored networking, where WSL and
Windows share `127.0.0.1`:

```ini
[wsl2]
networkingMode=mirrored
```

Then run `wsl --shutdown` and open the app again.

### `Failed` or `Stopped`

`hmz web` exited, and the window shows what it said. **Retry** or **Restart** starts it again.
The app's log has the rest:

::: code-group

```sh [macOS]
open ~/Library/Logs/ai.humanfia.humanize/"Humanize Desktop.log"
```

```powershell [Windows]
notepad "$env:LOCALAPPDATA\ai.humanfia.humanize\logs\Humanize Desktop.log"
```

:::

`hmz: the runs … are held by an older Humanize` is the most common: an older `hmz` holds them.
See [`hmz web`'s troubleshooting](/user/web#troubleshooting).

### My epics stopped after I quit the app

Windows only. WSL shut the distribution down: see [Your epics and WSL](#your-epics-and-wsl).

### No system notifications

They come only while the window is hidden or not in front. Check that **Settings →
Notifications** in the app has them switched on, and that the system's notification settings
allow Humanize Desktop.

### The window opened on a page that forgot what I chose

The page keeps your choices per port, and the port it had was taken by something else this
time, so it took another. It keeps the new one from then on.

### Using an `hmz` of your own

To have the app run another `hmz` -- a checkout you are working on, say -- name it in
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

- **macOS:** move it from Applications to the Trash. To forget what it kept as well -- its port
  and window, what the page remembers, and its log:

  ```sh
  rm -rf ~/Library/{Application\ Support,WebKit,Caches,Logs}/ai.humanfia.humanize
  ```

- **Windows:** remove it in **Settings → Apps → Installed apps**. Its own data is in
  `%APPDATA%\ai.humanfia.humanize` and `%LOCALAPPDATA%\ai.humanfia.humanize`; delete both to
  forget it.

`hmz`, and your epics, stay as they are; `uv tool uninstall hmz` -- in WSL, on Windows -- removes
`hmz` too.

## Next steps

- [In a browser (`hmz web`)](/user/web): the page itself, and what it refuses.
- [Leaving it running](/user/leaving): what goes on after the window closes.
- [Installation](/user/installation): the app, `hmz`, and the coding agent CLIs it drives.
