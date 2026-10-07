# Releasing

In this guide you cut a release of humanize: you merge the release pull request, and check
that PyPI has the release, with an attestation saying where it was built. It is for the
maintainers of [humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: warning No release yet
humanize has not been released, so every install is of `main` from GitHub, which calls itself
`0.0.0`. The first release
also turns each `git+https://github.com/humanfia/humanize.git` in `README.md` and the docs
into plain `hmz`, and `SECURITY.md` and the bug report template back to supporting, and asking
for, a release.
:::

::: info Before you start
- Write access to humanfia/humanize, and [`gh`](https://cli.github.com/) signed in to it.
- A checkout set up as in [Contributing](/contributing/).
- Optionally, coding agent CLIs signed in on your machine, for the system tests.
:::

## How it works

**`main` is the one long-lived branch, and always releasable.** Every change reaches it as a
pull request from a branch of its own, squashed into one commit whose message is the pull
request's title, once `ci-ok` is green: CI passing is what lets a change merge, not something
fixed after. `ci-ok` includes the check that the title is a Conventional Commit, because those
titles are what the next version and the changelog are made from.

**A release is a pull request.** [release-please](https://github.com/googleapis/release-please)
keeps one open, titled `chore(main): release X.Y.Z`, and updates it on every push to `main`.
Nobody tags, writes the changelog or runs a workflow by hand.
It bumps `version` in `pyproject.toml` and `uv.lock`, and adds the release's section to
`CHANGELOG.md`, written from the Conventional Commits titles on `main` since the last release.
So the version a checkout says is always the one it was released as, or will be next.
Merging the pull request is the release: it makes the tag, and publishes it.

The next version follows from those titles:

| Since the last release, `main` has | Bump |
| --- | --- |
| a breaking change: a `!` in a pull request's title | minor while the version is `0.x`, major after |
| a feature | minor |
| only fixes | patch |

The changelog lists breaking changes, features, fixes, performance and reverts. Documentation,
refactoring, tests, CI and chores, Dependabot's bumps among them, are left out unless they
break something. Its settings are `release-please-config.json`, and the last version
released is `.release-please-manifest.json`.

Merging the release pull request runs the `publish.yml` workflow on `main`, in four jobs:

1. **release-please** tags the merge commit `vX.Y.Z` and makes a **draft** GitHub release
   with the changelog's section as its notes. On every other push it only updates the release
   pull request, and starts `ci.yml` on it: a pull request a workflow opened or updated starts
   no checks of its own, and `ci-ok` is needed to merge it.
2. **build** builds a wheel and an sdist with `uv build`, and runs `twine check --strict`,
   which fails if PyPI could not render `README.md`.
3. **publish to PyPI** publishes the same two files to [PyPI](https://pypi.org/project/hmz/).
4. **publish the release** attaches them to the GitHub release and takes it out of draft. It
   runs after PyPI, so the release never offers files PyPI refused.

Nobody holds a PyPI token: PyPI lets that one workflow, run in the repository's `pypi`
environment, publish `hmz`, which is called trusted publishing. Every file it publishes carries
an attestation naming the workflow run that built it.

## Step 1: Run the system tests the release needs

CI never runs `tests/system`, which drives real agents on real tasks. Running it is optional,
and costs minutes and tokens a test, so run the files that cover what changed since the last
release, on the release pull request's branch. A release that changes how a backend is
driven runs that backend's `test_harness_*` file; one that changes a built-in flow runs its
`test_flows_*` file:

```sh
gh pr checkout "$(gh pr list --label 'autorelease: pending' --json number --jq '.[0].number')"
uv run pytest tests/system/test_flows_ralph.py
```

Release only when none of them fails: fix it on `main` first, and the release pull request
picks the fix up. A test that skips names what this machine lacks.
[Where a test goes](/contributing/#where-a-test-goes) has the rest.

## Step 2: Merge the release pull request

Read its `CHANGELOG.md` and its version. To change the notes, edit the pull request's
description: release-please takes the release notes from there. Then approve it and merge it,
once `ci-ok` is green.

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

**A version of your choosing.** A commit on `main` whose message ends with the footer
`Release-As: 1.0.0` makes that the next version, whatever the titles say:

```sh
git commit --allow-empty -m "chore: release 1.0.0" -m "Release-As: 1.0.0"
```

It goes to `main` in a pull request, like any commit.

**A patch to an older version.** Only when a fix has to reach users of an older version that
`main` has moved on from, say `1.2.0` once `main` is at `2.x`, cut a maintenance branch from
that version's tag, named after it:

```sh
git push origin v1.2.0:refs/heads/release/1.2.0
```

Then bring each fix over in a pull request against `release/1.2.0`, with a `fix:` title, after
it has merged to `main`:

```sh
git switch -c fix/backport-the-bug origin/release/1.2.0
git cherry-pick <the commit on main>
gh pr create --base release/1.2.0 --title "fix: …"
```

`publish.yml` runs on a push to any `release/*` branch exactly as on `main`: release-please
keeps a release pull request open against the branch, `chore(release/1.2.0): release 1.2.1`,
and merging it publishes `v1.2.1`. A release from such a branch is never marked the latest on
GitHub. Take only fixes onto it: a `feat` would make the next version `1.3.0`, which `main`
may already have released. The branch is held to the same rules as `main`; once nobody
needs it, delete it.

**A check of the package before a release.** The build the release runs, into `dist/`,
which git ignores. Run it after changing `README.md`, which is the page PyPI shows, or the
metadata in `pyproject.toml`:

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
| a failed `release-please` | usually a GitHub hiccup, or the setting below. Nothing was tagged | `gh run rerun <run-id> --failed`. If it says GitHub Actions may not create pull requests, an admin allows it in **Settings → Actions → General** |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published, but the tag and a draft release exist | `gh release delete vX.Y.Z --yes`, keeping the tag, and fix it on `main`: the next release pull request takes the next version |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml` and environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version already | merge the next release: PyPI never takes a version's files twice |
| a failed `publish the release` | PyPI has the release, and the GitHub release is still a draft | `gh run rerun <run-id> --failed` |
| the release pull request waits for `ci-ok` forever | GitHub held a `ci` run for `github-actions[bot]`, which is a first-time contributor until its first pull request merges, or the run `publish.yml` starts failed to start | **Approve workflows to run** on the pull request, or rerun the failed `release-please` job |

::: details For admins: guarding the `pypi` environment
In **Settings → Environments → pypi**, add yourself and another maintainer as required
reviewers, and limit deployments to `main` and `release/*`. Each upload then waits for a
second person to approve it on the run's page, and nothing but a release from those branches
can reach PyPI.
:::

## Next steps

| To | Read |
| --- | --- |
| run a system test, or add one | [Where a test goes](/contributing/#where-a-test-goes) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`publish.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yml) and [`release-please-config.json`](https://github.com/humanfia/humanize/blob/main/release-please-config.json) |
