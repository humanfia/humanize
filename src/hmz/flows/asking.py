"""What an outworlder is shown alongside a question: diffs, tables, images and the rest.

A prompt says what is asked; its context is what the person reads to decide. Each block is
one thing to read, which a frontend renders as what it is -- a diff with its hunks, a table
with its columns, a chart drawn -- and a caller answering for the person is handed as JSON::

    review = await human.run(
        "Merge this?",
        session=session,
        output_schema=Review,
        context=(Diff(patch=patch, title="the change"), Table(columns=cols, rows=rows)),
    )

The same blocks go to :meth:`~hmz.flows.Outworlder.show`, which tells the person something
and asks nothing. A block's :meth:`as_json` is the form it takes on the wire, whatever reads
it: an `asked` or `shown` record, a hook's caller, an SDK driver.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "Block",
    "Chart",
    "Code",
    "Diff",
    "Image",
    "Json",
    "Markdown",
    "Table",
]

#: The most bytes an image may hold before it is base64'd: 4 MiB.
_IMAGE_BYTES = 4 * 1024 * 1024


def _titled(form: dict[str, Any], title: str) -> dict[str, Any]:
    """`form`, with `"title"` where one is set."""
    if title:
        form["title"] = title
    return form


@dataclass(frozen=True, slots=True, kw_only=True)
class Markdown:
    """Prose, in Markdown, rendered as it would be on a page.

    Attributes:
      text: The Markdown.
      title: What the block is, in a few words, or "" for none.
    """

    text: str
    title: str = ""

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "markdown", "text"}`, with `"title"` where set."""
        return _titled({"kind": "markdown", "text": self.text}, self.title)


@dataclass(frozen=True, slots=True, kw_only=True)
class Code:
    """Source code, shown in a fixed-width face and highlighted where its language is known.

    Attributes:
      text: The code.
      language: Its language, as a fence would name it (`python`, `rust`), or "" for none.
      title: What the block is, in a few words -- a path, say -- or "" for none.
    """

    text: str
    language: str = ""
    title: str = ""

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "code", "text", "language"}`, with `"title"` where set."""
        return _titled(
            {"kind": "code", "text": self.text, "language": self.language}, self.title
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Diff:
    """A change, as `git diff` prints it, shown file by file with its hunks.

    Attributes:
      patch: A unified diff, which may span files.
      title: What the change is, in a few words, or "" for none.
    """

    patch: str
    title: str = ""

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "diff", "patch"}`, with `"title"` where set."""
        return _titled({"kind": "diff", "patch": self.patch}, self.title)


@dataclass(frozen=True, slots=True, kw_only=True)
class Table:
    """Rows under named columns.

    Attributes:
      columns: Each column's heading.
      rows: Each row's cells, one per column, each a JSON value.
      title: What the table is, in a few words, or "" for none.

    Raises:
      ValueError: If a row has more or fewer cells than there are columns.
    """

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    title: str = ""

    def __post_init__(self) -> None:
        """Refuses a row that does not fit the columns."""
        for n, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ValueError(
                    f"row {n} has {len(row)} cells for {len(self.columns)} columns"
                )

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "table", "columns", "rows"}`, with `"title"` where set."""
        return _titled(
            {
                "kind": "table",
                "columns": list(self.columns),
                "rows": [list(row) for row in self.rows],
            },
            self.title,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Image:
    """A picture: a screenshot, a plot already drawn.

    Attributes:
      data: The image's bytes, at most 4 MiB.
      mime: Its media type, `image/png` say.
      alt: What it shows, for whoever cannot see it, or "" for nothing.
      title: What it is, in a few words, or "" for none.

    Raises:
      ValueError: If `data` is more than 4 MiB or `mime` is not an image's.
    """

    data: bytes
    mime: str
    alt: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        """Refuses an image too big to send, or something that is not an image."""
        if len(self.data) > _IMAGE_BYTES:
            raise ValueError(
                f"an image is at most 4 MiB, and this one is {len(self.data)} bytes"
            )
        if not self.mime.startswith("image/"):
            raise ValueError(f"{self.mime!r} is not an image's media type")

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "image", "mime", "data", "alt"}`, `data` base64'd.

        Returns:
          The form, with `"title"` where set.
        """
        return _titled(
            {
                "kind": "image",
                "mime": self.mime,
                "data": base64.b64encode(self.data).decode("ascii"),
                "alt": self.alt,
            },
            self.title,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Json:
    """A JSON value, shown as a tree that folds.

    Attributes:
      value: The value: what `json.dumps` takes.
      title: What it is, in a few words, or "" for none.
    """

    value: Any
    title: str = ""

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "json", "value"}`, with `"title"` where set."""
        return _titled({"kind": "json", "value": self.value}, self.title)


@dataclass(frozen=True, slots=True, kw_only=True)
class Chart:
    """A chart, drawn from a Vega-Lite spec with its data inline.

    Attributes:
      spec: The Vega-Lite spec. Its data goes in `data.values`, which is also what a frontend
        that cannot draw it shows as a table.
      title: What it shows, in a few words, or "" for none.
    """

    spec: Mapping[str, Any]
    title: str = ""

    def as_json(self) -> dict[str, Any]:
        """Its wire form: `{"kind": "chart", "spec"}`, with `"title"` where set."""
        return _titled({"kind": "chart", "spec": dict(self.spec)}, self.title)


#: One block of context, whichever kind.
Block = Markdown | Code | Diff | Table | Image | Json | Chart
