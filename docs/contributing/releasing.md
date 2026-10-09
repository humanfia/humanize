# Releasing

In this guide you cut a release of humanize: you run the release workflow with the version,
merge the pull request it opens, and check that PyPI has the release, with an attestation
saying where it was built. It is for the maintainers of
[humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: warning Pre-releases only, so far
humanize has been released as pre-releases alone, so `README.md` and the docs install
`'hmz>=0.1.0b1'`, which lets an installer take one. The first release, `v0.1.0`, also turns
each of those into plain `hmz`.
:::

::: info Before you start
- Write access to humanfia/humanize, and [`gh`](https://cli.github.com/) signed in to it.
- A checkout set up as in [Contributing](/contributing/), for the system tests.
- Optionally, coding agent CLIs signed in on your machine, for the system tests.
:::

## How it works

**`main` is where changes land, and never what is released.** Every change reaches it as a
pull request, squashed into one commit titled with the pull request's title, through the merge
queue once `ci-ok` is green on it as `main` will be. `ci-ok` holds the title to Conventional
Commits and builds the package.

**Every release comes from a `release/X.Y` branch**, pre-releases included: `0.2.0-alpha.1`,
`0.2.0-rc.1`, `0.2.0` and `0.2.1` all come from `release/0.2`. The branch is held to the same
rules as `main`. Three workflows do it:

1. **`release.yml`**, run by hand on `main` with the version, checks it, finds `release/X.Y`,
   and has [release-please](https://github.com/googleapis/release-please) open the release
   pull request against it. For a new `X.Y` it first cuts `release/X.Y` from `main`. The pull
   request bumps `version` in `pyproject.toml` and `uv.lock`, and adds the release's section
   to `CHANGELOG.md`, written from the pull request titles since the last release of that line,
   or, for a new line, since the line before it was cut.
2. **`ci.yml`** runs on the release pull request, started by `release.yml`: a pull request a
   workflow opened starts no checks of its own, and `ci-ok` is needed to merge it.
3. **`publish.yml`**, on a push to a `release/*` branch that merged its release pull request,
   tags the merge commit `vX.Y.Z`, builds a wheel and an sdist, runs `twine check --strict`
   (which fails if PyPI could not render `README.md`), publishes both to
   [PyPI](https://pypi.org/project/hmz/), and only then publishes the GitHub release with
   them attached, so the release never offers files PyPI refused.

`main` itself never says a released version: its `pyproject.toml` says `0.0.0`.

The version is checked before anything is opened:

| You name | It comes from | It must |
| --- | --- | --- |
| `X.Y.0`, or its `-alpha.N`, `-beta.N`, `-rc.N` | `release/X.Y`, cut from `main` if it does not exist | come after every release of `X.Y`; a new `X.Y` must come after every line there is |
| `X.Y.Z` with `Z` above 0, or its pre-releases | `release/X.Y`, which must exist | come after every release of `X.Y`, with `X.Y.0` released |

So a line goes alpha, beta, rc, release, then patches, and never back. On PyPI each version
is in PEP 440: `0.2.0-beta.1` is `0.2.0b1`. An alpha, beta or rc is a pre-release on GitHub,
and the latest release is the newest that is not one, so a patch to an older line never takes
it.

Which version to name, since the last release:

| The line has | Bump |
| --- | --- |
| a breaking change: a `!` in a pull request's title | minor while the version is `0.x`, major after |
| a feature | minor |
| only fixes | patch, from the existing `release/X.Y` |

Nobody holds a PyPI token: PyPI lets `publish.yml`, run in the repository's `pypi`
environment, publish `hmz`, which is called trusted publishing. Every file it publishes carries
an attestation naming the workflow run that built it.

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

## Step 2: Open the release

```sh
gh workflow run release.yml -f version=0.2.0-beta.1
```

Or **Actions → release → Run workflow** on GitHub, from `main`. A minute later the pull request
`chore(release/0.2): release 0.2.0-beta.1` is open against `release/0.2`. Read its
`CHANGELOG.md`: it is what the release will say.

Running it again with the same version brings the pull request up to date with its branch.

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
uvx hmz@0.2.0b1 --version
```

```text
hmz 0.2.0b1
```

Then check that each file's attestation names this repository:

```sh
uvx pypi-attestations verify pypi --repository https://github.com/humanfia/humanize \
  pypi:hmz-0.2.0b1-py3-none-any.whl
```

```text
OK: hmz-0.2.0b1-py3-none-any.whl
```

Do the same for `pypi:hmz-0.2.0b1.tar.gz`. PyPI shows the same on the release's **Download
files** page: each file names `publish.yml` on humanfia/humanize as its publisher.

## Variations

**A change for a line already cut.** A fix that has to reach `0.2`, or a feature for a `0.2`
still in beta, merges to `main` first, then comes over in a pull request against
`release/0.2`:

```sh
git switch -c fix/backport-the-bug origin/release/0.2
git cherry-pick <the commit on main>
gh pr create --base release/0.2 --title "fix: …"
```

Then open the next version of that line, `0.2.1` or `0.2.0-beta.2`, as in Step 2.

**Changing your mind.** Close the release pull request and delete its branch: nothing was
released. A `release/X.Y` cut for it stays, and the next version of that line comes from it.

**A check of the package before a release.** CI's `package` job builds every pull request. The
same on your machine, into `dist/`, which git ignores:

```sh
uv build --no-sources
uvx --from dist/hmz-*.whl hmz --version
```

## Yanking a release

When a release is broken, yank it on PyPI: **Manage project**, the version, **Options**,
**Yank**, with a reason that names the version to use instead. A yanked version stays
installable for anyone who asks for it by number, and nothing else picks it. Then say so at
the top of the GitHub release's notes, fix it, and release the next patch.

Do not delete a release from PyPI, and do not move its tag. PyPI never takes the same file
name twice, so a deleted version cannot be published again either, and anyone who pinned it
can no longer install it.

## Pitfalls

| The run fails with | Because | Do |
| --- | --- | --- |
| `… is not X.Y.Z or X.Y.Z-(alpha\|beta\|rc).N`, `… is released already`, `… does not come after …`, `… which is not released`, `… has nowhere to come from` or `… would start a line before …` in `release` | the version named. Nothing was opened | run it again with one that is |
| `GitHub Actions is not permitted to create or approve pull requests` in `release` | the repository's setting | an admin allows it in **Settings → Actions → General**, then run it again |
| the release pull request waits for `ci-ok` forever | GitHub held a `ci` run for `github-actions[bot]`, a first-time contributor until its first pull request merges | **Approve workflows to run** on the pull request |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published, but the tag and a draft release exist | `gh release delete vX.Y.Z --yes`, keeping the tag; fix it on `main`, bring it to the line, and open the next version |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml` and environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version already | open the next version: PyPI never takes a version's files twice |
| a failed `publish the release` | PyPI has the release, and the GitHub release is still a draft | `gh run rerun <run-id> --failed` |

::: details For admins: guarding the `pypi` environment
In **Settings → Environments → pypi**, add yourself and another maintainer as required
reviewers, and limit deployments to `release/*` branches. Each upload then waits for a second
person to approve it on the run's page.
:::

## Next steps

| To | Read |
| --- | --- |
| run a system test, or add one | [Where a test goes](/contributing/#where-a-test-goes) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`release.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/release.yml), [`publish.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yml) and [`release-please-config.json`](https://github.com/humanfia/humanize/blob/main/release-please-config.json) |
