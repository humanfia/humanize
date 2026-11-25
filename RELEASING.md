# Releasing Humanize

For maintainers of [humanfia/humanize](https://github.com/humanfia/humanize). You run the
release workflow with a version, merge the pull request it opens, and check what was
published. A release is never replaced: a broken one is yanked, and the next one fixes it.

## How it works

`main` is where changes land, and never what is released: its `pyproject.toml`,
`desktop/src-tauri/tauri.conf.json` and `crates/coganchor/Cargo.toml` say `0.0.0`. Every
release, pre-releases included, comes from a `release/X.Y` branch, held to the same rules as
`main`.

1. **`release.yml`**, run by hand on `main` with the version, checks it, cuts `release/X.Y`
   from `main` if the line is new, and has
   [release-please](https://github.com/googleapis/release-please) open the release pull
   request against it. The pull request bumps the version in `pyproject.toml`, `uv.lock`,
   `tauri.conf.json` and `crates/coganchor`'s `Cargo.toml` and `Cargo.lock`, and writes the
   release's section of `CHANGELOG.md` from the pull request titles since the last release of
   the line.
2. **`ci.yml`** runs on the release pull request, started by `release.yml`, and `ci-ok` is
   needed to merge it.
3. **`publish.yml`**, on the push that merges it, tags the commit `vX.Y.Z`; builds `coganchor`
   for Linux and macOS on x86-64 and arm64, a wheel carrying all four, and an sdist; runs
   `twine check --strict`; publishes to [PyPI](https://pypi.org/project/hmz/) by trusted
   publishing, from the `pypi` environment, with attestations; builds and attests
   `humanize-X.Y.Z-macos-universal.dmg` and `humanize-X.Y.Z-windows-x64-setup.exe`; and only
   then publishes the GitHub release with the apps' files.

### Versions

| You name | It comes from | It must |
| --- | --- | --- |
| `X.Y.0`, or its `-alpha.N`, `-beta.N`, `-rc.N` | `release/X.Y`, cut from `main` if it does not exist | come after every release of `X.Y`; a new `X.Y` after every line there is |
| `X.Y.Z` with `Z` above 0, or its pre-releases | `release/X.Y`, which must exist | come after every release of `X.Y`, with `X.Y.0` released |

A breaking change (a `!` in a title) bumps the minor while the version is `0.x` and the major
after; a feature bumps the minor; only fixes, the patch. On PyPI a version is in PEP 440:
`0.2.0-beta.1` is `0.2.0b1`. A pre-release is a pre-release on GitHub and never the latest
release.

### The apps' signing and updates

- The disk image is signed ad hoc unless the repository holds an Apple Developer ID in the
  secrets `APPLE_CERTIFICATE` (the `.p12`, in base64), `APPLE_CERTIFICATE_PASSWORD` and
  `APPLE_SIGNING_IDENTITY`; with `APPLE_ID`, `APPLE_PASSWORD` and `APPLE_TEAM_ID` as well it is
  notarized.
- An installed app updates itself from the `latest.json` of the newest release that is not a
  pre-release. `publish.yml` builds the update (`humanize-X.Y.Z-macos-universal.app.tar.gz`;
  on Windows the installer itself, with a `.sig` beside it), signs it with the updater's key
  in the secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, and
  writes `latest.json`. Without those secrets the release has no update, with a warning.
- **Back up the updater's key**, and its password, in the maintainers' password manager. Its
  public half is `plugins.updater.pubkey` in `tauri.conf.json`, and an app takes no update
  signed with another: if the key is lost, every installed app must be downloaded again by
  hand.

## Cut a release

1. **Run the system tests that cover what changed** since the last release, on the commit you
   are about to release, a file at a time: `uv run pytest tests/system/test_flows_ralph.py`.
   CI never runs them. Fix a failure on `main` first.
2. **Open the release.** The pull request `chore(release/0.2): release 0.2.0-beta.1` opens
   against `release/0.2` a minute later. Read its `CHANGELOG.md`: it is what the release will
   say. Running it again with the same version brings the pull request up to date.

   ```sh
   gh workflow run release.yml -f version=0.2.0-beta.1
   ```

3. **Approve and merge it** once `ci-ok` is green.
4. **Check it worked.**

   ```sh
   gh run watch "$(gh run list --workflow publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
   uvx hmz@0.2.0b1 --version
   uvx pypi-attestations verify pypi --repository https://github.com/humanfia/humanize \
     pypi:hmz-0.2.0b1-py3-none-any.whl
   gh release download v0.2.0-beta.1 --repo humanfia/humanize --pattern '*.dmg'
   gh attestation verify humanize-0.2.0-beta.1-macos-universal.dmg --repo humanfia/humanize
   ```

## Variations

- **A change for a line already cut** merges to `main` first, then is cherry-picked onto a
  branch from `origin/release/X.Y` and opened as a pull request against `release/X.Y`. Then
  open the line's next version.
- **Changing your mind.** Close the release pull request and delete its branch: nothing was
  released. The `release/X.Y` branch stays.
- **Checking the package without releasing**: `uv build --no-sources`, then
  `uvx --from dist/hmz-*.whl hmz --version`.

## Yanking

Yank a broken release on PyPI (**Manage project**, the version, **Options**, **Yank**) with a
reason naming the version to use instead, say so at the top of the GitHub release's notes, and
release the next patch. Never delete a release from PyPI or move its tag: PyPI never takes the
same file name twice.

## When a run fails

| The run fails with | Do |
| --- | --- |
| a refusal of the version in `release` (`is not X.Y.Z…`, `is released already`, `does not come after`, `which is not released`, `has nowhere to come from`, `would start a line before`) | nothing was opened: run it again with a version that passes |
| `GitHub Actions is not permitted to create or approve pull requests` | an admin allows it in **Settings → Actions → General**; run it again |
| the release pull request waits for `ci-ok` forever | **Approve workflows to run** on the pull request |
| a failed `twine check` | nothing was published, but the tag and a draft release exist: `gh release delete vX.Y.Z --yes`, keeping the tag; fix it on `main`, bring it to the line, open the next version |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml`, environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version: open the next one |
| a failed `publish the release`, `desktop` or `desktop-windows` | PyPI may have the release and the GitHub release is still a draft: fix what the log says and `gh run rerun <run-id> --failed`; a fix that needs a commit goes to `main`, then the next version |

Admins: in **Settings → Environments → pypi**, require a second maintainer as reviewer and
limit deployments to `release/*` branches.
