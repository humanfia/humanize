# Releasing

In this guide you cut a release of humanize: you push a version tag, and check that PyPI has
the release, with an attestation saying where it was built. It is for the maintainers of
[humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: warning No release yet
humanize has not been released, so every install is of `main` from GitHub. The first release
also turns each `git+https://github.com/humanfia/humanize.git` in `README.md` and the docs
into plain `hmz`, and `SUPPORT.md`, `SECURITY.md` and the bug report and question templates
back to supporting, and asking for, a release.
:::

::: info Before you start
- Write access to humanfia/humanize, and [`gh`](https://cli.github.com/) signed in to it.
- A checkout set up as in [Contributing](/contributing/).
- Optionally, coding agent CLIs signed in on your machine, for the system tests.
:::

## How it works

**A release is a tag, and the tag is the version.** Nothing in the repository is edited to
cut one: `version` in `pyproject.toml` is only what a checkout between releases calls itself.
Tags are SemVer, and the release turns each into the PEP 440 version a Python package needs:

| Tag | Version | On GitHub and PyPI |
| --- | --- | --- |
| `v1.2.3` | `1.2.3` | a release |
| `v1.2.3-rc.1` | `1.2.3rc1` | a pre-release |
| `v1.2.3-beta.2` | `1.2.3b2` | a pre-release |
| `v1.2.3-alpha.1` | `1.2.3a1` | a pre-release |

Any other tag starting with `v`, such as `v1.2` or `v1.2.3-preview.1`, fails the run before
anything is published. `uv` and `pip` skip a pre-release unless it is asked for by number.

Pushing the tag starts the `publish.yml` workflow, in three jobs:

1. **build** runs [GoReleaser](https://goreleaser.com) with `.goreleaser.yaml`. It writes
   the tag's version into `pyproject.toml` with `scripts/release_version.py`, builds a wheel and
   an sdist with `uv build`, and puts them on a **draft** GitHub release with their
   `checksums.txt`. It then runs `twine check --strict`, which fails if PyPI could not render
   `README.md`.
2. **publish to PyPI** publishes the same two files to [PyPI](https://pypi.org/project/hmz/).
3. **publish the release** takes the GitHub release out of draft. It runs after PyPI, so the
   release never offers files PyPI refused.

Nobody holds a PyPI token: PyPI lets that one workflow, run in the repository's `pypi`
environment, publish `hmz`, which is called trusted publishing. Every file it publishes carries
an attestation naming the workflow run that built it.

The release notes are GoReleaser's, generated from the commits on `main` since the last tag
and grouped by their Conventional Commits titles (`.goreleaser.yaml`): breaking changes,
features, fixes, performance, documentation, and everything else. Chores that break nothing,
and Dependabot's bumps, are left out.

Which part of the version to bump:

| Since the last release, `main` has | Bump |
| --- | --- |
| a breaking change: a `!` in a pull request's title | minor while the version is `0.x`, major after |
| a feature | minor |
| only fixes | patch |

## Step 1: Run the system tests the release needs

CI never runs `tests/system`, which drives real agents on real tasks. Running it is optional,
and costs minutes and tokens a test, so run the files that cover what changed since the last
release, on the commit you are about to release. A release that changes how a backend is
driven runs that backend's `test_harness_*` file; one that changes a built-in flow runs its
`test_flows_*` file:

```sh
uv run pytest tests/system/test_flows_ralph.py
```

Release only when none of them fails: fix it on `main` first. A test that skips names what
this machine lacks. [Where a test goes](/contributing/#where-a-test-goes) has the rest.

## Step 2: Push the tag

On the commit of `main` you tested:

```sh
git switch main && git pull
git tag v0.2.0
git push origin v0.2.0
```

### Check it worked

The run takes a few minutes. Follow it with:

```sh
gh run watch "$(gh run list --workflow publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Once its three jobs are green, the release is on
[GitHub Releases](https://github.com/humanfia/humanize/releases). Read its generated notes,
and add a line on top if the release has a headline. Then install it from PyPI:

```sh
uvx hmz@0.2.0 --version
```

```text
hmz 0.2.0
```

Then check that each file's attestation names this repository:

```sh
uvx pypi-attestations verify pypi --repository https://github.com/humanfia/humanize \
  pypi:hmz-0.2.0-py3-none-any.whl
```

```text
OK: hmz-0.2.0-py3-none-any.whl
```

Do the same for `pypi:hmz-0.2.0.tar.gz`. PyPI shows the same on the release's **Download
files** page: each file names `publish.yml` on humanfia/humanize as its publisher.

## Variations

**A release candidate.** Tag `v0.2.0-rc.1`, then `v0.2.0-rc.2`, and `v0.2.0` once it holds.
Both GitHub and PyPI mark it as a pre-release.

**A dry run.** `gh workflow run publish.yml --ref main` builds and checks the package as a
release would, but keeps `pyproject.toml`'s version, there being no tag to take one from, and
publishes nothing. Use it after changing `README.md`, which is the
page PyPI shows, or the metadata in `pyproject.toml`.

**On your machine.** GoReleaser builds the same files without publishing anything:

```sh
brew install goreleaser       # or see goreleaser.com/install
goreleaser check
goreleaser release --snapshot --clean
uvx --from dist/wheel_none-any/hmz-*.whl hmz --version
```

They land in `dist/`, which git ignores. A snapshot leaves `pyproject.toml` alone, so it
carries that version. To see which version a tag would get:

```sh
uv run --no-project scripts/release_version.py v0.2.0-rc.1    # 0.2.0rc1
```

## Yanking a release

When a release is broken, yank it on PyPI: **Manage project**, the version, **Options**,
**Yank**, with a reason that names the version to use instead. A yanked version stays
installable for anyone who asks for it by number, and nothing else picks it. Then say so at
the top of the GitHub release's notes, fix it on `main`, and release the next patch.

Do not delete a release from PyPI, and do not move its tag. PyPI never takes the same file
name twice, so a deleted version cannot be published again either, and anyone who pinned it
can no longer install it.

## Pitfalls

| The run fails with | Because | Do |
| --- | --- | --- |
| `'v…' is not a release tag` | the tag is not one of the forms above. Nothing was published | `git push origin :refs/tags/<tag>`, delete the tag locally, and push one that is |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published | delete the draft release and the tag, fix it on `main`, and tag again |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml` and environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version already | tag the next version: PyPI never takes a version's files twice |
| a failed `publish the release` | PyPI has the release, and the GitHub release is still a draft | `gh run rerun <run-id> --failed` |

::: details For admins: guarding the `pypi` environment
In **Settings → Environments → pypi**, add yourself and another maintainer as required
reviewers, and limit deployments to tags matching `v*`. Each upload then waits for a second
person to approve it on the run's page, and nothing but a release tag can reach PyPI.
:::

## Next steps

| To | Read |
| --- | --- |
| run a system test, or add one | [Where a test goes](/contributing/#where-a-test-goes) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`publish.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yml) and [`.goreleaser.yaml`](https://github.com/humanfia/humanize/blob/main/.goreleaser.yaml) |
