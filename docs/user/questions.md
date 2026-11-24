---
title: Answer a flow's questions
description: Answer what a running flow asks you, as a form or in words, hold a role so only you answer it, and say you are away so the flow stops asking.
---

# Answer a flow's questions

A flow can assign a role to a person. When the flow reaches that role, it pauses, asks a question, and waits until somebody answers or marks the role away.

![Humanize Desktop with an epic waiting: a card under the graph asks Ship this change?, with a note, a diff and a table above a short form](/shots/user-questions-asked.svg)

A question has up to three parts: the prompt, context to read, and a place to answer. You answer in words or by filling a form. When a flow needs several values, it asks for them together in one form.

## In the app

Humanize Desktop and the web page work the same way.

Open the epic, which the sidebar marks **Asking**. Each question appears as a card above the message box, headed with who is asking, such as `Reviewer asks`.

### Tell asking from waiting

Check the sidebar word or the top bar badge to see if an epic has an open question.

| State | What it means | How it looks |
| --- | --- | --- |
| `asking` | The epic has a question you have not opened in this browser. | Blinking gold word in the sidebar and dot in the badge. |
| `waiting` | You have seen every open question on the epic's page. | Steady gold. |

Open the epic to change `asking` to `waiting`. Each browser tracks seen questions separately, so other browsers or devices show `asking` until you open the epic there.

### Read the context

Context is a list of blocks. The first block starts open; the rest fold behind a summary line such as `+6 −3 in 1 file`. Click a summary line to open or close its block.

| Block | What you see |
| --- | --- |
| **Note** | Markdown text. |
| **Code** | Source code in a fixed-width font. |
| **Diff** | Added and removed lines per file. Click **Show N more lines** to expand a long diff. |
| **Table** | Rows and columns. Click **Show all N rows** to expand a long table. |
| **Image** | A picture. Click it for full size. |
| **Data** | A foldable JSON tree. |
| **Chart** | A drawn chart, or a data table if the chart cannot be drawn. |

### Answer a form

![A question card: Ship this change?, three context blocks, a Verdict choice of ship or hold, an Announce choice marked Suggested, and a button reading 1 required left](/shots/user-questions-card.svg)

Fill the fields and click **Send answer** (or press <kbd>⌘↵</kbd> on macOS, <kbd>ctrl+enter</kbd> on Windows and Linux). Until every required field is filled, the button reads `N required left`.

Each field uses a control matching its type:

| The field takes | Control |
| --- | --- |
| One of up to five choices | Buttons side by side. The first such field is numbered: press <kbd>1</kbd> to <kbd>9</kbd> when not typing in a text box. |
| One of more choices | A drop-down list, with a search box above it past twelve choices. |
| Yes or no | Two buttons. |
| A number | A number box. |
| Text | Single-line or multi-line input. |
| Markdown | An editor with **Write** and **Preview**. |
| A secret | A masked box with **Show** and **Hide**. |
| A list | One row per item, with **+ Add** and a remove button. A list of up to eight fixed choices is a row of toggle buttons. |
| Anything else | A JSON input box. |

Required fields appear first. Pre-filled fields are marked `Suggested` and can be left as they are. Optional fields are marked `Optional`. In forms with more than three fields, suggested fields fold under **More options (N)**.

Validation errors appear beside their field, such as `This needs an answer.` If the daemon rejects the submission, the card stays open and marks the fields to fix.

### Answer in words

A text question shows a **Your answer** input and an **Answer** button. If preset answers are offered, they appear as numbered buttons above the input; click one or press its number. A chat has no cards: when its coding agent pauses to ask you something, the preset answers appear under its message, and whatever you send from the message box is the answer.

![A form is answered with ship and Send answer; the card folds to one line; the next question is answered by typing Discount codes at checkout](/shots/user-questions-answer.svg)

Once answered, the card folds into one line: `You answered: …`, or the responder's name if somebody else answered. Unanswered questions fold to `Withdrawn:` with the reason. The last three folded cards remain visible until you click **×**.

### Use a flow's custom view

A flow can provide its own interface, called a face, in place of the standard form.

