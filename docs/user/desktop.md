# The macOS app

The humanize app is [`hmz web`](/user/web) in a window of its own: the same page, every epic on
this Mac, with no terminal to keep open and no browser tab to find. It starts `hmz web` when it
opens and stops it when you quit.

::: info At a glance
- **You will** have humanize in your Dock and Applications, opening on every epic on this Mac.
- **Use it when** you would rather open an app than run `hmz web` and keep its terminal.
- **You need** macOS 11 or newer, on Apple silicon or Intel, and `hmz` installed as in
  [Installation](/user/installation): the app runs it, and brings none of its own.
:::

## Try it

1. Install `hmz`, if you have not:

   ```sh
   uv tool install hmz
   ```

2. Download `humanize-<version>-macos-universal.dmg` from the
   [latest release](https://github.com/humanfia/humanize/releases/latest).
3. Open it, and drag **humanize** onto **Applications**.
4. Open humanize from Applications. The first time, macOS stops it: see
   [The first time it opens](#the-first-time-it-opens).

It shows its mark while `hmz web` starts, then the page, with the sidebar of your epics.

## How it works

The app is a window, not a second humanize. It runs the `hmz` you installed, as
`hmz web --no-open --attached`, and shows the page it serves, so the app is always as new as your
`hmz`: `uv tool upgrade hmz` upgrades both.

- **It starts in your home directory**, with the environment your login shell gives you, so
  `hmz` and the coding agent CLIs are found as a terminal finds them, and your home is the
  directory a new epic is offered first.
- **It keeps its port.** `hmz web` listens on the port it had last time, so the page opens as
  you left it.
- **Closing the window is not quitting.** The app stays in the Dock and `hmz web` keeps serving;
  click the Dock icon to bring the window back. Quit with <kbd>cmd+q</kbd>, which stops
  `hmz web` too. However the app ends, `hmz web` goes with it.
- **Your epics outlive it**, as they outlive `hmz web`: quitting the app leaves an epic going.
  See [Leaving it running](/user/leaving).
- **Links to elsewhere open in your browser**, and an export is saved to **Downloads** and shown
  in the Finder.

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
- **humanize → About humanize** names the version you downloaded.

## Troubleshooting

### `Install humanize`

The app found no `hmz`. It looks in your login shell's `PATH`, then in `~/.local/bin`,
`$UV_TOOL_BIN_DIR`, `/opt/homebrew/bin` and `/usr/local/bin`. Install it with **Copy** and a
terminal, then press **Retry**:

```sh
uv tool install hmz
```

### `Update humanize`

The `hmz` it found is older than the app. Upgrade it, then press **Retry**:

```sh
uv tool upgrade hmz
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

`hmz`, and your epics, stay as they are.

## Next steps

- [In a browser (`hmz web`)](/user/web): the page itself, and what it refuses.
- [Leaving it running](/user/leaving): what goes on after the window closes.
- [Installation](/user/installation): `hmz`, and the coding agent CLIs it drives.
