---
title: Desktop app
description: Look up what Humanize Desktop ships as, which files it keeps, its menus, the environment variables it reads, and what the page inside it is allowed to do.
---

# Desktop app

Look up the files, menus, environment variables, commands and limits of Humanize Desktop. To use the app, see [Humanize Desktop](/user/desktop). To install or update it, see [Install and update](/user/install).

## Platforms and artefacts

Every release on [GitHub](https://github.com/humanfia/humanize/releases/latest) includes these files:

| File | For |
| --- | --- |
| `humanize-<version>-macos-universal.dmg` | macOS 11 or later, Apple silicon and Intel in one disk image |
| `humanize-<version>-windows-x64-setup.exe` | Windows 10 or later on x64, with WSL 2 |
| `humanize-<version>-macos-universal.app.tar.gz` | The signed macOS update the app downloads by itself |
| `humanize-<version>-windows-x64-setup.exe.sig` | The signature of the Windows update |
| `latest.json` | What the app reads to find an update, for `darwin-aarch64`, `darwin-x86_64` and `windows-x86_64` |

Only releases signed with the updater's key include the last three files. The app never offers an unsigned release as an update.

| Property | macOS | Windows |
| --- | --- | --- |
| Name | `Humanize Desktop` (menu bar: `Humanize`) | `Humanize Desktop` |
| Identifier | `ai.humanfia.humanize` | `ai.humanfia.humanize` |
| Installed as | `Humanize Desktop.app`, dragged to Applications | `%LOCALAPPDATA%\Humanize Desktop\humanize.exe`, for the current user only, no administrator |
| Signing | Apple Developer ID and notarized where the release has one, ad hoc otherwise | Not signed |
| Page address inside the window | `tauri://localhost/` | `http://tauri.localhost/` |
| User agent ends with | `humanize-desktop/<version>` | `humanize-desktop/<version>` |
| Local daemon route | `stdio:local` | `stdio:wsl` |
| Installs `hmz` | Never | In the default WSL distribution, at the app's own version |

The app opens `.hmzepic` files (media type `application/vnd.hmz.epic+gzip`, macOS type identifier `ai.humanfia.humanize.epic`). The executable also takes a `.hmzepic` path as its argument, relative to the current directory. If the app is already running, the second launch hands the file to it: the running app imports the epic and comes forward.

```sh
"/Applications/Humanize Desktop.app/Contents/MacOS/humanize" run.hmzepic   # macOS
humanize.exe run.hmzepic                                                    # Windows
```

### What the app downloads

| What | Version | When | Where it goes |
| --- | --- | --- | --- |
| `hmz` | The app's version (app `0.5.0-rc.1` installs hmz `0.5.0rc1`) | Windows only, at launch, when WSL has no `hmz` or one of another version | WSL, as a uv tool |
| `uv` | `0.12.24` | Windows only, when WSL has no `uv` on `PATH`, in `~/.local/bin` or in `~/.cargo/bin` | `~/.local/bin/uv` in WSL |
| EasyTier | `2.6.4` | The first time an `easytier:` daemon is opened | `easytier/<version>/` in the data directory |
| The app's own update | Newer than the running version | 5 seconds after launch, then every 6 hours | Replaces the app |

On Windows, the app runs this command in the WSL home directory to install `hmz`, keeping any `<extras>` from an existing installation:

```sh
uv tool install --force --python '>=3.12' --refresh-package hmz hmz[<extras>]==<version>
```

The app checks each `uv` and EasyTier download against a pinned SHA-256 hash. It accepts an app update only if signed with the updater's key, and offers pre-releases only to pre-release builds. It never replaces `hmz` in WSL while the WSL daemon is running, unless you choose **Update now** on the launch screen.

Over an ssh route, the app also installs its own version of `hmz` on the host. See [Connect to other machines](/user/daemons).

## Files the app keeps

### Data directory

The data directory is `~/Library/Application Support/ai.humanfia.humanize/` on macOS and `%APPDATA%\ai.humanfia.humanize\` on Windows. The app stores only these entries in it:

| Entry | Holds |
| --- | --- |
| `.window-state.json` | The window's size, position and whether it is maximized |
| `identity/key.pem` | The private key of the app's device identity. Written once, readable by you alone |
| `identity/cert.pem` | The certificate of the app's device identity. Made again only if it does not match the key |
| `easytier.json` | The EasyTier entries: each name with its secret and nodes. Readable by you alone |
| `easytier/<version>/` | The EasyTier programs the app downloaded |

If you delete the data directory while the app is closed, the app generates a new device identity on next launch. Previously paired daemons will reject the app until you pair again, and your EasyTier entries and window placement are lost.

### Other files

| File | macOS | Windows |
| --- | --- | --- |
| Log, `Humanize Desktop.log` | `~/Library/Logs/ai.humanfia.humanize/` | `%LOCALAPPDATA%\ai.humanfia.humanize\logs\` |
| Web view stores (preferences, remote daemons, WebRTC certificate) | `~/Library/WebKit/ai.humanfia.humanize/` and `~/Library/Caches/ai.humanfia.humanize/` | `%LOCALAPPDATA%\ai.humanfia.humanize\` |
| Single-instance socket, while the app runs | `/tmp/ai_humanfia_humanize_si.sock` | None |
| Downloads from the page | `~/Downloads/` | The Downloads folder |
| Notification logo | None | `%ProgramData%\ai.humanfia.humanize\logo.png` |
| While an update installs | Temporary directories named `tauri_current_app…` and `tauri_updated_app…`, removed afterwards | The downloaded installer, in the Windows temporary directory |

The app empties the log when it exceeds 40,000 bytes. The log records uv install output, opened and closed connections, and update check results. It contains no secrets.

Downloads never overwrite existing files. If a name is taken, the app appends ` (1)`, ` (2)` and so on before the extension.

The app writes to `hmz` directories only by running `hmz`. See [Files on disk](/reference/files).

## Menus

### macOS menu bar

| Menu | Item | Key | Does |
| --- | --- | --- | --- |
| **Humanize** | **About Humanize** | | Shows the app's name and version |
| | **Check for Updates…** | | Looks for an update now and says what it found |
| | **Hide Humanize**, **Hide Others**, **Show All** | | The standard macOS items |
| | **Quit Humanize** | | Quits the app. Epics keep running |
| **Edit** | **Undo**, **Redo**, **Cut**, **Copy**, **Paste**, **Select All** | | The standard macOS items |
| **View** | **Reload** | <kbd>⌘R</kbd> | Loads the page again. Every connection closes and opens again |
| | **Actual Size** | <kbd>⌘0</kbd> | Sets the zoom to 100% |
| | **Zoom In** | <kbd>⌘=</kbd> | Multiplies the zoom by 1.1, up to 300% |
| | **Zoom Out** | <kbd>⌘-</kbd> | Divides the zoom by 1.1, down to 50% |
| | Full screen | | The standard macOS item |
| **Window** | **Minimize**, **Zoom**, **Close Window** | | The standard macOS items. Closing hides the window |
| **Help** | **Documentation** | | Opens `https://humanfia.ai/humanize/` in the browser |

Standard items use the default macOS shortcuts. Zoom resets when you quit the app. **Check for Updates…** is disabled in development builds and reads **Checking for Updates…** during a check. Menus remain in English regardless of the page language.

### Windows tray menu

Windows has no menu bar. Left-click the tray icon to show the window, or right-click it to open this menu:

| Item | Does |
| --- | --- |
| **Show Humanize Desktop** | Shows the window |
| **Check for Updates…** | Looks for an update now and says what it found |
| **Documentation** | Opens `https://humanfia.ai/humanize/` in the browser |
| **Quit** | Quits the app. Epics keep running |

The top-right window buttons are **Minimize**, **Maximize** (**Restore Down** when maximized) and **Close**, each 46 by 32 pixels. **Close** hides the window. Use the standard WebView2 shortcuts to reload and zoom.

### Update dialogs

| Dialog | Buttons | Meaning |
| --- | --- | --- |
| `Humanize Desktop <version>` | **Restart**, **Later** | An update is downloaded. **Restart** installs it now. **Later** installs it when the app quits |
| `Humanize Desktop is up to date` | **OK** | A check by hand found nothing newer |
| `Update failed` | **OK** | A check by hand failed, with the reason |
| `Update failed`: `Humanize Desktop cannot replace itself where it is. Move it to Applications, and open it from there.` | **OK** | macOS: a check by hand where the app cannot replace itself |
| `Update failed`: `Humanize Desktop cannot replace itself where it is. Install it for yourself with its setup, and open it from there.` | **OK** | Windows: the same |

During a check by hand, a small `Software Update` window shows the check, then the download's progress. The app downloads no update where it cannot replace itself. On macOS that is an app run from the disk image, moved aside by Gatekeeper, or in a folder you cannot write; on Windows, one run from outside the folder its setup installed it in.

## Environment variables

At launch, the app queries your login shell (or the WSL login shell on Windows) for its environment. It waits 5 seconds before falling back to its own environment.

| Variable | Effect |
| --- | --- |
| `HUMANIZE_HMZ` | The `hmz` to run for Local. The app looks for no other and installs nothing. On Windows the value is a path inside WSL |
| `SHELL` | The login shell that is asked. `/bin/zsh` where it is not set on macOS |
| `PATH` | Where `hmz` and the coding agents are found. The app adds `~/.local/bin`, `$UV_TOOL_BIN_DIR`, `/opt/homebrew/bin` (macOS only), `/usr/local/bin`, `/usr/bin` and `/bin` where they are missing |
| `UV_TOOL_BIN_DIR` | Added to `PATH` |
| `HTTPS_PROXY`, `https_proxy`, `ALL_PROXY`, `all_proxy` | On Windows, the proxy for downloading `uv`. The first one set in the WSL login shell is used |

For variables read by `hmz` itself, see [Environment variables](/reference/environment).

## Building from source

The app is a Tauri 2 project in `desktop/`, built with pnpm. Run these in that directory:

| Command | Does |
| --- | --- |
| `pnpm dev` | Runs the app on the page in `src/hmz/web/static` |
| `pnpm build` | Builds the app and its disk image on macOS, the installer on Windows |
| `pnpm dmg-background` | Draws the disk image's backgrounds again. macOS only |
| `pnpm nsis-images` | Draws the Windows installer's pictures again |

A build from source has version `0.0.0`, which makes it a development build. Development builds install nothing, skip update checks, and run `HUMANIZE_HMZ` or the first `hmz` found on `PATH` or in the fallback directories above.

## Commands the page may call

The page inside the window can call only these app commands. Bytes pass as base64 in `data`.

| Command | Arguments | Answer | Does |
| --- | --- | --- | --- |
| `notify` | `{title, body, address}` | Nothing | Shows a system notification. A click opens `address` when it is a `#/` address of the page of at most 2048 characters |
| `file_read` | `{path, offset, length}` | `{data, eof}` | Reads a `.hmzepic` that was opened with the app or dropped on it, at most 1,048,576 bytes a call |
| `pipe_open` | `{route, id}` | `{pipe}` | Opens a connection to one daemon |
| `pipe_send` | `{pipe, data}` | Nothing | Sends bytes on a connection that is `up` |
| `pipe_close` | `{pipe}` | Nothing | Closes a connection |
| `easytier_list` | None | A list of `{name, nodes, secret}` | Lists the EasyTier entries. `secret` is only true or false |
| `easytier_set` | `{name, secret, nodes}` | Nothing | Writes an entry. Leaving `secret` out keeps the one written |
| `easytier_remove` | `{name}` | Nothing | Removes an entry |

The app sends these events to the page:

| Event | Payload | Meaning |
| --- | --- | --- |
| `pipe_state` | `{pipe, state, detail}` | `state` is `connecting`, `installing`, `up` or `failed` |
| `pipe_data` | `{pipe, data}` | Bytes from the daemon |
| `pipe_closed` | `{pipe, why}` | The connection ended. `why` is `closed` when the page closed it, otherwise the reason |

The page can also drag and zoom the window by its top row, and minimize, maximize and close it on Windows. The app tells the page whether the window is full screen. The page has no other app privileges. Each face runs in an isolated frame and cannot call any commands.

The launch screen has its own commands: `status`, and on Windows `retry`, `keep` and `update_now` (for the **Retry**, **Continue** and **Update now** buttons). `status` returns `starting` or `running`, and on Windows also `installing`, `waiting`, `install-failed` or `missing`.

### Routes the app opens

| Route | Opened by |
| --- | --- |
| `stdio:local` | The app, on macOS only |
| `stdio:wsl` | The app, on Windows only |
| `stdio:ssh://`, `tcp://`, `ws://`, `wss://`, `easytier:`, `relay:` | The app, on both |
| `webrtc:` | The web view's own WebRTC |

On `tcp`, `ws`, `wss`, `easytier` and `relay` routes, the app establishes mutual TLS 1.3 using its device identity and verifies the daemon's ID. For the route grammar, see [Daemon and wire](/reference/daemon).

A connection that fails or ends gives its reason as a sentence. The most common are:

| Reason | Meaning |
| --- | --- |
| `<route> cannot be reached from here.` | The app opens no such route on this platform |
| `<route> needs the id of the daemon it reaches.` | A route other than `stdio:` was opened without a daemon ID |
| `hmz is not installed on this machine.` | macOS: no `hmz` was found for `stdio:local` |
| `<route> did not open within 30 seconds.` | The connection or its TLS took too long |
| `<name> is not the daemon it was paired with.` | The daemon's certificate does not match the pinned ID. Check the address, or pair again |
| `TLS with <name> failed: <why>` | The TLS handshake failed for another reason |
| `The daemon closed it.` | The daemon ended the connection without saying why. Otherwise the reason is the last line its process wrote to standard error |

### Limits

| Limit | Value |
| --- | --- |
| Opening a connection, TLS included | 30 seconds |
| Finding `hmz` on an ssh host | 30 seconds |
| Installing `hmz` on an ssh host | 900 seconds |
| WSL starting | 60 seconds |
| An update check or download | 5 minutes |
| A process still running after quit | Killed after 3 seconds |
| First window size | 1280 by 820 |
| Smallest window size | 640 by 480 |
| An EasyTier secret | At least 16 bytes |

## Content security policy

Every page in the window follows this policy:

| Directive | Value |
| --- | --- |
| `default-src` | `'self'` |
| `connect-src` | `ipc: http://ipc.localhost ws: wss:` |
| `script-src` | `'self' 'unsafe-inline'` |
| `style-src` | `'self' 'unsafe-inline'` |
| `img-src` | `'self' data: blob:` |
| `font-src` | `'self' data:` |
| `frame-src` | `'self'` |

The main page narrows the policy to `script-src 'self'`, blocking inline scripts; inline scripts run only inside face frames. `ipc:` and `http://ipc.localhost` handle app commands. `ws:` and `wss:` connect to `webrtc:` relays.

The window loads only the launch screen and the bundled page. Any `http`, `https` or `mailto` link opens in your default browser; all other addresses are blocked.
