# Vendored web code

The web page has no bundler: it is plain ES modules served as they are. Its only third-party
code, the editor and the terminal of the env panels, is built here into
`../static/vendor/`, and the page imports it from there and nowhere else:

| Served at | Built from | What it exports |
| --- | --- | --- |
| `/vendor/codemirror.js` | `codemirror.mjs` | CodeMirror 6 (`EditorView`, `EditorState`, `basicSetup`, search, merge, ...), plus `languageFor(filename)`, `languageName(filename)` and `themeFor({dark, tokens})` |
| `/vendor/xterm.js` | `xterm.mjs` | xterm.js 5 `Terminal` and the `FitAddon`, `WebglAddon`, `SearchAddon`, `WebLinksAddon` and `Unicode11Addon` |
| `/vendor/xterm_css.css` | `@xterm/xterm/css/xterm.css` | xterm's stylesheet |

Each output is one minified file, so its name passes the server's rules for the page's files
(letters, digits, `_` and `-`, then one extension), and each starts with the licences of every
package bundled into it.

## Rebuild

Every version is pinned in `package.json` and `pnpm-lock.yaml`. After changing either, or
`build.mjs`, `codemirror.mjs` or `xterm.mjs`:

```sh
cd src/hmz/web/vendor
pnpm install --frozen-lockfile   # `pnpm install` after editing package.json
pnpm build
```

Commit what it wrote under `src/hmz/web/static/vendor/`. CI's `vendor` job builds it again
from the lockfile and fails if the committed files differ. pre-commit leaves that folder
alone, as its whitespace can be inside strings.

The wheel carries only the built files; this folder ships in the sdist alone.
