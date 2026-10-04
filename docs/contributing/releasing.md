# Releasing

In this guide you cut a release of humanize: you bump its version, publish a GitHub release for
it, and check that PyPI has it, with an attestation saying where it was built. It is for the
maintainers of [humanfia/humanize](https://github.com/humanfia/humanize).

Cut a release when `main` holds something people installing `hmz` should have. A release is
never replaced: one that turns out broken is yanked, and the next one fixes it.

::: info Before you start
- Write access to humanfia/humanize, and [`gh`](https://cli.github.com/) signed in to it.
- A checkout set up as in [Contributing](/contributing/).
- Coding agent CLIs signed in on your machine, for
  [the regression matrix](/contributing/regression-matrix).
:::

## How it works

A release is a GitHub release whose tag is `v` followed by the version in `pyproject.toml`:
`v0.2.0` for `0.2.0`. Publishing it starts the `publish.yaml` workflow, which builds the package
from the tagged commit, refuses a tag naming any other version, publishes the package to
[PyPI](https://pypi.org/project/hmz/), and then attaches the same files to the release.

Nobody holds a PyPI token: PyPI lets that one workflow, run in the repository's `pypi`
environment, publish `hmz`, which is called trusted publishing. Every file it publishes carries
an attestation naming the workflow run that built it.

The release notes are generated from the pull requests merged since the last release, grouped
by the labels their titles give them: breaking changes, features, fixes, performance,
documentation, and everything else. Chores that break nothing, and Dependabot's bumps, are left
out.

Which part of the version to bump:

| Since the last release, `main` has | Bump |
| --- | --- |
| a breaking change: a `!` in a pull request's title | `minor` while the version is `0.x`, `major` after |
| a feature | `minor` |
| only fixes | `patch` |

## Step 1: Run the regression matrix

CI runs the system tier with no coding agent CLI installed. The matrix is the part of it that
drives every feature through every CLI you have, so run it on the commit you are about to
release:

```sh
uv run pytest tests/system/matrix --run-agents -m matrix
```

Release only when no cell reads `FAIL` or `XPASS`: fix it on `main` first.
[The regression matrix](/contributing/regression-matrix) says what each mark means.

## Step 2: Bump the version

```sh
git switch main && git pull
git switch -c chore/release-v0.2.0
uv version --bump minor
```

```text
Resolved 53 packages in 11ms
   Building hmz @ file:///home/you/humanize
      Built hmz @ file:///home/you/humanize
Prepared 1 package in 421ms
Uninstalled 1 package in 0.54ms
Installed 1 package in 1ms
 - hmz==0.1.0 (from file:///home/you/humanize)
 + hmz==0.2.0 (from file:///home/you/humanize)
hmz 0.1.0 => 0.2.0
```

That changes `pyproject.toml` and `uv.lock`, and nothing else: the version is written down
there alone. Open a pull request with the two, and merge it once CI is green:

```sh
git commit -am "chore(release): v0.2.0"
gh pr create --fill
```

## Step 3: Publish the release

On `main` with the bump merged, make the release as a draft, tagged at that commit:

```sh
git switch main && git pull
gh release create v0.2.0 --target "$(git rev-parse HEAD)" --generate-notes --draft
```

`gh` prints the draft's address. Open it, read the generated notes, add a line on top if the
release has a headline, and press **Publish release**. Publishing is what starts the upload,
so nothing reaches PyPI while it is a draft.

### Check it worked

The run takes a few minutes. Follow it with:

```sh
gh run watch "$(gh run list --workflow publish.yaml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Its three jobs are `build`, `publish to PyPI` and `attach to the release`. Once all three are
green, install the release from PyPI:

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
files** page: each file names `publish.yaml` on humanfia/humanize as its publisher.

## Variations

**A release candidate.** Bump with `uv version --bump minor --bump rc` for `0.2.0rc1`, and
`--bump rc` again for `0.2.0rc2`. Add `--prerelease` to `gh release create`. Nobody installs it
by accident: `uv` and `pip` skip a pre-release unless it is asked for by number. When it holds,
`uv version --bump stable` gives `0.2.0`.

**A dry run.** `gh workflow run publish.yaml --ref main` builds and checks the package exactly
as a release would, and publishes nothing. Use it after changing `README.md`, which is the
page PyPI shows, or the metadata in `pyproject.toml`.

## Yanking a release

When a release is broken, yank it on PyPI: **Manage project**, the version, **Options**,
**Yank**, with a reason that names the version to use instead. A yanked version stays
installable for anyone who asks for it by number, and nothing else picks it. Then say so at
the top of the GitHub release's notes, fix it on `main`, and release the next `patch`.

Do not delete a release from PyPI. PyPI never takes the same file name twice, so a deleted
version cannot be published again either, and anyone who pinned it can no longer install it.

## Pitfalls

| The run fails with | Because | Do |
| --- | --- | --- |
| `release v0.2.1 publishes pyproject.toml's 0.2.0; tag it v0.2.0` | the tag and the version disagree. Nothing was published | `gh release delete v0.2.1 --cleanup-tag --yes`, then step 3 again with the right tag |
| a failed `twine check` | PyPI would not render `README.md`. Nothing was published | fix it on `main`, delete the release and its tag as above, and run step 3 again |
| `invalid-publisher` in `publish to PyPI` | PyPI's trusted publisher does not describe this workflow | on PyPI, the publisher must name owner `humanfia`, repository `humanize`, workflow `publish.yaml` and environment `pypi` |
| `File already exists` | PyPI has this version already | bump again: PyPI never takes a version's files twice |
| a failed `attach to the release` | PyPI has the release, and the GitHub release lacks its files | `gh run rerun <run-id> --failed` |

::: details For admins: guarding the `pypi` environment
GitHub creates the `pypi` environment the first time the workflow runs. In **Settings →
Environments → pypi**, add yourself and another maintainer as required reviewers, and limit
deployments to tags matching `v*`. Each upload then waits for a second person to approve it on
the run's page, and nothing but a release tag can reach PyPI.
:::

## Next steps

| To | Read |
| --- | --- |
| read the matrix's grid, or add a row to it | [The regression matrix](/contributing/regression-matrix) |
| set up a checkout and run the checks | [Contributing](/contributing/) |
| see every step the release runs | [`publish.yaml`](https://github.com/humanfia/humanize/blob/main/.github/workflows/publish.yaml) |
