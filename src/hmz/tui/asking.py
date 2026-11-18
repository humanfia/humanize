"""What an `Outworlder` asks as a schema: its context in the transcript, and the form it is.

A question with a schema is asked whole -- every field of the answer at once -- and read before
it is answered: its prompt is the headline in the transcript, the context it carries sits under
that (a diff as a diff, a table as a table, markdown set as markdown), and the form comes last,
on a sheet of its own that opens with enter on an empty prompt. Nothing opens by itself: a
question arriving while somebody is typing is a line in the transcript, not a screen taken
from under their hands.

The sheet (:class:`Asks`) is the `Form` every other sheet is, laid along the bottom of the
screen so that the context above it stays readable while it is answered. Required fields come
first; those with a value already -- a default, marked `suggested` -- fold under one row until
it is opened, so that a form whose every answer is suggested is an enter away from being sent.
A choice of a few is a row of segments picked with 1-9 or the arrows across, a yes or no is two
worded segments, and what the host refuses is said beside the field it is about. Esc keeps
what was typed for the next time the sheet is opened.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from rich import box
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.syntax import Syntax
from rich.table import Table
from textual.binding import Binding
from textual.widgets import Label, OptionList

from .pick import Action, Form, Key, Question

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rich.console import RenderableType
    from textual import events


__all__ = ["Asks", "Field", "blocks", "fields", "summary", "valued"]

#: The kinds of row a form has, as :class:`hmz.tui.pick.Form` names them.
_WRITES, _STEPS, _OPENS = "writes", "steps", "opens"

#: The row the fields with a value already are folded under, and the row a schema that is not
#: an object is answered on: ids no field name can be, carrying a byte no name has in it.
_MORE = "\x1emore"
_WHOLE = "\x1eanswer"

#: How many choices are laid out as segments; more than that are dropped under the row, as a
#: list to pick from is.
_SEGMENTS = 5

#: The highest choice a digit picks.
_DIGITS = 9

#: How many lines of the first block of context are shown, and of each block after it: the
#: first is what the question is about, and the rest are there to be looked up.
_FIRST_LINES = 40
_LATER_LINES = 12

#: How far in what a question carries is set, under the bullet the question is on.
_IN = "  "

#: What separates the parts of a line.
_DOT = " · "

#: How many rows of a table are shown before the rest are counted rather than drawn.
_TABLE_ROWS = 10

#: The longest description a yes is worded from: "Yes, write tests" reads as an answer, and a
#: paragraph after "Yes," does not.
_WORDED = 40

#: How much of a free-text answer the line saying what was answered quotes.
_QUOTED = 40


class Field(NamedTuple):
    """One field of an answer, as its row of the form asks it.

    Attributes:
      name: The field, as the answer is keyed by it, or "" for a schema that is not an object,
        whose answer is the one value.
      title: What the row is called.
      about: The field's description, said under it.
      kind: `text`, `lines` (text of several lines), `integer`, `number`, `choice`, `list` (a
        value a line) or `json` (anything else, written as JSON).
      required: Whether the answer must have it.
      has_default: Whether the schema gives it a value of its own.
      default: That value.
      choices: What a choice is picked from: what each says, and the value it is.
      items: For a list, the kind of each of its values.
      nullable: Whether it may be null, which a blank row answers.
      secret: Whether it holds a secret: drawn as bullets, and written back as `***`.
    """

    name: str
    title: str
    about: str
    kind: str
    required: bool
    has_default: bool = False
    default: Any = None
    choices: tuple[tuple[str, Any], ...] = ()
    items: str = "text"
    nullable: bool = False
    secret: bool = False


# -- The schema ---------------------------------------------------------------------------------


def _resolved(node: Mapping[str, Any], defs: Mapping[str, Any]) -> dict[str, Any]:
    """A schema node with its `$ref` and lone `allOf` taken in, its own keys winning.

    Args:
      node: The node.
      defs: The schema's `$defs`.

    Returns:
      The node, as a plain dict.
    """
    out: dict[str, Any] = dict(node)
    for _ in range(
        16
    ):  # a reference to itself is a schema to stop reading, not to loop on
        ref = out.get("$ref")
        all_of = out.get("allOf")
        if isinstance(ref, str):
            target = defs.get(ref.rpartition("/")[2])
            rest = {key: value for key, value in out.items() if key != "$ref"}
            out = (
                {**cast("dict[str, Any]", target), **rest}
                if isinstance(target, Mapping)
                else rest
            )
        elif isinstance(all_of, list) and len(cast("list[Any]", all_of)) == 1:
            (only,) = cast("list[Any]", all_of)
            rest = {key: value for key, value in out.items() if key != "allOf"}
            out = (
                {**cast("dict[str, Any]", only), **rest}
                if isinstance(only, Mapping)
                else rest
            )
        else:
            break
    return out


def _label(value: object) -> str:
    """What a choice says: its value, as it is written."""
    return value if isinstance(value, str) else json.dumps(value)


def _yes(about: str) -> str:
    """What the yes of a yes or no says, worded from its description where that is short.

    Args:
      about: The field's description.

    Returns:
      `Yes, write tests` for `Write tests.`, and `Yes` where there is nothing short to word it
      from.
    """
    said = about.strip().rstrip(".")
    if not said or len(said) > _WORDED or "\n" in said:
        return "Yes"
    return f"Yes, {said[:1].lower()}{said[1:]}"


def _field(
    name: str, node: Mapping[str, Any], defs: Mapping[str, Any], *, required: bool
) -> Field:
    """One field, read off its schema.

    Args:
      name: The field's name, or "" for the whole answer.
      node: Its schema.
      defs: The schema's `$defs`.
      required: Whether the answer must have it.

    Returns:
      The field.
    """
    said = _resolved(node, defs)
    # Named by the title written on the field, never by the one its type is defined under.
    title = str(node.get("title") or name.replace("_", " ") or "answer")
    about = str(said.get("description") or "")
    has_default = "default" in said
    default = said.get("default")
    nullable = False
    for union in ("anyOf", "oneOf"):
        among = said.get(union)
        if not isinstance(among, list):
            continue
        options = [
            _resolved(cast("Mapping[str, Any]", one), defs)
            for one in cast("list[Any]", among)
            if isinstance(one, Mapping)
        ]
        rest = [one for one in options if one.get("type") != "null"]
        nullable = nullable or len(rest) < len(options)
        if len(rest) != 1:
            return Field(
                name,
                title,
                about,
                "json",
                required,
                has_default,
                default,
                (),
                "text",
                nullable,
            )
        said = {
            **rest[0],
            **{key: value for key, value in said.items() if key != union},
        }
    kind = said.get("type")
    if isinstance(kind, list):
        kinds = [str(one) for one in cast("list[Any]", kind) if one != "null"]
        nullable = nullable or len(kinds) < len(cast("list[Any]", kind))
        kind = kinds[0] if len(kinds) == 1 else None
    made = Field(
        name, title, about, "json", required, has_default, default, (), "text", nullable
    )
    enum = said.get("enum")
    if isinstance(enum, list):
        return made._replace(
            kind="choice",
            choices=tuple((_label(one), one) for one in cast("list[Any]", enum)),
        )
    if "const" in said:
        return made._replace(
            kind="choice", choices=((_label(said["const"]), said["const"]),)
        )
    if kind == "boolean":
        return made._replace(
            kind="choice", choices=((_yes(about), True), ("No", False))
        )
    if kind in ("integer", "number"):
        return made._replace(kind=str(kind))
    if kind == "string":
        widget = said.get("hmz:widget") or said.get("format")
        if widget in ("secret", "password"):
            return made._replace(kind="text", secret=True)
        return made._replace(
            kind="lines" if widget in ("markdown", "code", "textarea") else "text"
        )
    if kind == "array":
        items = said.get("items")
        item = (
            _field("", cast("Mapping[str, Any]", items), defs, required=True)
            if isinstance(items, Mapping)
            else None
        )
        if item is not None and item.kind in ("text", "integer", "number"):
            return made._replace(kind="list", items=item.kind)
    return made


def fields(schema: Mapping[str, Any] | None) -> list[Field]:
    """The fields of an answer, in the order the schema declares them.

    Args:
      schema: The answer's JSON Schema, as `model_json_schema()` writes it.

    Returns:
      A field per property of an object, or the one unnamed field of a schema that is not one.
    """
    if not isinstance(schema, Mapping):
        return []
    defs = cast(
        "Mapping[str, Any]", schema.get("$defs") or schema.get("definitions") or {}
    )
    root = _resolved(schema, defs)
    properties = root.get("properties")
    if root.get("type") == "object" or isinstance(properties, Mapping):
        needed = {str(one) for one in cast("list[Any]", root.get("required") or [])}
        return [
            _field(
                str(name),
                cast("Mapping[str, Any]", node),
                defs,
                required=name in needed,
            )
            for name, node in cast("Mapping[str, Any]", properties or {}).items()
            if isinstance(node, Mapping)
        ]
    return [_field("", root, defs, required=True)]


def _typed(field: Field, value: object) -> str:
    """A value as the form writes it in a field's row."""
    if field.kind == "choice":
        return next((said for said, one in field.choices if one == value), "")
    if value is None:
        return ""
    if field.kind == "list" and isinstance(value, list):
        return "\n".join(str(one) for one in cast("list[Any]", value))
    if field.kind == "json":
        return json.dumps(value)
    return str(value)


