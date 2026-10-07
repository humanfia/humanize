# Releasing

In this guide you cut a release of humanize: you publish a release on GitHub, and check that
PyPI has it, with an attestation saying where it was built. It is for the maintainers of
[humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: warning Pre-releases only, so far
humanize has been released as pre-releases alone, so `README.md` and the docs install
`'hmz>=0.1.0b1'`, which lets an installer take one. The first release, `v0.1.0`, also turns
each of those into plain `hmz`.
:::

::: info Before you start
- Maintain or admin access to humanfia/humanize: only those may create a `v*` tag.
- A checkout set up as in [Contributing](/contributing/), for the system tests.
- Optionally, coding agent CLIs signed in on your machine, for the system tests.
:::

## How it works

**`main` is the one long-lived branch, and always releasable.** Every change reaches it as a
pull request, squashed into one commit titled with the pull request's title, once `ci-ok` is
green. `ci-ok` holds the title to Conventional Commits and builds the package, so any commit
on `main` can be released as it is.

**A release is a GitHub release a maintainer publishes.** Publishing it creates its tag, and
runs `publish.yml`, which:

1. checks the tag, as below, before anything is built;
2. builds a wheel and an sdist with `uv build`, giving them the tag's version, and runs
   `twine check --strict`, which fails if PyPI could not render `README.md`;
3. publishes both to [PyPI](https://pypi.org/project/hmz/).

The version lives in the tag alone. `pyproject.toml` says `0.0.0`, and nothing is committed to
release. The release's notes are GitHub's: the title of every pull request merged since the
previous release.

Tags are SemVer, and the package says each in PEP 440. Each tag is released from one branch,
and comes after every earlier release of its line, so a line goes alpha, beta, rc, release:

| Tag | Target | On PyPI |
| --- | --- | --- |
| `v0.2.0` | `main` | `0.2.0` |
| `v0.2.0-alpha.1`, `-beta.1`, `-rc.1` | `main` | `0.2.0a1`, `0.2.0b1`, `0.2.0rc1` |
| `v0.1.1`, and its pre-releases | `release/0.1`, once `v0.1.0` is released | `0.1.1` |

Which version to name, since the last release:

| `main` has | Bump |
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
release, on the commit you are about to release. A release that changes how a backend is
driven runs that backend's `test_harness_*` file; one that changes a built-in flow runs its
`test_flows_*` file:

```sh
uv run pytest tests/system/test_flows_ralph.py
```

Release only when none of them fails: fix it on `main` first. A test that skips names what
this machine lacks. [Where a test goes](/contributing/#where-a-test-goes) has the rest.

## Step 2: Publish the release

On GitHub, **Releases → Draft a new release**:

1. **Tag:** type the new one, such as `v0.2.0`, and create it on publish.
2. **Target:** `main`, or `release/X.Y` for a patch.
3. **Generate release notes**, and read them: they are what the release says.
4. For an alpha, beta or rc, tick **Set as a pre-release**.
5. **Publish release**.

Or the same from a terminal:

```sh
gh release create v0.2.0 --target main --generate-notes
```

Add `--prerelease` for an alpha, beta or rc.

### Check it worked

The run takes a few minutes. Follow it with:

```sh
gh run watch "$(gh run list --workflow publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Once both jobs are green, install it from PyPI:

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

**A patch to an older version.** Only when a fix has to reach users of a version `main` has
moved on from, say `0.1` once `main` is at `0.2`, cut its maintenance branch from the last tag
of that line:

```sh
git push origin v0.1.0:refs/heads/release/0.1
```

Bring each fix over in a pull request against `release/0.1`, after it has merged to `main`:

```sh
git switch -c fix/backport-the-bug origin/release/0.1
git cherry-pick <the commit on main>
gh pr create --base release/0.1 --title "fix: …"
```

Then publish `v0.1.1` targeting `release/0.1`, and untick **Set as the latest release**. The
branch is held to the same rules as `main`; once nobody needs it, delete it.

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
the top of the GitHub release's notes, fix it on `main`, and release the next patch.

Do not delete a release from PyPI. PyPI never takes the same file name twice, so a deleted
version cannot be published again either, and anyone who pinned it can no longer install it.

## Pitfalls

Releases are immutable once published, and a tag is never used twice, so a release whose run
fails before PyPI is left with nothing on PyPI: delete it on GitHub, and publish the next
version.

| The run fails with | Because | Do |
| --- | --- | --- |
| `… is not vX.Y.Z or vX.Y.Z-(alpha\|beta\|rc).N` | the tag. Nothing was built | delete the release, and publish one with a tag that is |
| `… is released from …, and this release targets …` | the target branch is not the tag's | delete the release, and publish the next version from the right branch |
| `… does not come after …` or `… which is not released` | the version is behind its line, or its line has no `.0` yet | delete the release, and publish a version that comes next |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published | delete the release, fix it on `main`, and publish the next version |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yml` and environment `pypi`; then `gh run rerun <run-id> --failed` |
| `File already exists` | PyPI has this version already | publish the next version: PyPI never takes a version's files twice |

::: details For admins: guarding the `pypi` environment
In **Settings → Environments → pypi**, add yourself and another maintainer as required
reviewers, and limit deployments to tags matching `v*`. Each upload then waits for a second
person to approve it on the run's page.
:::

## Next steps

| To | Read |
| --- | --- |
| run a system test, or add one | [Where a test goes](/contributing/#where-a-test-goes) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`publish.yml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yml) |
