# A face for the person

In this guide you give the person a screen made for one decision. You build `gate`: a builder
works, and the person reviews each round's diff in a review face of the flow's own, then
approves it or sends notes back.

Reach for a face when the form Humanize draws is not the best way to decide: a diff to read file
by file, a picture to mark up, a plan to reorder. Most flows never need one. The form Humanize
draws from your schema is already a whole, keyboard-friendly form, on the web page and at the
prompt alike, and every face falls back to it.

::: info Before you start
- [The person as an agent](/weaver/human-agent): `Outworlder`, `spawn`, `run` with an
  `output_schema`, and context.
- A little HTML and JavaScript. A face is one HTML file, with no build step.
- `hmz web` or Humanize Desktop, to see it: a face is drawn only on the [web page](/user/web).
:::

## How it works

A person can be asked in three ways, each richer than the one before:

| | What the person sees | What you write |
| --- | --- | --- |
| **Text** | The prompt, its context, and a line to type in | `human.run(prompt, …)` |
| **A form** | The prompt, its context, and a whole form drawn from the schema | `output_schema=Model` |
| **A face** | Your own HTML, handed the prompt, its context and the schema | `human.spawn(face=Face.file(…))` |

A face changes how the question looks, never what it asks. Whatever the face sends back goes
through the same check as an answer typed into the form: it must be a value of the schema, or it
is refused with the reasons, and the face is told them. Nothing in a face can reach the run any
other way.

A face belongs to a session. It is mounted when the first question of the session comes up and
stays mounted until the session ends, so it may keep what it likes between questions: the
rounds so far, a draft, where the person had scrolled to.

## Example: a review face

Two files, side by side in the flow's directory:

```text
.hmz/flows/gate/
├── __init__.py
└── review.html
```

### The flow

```python
# .hmz/flows/gate/__init__.py
from typing import Literal

from pydantic import BaseModel, Field

from hmz.flows import (
    Agent,
    AgentCollection,
    Diff,
    EnvCollection,
    Face,
    FlowContext,
    FlowParams,
    LocalEnv,
    Markdown,
    Outworlder,
    ShellEnvMixin,
    Table,
    flow,
)

REVIEW = Face.file("review.html", title="Review")  # ①


class Review(BaseModel):  # ②
    verdict: Literal["approve", "changes"] = Field(description="Ship it, or send it back?")
    notes: str = Field(default="", description="What to tell the builder, word for word.")


class Agents(AgentCollection):
    builder: Agent
    human: Outworlder


class Workspace(LocalEnv, ShellEnvMixin): ...


class Envs(EnvCollection):
    workspace: Workspace


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def gate(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> bool:
    """Build, and let the person approve each round or send it back."""
    builder, human = agents["builder"], agents["human"]
    workspace = envs["workspace"]
    working = await builder.spawn()
    reviewing = await human.spawn(face=REVIEW)  # ③
    said = task
    for round_ in range(1, 4):
        await human.show(  # ④
            [Markdown(text=f"Round {round_}: the builder is working…")], session=reviewing
        )
        await builder.run(said, session=working, env=workspace)
        _, patch, _ = await workspace.exec(["git", "diff"])
        _, numstat, _ = await workspace.exec(["git", "diff", "--numstat"])
        files = tuple(tuple(line.split("\t")) for line in numstat.splitlines())
        review = await human.run(  # ⑤
            f"Round {round_}: ship it?",
            session=reviewing,
            output_schema=Review,
            context=[
                Diff(patch=patch, title="The change"),
                Table(columns=("added", "removed", "file"), rows=files, title="Files"),
            ],
        )
        if review.verdict == "approve":  # ⑥
            return True
        said = review.notes
    return False
```

### The face

