# Security policy

humanize runs coding agents unattended, on your machine and with your logins. A flaw in what
holds those agents back is worth reporting privately, and this file says how.

## Supported versions

humanize is before 1.0. A security fix lands on `main` first and ships in the next release; it
is not backported.

| Version | Supported |
| --- | --- |
| `main` | yes |
| the latest release, pre-releases included | yes |
| any older release | no: upgrade |

## Reporting a vulnerability

**Do not report a vulnerability in a public issue, pull request or discussion.**

Report it privately on GitHub, with
[Report a vulnerability](https://github.com/humanfia/humanize/security/advisories/new) on the
repository's Security tab. Only you and the maintainers see the
report and what is said about it.

Say what you can of:

- what an attacker gains, and what they need first: a flow or flowverse you install, a repository
  an agent works in, a page an agent reads, a place on the network;
- the version (`hmz --version`), the operating system, and the backend;
- the steps, or a proof of concept, that show it;
- a fix, if you have one in mind.

## What happens next

| When | What |
| --- | --- |
| within 3 working days | a maintainer acknowledges the report |
| within 10 working days | whether it is accepted, how severe it is, and the plan |
| within 90 days of the report | the fix is released, sooner for something severe |

We fix it in a private fork, release, then publish a
[GitHub security advisory](https://github.com/humanfia/humanize/security/advisories), with a CVE
where one is warranted. You are credited in the advisory unless you would rather not be.

Please keep the details private until the advisory is out, or until 90 days have passed,
whichever comes first. If a fix needs longer, we will say why and agree a date with you.

## Scope

The [Security](https://docs.humanfia.ai/humanize/user/security) page of the docs is the model
this policy is held to: what a flow lets its agents touch, how that is enforced, and where your
credentials are kept. Read it first.

These are vulnerabilities, for example:

- an agent, or a command it runs, reaching past the permission its flow declared, on a machine
  where humanize says the grant is held;
- a grant that cannot be held being widened rather than refused;
- account credentials humanize keeps reaching someone else: another user on the machine, a log,
  a trace, an export, a crash report, or another account's turn;
- a remote target, a container, an ssh host or the daemon accepting a connection or a command it
  should refuse;
- humanize fetching or running a flow's code from anywhere other than where its flowverse says
  that code is.

These are not, because they are how humanize is meant to work or are already documented:

- **Agents run with approvals bypassed.** Every flow's agents edit files, run commands and make
  commits without asking. That is the design: what holds an agent back is the permission its
  flow declares, not a prompt.
- **A flow is Python, and runs with your privileges.** Installing a flow, or adding a flowverse,
  trusts the people who wrote it.
- **The limits the docs already state**, under
  [What a flow lets its agents touch](https://docs.humanfia.ai/humanize/user/security#what-a-flow-lets-its-agents-touch)
  and [Other things worth knowing](https://docs.humanfia.ai/humanize/user/security#other-things-worth-knowing).
- **What an agent does within the access it was given**, prompt injection included.

Some reports belong elsewhere:

- a coding agent CLI itself, such as Claude Code or Codex: its vendor;
- a flow that is not built into humanize: the repository the flow comes from.

A flow in [humanfia/flowverse](https://github.com/humanfia/flowverse) that is malicious, or a
flaw in that repository itself, is reported here, the same way: the same maintainers run it.