def _read(kind: str, typed: str) -> tuple[Any, str]:
    """A written value read as a kind of value, or what is wrong with it.

    Args:
      kind: `text`, `lines`, `integer` or `number`.
      typed: What was written.

    Returns:
      The value, and "" -- or None, and what is wrong, in plain words.
    """
    if kind == "integer":
        try:
            return int(typed.strip()), ""
        except ValueError:
            return None, "this needs a whole number"
    if kind == "number":
        try:
            number = float(typed.strip())
        except ValueError:
            return None, "this needs a number"
        if not math.isfinite(number):
            return None, "this needs a number"
        return (int(number) if number.is_integer() and "." not in typed else number), ""
    return typed, ""


def _valued(field: Field, typed: str) -> tuple[bool, Any, str]:
    """One field's value as the form now holds it.

    Args:
      field: The field.
      typed: What its row holds.

    Returns:
      Whether it is answered, the value, and what is wrong with it, or "".
    """
    if not typed.strip():
        if field.required and field.nullable:
            return True, None, ""  # nothing, which it may be
        return False, None, "this is needed" if field.required else ""
    if field.kind == "choice":
        for said, value in field.choices:
            if said == typed:
                return True, value, ""
        return False, None, "pick one of the choices"
    if field.kind == "list":
        values: list[Any] = []
        for line in typed.splitlines():
            if not line.strip():
                continue
            value, wrong = _read(field.items, line)
            if wrong:
                return False, None, f"{line.strip()}: {wrong}"
            values.append(value)
        return True, values, ""
    if field.kind == "json":
        try:
            return True, json.loads(typed), ""
        except json.JSONDecodeError as why:
            return False, None, f"this is not valid JSON: {why.msg}"
    value, wrong = _read(field.kind, typed)
    return not wrong, value, wrong