```html
<!-- .hmz/flows/gate/review.html -->
<!doctype html>
<meta charset="utf-8" />
<style>
  body { margin: 0; padding: 12px; font: 14px/1.5 var(--sans); color: var(--ink); }
  #status { color: var(--ink-3); margin: 0 0 8px; }
  #prompt { font-weight: 600; margin: 0 0 8px; }
  details { border: 1px solid var(--line); margin: 0 0 8px; }
  summary { padding: 4px 8px; font-family: var(--mono); cursor: pointer; }
  pre { margin: 0; padding: 4px 8px; font: 12px/1.45 var(--mono); overflow-x: auto; }
  .add { background: color-mix(in srgb, var(--done) 15%, transparent); }
  .del { background: color-mix(in srgb, var(--fail) 15%, transparent); }
  [role="group"] { display: flex; gap: 8px; margin: 12px 0; }
  [aria-pressed="true"] { outline: 2px solid var(--cyan); }
  textarea { display: block; width: 100%; min-height: 4em; margin: 4px 0; }
  #error { color: var(--fail); min-height: 1.5em; margin: 0; }
</style>

<p id="status"></p>
<p id="prompt"></p>
<div id="files"></div>
<div role="group" aria-label="Verdict">
  <button type="button" data-verdict="approve" aria-pressed="false">Approve</button>
  <button type="button" data-verdict="changes" aria-pressed="false">Request changes</button>
</div>
<label for="notes">Notes for the builder</label>
<textarea id="notes" aria-describedby="error"></textarea>
<p id="error" role="alert"></p>
<button type="button" id="send" disabled>Send review</button>

<script>
  const $ = (id) => document.getElementById(id)
  let verdict = ''

  function files(patch) {  // ⑦
    $('files').replaceChildren()
    for (const part of patch.split(/^(?=diff --git )/m).filter(Boolean)) {
      const file = document.createElement('details')
      const name = document.createElement('summary')
      const lines = document.createElement('pre')
      name.textContent = (part.match(/^diff --git a\/(\S+)/) || [, 'the change'])[1]
      for (const line of part.split('\n')) {
        const row = lines.appendChild(document.createElement('div'))
        row.textContent = line
        if (/^\+(?!\+\+)/.test(line)) row.className = 'add'
        if (/^-(?!--)/.test(line)) row.className = 'del'
      }
      file.open = $('files').childElementCount === 0
      file.append(name, lines)
      $('files').append(file)
    }
  }

  for (const button of document.querySelectorAll('[data-verdict]')) {
    button.addEventListener('click', () => {
      verdict = button.dataset.verdict
      for (const other of document.querySelectorAll('[data-verdict]')) {
        other.setAttribute('aria-pressed', String(other === button))
      }
      $('send').disabled = false
    })
  }

  hmz.on('ask', ({ prompt, context, errors }) => {  // ⑧
    const diff = context.find((block) => block.kind === 'diff')
    verdict = ''
    for (const button of document.querySelectorAll('[data-verdict]')) {
      button.setAttribute('aria-pressed', 'false')
    }
    $('notes').value = ''
    $('send').disabled = true
    $('prompt').textContent = prompt
    $('status').textContent = ''
    $('error').textContent = errors.length ? errors[0].message : ''
    files(diff ? diff.patch : '')
  })

  hmz.on('show', (context) => {  // ⑨
    $('status').textContent = context.map((block) => block.text ?? '').join(' ')
  })

  $('send').addEventListener('click', async () => {  // ⑩
    $('send').disabled = true
    const answer = await hmz.submit({ verdict, notes: $('notes').value })
    if (!answer.ok) $('error').textContent = answer.errors[0].message
    $('send').disabled = answer.ok
  })
</script>
```

### What each part does

1. **`Face.file("review.html", …)`** reads the face from beside the flow's own module, once,
   as the module loads. `title` names it in the page.
2. **`Review`** is still the question. The face is only how it is drawn; the answer must be a
   `Review` whatever draws it.
3. **`human.spawn(face=REVIEW)`** mounts the face for the whole of that session. Every
   question asked in `reviewing` goes to the same face, which keeps its state between them.
4. **`human.show(…)`** pushes something for the person to see, with nothing to answer. It
   returns at once, and does nothing while the person is away.
5. **`context=[Diff(…), Table(…)]`** goes with the question. Without a face, the form draws them
   above itself; with one, the face is handed them and draws them its own way.
6. **`review.verdict`** is a typed value the flow branches on, however the person answered.
7. **`files(patch)`** splits a unified diff into one fold per file, the first one open. It
   builds every node with `textContent`, so nothing in the diff is ever read as HTML.
8. **`hmz.on('ask', …)`** is called with each question of the session: its `prompt`, its
   `context` as JSON, its `schema` and the `errors` of a try that was refused. This face starts
   each round afresh: no verdict, no notes, and the diff of that round. A face must register it
   as it loads, or the page takes it for broken.
9. **`hmz.on('show', …)`** is called with what `human.show` pushed.
10. **`hmz.submit(value)`** answers. It resolves to `{ok: true}`, or to `{ok: false, errors}`
    where the value does not fit `Review`, and the face says why and lets the person try again.

### Run it

```sh
hmz web
```

