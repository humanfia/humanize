# The Windows app

Humanize Desktop on Windows is [`hmz web`](/user/web) in a window of its own, as
[on a Mac](/user/desktop). The difference is where `hmz` runs. Humanize needs Linux or macOS,
so on Windows `hmz` runs in [WSL](https://learn.microsoft.com/windows/wsl/), in your default
distribution. That distribution is **Local**: your epics, your repositories, uv, `hmz` and the
coding agent CLIs all live there. The window, the tray icon, notifications and downloads stay
on Windows.

::: info At a glance
- **You will** have Humanize Desktop in your Start menu and tray, opening on every epic in your WSL
  distribution.
- **Use it when** you work on Windows and would rather open an app than run `hmz web` in WSL
  and keep its terminal.
- **You need** Windows 10 or 11 on x64, with WSL 2 and a default distribution, a coding agent
  CLI installed and signed in inside that distribution, and a connection the first time: the
  app installs `hmz` itself.
:::

## Before you start

1. Install WSL, if you have not. In PowerShell:

   ```powershell
   wsl --install
   ```

   This installs WSL 2 and Ubuntu; restart when it asks, and make your Linux user. Any
   distribution will do, as long as it is the default one: `wsl --list --verbose` marks it with
   `*` and shows its version as `2`. `wsl --set-default <distro>` changes it.
2. Inside WSL, install a coding agent CLI and sign in to it, as on any Linux machine:
   [Installation](/user/installation#signing-each-backend-in). The app finds what a login
   shell in WSL finds; a CLI installed on Windows is not seen.

## Try it

1. Download `humanize-<version>-windows-x64-setup.exe` from the
   [latest release](https://github.com/humanfia/humanize/releases/latest).
2. Run it. It installs Humanize Desktop for you alone, so it asks for no administrator rights.
3. Open Humanize Desktop from the Start menu.

The first time, it says **Installing Humanize CLI**, with each step, while it installs uv and `hmz`
in WSL; from then on it shows its mark while `hmz web` starts, then the page, with the sidebar
of your epics.

## How it works

The app runs `hmz web --no-open --attached` in WSL, through `wsl.exe`, and shows the page it
serves. Windows reaches that page on `127.0.0.1` by WSL's localhost forwarding.

- **Local is your WSL distribution.** The sidebar and **Settings → Daemons** name Local's host
  as `<distro> (WSL)`, `Ubuntu (WSL)` say. Epics run there, in its files, with its tools.
- **It installs `hmz` in WSL, at its own version**, as the macOS app does: where there is none,
  or one of another version, it runs `uv tool install --force hmz==<its version>` there. That
  is the same `~/.local/bin/hmz` a WSL terminal finds. Where WSL has no uv, the app downloads
  the Linux uv, checks it against a checksum it carries, and puts it in `~/.local/bin` in WSL.
  It never updates under running epics: see [`Update waiting`](/user/desktop#update-waiting).
- **It starts in your WSL home**, with the environment your login shell there gives you, so
  `hmz` and the coding agent CLIs are found as a WSL terminal finds them.
- **Keep your repositories in WSL**, under your Linux home -- `~/src/project`, not
  `/mnt/c/Users/you/project`. Files on a Windows drive are reached from WSL through a slow
  share, and locks and permissions there do not behave as Linux's do, which Humanize relies on.
  From Windows, Explorer reaches your WSL files under **Linux** in its sidebar, or at
  `\\wsl.localhost\<distro>`.
- **It keeps its port**, as the macOS app does, so the page opens as you left it.
- **The page is the whole window**, up to its top edge, with Windows' minimize, maximize and
  close buttons over its top right. Drag the window by any empty part of the top row, and
  double-click it to maximize; hovering the maximize button offers Windows' snap layouts.
- **Closing the window is not quitting.** The window goes, `hmz web` keeps serving, and
  Humanize Desktop stays in the tray. Click the tray icon, or open Humanize Desktop again, to bring the window
  back. The tray icon's menu has **Show Humanize Desktop**, **Check for Updates…**, **Documentation**
  and **Quit**; **Quit** stops `hmz web` too.
- **Links to elsewhere open in your browser**, and an export is saved to your Windows
  **Downloads** folder and shown in Explorer.
- **Other machines too.** The [daemons](/user/web#daemons) the page reaches -- your ssh hosts
  -- are reached from WSL, with the ssh config in your WSL home.

## Your epics and WSL {#your-epics-and-wsl}

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

## Opening a `.hmzepic`

The app is what a `.hmzepic` -- an [exported epic](/user/export) -- opens with. Double-click one
in Explorer, or choose **Open with → Humanize Desktop**: the app imports it, as **Import** on the page
does, and opens it on its [Exomyth](/user/web#exomyth). A file on a Windows drive, or one in
WSL reached as `\\wsl.localhost\<distro>\…`, is found in WSL at the path it has there. Opened
while the app is starting, or while it is already open, it is imported once the page is there.

## Notifications

The page's [notifications](/user/web#notifications) show in the window's bell and toasts as in
a browser, and, while the window is hidden or not in front, as Windows notifications from
Humanize Desktop. Click one: the window comes back, on the epic it is about. Which kinds appear is set
in **Settings → Notifications**; Windows' own **Settings → System → Notifications → Humanize Desktop**
decides how they are shown, or silences them.

## Updates

The app updates itself as the macOS app does: see [Updates](/user/desktop#updates). To look now,
choose **Check for Updates…** from the tray icon's menu. **Restart** installs the new release
and opens Humanize Desktop again on it; **Later** installs it when you quit. Once the new app opens, it
updates `hmz` in WSL to its own version too.

### Check it worked

- The window shows the sidebar of your epics, with Local named `<distro> (WSL)`.
- In WSL, `~/.local/bin/hmz --version` names the version you downloaded, or the one the app
  updated itself to since.

## Troubleshooting

### `WSL missing`

Windows has no WSL, or WSL has no distribution. Run `wsl --install` in PowerShell, restart if it
asks, open the distribution once to make your Linux user, then **Retry**. `wsl --list --verbose`
shows what you have; the app uses the default one, marked `*`.

### The window stays on its mark, or says the page cannot be reached

`hmz web` is serving in WSL, but Windows cannot reach it on `127.0.0.1`. WSL forwards
localhost unless `%UserProfile%\.wslconfig` turns it off: remove `localhostForwarding=false`
from its `[wsl2]` section, or use mirrored networking, where WSL and Windows share `127.0.0.1`:

```ini
[wsl2]
networkingMode=mirrored
```

Then run `wsl --shutdown` and open the app again.

### `Install failed`, `Update failed` or `Update waiting`

As on a Mac: see [the macOS app's troubleshooting](/user/desktop#troubleshooting). uv runs in
WSL, so it takes the proxy and index your WSL login shell sets.

### Using an `hmz` of your own

`HUMANIZE_HMZ` names an `hmz` to run instead -- a checkout you are working on, say -- and the app
then installs nothing. It is a path in WSL, set in Windows before you open the app. In
PowerShell:

```powershell
$env:HUMANIZE_HMZ = '/home/you/src/humanize/.venv/bin/hmz'
& "$env:LOCALAPPDATA\Humanize Desktop\humanize.exe"
```

### `Failed` or `Stopped`

`hmz web` exited, and the window shows what it said. **Retry** or **Restart** starts it again.
The app's log has the rest, at `%LOCALAPPDATA%\ai.humanfia.humanize\logs\Humanize Desktop.log`.

### My epics stopped after I quit the app

WSL shut the distribution down: see [Your epics and WSL](#your-epics-and-wsl).

## Uninstall

Quit Humanize Desktop from its tray icon, then remove it in **Settings → Apps → Installed apps**. Its
own data -- its port and window, what the page remembers, and its log -- is in
`%APPDATA%\ai.humanfia.humanize` and `%LOCALAPPDATA%\ai.humanfia.humanize`; delete both to
forget it.

`hmz`, uv and your epics stay in WSL as they are; `uv tool uninstall hmz` there removes `hmz`
too.

## Next steps

- [The macOS app](/user/desktop): the same app on a Mac.
- [In a browser (`hmz web`)](/user/web): the page itself, and what it refuses.
- [Installation](/user/installation): `hmz`, and the coding agent CLIs it drives.
