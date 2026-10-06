"""The table mapping the paths a client speaks onto this machine's own."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from hmz.coganchor.serve.exports import Export, ExportTable


@pytest.mark.parametrize(
    ("spec", "export"),
    [
        ("/w", Export("/w", "/w")),
        ("/w:/srv/real", Export("/w", "/srv/real")),
        ("/w/../v/:/srv", Export("/v", "/srv")),
        ("/w:/srv/../opt", Export("/w", "/opt")),
    ],
)
def test_an_export_reads_as_virtual_and_real(spec: str, export: Export) -> None:
    assert Export.parse(spec) == export


def test_a_real_path_is_made_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert Export.parse("/w:real").real == str(Path.cwd() / "real")


@pytest.mark.parametrize("spec", ["", ":/real", "relative", "relative:/real"])
def test_a_misspelled_export_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match=r"malformed export|must be absolute"):
        Export.parse(spec)


def test_a_table_needs_an_export() -> None:
    with pytest.raises(ValueError, match="at least one export"):
        ExportTable([])


def test_the_longest_export_wins() -> None:
    table = ExportTable.parse(["/w:/a", "/w/deep:/b"], insensitive=False)
    assert [one.virtual for one in table.exports] == ["/w/deep", "/w"]
    assert table.resolve("/w/deep/f") == "/b/f"
    assert table.resolve("/w/other/f") == "/a/other/f"
    assert table.resolve("/w") == "/a"


@pytest.mark.parametrize("path", ["/elsewhere", "/wide/f", "/w/../etc/passwd", "/"])
def test_a_path_outside_every_export_is_refused(path: str) -> None:
    table = ExportTable.parse(["/w:/a"], insensitive=False)
    with pytest.raises(PermissionError) as raised:
        table.resolve(path)
    assert raised.value.errno == errno.EACCES


def test_a_relative_path_is_refused() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        ExportTable.parse(["/w:/a"]).resolve("w/f")


def test_a_path_is_matched_under_its_other_name() -> None:
    table = ExportTable.parse(["/tmp/w:/a"], insensitive=False)
    assert table.resolve("/private/tmp/w/f") == "/a/f"


def test_case_is_folded_only_where_this_filesystem_ignores_it() -> None:
    folding = ExportTable.parse(["/Work:/a"], insensitive=True)
    assert folding.resolve("/work/Sub/F") == "/a/Sub/F"
    exact = ExportTable.parse(["/Work:/a"], insensitive=False)
    with pytest.raises(PermissionError):
        exact.resolve("/work/f")


@pytest.mark.parametrize(
    ("text", "rewritten"),
    [
        ("cat /w/f", "cat /a/f"),
        ("--out=/w/deep/x", "--out=/b/x"),
        ("cd /private/tmp/t && ls", "cd /c && ls"),
        ("cd /tmp/t", "cd /c"),
        ("echo hello/w", "echo hello/w"),
    ],
)
def test_an_argument_naming_an_export_is_rewritten(text: str, rewritten: str) -> None:
    table = ExportTable.parse(["/w:/a", "/w/deep:/b", "/tmp/t:/c"], insensitive=False)
    assert table.rewrite(text) == rewritten


def test_an_identity_export_rewrites_nothing() -> None:
    assert (
        ExportTable.parse(["/w"], insensitive=False).rewrite("cat /w/f") == "cat /w/f"
    )
