"""A face: the page a flow ships to ask its outworlder in, in place of the form made for it.

Every question to an outworlder is answered with a value of its schema, and a frontend asks
it with a form made from that schema. A flow that knows better how its question reads -- a
review that wants the diff beside the verdict, a choice best made on a picture -- ships a
face, one HTML file the web page mounts for the session::

    session = await human.spawn(face=Face.file("review.html", title="Review"))
    review = await human.run("Merge this?", session=session, output_schema=Review)

The face is shown each question of the session, and answers it with `hmz.submit(value)`,
which is checked against the schema exactly as the form's answer is: a face can say nothing
the form could not. Where a face cannot be mounted -- the terminal, a caller answering for
the person, a face that breaks -- the form is asked instead, and the person can switch to
the form at any time. :data:`FACE_GUIDE` is the contract a face is written to, for whoever
writes one; :meth:`Face.design` hands it to an agent to write one.
"""

from __future__ import annotations

import hashlib
import html
import inspect
import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, Self, overload

if TYPE_CHECKING:
    import pydantic

    from .agents import Agent, Session
    from .envs import Env

__all__ = ["FACE_GUIDE", "Face"]

#: What an agent is told to write a face to: the bridge, the theme, and how a good one reads.
FACE_GUIDE = """\
# Writing a face

A face is the page a person answers one kind of question in. You write it as ONE
self-contained HTML file. A web page mounts it in a sandboxed frame beside the question,
hands it each question as it is asked, and takes its answer.

## Rules

- One file: inline every `<style>` and `<script>`. Nothing is fetched: no network, no CDN,
  no web fonts, no `fetch`, no external images (use `data:` URLs or inline SVG). The frame's
  Content-Security-Policy blocks all of it.
- Two bundles of the page may be imported as modules, and nothing else:
  `import { render } from "/vendor/markdown.js"` (`render(md)` returns safe HTML) and
  `import { embed } from "/vendor/vega.js"` (`await embed(element, vegaLiteSpec, {theme})`).
- No cookies, `localStorage`, `alert`, `prompt`, popups or navigation: the frame has none.
- Use the theme's CSS variables for every colour and font, never fixed colours, so the face
  looks native in light and dark alike. They are set on `:root` before your code runs:
  `--paper` (background), `--surface` and `--raised` (cards), `--ink`, `--ink-2`, `--ink-3`
  (text, strongest to faintest), `--line` and `--line-strong` (borders), `--live` (accent),
  `--link`, `--done` (good), `--fail` (bad), `--sans` and `--mono` (fonts). Plain elements --
  buttons, inputs, tables -- already look like the page's own.

## The bridge: `window.hmz`

It is there before your scripts run. Register for `ask` straight away: a face that has not
called `hmz.on("ask", ...)` once it has loaded, or that throws first, is replaced by the
plain form.

- `hmz.on("ask", ({prompt, context, schema, errors}) => ...)` -- a new question. `prompt` is
  its text; `context` is a list of blocks to show (below); `schema` is the JSON Schema the
  answer must fit, or `null` for a text answer; `errors` is `[]`, or, when the last answer
  was refused, `[{path, message}]` with `path` the list of keys to the field at fault.
  Questions of one session reach the same frame, so keep state across them where it helps.
- `hmz.on("show", (context) => ...)` -- blocks the flow shows with nothing to answer.
- `hmz.on("theme", (tokens) => ...)` -- the theme changed; `tokens` maps each variable name
  to its value, already set on `:root`.
- `await hmz.submit(value)` -- answers the current question with a value of its schema (an
  object for an object schema; a string where `schema` is `null`). It resolves to
  `{ok: true}`, or to `{ok: false, errors: [{path, message}]}` where the value does not fit;
  show each message beside its field and let the person fix it.
- `hmz.resize(height)` -- sets the frame's height in pixels; call it when the content grows.

A context block is `{kind, title?, ...}`, one of: `markdown {text}`, `code {text, language}`,
`diff {patch}` (a unified diff), `table {columns, rows}`, `image {mime, data, alt}` (`data`
base64), `json {value}`, `chart {spec}` (Vega-Lite).

## Making it easy to answer

- Read, then decide: the prompt is the headline, the context sits beneath it, the controls
  come last. Fold long context behind a one-line summary ("+12 -3 in 2 files").
- Few choices first: up to five options are big buttons, more are a searchable list. A yes
  or no is two buttons worded from the question ("Yes, merge" / "Not yet"), not a checkbox.
- Prefill the schema's defaults and mark them as suggested, so one click answers. Required
  fields first; the ones with defaults may fold under "More options".
- Never punish typing: check fields on blur and on submit, not on each keystroke, and say
  what is wrong in plain words beside the field. Move focus to the first field at fault.
- Show what is left on the submit button ("2 required left"). Ctrl/Cmd+Enter submits; Tab
  goes in reading order. Give every control a real `<label>`.
- After a submit, settle into a one-line summary of the answer until the next question.
- Stay calm: no shaking, no autoplay; respect `prefers-reduced-motion`.

## A small example

```html
<!doctype html>
<meta charset="utf-8">
<style>
  body { margin: 0; padding: 12px; font: 14px var(--sans); color: var(--ink);
         background: var(--paper); }
  .row { display: flex; gap: 8px; margin-top: 12px; }
  .error { color: var(--fail); }
</style>
<h2 id="prompt"></h2>
<label for="notes">Notes</label>
<textarea id="notes" rows="3" style="width: 100%"></textarea>
<p id="error" class="error" role="alert"></p>
<div class="row">
  <button data-verdict="approve">Approve</button>
  <button data-verdict="reject">Request changes</button>
</div>
<script>
  hmz.on("ask", ({ prompt, errors }) => {
    document.getElementById("prompt").textContent = prompt;
    document.getElementById("error").textContent = errors.map((e) => e.message).join("; ");
    hmz.resize(document.body.scrollHeight);
  });
  for (const button of document.querySelectorAll("[data-verdict]")) {
    button.onclick = async () => {
      const notes = document.getElementById("notes").value;
      const said = await hmz.submit({ verdict: button.dataset.verdict, notes });
      if (!said.ok) {
        document.getElementById("error").textContent = said.errors[0].message;
      }
    };
  }
</script>
```
"""