def valued(
    asked: Sequence[Field], typed: Mapping[str, str]
) -> tuple[Any, dict[str, str]]:
    """The answer a form holds, or what is wrong with it, field by field.

    A field left blank that is not required is left out, for the host to take its default.

    Args:
      asked: The fields.
      typed: What each row holds, by field name -- "" for the whole answer.

    Returns:
      The answer -- an object, or the one value of a schema that is not one -- and what is
      wrong, by field name; the answer is None wherever anything is.
    """
    answer: dict[str, Any] = {}
    wrong: dict[str, str] = {}
    for field in asked:
        given, value, problem = _valued(field, typed.get(field.name, ""))
        if problem:
            wrong[field.name] = problem
        elif given:
            answer[field.name] = value
    if wrong:
        return None, wrong
    if len(asked) == 1 and not asked[0].name:
        return answer.get(""), {}
    return answer, {}


def summary(value: object, schema: Mapping[str, Any] | None = None) -> str:
    """An answer said in a line, for the transcript to close the question with.

    Choices as the words picked, written answers quoted and shortened: `approve · 'LGTM'`.

    Args:
      value: The answer.
      schema: The schema it answers, which says which of its values were picked.

    Returns:
      The line, unescaped.
    """
    by = {one.name: one for one in fields(schema)}

    def said(field: Field | None, one: object) -> str:
        if field is not None and field.secret:
            return "***"
        if field is not None and field.kind == "choice":
            return _typed(field, one) or _label(one)
        if isinstance(one, str):
            flat = " ".join(one.split())
            return repr(flat if len(flat) <= _QUOTED else f"{flat[: _QUOTED - 1]}…")
        flat = json.dumps(one)
        return flat if len(flat) <= _QUOTED else f"{flat[: _QUOTED - 1]}…"

    if isinstance(value, Mapping):
        parts = [
            said(by.get(str(name)), one)
            for name, one in cast("Mapping[str, Any]", value).items()
            if one not in (None, "", [], {})
        ]
        return " · ".join(parts) or "the suggested values"
    return said(by.get(""), value)


