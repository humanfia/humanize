# The macOS app

The humanize app is [`hmz web`](/user/web) in a window of its own: the same page, every epic on
this Mac, with no terminal to keep open and no browser tab to find. It starts `hmz web` when it
opens and stops it when you quit.

::: info At a glance
- **You will** have humanize in your Dock and Applications, opening on every epic on this Mac.
- **Use it when** you would rather open an app than run `hmz web` and keep its terminal.
- **You need** macOS 11 or newer, on Apple silicon or Intel, and a connection the first time:
  the app installs `hmz` itself.
:::

## Try it

1. Download `humanize-<version>-macos-universal.dmg` from the
   [latest release](https://github.com/humanfia/humanize/releases/latest).
2. Open it, and drag **humanize** onto **Applications**.
3. Open humanize from Applications. The first time, macOS stops it: see
   [The first time it opens](#the-first-time-it-opens).

The first time, it says **Installing humanize**, with each step, while it installs `hmz`; from
then on it shows its mark while `hmz web` starts, then the page, with the sidebar of your epics.

## How it works

The app is a window, not a second humanize. It runs `hmz` as
`hmz web --no-open --attached` and shows the page it serves.

- **It installs `hmz` for you, at its own version.** humanize 0.5.0 runs `hmz` 0.5.0, since both
  come from the same release. Where there is none, or one of another version, it runs
  `uv tool install --force hmz==<its version>`, keeping any extras you installed with, and says
  **Installing humanize** or **Updating humanize** while it does. That is the same
  `~/.local/bin/hmz` a terminal finds, so the `hmz` you type is the app's version too; another
  `hmz` on your `PATH`, from pipx or pip, is left alone and not used.
- **It brings uv only where you have none.** It uses yours -- on your `PATH`, or in
  `~/.local/bin`, `~/.cargo/bin` or `/opt/homebrew/bin` -- and otherwise downloads uv, checked
  against a checksum it carries, to
  `~/Library/Application Support/ai.humanfia.humanize/uv/uv`. uv gets Python where it needs to.
  Your shell profile is never touched.
- **It never updates under running epics.** While epics are running, the `hmz` there keeps
  running them and the app opens it as it is; it updates on a later launch, once they have
  ended. See [`Update waiting`](#update-waiting).

- **It starts in your home directory**, with the environment your login shell gives you, so
  `hmz` and the coding agent CLIs are found as a terminal finds them, and your home is the
  directory a new epic is offered first.
- **It keeps its port.** `hmz web` listens on the port it had last time, so the page opens as
  you left it, in the [theme](/user/web#themes) you chose. A theme made in a browser is brought
  into the app by exporting it there and importing it here.
- **Closing the window is not quitting.** The app stays in the Dock and `hmz web` keeps serving;
  click the Dock icon to bring the window back. Quit with <kbd>cmd+q</kbd>, which stops
  `hmz web` too. However the app ends, `hmz web` goes with it.
- **Your epics outlive it**, as they outlive `hmz web`: quitting the app leaves an epic going.
  See [Leaving it running](/user/leaving).
- **The page is the whole window**, up to its top edge, with the window's buttons over the
  sidebar's top. Drag the window by any empty part of the top row, and double-click it to zoom.
- **Links to elsewhere open in your browser**, and an export is saved to **Downloads** and shown
  in the Finder.
- **It updates itself.** See [Updates](#updates).

## Opening a `.hmzepic` {#opening-a-hmzepic}

The app is what a `.hmzepic` -- an [exported epic](/user/export) -- opens with. Double-click one
in the Finder, choose **Open With → humanize**, or drop one on the window: the app imports it,
as **Import** on the page does, and opens it on its [Exomyth](/user/web#exomyth). Opened while
the app is still starting, it is imported once the page is there. Of several opened or dropped
at once, the last is imported; anything but a `.hmzepic` is left alone.

One you already have is refused, with **Open** to go to it; one that cannot be picked up on this
Mac says why on its own page, as any [imported epic](/user/web#importing-an-epic) does.

## Updates {#updates}

The app looks for a new release a few seconds after it opens, and every 6 hours after. It
downloads one in the background, checks that it was signed by humanize's release, and then asks
once, naming the version:

- **Restart** installs it, and opens humanize again on it, `hmz web` stopped and started with it.
- **Later** leaves it until you quit humanize, which installs it then.

To look now, choose **humanize → Check for Updates…**: it offers the new release, or says
humanize is up to date, or why it could not look. Only releases are offered, never a
pre-release.

Once the new app opens, it updates `hmz` to its own version too, as it would at any launch: at
once where no epics are running, and otherwise once they have ended.

## The first time it opens {#the-first-time-it-opens}

humanize is not yet signed with an Apple Developer ID, so the first time you open it, macOS says
it cannot check it and offers only **Done** or **Move to Trash**. Choose **Done**, then either:

- open **System Settings → Privacy & Security**, scroll to the message about humanize, and click
  **Open Anyway**; or
- in a terminal, take the quarantine off the app:

  ```sh
  xattr -dr com.apple.quarantine /Applications/humanize.app
  ```

Either is once: macOS remembers it, until you install the app again.

### Check it worked

- The window shows the sidebar of your epics, as `hmz web` does in a browser.
- **humanize → About humanize** names the version you downloaded, or the one it updated itself
  to since.

## Troubleshooting

### `Install failed` or `Update failed`

uv could not install `hmz`: most often you are offline, or a proxy is in the way. The window
shows what uv said; press **Retry** once you are connected. Where an `hmz` of another version is
already installed and can serve the app, **Continue** opens it as it is, and the app tries again
next time. uv takes the proxy and index your login shell sets (`HTTPS_PROXY`, `UV_INDEX_URL`).

### `Update waiting` {#update-waiting}

Epics are running in an `hmz` too old for the app to open, and updating it now could stop them.
The app waits, and updates as soon as they have ended. **Update now** updates at once, if you
would rather not wait.

### Using an `hmz` of your own

To have the app run another `hmz` -- a checkout you are working on, say -- name it in
`HUMANIZE_HMZ` and open the app from that shell. It then installs nothing:

```sh
HUMANIZE_HMZ=~/src/humanize/.venv/bin/hmz /Applications/humanize.app/Contents/MacOS/humanize
```

### `Failed` or `Stopped`

`hmz web` exited, and the window shows what it said. **Retry** or **Restart** starts it again.
The app's log has the rest:

```sh
open ~/Library/Logs/ai.humanfia.humanize/humanize.log
```

`hmz: the runs … are held by an older humanize` is the most common: an older `hmz` holds them.
See [`hmz web`'s troubleshooting](/user/web#troubleshooting).

### The window opened on a page that forgot what I chose

The page keeps your choices per port, and the port it had was taken by something else this
time, so it took another. It keeps the new one from then on.

## Uninstall

Quit humanize and move it from Applications to the Trash. To forget what it kept as well -- its
port and window, what the page remembers, and its log:

```sh
rm -rf ~/Library/{Application\ Support,WebKit,Caches,Logs}/ai.humanfia.humanize
```

`hmz`, and your epics, stay as they are; `uv tool uninstall hmz` removes `hmz` too.

## Next steps

- [In a browser (`hmz web`)](/user/web): the page itself, and what it refuses.
- [Leaving it running](/user/leaving): what goes on after the window closes.
- [Installation](/user/installation): `hmz`, and the coding agent CLIs it drives.
