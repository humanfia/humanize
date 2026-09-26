---
pageClass: hmz-feature
---

# One system, three ways in

You can drive humanize three ways: the terminal interface, the command line and Python. They
run the same flows on the same accounts, and every run lands in the same history, whichever way
it was started.

<HmzSurfaces />

<p class="hmz-note">
Pick what you want to do, and see which way in does it.
</p>

## The three

| | Start with | Reach for it when |
| --- | --- | --- |
| **[The terminal interface](/user/)** | `hmz` | you want to watch a run, steer it, answer its questions, or walk away and come back |
| **[The command line](/user/unattended)** | `hmz exec` | a script, CI or cron runs the flow, with the whole run on one line |
| **[Python](/reference/sdk)** | `hmz.sdk` | a program of yours starts runs, reads them, or looks after the ones left going |

## What they share

- **The same flows.** A name means the same flow whichever way you ask for it: this project's
  first, then yours, then the flowverses. A flowverse added one way shows up in all three.
- **The same accounts.** An account added at the terminal interface is one the command line and
  Python can run as.
- **The same history.** A run started from the command line is in the terminal interface's list
  of runs. It can be exported, traced and picked up like any other.
- **The same checks.** A flow's settings are one model. The command line and Python take the
  same values the terminal interface offers, and a bad value is refused the same way
  everywhere, before any agent starts.

## A flow's settings, drawn for you

The terminal interface turns a flow's settings into a form, with each field's description
beside it. The flow's author writes none of the form:

| In the flow | In the terminal interface |
| --- | --- |
| a yes or no | a switch |
| one of a fixed set | a list to step through |
| a number | stepped one at a time, or typed |
| anything else | typed |

## Where the detail is

- [User Guide](/user/): the terminal interface, from a first run on
- [Run it unattended](/user/unattended): the command line
- [SDK reference](/reference/sdk): Python
- [The terminal can leave](/features/daemon): walking away from a run
- [Params of its own](/weaver/flow-settings): giving a flow settings