# -- The context --------------------------------------------------------------------------------


def _clipped(text: str, room: int) -> tuple[str, int]:
    """The first `room` lines of a text, and how many more there were."""
    lines = text.splitlines()
    return "\n".join(lines[:room]), max(len(lines) - room, 0)


def _more(count: int, what: str, web: str) -> str:
    """The line saying how much of a block was left out, and where to read all of it."""
    where = f" -- all of it in the web page: {web}" if web else ""
    return f"{_IN}[dim]… {count} more {what}{escape(where)}[/dim]"


def _changed(patch: str) -> str:
    """What a unified diff changes, in a few words: `+12 -3 in 2 files`, a minus sign."""
    lines = patch.splitlines()
    files = sum(1 for line in lines if line.startswith("+++ ")) or 1
    added = sum(1 for line in lines if line[:1] == "+" and not line.startswith("+++"))
    taken = sum(1 for line in lines if line[:1] == "-" and not line.startswith("---"))
    return f"+{added} \N{MINUS SIGN}{taken} in {files} file{'s' if files != 1 else ''}"


def _code(text: str, language: str) -> Syntax:
    """Code coloured in the terminal's own colours, on its own background."""
    return Syntax(
        text,
        language or "text",
        theme="ansi_dark",
        background_color="default",
        word_wrap=True,
    )


def _counted(count: int, what: str) -> str:
    """A count of something, said as `1 row` or `3 rows`."""
    return f"{count} {what}{'s' if count != 1 else ''}"


def _block(
    block: Mapping[str, Any], *, room: int, web: str
) -> tuple[str, RenderableType | None, str]:
    """One block of context, as the transcript draws it.

    Args:
      block: The block, as its JSON form says it.
      room: How many lines of it to draw.
      web: The web page that shows it whole, or "".

    Returns:
      What it is and how much, unescaped; the block itself, or None for one a terminal
      cannot draw; and the line saying what was left out of it, or "".
    """
    kind = str(block.get("kind") or "")
    if kind == "markdown":
        text, left = _clipped(str(block.get("text") or ""), room)
        return "", Markdown(text), _more(left, "lines", web) if left else ""
    if kind in ("code", "json", "diff"):
        if kind == "diff":
            whole, language = str(block.get("patch") or ""), "diff"
            said = f"diff{_DOT}{_changed(whole)}"
        else:
            whole, language = (
                (str(block.get("text") or ""), str(block.get("language") or ""))
                if kind == "code"
                else (json.dumps(block.get("value"), indent=2), "json")
            )
            said = (
                f"{language or kind}{_DOT}{_counted(len(whole.splitlines()), 'line')}"
            )
        text, left = _clipped(whole, room)
        return said, _code(text, language), _more(left, "lines", web) if left else ""
    if kind == "table":
        columns = [str(one) for one in cast("list[Any]", block.get("columns") or [])]
        rows = [
            cast("list[Any]", one)
            for one in cast("list[Any]", block.get("rows") or [])
            if isinstance(one, list | tuple)
        ]
        # Collapsed past a screenful, as a long table is folded on the web page.
        shown = len(rows) if len(rows) <= room else min(room, _TABLE_ROWS)
        table = Table(*columns, box=box.SIMPLE_HEAD, expand=False)
        for row in rows[:shown]:
            table.add_row(
                *(
                    escape(one if isinstance(one, str) else json.dumps(one))
                    for one in row
                )
            )
        left = len(rows) - shown
        return (
            f"table{_DOT}{_counted(len(rows), 'row')}",
            table,
            _more(left, "rows", web) if left else "",
        )
    # An image or a chart, which a terminal cannot draw: where it can be seen instead.
    spec = block.get("spec")
    about = str(block.get("alt") or "") or (
        str(cast("Mapping[str, Any]", spec).get("title") or "")
        if isinstance(spec, Mapping)
        else ""
    )
    where = f"open in web: {web}" if web else "open the web page (hmz web) to see it"
    return f"{kind or 'block'}{_DOT + about if about else ''}{_DOT}{where}", None, ""


