# Governance

Who decides what happens to humanize, how they decide, and how you join them. The project is
small and this file is kept small to match: it grows when the project does.

It covers [humanfia/humanize](https://github.com/humanfia/humanize).
[humanfia/flowverse](https://github.com/humanfia/flowverse) and the official flow repositories
under [humanfia](https://github.com/humanfia) are run by the same maintainers under the same
rules, unless a repository's own GOVERNANCE.md says otherwise.

## Roles

### Contributors

Anyone who opens an issue, answers one, reviews a pull request or sends one. Nothing to apply
for. [CONTRIBUTING.md](CONTRIBUTING.md) is how.

### Reviewers

Contributors trusted to review one part of the repository. A reviewer is listed against the
paths they review in [`.github/CODEOWNERS`](.github/CODEOWNERS), so GitHub asks them to review
every pull request that touches those paths. A reviewer's approval tells a maintainer the change
is ready; a maintainer still approves before it merges.

There are none yet.

### Maintainers

Maintainers are responsible for the project as a whole. They:

- review and merge pull requests, and decide what is in scope;
- triage issues and set priorities;
- keep `specs/`, the contract the code is held to;
- cut releases;
- handle vulnerability reports, as [SECURITY.md](SECURITY.md) says;
- enforce the [Code of Conduct](CODE_OF_CONDUCT.md);
- grant and remove access to the repositories this file covers.

| Maintainer | GitHub |
| --- | --- |
| Zijian Zhang | [@futrime](https://github.com/futrime) |

## How decisions are made

Decisions are made in public, on issues and pull requests, so that the reasoning is there for
whoever comes next.

- **Lazy consensus.** A proposal goes ahead when nobody with a stake objects in reasonable time.
  For anything bigger than a bug fix, a maintainer waits at least a week before taking silence
  as agreement.
- **A maintainer decides when consensus fails.** With more than one maintainer, by simple
  majority of those who vote; a tie keeps things as they are.
- **Some changes need a maintainer's explicit approval**, never silence:
  - a change to `specs/`;
  - a breaking change to the CLI, the flow API or the files humanize keeps;
  - a new runtime dependency;
  - adding or removing a reviewer or maintainer;
  - a change to this file, the [Code of Conduct](CODE_OF_CONDUCT.md) or the license.
- **Security fixes are decided in private**, then published, as [SECURITY.md](SECURITY.md)
  says.

## Becoming a reviewer

You are ready when you have had several substantial pull requests merged in one part of the
code, and have reviewed others' pull requests there in a way their authors found useful.

Open a pull request that adds you to [`.github/CODEOWNERS`](.github/CODEOWNERS) for those
paths, linking the work that shows it, or ask a maintainer to nominate you. A maintainer
approves it.

## Becoming a maintainer

You are ready when you have been a reviewer for at least three months, have contributed across
more than one part of the project, and your judgment on what belongs in humanize has proved
sound.

An existing maintainer nominates you with a pull request that adds you to the table above. It
stays open for two weeks, and merges if a majority of the maintainers approve it and none
objects.

## Stepping down

Anyone may step down at any time, with a pull request that removes them. A reviewer or
maintainer who has been inactive for six months is asked whether they want to stay; without an
answer in a month, they are moved to an emeritus list here. Coming back is the same process as
joining, made shorter by the record you already have.

## Conflicts of interest

A maintainer does not decide a Code of Conduct report about themselves. A maintainer's own pull
request is reviewed by another maintainer; while there is only one, it merges on green CI, in
public, where anyone can still object.

## Changing this file

A pull request, approved by a majority of the maintainers.
