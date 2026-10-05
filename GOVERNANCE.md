# Governance

Who decides what happens to humanize, and how. The roles, how decisions are made and how you
join are the same in every humanfia repository, and the organization's
[GOVERNANCE.md](https://github.com/humanfia/.github/blob/main/GOVERNANCE.md) says them once.
This file is what humanize adds to it.

## Maintainers

humanize's maintainers are the people [`.github/CODEOWNERS`](.github/CODEOWNERS) names on its
`*` line. Besides what every repository's maintainers do, they:

- keep `specs/`, the contract the code is held to;
- cut releases, as [Releasing](https://docs.humanfia.ai/humanize/contributing/releasing) says;
- steward what belongs to the whole organization:
  [humanfia/.github](https://github.com/humanfia/.github), with the default files and shared
  workflows every repository inherits, and the organization's settings.

| Maintainer | GitHub |
| --- | --- |
| Zijian Zhang | [@futrime](https://github.com/futrime) |

## What needs a maintainer's explicit approval

On top of the organization's list, these changes are approved by a maintainer explicitly, never
by silence:

- a change to `specs/`;
- a breaking change to the CLI, the flow API or the files humanize keeps.

## Changing this file

A pull request, approved by a majority of the maintainers.