def blocks(context: Sequence[Mapping[str, Any]], *, web: str = "") -> list[object]:
    """Every block of context, in order, as the transcript draws them.

    Each under a line saying what it is and how much -- its title, then `diff · +2 -1 in 1
    file` or `table · 40 rows` -- and set in under the question it belongs to. The first is
    drawn at length, being what the question is about; those after it shorter, each saying
    how much more there is and where to read it whole.

    Args:
      context: The blocks, as their JSON forms say them.
      web: The web page that shows this question, or "" where none is known.

    Returns:
      What to draw, a thing apiece: markup for a line, or something Rich renders.
    """
    drawn: list[object] = []
    for at, block in enumerate(context):
        said, body, more = _block(
            block, room=_FIRST_LINES if at == 0 else _LATER_LINES, web=web
        )
        title = str(block.get("title") or "")
        named = _DOT.join(
            part
            for part in (
                f"[b]{escape(title)}[/b]" if title else "",
                f"[dim]{escape(said)}[/dim]" if said else "",
            )
            if part
        )
        drawn.append("")
        if named:
            drawn.append(f"{_IN}{named}")
        if body is not None:
            drawn.append(Padding(body, (0, 0, 0, len(_IN))))
        if more:
            drawn.append(more)
    return drawn


# -- The sheet ----------------------------------------------------------------------------------