#: The first fenced HTML block of what an agent said, closed by a fence on a line of its own
#: -- so a fence inside the page, in a script's string say, does not end it.
_FENCED = re.compile(
    r"^[ \t]*```html[^\n]*\n(.*?)^[ \t]*```[ \t]*$",
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)

#: How HTML starts: a doctype, a comment or a tag.
_TAG = re.compile(r"<[a-zA-Z!]")

#: A document's own title.
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


class _MakesFace(Protocol):
    """`Face.html`: a face of the given HTML."""

    def __call__(self, text: str, /, *, title: str = "") -> Face: ...


class _Html:
    """`Face.html`: on the class, the maker of a face from HTML; on a face, its HTML."""

    @overload
    def __get__(self, instance: None, owner: type[Face]) -> _MakesFace: ...

    @overload
    def __get__(self, instance: Face, owner: type[Face]) -> str: ...

    def __get__(self, instance: Face | None, owner: type[Face]) -> _MakesFace | str:
        if instance is None:

            def make(text: str, /, *, title: str = "") -> Face:
                return owner(text, title=title)

            return make
        text: str = object.__getattribute__(instance, "_text")
        return text


class Face:
    """One HTML file a flow ships to ask its outworlder in, and what it is called.

    Made with :meth:`file`, :meth:`html` or :meth:`design`, and given to
    :meth:`~hmz.flows.Outworlder.spawn`. Frozen: two faces of the same HTML and title are
    equal.

    Attributes:
      html: The HTML, one self-contained file written to :data:`FACE_GUIDE`. On the class
        itself, `Face.html(text, title=...)` makes a face of `text`.
      title: What the face is, in a few words, which a frontend names it by; "" for none.
    """

    __slots__ = ("_hash", "_text", "_title")

    html = _Html()

    _text: str
    _title: str
    _hash: str

    def __init__(self, html: str, title: str = "") -> None:
        """A face of `html`, called `title`."""
        object.__setattr__(self, "_text", html)
        object.__setattr__(self, "_title", title)
        object.__setattr__(
            self, "_hash", hashlib.sha256(html.encode("utf-8")).hexdigest()
        )

    @property
    def title(self) -> str:
        """What the face is, in a few words; "" for none."""
        return self._title

    @property
    def hash(self) -> str:
        """The SHA-256 of its HTML, in hex: what an `asked` record names it by."""
        return self._hash

    def __setattr__(self, name: str, value: object) -> None:
        """Refuses every change: a face is frozen."""
        raise FrozenInstanceError(f"cannot assign to field {name!r}")

    def __delattr__(self, name: str) -> None:
        """Refuses every change: a face is frozen."""
        raise FrozenInstanceError(f"cannot delete field {name!r}")

    def __eq__(self, other: object) -> bool:
        """Whether `other` is a face of the same HTML and title."""
        if not isinstance(other, Face):
            return NotImplemented
        return (self._hash, self.title) == (other._hash, other.title)

    def __hash__(self) -> int:
        """Its HTML's and title's."""
        return hash((self._hash, self.title))

    def __repr__(self) -> str:
        """The face's title and hash, never its whole HTML."""
        return f"Face(title={self.title!r}, hash={self._hash[:12]!r})"

    @classmethod
    def file(cls, path: str | Path, *, title: str = "") -> Self:
        """A face of an HTML file, read now.

        Args:
          path: The file. A relative path is from the directory of the module calling this
            -- the flow's own -- wherever the run was started.
          title: What the face is called.

        Returns:
          The face.

        Raises:
          OSError: If the file cannot be read.
        """
        where = Path(path)
        if not where.is_absolute():
            where = _calling_dir() / where
        return cls(where.read_text(encoding="utf-8"), title=title)

    @classmethod
    async def design(
        cls,
        agent: Agent,
        *,
        session: Session,
        about: str,
        output_schema: type[pydantic.BaseModel] | None = None,
        env: Env | None = None,
    ) -> Self:
        """A face an agent writes, to :data:`FACE_GUIDE`, in one turn of a session of its own.

        Args:
          agent: Who writes it.
          session: The session of `agent` the turn is taken in.
          about: What the face is for: the questions it will be asked and how they read best.
          output_schema: The schema its questions' answers fit, which the agent is shown, or
            None for questions answered in text.
          env: Where the turn works, as for :meth:`~hmz.flows.Agent.run`.

        Returns:
          The face of the first fenced `html` block of what the agent said, or of all it said
          where it fenced none, called by the document's `<title>`.

        Raises:
          ValueError: If what the agent said holds no HTML: no fenced block, and not a page
            from its first character.
        """
        prompt = f"{FACE_GUIDE}\n# The face to write\n\n{about}\n"
        if output_schema is not None:
            schema = json.dumps(output_schema.model_json_schema(), indent=2)
            prompt += f"\nIts answers fit this JSON Schema:\n\n```json\n{schema}\n```\n"
        else:
            prompt += "\nIts answers are text: `hmz.submit` takes a string.\n"
        prompt += "\nAnswer with the whole file in one ```html block.\n"
        said = await agent.run(prompt, session=session, env=env)
        fenced = _FENCED.search(said)
        page = (fenced.group(1) if fenced else said).strip()
        if not _TAG.match(page):
            raise ValueError(f"{agent.role or 'the agent'} wrote no HTML for a face")
        named = _TITLE.search(page)
        title = " ".join(html.unescape(named.group(1)).split()) if named else ""
        return cls(page, title=title)


def _calling_dir() -> Path:
    """The directory of the module that called the caller of this, or the working one."""
    frame = inspect.currentframe()
    try:
        caller = frame.f_back.f_back if frame and frame.f_back else None
        where: Any = caller.f_globals.get("__file__") if caller else None
    finally:
        del frame
    return Path(where).resolve().parent if isinstance(where, str) else Path.cwd()