![A question card showing a flow's own view named Release: a coloured diff with Ship it and Hold it buttons, and a Plain form switch](/shots/user-questions-face.svg)

Click **Plain form** to switch to the standard form, and **Back to** the face's name to return. If the face fails or takes longer than 5 seconds to load, the plain form opens automatically; click **Try again** to reload the face.

### Claim a role or go away

Open the side panel and click **People**. This tab appears while the epic runs if the flow includes a person role. It lists each role and who holds it: **You**, another window's name, or **Anyone**.

![The People tab: the reviewer role is held by You, with Release and Away buttons, and Away for all below](/shots/user-questions-people.svg)

| Button | What it does |
| --- | --- |
| **Claim** | Restricts the role to this window. Other windows see the question but cannot answer it. |
| **Take over** | Takes the role from another window. |
| **Release** | Opens the role to anyone again. |
| **Away** / **Back** | Marks this role away or back. |
| **Away for all** / **Back for all** | Marks every role away or back. |

When you mark a role away, its waiting question is withdrawn and the flow continues without an answer.

![A folded card reading Withdrawn: reviewer went away, for the question Ship this change?](/shots/user-questions-away.svg)

## In the terminal

In `hmz`, questions appear in the transcript: the prompt, its context blocks, and either numbered preset answers or `Form of N fields · Enter opens it`.

![The terminal interface: Ship this change?, the agent's note, a diff, a table of checks, and the line saying it is a form of 2 fields that Enter opens](/shots/user-questions-terminal.svg)

The first context block shows up to 40 lines, later blocks up to 12 lines, and tables up to 10 rows. Images and charts appear as a single line linking to the web page.

To answer:

- **Words:** Type your answer and press <kbd>enter</kbd>. Type a number to pick that preset answer.
- **A form:** Press <kbd>enter</kbd> on an empty prompt. The form opens at the bottom while the context stays visible above. When the form has required fields, those with a suggested value fold under `More options (N)`.

![The form opens with enter, 1 picks ship, tab and enter send it; the next question is answered by typing at the prompt](/shots/user-questions-terminal-form.svg)

| Key in the form | What it does |
| --- | --- |
| <kbd>↑</kbd> <kbd>↓</kbd> | Move between fields. |
| <kbd>1</kbd> to <kbd>9</kbd> | Pick the numbered choice. |
| <kbd>←</kbd> <kbd>→</kbd> | Move across a row of choices. |
| <kbd>pgup</kbd> <kbd>pgdn</kbd> | Scroll the transcript above. |
| <kbd>tab</kbd> | Jump to the **Answer** button, which reads `Answer · N required left` until the form is complete. Press <kbd>enter</kbd> on it to send. |
| <kbd>esc</kbd> | Close the form and save your draft for next time. |

You can also type at the prompt while a form waits. Enter a JSON object to submit the entire form at once. Enter any other text to open the form with that text placed into a matching choice or the first empty text field.

The main view answers the oldest waiting question. To answer for a specific role, press <kbd>shift+tab</kbd> until that role's view appears.

### Read the role status lines

Look above the prompt on the right while an epic runs to see one status line per person's role. Each line starts with `<role> · outworlder` and lists its active marks. Chats do not show these lines.

| Mark | Meaning |
| --- | --- |
| `yours` | This terminal claimed the role with `/claim`. |
| `<name>'s` | Another window or terminal holds the role. |
| `away` | The role is marked away with `/afk`. |
| `asking` | The role has a question waiting. |
| `reading` / `unread` | The role's view is on screen, or it has unread lines. |

### Claim a role or go away

| Command | What it does |
| --- | --- |
| `/claim` | On a role's view, restricts that role to this terminal. `/claim off` releases it. |
| `/afk` | On a role's view, marks that role away. On any other view, marks every role you can answer for away. `/afk off` marks you back. |

Both commands accept `on` or `off`, and toggle when run without arguments. While you are away, the status line shows `afk`, followed by the role's name when only some roles are away.

![The terminal after /claim and /afk on the reviewer's view: only you can answer for reviewer, you are away as reviewer, the question withdrawn, the flow done](/shots/user-questions-terminal-away.svg)

## From the command line

`hmz exec` runs non-interactively, so every person role starts away and the run never pauses to ask.

![hmz exec runs the ship_it flow: the agent works and answers, and the run ends without asking anything](/shots/user-questions-exec.svg)

An epic started with `hmz epic start` does ask. Answer it from any shell:

```bash
hmz epic status                      # q1  reviewer  Ship it?
hmz epic answer yes                  # answers the only question waiting
hmz epic answer -q q2 --value '{"verdict": "approve"}'
```

`hmz epic answer` takes words, the number of an offered answer, or with `--value` the JSON of a form. An answer that does not fit the form is refused and the question keeps waiting.

| Command | What it does |
| --- | --- |
| `hmz epic afk [ROLE]` | Sets a role, or every role, away. `--back` sets it back. |
| `hmz epic claim ROLE` | Holds the role while the command runs and answers its questions with the lines typed into it. `--take` takes the role from another window. |
| `hmz epic release ROLE` | Frees a role another window holds, so anyone can answer for it. |

To answer questions from code, use the [Python SDK](/builder/sdk).

## What the flow receives when you are away

| The question asks for | The flow gets |
| --- | --- |
| Words | An empty answer. |
| A form where every field has a suggested value | The suggested values. |
| A form with a field that has no suggested value | An error. The flow handles it, or the epic fails. |

## Good to know

- The daemon remembers away status after you close the window or terminal. Claims end when the window or terminal disconnects.
- If another window holds the role, your card reads `Waiting for` with that window's name and disables input. In the terminal, the form does not open.
- The first answer wins. Later submissions are rejected with the name of the person who answered.
- The browser saves half-filled drafts for 14 days, excluding secrets.
- A flow can also show you context blocks without asking anything. In the app they appear in the role's log; in the terminal, on the role's view.
- The terminal cannot take a role from another window: `/claim` and `/afk` are refused on a role somebody else holds. Use **Take over** in the app.
- Custom faces appear only in the app. The terminal notes that a richer view is available on the web page and displays the plain form.
- Ending or stopping an epic withdraws its waiting questions.
- To write flows that ask questions, see [The person as an agent](/builder/outworlder), [Faces](/builder/faces), and [Build a flow that asks you](/tutorials/ask-the-person).