At the prompt of the page, start it with `$@local/gate add a subtract function to calc.py`.
While the builder works, the person's card says `Round 1: the builder is working…`. When it
asks, the card holds the review face: one fold per file, the first one open, two verdict
buttons and the notes. **Approve** and **Send review** end the flow with `True`. Request
changes with a note, and the note is the builder's next prompt.

Above the face, beside its title, the card keeps one switch, **Plain form**. Press it and the
same question is the form Humanize draws from `Review`: the verdict as two large buttons, the
notes as a text box, with the diff and the table above them. The switch then says **Back to
Review**, and takes you back to the face as you left it. Your answer goes through either way.

At the prompt in a terminal, there is no face: the question is the form, with a line saying the
web page has a richer view of it. See [Questions](/user/questions).

## The bridge {#the-bridge}

A face reaches the page through one object, `window.hmz`, there before the face's own scripts
run:

| Call | What it does |
| --- | --- |
| `hmz.on("ask", ({prompt, context, schema, errors}) => …)` | Receives each new question of the session. `context` is a list of [blocks](#context-blocks) as JSON, `schema` the JSON Schema or `null` for text, `errors` `[]` or the reasons the last try was refused. |
| `hmz.on("show", (context) => …)` | Receives what the flow pushed with `show`. |
| `hmz.on("theme", (tokens) => …)` | Receives the page's colours, fonts and the measures of its controls -- the width of a line, the radii, a control's heights -- when the person changes theme. They are set on `:root` before the face loads, so `var(--ink)` or `var(--radius-md)` just works. The page draws flat, and `--shadow` is `none`. |
| `hmz.submit(value)` | Answers the current question. Returns a promise of `{ok: true}` or `{ok: false, errors}`; each error is `{path, message}`, `path` the field's path in the value. A text question takes a string. |
| `hmz.resize(height)` | Sets the frame's height in pixels. The frame follows the face's own height without it. |

The frame also styles plain HTML the way the page styles its own: buttons, fields, links and
text use the page's fonts and colours. A face made of plain elements looks at home in both
themes without a line of CSS.

### Context blocks {#context-blocks}

What a flow passes as `context`, as the face receives it:

| In the flow | As JSON |
| --- | --- |
| `Markdown(text=…)` | `{"kind": "markdown", "text"}` |
| `Code(text=…, language="")` | `{"kind": "code", "text", "language"}` |
| `Diff(patch=…)` | `{"kind": "diff", "patch"}`, a unified diff, which may span files |
| `Table(columns=…, rows=…)` | `{"kind": "table", "columns", "rows"}` |
| `Image(data=…, mime=…, alt="")` | `{"kind": "image", "mime", "data", "alt"}`, `data` in base64 |
| `Json(value=…)` | `{"kind": "json", "value"}` |
| `Chart(spec=…)` | `{"kind": "chart", "spec"}`, a [Vega-Lite](https://vega.github.io/vega-lite/) spec |

Every block takes a `title=` too, which the JSON carries as `"title"` where it is set.

## What a face may not do {#what-a-face-may-not-do}

A face is code the flow brought, run in the page that holds your runs, so it runs fenced in:

- **A sandboxed frame.** It runs in an `<iframe sandbox="allow-scripts allow-forms">`, with an
  opaque origin of its own. It has no cookies, cannot read the page, and cannot call the daemon.
- **No network.** Its policy is `connect-src 'none'`: no `fetch`, no WebSocket, no image or
  font from elsewhere. Images come as `data:` or `blob:` URLs, and so do fonts. Everything else
  is in the one HTML file.
- **One way out.** It talks to the page over a channel handed to it once, as it loads, and that
  channel takes `submit` and `resize` and nothing more. What it submits is checked as any answer
  is.
- **The page's own libraries.** It may `import` the scripts the page itself serves under
  `/vendor/`, such as `/vendor/markdown.js`, and nothing else.

## When a face is not drawn {#falling-back}

The person always gets the question. The plain form takes the face's place where:

- the face fails to load, or throws before it calls `hmz.on("ask", …)`;
- it has not called `hmz.on("ask", …)` within 5 seconds of its frame loading;
- the person presses **Plain form**, which they can do at any time, and **Back to …** again;
- the question is answered somewhere with no faces: at the prompt in a terminal, by a
  [stand-in](/weaver/human-agent#stand-in-for-the-person), which is handed the `Face` as
  `params.face` and answers the schema, or by a
  [program](/weaver/human-agent#from-a-program), which is told the face's hash alone.

When the face could not be shown, the card says why above the form, with **Try again**, which
loads the face afresh and, once it answers, shows it in place of the form.

## Faces written by an agent {#face-design}

`Face.design` has an agent write the face, from what it is for and the schema:

```python
from hmz.flows import Face

face = await Face.design(
    designer,  # ①
    session=await designer.spawn(),
    about="A review of a diff, file by file, with a verdict and notes.",  # ②
    output_schema=Review,
)
reviewing = await human.spawn(face=face)
```

1. **`designer`** is any agent of the flow. It is run once with `FACE_GUIDE`, then `about`,
   then the schema's JSON Schema.
2. **`about`** says what the person is deciding and what helps them decide.

It returns the first fenced `html` block the agent wrote, or the whole of what it said where
there is none, titled by the page's `<title>`. An answer with no HTML in it, one that does not
start with a tag, raises `ValueError`. `FACE_GUIDE` is the bridge
above written for an agent: one self-contained HTML file, no network, the page's colours. It is
exported from `hmz.flows`, should you want to prompt an agent yourself.

A face from `Face.design` is fenced in exactly as one you wrote: whatever it does, it can only
submit a value of the schema.

## Check it worked

- On the web page, the card holds the face, and pressing **Plain form** shows the form drawn
  from `Review`, with the diff and the table above it.
- Switch to the plain form and back, then answer from either: the round ends the same way,
  because both send a `Review`.
- In a test, the person is a script, and every question it was asked carries the face's hash:

```python
# tests/test_gate.py
from hmz.sdk import fakes


PATCH = "diff --git a/calc.py b/calc.py\n+def subtract(a, b):\n+    return a - b\n"
GIT = {
    ("git", "diff"): (0, PATCH, ""),
    ("git", "diff", "--numstat"): (0, "2\t0\tcalc.py\n", ""),
}


async def test_the_person_sends_it_back_then_approves() -> None:
    builder = fakes.FakeAgentDriver()
    here = fakes.FakeEnvDriver(run=GIT)
    person = fakes.FakeOutworlder(
        [{"verdict": "changes", "notes": "add a test"}, {"verdict": "approve"}]  # ①
    )

    approved = await fakes.run_fake(
        "gate", "add subtract", agents={"builder": builder}, outworlder=person, local=here
    )

    assert approved is True
    assert builder.prompts == ["add subtract", "add a test"]
    first = person.asks[0]  # ②
    assert first.prompt == "Round 1: ship it?"
    assert first.face  # ③
    assert first.context[0] == {"kind": "diff", "patch": PATCH, "title": "The change"}  # ④
    assert len(first.context[1]["rows"]) == 1
```

1. **A list of mappings** answers question by question, each read as a `Review`.
2. **`person.asks`** is every question put to the person, whole, as the `Ask` a program
   receives; `person.asked` is just their prompts.
3. **`face`** is the face's hash. The script never runs the face: it answers the schema.
4. **`context`** is each block as JSON, exactly as the face is handed it.

## Variations

**A face from a string.** `Face.html(text, title="")` takes the HTML itself, for a face made up
in code. A `Face` is frozen: `face.html` is its HTML, `face.title` its title, and `face.hash`
the SHA-256 of the HTML that every question of its session names it by.

**Text with a face.** A face can serve a question with no schema: `schema` is `null`, and it
submits a string.

**One face, many questions.** Ask several things in one session and the face sees each in turn,
keeping its state. A second session gets a frame of its own.

## Pitfalls

- **One face per session.** A session's face is the one it was spawned with. To change faces,
  spawn another session.
- **A face is never required.** Make sure the schema reads well as a form too, with a
  `description` on every field: the terminal, a caller and anyone who presses **Plain form**
  see that, not your face.
- **Don't trust the face.** Validate in the schema, not in the face. A face's own checks are
  for the person's comfort; the schema's are what the flow gets.
- **Build nodes, don't paste HTML.** A diff or a note from an agent is text. Set it with
  `textContent`, or render Markdown with `/vendor/markdown.js`, which cleans what it renders.
- **No network means none.** A face that loads a library from a CDN fails to load, and the
  person gets the plain form.

## Next steps

- [The person as an agent](/weaver/human-agent): text, forms, context and callers
- [Questions](/user/questions): what the person sees, at the prompt and in the browser
- [In a browser](/user/web): the page that draws faces
- [Reference › `Face`](/reference/flows#face) and [context blocks](/reference/flows#context-blocks)
