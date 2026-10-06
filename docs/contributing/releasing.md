# Releasing

In this guide you cut a release of humanize: you start the release with the version you want,
merge the pull request it opens, and check that PyPI has the release, with an attestation
saying where it was built. It is for the maintainers of
[humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: warning No release yet
humanize has not been released, so every install is of `main` from GitHub, which calls itself
`0.0.0`. The first release also turns each `git+https://github.com/humanfia/humanize.git` in
`README.md` and the docs into plain `hmz`, and `SECURITY.md` and the bug report template back
to supporting, and asking for, a release.
:::

::: info Before you start
- Write access to humanfia/humanize, and [`gh`](https://cli.github.com/) signed in to it.
- A checkout set up as in [Contributing](/contributing/).
- Optionally, coding agent CLIs signed in on your machine, for the system tests.
:::

## How it works

**A release is a pull request you asked for.** Nothing is released until a maintainer names a
version, and `version` in `pyproject.toml` is always the last one released, so a checkout and
its tag never disagree. Two workflows do it:

1. **`release.yml`**, run by hand with the version, checks it, and opens a pull request from
   the branch `release/vX.Y.Z` that sets that version in `pyproject.toml` and `uv.lock`. Its
   description holds the release notes.
2. **`publish.yml`** runs on every push to `main`, and does something only for the merge of
   such a pull request. It checks that `pyproject.toml` says the branch's version, builds a
   wheel and an sdist with `uv build`, runs `twine check --strict` (which fails if PyPI could
   not render `README.md`), publishes both to [PyPI](https://pypi.org/project/hmz/), and only
   then tags the merge commit `vX.Y.Z` and publishes the GitHub release with them attached, so
   the release never offers files PyPI refused.

Versions are SemVer, and the package says each in PEP 440:

| Version | On PyPI | On GitHub and PyPI |
| --- | --- | --- |
| `1.2.3` | `1.2.3` | a release |
| `1.2.3-rc.1` | `1.2.3rc1` | a pre-release |
| `1.2.3-beta.2` | `1.2.3b2` | a pre-release |
| `1.2.3-alpha.1` | `1.2.3a1` | a pre-release |

Anything else, a version already tagged, or one that does not come after the current one
fails the run before anything is opened. `uv` and `pip` skip a pre-release unless it is asked
for by number.

The release notes are the title of every commit on `main` since the previous release's tag,
or since the first commit for the first release, newest first, release commits left out. Each
title is a squashed pull request's, so it ends with its number, which GitHub links.

Which version to name:

| Since the last release, `main` has | Bump |
| --- | --- |
| a breaking change: a `!` in a pull request's title | minor while the version is `0.x`, major after |
| a feature | minor |
| only fixes | patch |

Nobody holds a PyPI token: PyPI lets `publish.yml`, run in the repository's `pypi`
environment, publish `hmz`, which is called trusted publishing. Every file it publishes carries
an attestation naming the workflow run that built it.

## Step 1: Run the system tests the release needs

CI never runs `tests/system`, which drives real agents on real tasks. Running it is optional,
and costs minutes and tokens a test, so run the files that cover what changed since the last
release, on the commit of `main` you are about to release. A release that changes how a
backend is driven runs that backend's `test_harness_*` file; one that changes a built-in flow
runs its `test_flows_*` file:

```sh
uv run pytest tests/system/test_flows_ralph.py
```

Release only when none of them fails: fix it on `main` first. A test that skips names what
this machine lacks. [Where a test goes](/contributing/#where-a-test-goes) has the rest.

## Step 2: Open the release

```sh
gh workflow run release.yml -f version=0.2.0
```

Or **Actions → release → Run workflow** on GitHub. A minute later the pull request
`chore(release): v0.2.0` is open. Read its notes: they are what the release will say.

## Step 3: Merge it

Approve the pull request and merge it once `ci-ok` is green.

### Check it worked

The run takes a few minutes. Follow it with:

```sh
gh run watch "$(gh run list --workflow publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Once its four jobs are green, the release is on
[GitHub Releases](https://github.com/humanfia/humanize/releases). Then install it from PyPI:

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

**A release candidate.** Open `0.2.0-rc.1`, then `0.2.0-rc.2`, and `0.2.0` once it holds.
Both GitHub and PyPI mark it as a pre-release.

**Changing your mind.** Close the release pull request and delete its branch: nothing was
released.

**A dry run.** `gh workflow run publish.yml --ref main` builds and checks the package as a
release would, and publishes nothing. Use it after changing `README.md`, which is the page
PyPI shows, or the metadata in `pyproject.toml`.

**On your machine.** The same build, into `dist/`, which git ignores:

```sh
uv build --no-sources
uvx --from dist/hmz-*.whl hmz --version
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
| `… is not X.Y.Z or X.Y.Z-(alpha\|beta\|rc).N`, `… is released already` or `… does not come after …` in `release` | the version named. Nothing was opened | run it again with one that is |
| `GitHub Actions is not permitted to create or approve pull requests` in `release` | the repository's setting | an admin allows it in **Settings → Actions → General**, then run it again after deleting the branch it pushed |
| the release pull request waits for `ci-ok` forever | GitHub holds a run for a contributor whose first pull request has not merged yet, and `github-actions[bot]` is one until the first release | **Approve workflows to run** on the pull request |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published or tagged | fix it on `main`, and open the next version |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml` and environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version already | open the next version: PyPI never takes a version's files twice |
| a failed `publish the release` | PyPI has the release, and GitHub has no tag or release yet | `gh run rerun <run-id> --failed` |

::: details For admins: guarding the `pypi` environment
In **Settings → Environments → pypi**, add yourself and another maintainer as required
reviewers, and limit deployments to the `main` branch. Each upload then waits for a second
person to approve it on the run's page, and nothing but a release from `main` can reach PyPI.
:::

## Next steps

| To | Read |
| --- | --- |
| run a system test, or add one | [Where a test goes](/contributing/#where-a-test-goes) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`publish.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yml) and [`release.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/release.yml) |