class Asks(Form[Any]):
    """A question with a schema, answered as a form along the bottom of the screen.

    Answered by its `answer` button, which says how many required fields are left until none
    is; the answer is handed to `send`, and the sheet stays up until whoever opened it either
    closes it -- the host took the answer -- or says what the host refused (:meth:`refused`).
    """

    DONE = "answer"

    #: The transcript beneath, scrolled from here: what is asked about stays readable while
    #: it is being answered.
    BINDINGS: ClassVar = [
        Binding("pageup", "context(-1)", "context", show=False),
        Binding("pagedown", "context(1)", "context", show=False),
    ]

    #: Along the bottom, over the transcript rather than instead of it: the context above is
    #: what the question is about, and a form that hid it would be answered from memory.
    CSS: ClassVar[str] = """
    Asks { align: left bottom; background: transparent; }
    Asks #sheet { height: auto; max-height: 80%; padding: 0 2;
                  border-top: solid $primary; background: $background; }
    Asks #choices { height: auto; max-height: 22; }
    Asks #about { padding: 0; }
    Asks #keys { padding: 0; }
    """

    def __init__(
        self,
        question: Mapping[str, Any],
        *,
        send: Callable[[Asks, Any], None],
        keep: Callable[[object], None],
        draft: object = None,
        typed: str = "",
    ) -> None:
        """Initializes the asking.

        Args:
          question: The question, as the `asked` record says it: `text`, `role` and `schema`.
          send: What answering it does with the answer: sends it, and says back how that went.
          keep: What closing it without an answer does with what it holds, for next time.
          draft: What it held when it was last closed, or None to open on the suggestions.
          typed: Words typed at the prompt for it, put in the first written field still
            empty -- a required one first -- so that what was typed is where it would go.
        """
        super().__init__()
        self.question = dict(question)
        self._send = send
        self._keep = keep
        self._fields = fields(cast("Mapping[str, Any] | None", question.get("schema")))
        self._by = {self._held(one): one for one in self._fields}
        #: What is wrong with each field, by row, as the form or the host found it.
        self._problems: dict[str, str] = {}
        #: Whether the answer is on its way, so that it is not sent twice.
        self._sending = False
        kept, expanded = (
            cast("tuple[dict[str, str], bool]", draft)
            if isinstance(draft, tuple)
            else ({}, False)
        )
        for row, one in self._by.items():
            if row in kept:
                self._typed_in[row] = kept[row]
            elif one.has_default:
                self._typed_in[row] = _typed(one, one.default)
                if one.kind != "choice":
                    self._fresh.add(row)
        required = [one for one in self._fields if one.required]
        #: Whether the fields with a value already are shown: folded only under required
        #: ones, since a form of nothing but a fold is a form that hides all it asks.
        self._expanded = expanded or not required or len(required) == len(self._fields)
        if typed.strip():
            self._seeds(typed)

    def _seeds(self, typed: str) -> None:
        """Puts words typed at the prompt where they answer, or says they answer nothing.

        A choice still unanswered that they name, by its words or its number; else the
        first written field still empty, a required one first.

        Args:
          typed: The words.
        """
        empty = [
            one
            for one in self._fields
            if not self._typed_in.get(self._held(one), "").strip()
        ]
        word = typed.strip().casefold()
        for one in empty:
            for at, (said, _) in enumerate(one.choices, 1):
                if word in (said.casefold(), str(at)):
                    self._typed_in[self._held(one)] = said
                    return
        written = sorted(
            (one for one in empty if one.kind in ("text", "lines")),
            key=lambda one: not one.required,
        )
        if written:
            self._typed_in[self._held(written[0])] = typed
            self._expanded = self._expanded or not written[0].required
            return
        # Never dropped without a word: what was typed is said, and where to answer instead.
        self._wrong = f'"{typed.strip()}" answers none of these; pick or write below'

    @staticmethod
    def _held(field: Field) -> str:
        """The row a field is on."""
        return field.name or _WHOLE

    def _segmented(self, row: str) -> Field | None:
        """The field of a row that is a choice of a few, laid out as segments, or None."""
        one = self._by.get(row)
        if one is None or one.kind != "choice" or len(one.choices) > _SEGMENTS:
            return None
        return one

    def _left(self) -> list[str]:
        """The required rows that hold nothing yet, in the order they are asked."""
        return [
            row
            for row, one in self._by.items()
            if one.required
            and not one.nullable
            and not self._typed_in.get(row, "").strip()
        ]

    def draft(self) -> object:
        """What the form holds now, for it to be opened on again."""
        return (dict(self._typed_in), self._expanded)

    # -- What is asked --------------------------------------------------------------------------

    def _ask(self) -> None:
        """Says what is asked: the prompt's first line, and who asks it."""
        prompt = str(self.question.get("text") or "").strip()
        first, _, rest = prompt.partition("\n")
        self.query_one("#asked", Label).update(escape(first or "Answer the form"))
        role = str(self.question.get("role") or "")
        about = " ".join(rest.replace("**", "").replace("`", "").split())
        if len(about) > 160:  # noqa: PLR2004 -- the rest is in the transcript, above
            about = f"{about[:159]}…"
        self.query_one("#about", Label).update(
            escape(
                about
                or (
                    f"{role} asks; the context is in the transcript above"
                    if role
                    else ""
                )
            )
        )
        self._fill()

    def asked(self) -> list[Question]:
        """Required fields first, then the rest, under one fold while it is shut."""
        required = [one for one in self._fields if one.required]
        rest = [one for one in self._fields if not one.required]
        rows = [self._question(one) for one in required]
        if rest and required:
            rows.append(
                Question(
                    _MORE,
                    f"More options ({len(rest)})",
                    "suggested values are filled in" if not self._expanded else "",
                    kind=_OPENS,
                )
            )
        if self._expanded:
            rows.extend(self._question(one) for one in rest)
        return rows

    def _question(self, field: Field) -> Question:
        """One field as its row asks it."""
        row = self._held(field)
        typed = self._typed_in.get(row, "")
        suggested = (
            field.has_default and typed == _typed(field, field.default) and bool(typed)
        )
        about = " · ".join(
            part
            for part in (
                "suggested" if suggested else "",
                "required" if field.required and not typed.strip() else "",
                field.about,
            )
            if part
        )
        return Question(
            row,
            field.title,
            about,
            kind=_STEPS if field.kind == "choice" else _WRITES,
            secret=field.secret,
            needed=field.required and not typed.strip(),
        )

    def choices(self, held: str) -> Sequence[str]:
        """What a choice is picked from, by what each says."""
        one = self._by.get(held)
        return [said for said, _ in one.choices] if one is not None else []

    def lines(self, held: str) -> bool:
        """Whether a row takes several lines: long text, a list, JSON."""
        one = self._by.get(held)
        return one is not None and one.kind in ("lines", "list", "json")

    def opens(self, held: str) -> None:
        """Opens the fold, or shuts it."""
        if held == _MORE:
            self._expanded = not self._expanded
            self._fill()

    def drops(self, row: str) -> bool:
        """A choice of a few is picked where it stands; one of more drops its list."""
        return super().drops(row) and self._segmented(row) is None

    def _line(self, one: Question, *, here: bool) -> str:
        """One row: the fold, a choice as segments, or a written row; and what is wrong."""
        if one.held == _MORE:
            mark = "▾" if self._expanded else "▸"
            said = f" [b]{escape(one.named)}[/b] {mark}"
            if not one.about:
                return said
            about = escape(one.about)
            return f"{said}\n   {about if here else f'[$text-muted]{about}[/]'}"
        field = self._segmented(one.held)
        if field is None:
            line = super()._line(one, here=here)
        else:
            picked = self._typed_in.get(one.held, "")
            segments = "  ".join(
                f"[reverse] {at} {escape(said)} [/reverse]"
                if said == picked
                else f"[$text-muted]{at}[/] {escape(said)}"
                if not here
                else f"{at} {escape(said)}"
                for at, (said, _) in enumerate(field.choices, 1)
            )
            line = f" [b]{escape(one.named)}[/b]\n   {segments}"
            if one.about:
                about = escape(one.about)
                line += f"\n   {about if here else f'[$text-muted]{about}[/]'}"
        problem = self._problems.get(one.held)
        if not problem:
            return line
        # Plain on the row under the cursor, whose own colours a red would sink into.
        said = f"✗ {escape(problem)}"
        return f"{line}\n   {said if here else f'[$error]{said}[/]'}"

    # -- Picking --------------------------------------------------------------------------------

    def _picks(self, row: str, at: int) -> None:
        """Picks one of a choice's segments, by where it stands."""
        field = self._by[row]
        self._typed_in[row] = field.choices[at][0]
        self._problems.pop(row, None)
        self._wrong = ""
        self._fill()

    def on_key(self, event: events.Key) -> None:
        """Takes a digit as picking that choice, on a row of choices, and anything else as typing.

        Args:
          event: The key.
        """
        focus = self.focused
        row = self.under() if focus is None or focus.id == "choices" else ""
        one = self._by.get(row)
        if (
            not self._editing
            and one is not None
            and one.kind == "choice"
            and event.character is not None
            and event.character.isdigit()
        ):
            at = int(event.character)
            event.prevent_default()  # and not taken as typing by the form under this
            event.stop()
            if 1 <= at <= min(len(one.choices), _DIGITS):
                self._picks(row, at - 1)
            return
        # The form's own: a letter on a written row begins writing it.

    def action_across(self, by: int) -> None:
        """Moves a choice of a few along its segments; elsewhere, what the arrows always do.

        Args:
          by: One on, or one back.
        """
        focus = self.focused
        row = self.under() if focus is None or focus.id == "choices" else ""
        field = self._segmented(row)
        if field is None:
            super().action_across(by)
            return
        said = [one for one, _ in field.choices]
        now = self._typed_in.get(row, "")
        at = said.index(now) + by if now in said else (0 if by > 0 else len(said) - 1)
        self._picks(row, max(0, min(at, len(said) - 1)))

    def pressed(self) -> bool:
        """Takes enter on a choice of a few as keeping it and moving on, as a written row does.

        Returns:
          Whether enter was taken.
        """
        row = self.under()
        if not self._editing and self._segmented(row) is not None:
            self.kept(row)
            return True
        return super().pressed()

    def writes(self, row: str, event: events.Key) -> bool:
        """Types into a written row, and lets go of what was wrong with it.

        Returns:
          Whether the key was taken.
        """
        taken = super().writes(row, event)
        if taken:
            self._problems.pop(row, None)
        return taken

    # -- Answering ------------------------------------------------------------------------------

    def actions(self) -> list[Action]:
        """Answering it, which says what is still to be answered first."""
        left = len(self._left())
        return [
            Action(
                "done",
                self.DONE if not left else f"{self.DONE} · {left} required left",
                "sending…" if self._sending else "send this answer",
                self.action_done,
                variant="primary",
            )
        ]

    def _footed(self, *keys: Key) -> None:
        """Says the keys, with 1-9 on a row of choices and esc keeping the draft."""
        row = self.under()
        one = self._by.get(row)
        kept = [
            key for key in keys if key.key not in ("esc", "1-9", "←/→", "pgup/pgdn")
        ]
        if one is not None and one.kind == "choice" and not self._editing:
            kept.insert(0, Key("1-9", "pick"))
            if self._segmented(row) is not None:
                kept.insert(1, Key("←/→", "move"))
        if not self._editing:
            kept.append(Key("pgup/pgdn", "read above"))
        kept.append(Key("esc", "back" if self._editing else "close, keeping the draft"))
        super()._footed(*kept)

    def action_context(self, by: int) -> None:
        """Scrolls the transcript beneath a page, to read what the question is about.

        Args:
          by: One page down, or one up.
        """
        stack = self.app.screen_stack  # pyright: ignore[reportUnknownMemberType]
        under = (
            stack[stack.index(self) - 1]
            if self in stack and stack[0] is not self
            else None
        )
        for one in under.query("#transcript") if under is not None else ():
            if by > 0:
                one.scroll_page_down(animate=False)
            else:
                one.scroll_page_up(animate=False)

    def _holding(self) -> bool:
        """Nothing here is ever lost to closing it, so nothing is said to be unsaved."""
        return False

    def closes(self) -> None:
        """Closes, keeping what was typed for the next time it is opened."""
        self._keep(self.draft())
        self.dismiss(None)

    def _lands(self, rows: Sequence[str]) -> None:
        """Puts the cursor on the first of some rows, opening the fold where it hides one."""
        if not rows:
            return
        if any(
            row not in [self._held(one) for one in self._fields if one.required]
            for row in rows
        ):
            self._expanded = True
        self._fill()
        listing = self.query_one("#choices", OptionList)
        ids = [str(option.id or "").removeprefix("=") for option in listing.options]
        if rows[0] in ids:
            listing.highlighted = ids.index(rows[0])
        listing.focus()
        self._fill()

    def action_done(self) -> None:
        """Sends the answer, or says what is still to be answered and goes to it."""
        if self._sending:
            return
        if self._editing:
            self._keeps_writing()
        typed = {
            one.name: self._typed_in.get(self._held(one), "") for one in self._fields
        }
        answer, wrong = valued(self._fields, typed)
        if wrong:
            self._problems = {
                self._held(self._named(name)): said for name, said in wrong.items()
            }
            left = len(self._left())
            self._wrong = (
                f"{left} required left"
                if left and left == len(wrong)
                else "some answers need a look"
            )
            self._lands([row for row in self._by if row in self._problems])
            return
        self._sending = True
        self._wrong = ""
        self._fill()
        self._send(self, answer)

    def _named(self, name: str) -> Field:
        """The field of a name."""
        return next(one for one in self._fields if one.name == name)

    def refused(self, why: str, errors: Sequence[Mapping[str, Any]] = ()) -> None:
        """Says what the host refused about the answer, beside the fields it is about.

        Args:
          why: The refusal, in its words.
          errors: Its `data.errors`, each a `path` into the answer and a `message`.
        """
        self._sending = False
        problems: dict[str, str] = {}
        loose: list[str] = []
        for one in errors:
            path = [str(part) for part in cast("list[Any]", one.get("path") or [])]
            message = str(one.get("message") or "")
            whole = len(self._fields) == 1 and not self._fields[0].name
            row = _WHOLE if whole else (path[0] if path and path[0] in self._by else "")
            if row:
                deeper = path[0 if whole else 1 :]
                problems.setdefault(
                    row, f"{'.'.join(deeper)}: {message}" if deeper else message
                )
            else:
                loose.append(message)
        self._problems = problems
        # Said once, beside the field, where every refusal has one; under the list only what
        # belongs to no field, or how many fields there are to look at.
        self._wrong = (
            "; ".join(loose)
            if loose
            else f"{_counted(len(problems), 'answer')} to look at"
            if problems
            else why
        )
        if problems:
            self._lands([row for row in self._by if row in problems])
        else:
            self._fill()
