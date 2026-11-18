---
name: review-notes
description: How to read a working agent's changes and write the review it will be handed. Use when reviewing work in a repository, checking a change against the task it was for, or looking for work that was faked, stubbed or special-cased to pass.
---

# Reviewing a round of work

The review is not a report for a person. It is the next prompt of the agent that did the
work, word for word, and it is everything that agent will hear about this round.

## Read the repository, not the summary

What the working agent said it did is a claim. What the repository holds is the evidence.

- `git status` and `git diff` for what actually changed this round.
- Read the changed files themselves, and the files they call into.
- Run what the project runs -- its tests, its linter, its build -- rather than trusting a
  line saying they pass.

## Look for the work that only looks done

In order of how often it is the answer:

1. A test weakened, skipped, or narrowed until it passes.
2. A branch special-cased on the exact input the test uses.
3. A function stubbed with a `TODO`, a `pass`, or a hard-coded return.
4. An error swallowed so a failure reads as a success.
5. A file written but never reached from anything that runs.

Any of these means the round is not done, however much else was built.

## Write it as an instruction

Cite the file and the line. Say what is wrong, and what to do next. Leave nothing to be
inferred: the agent reading this cannot ask a follow-up question, and has no memory of your
last review beyond what the code now holds.

Say it is finished only when everything asked for is implemented, it works, nothing was
faked, and there is no next step worth taking. When it is finished, say what was built and
how it was checked -- that is what the run ends on.
