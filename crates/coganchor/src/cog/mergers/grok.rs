//! Grok Build's merger: one `[model.*]` entry into the virtual home's copy of `config.toml`.
//! Port of `hmz.coganchor.agents.grok._entered`.
//!
//! Python edits the file with `tomlkit`, which keeps everything of the user's -- comments,
//! order, spacing -- and adds the entry where it puts a new table. No crate here does that
//! (`toml_edit` keeps a file too, but lays a new table out its own way), so this reads the
//! file only as far as it must -- where its tables and keys are -- and writes the entry in as
//! text, where and as `tomlkit` 0.13 writes it:
//!
//! - into a file with no `model` table, at its end;
//! - into one with `[model]` or `[model.*]` tables, after the first run of them;
//! - into one saying `model.x = ...` at its top level, after the last such line;
//! - over an entry of the same name, in its place, its own subtables with it;
//!
//! each after one blank line unless the text before already ends in one. Its line endings are
//! `\n`, as Python's `read_text` reads any and `write_text` writes them. What `tomlkit` does
//! with the rarer shapes -- `model` as an inline table or an array of tables, an entry of that
//! name said as a key rather than a table -- is refused instead, as is a file that is not TOML
//! (a key or a table said twice among it).

use std::collections::HashSet;
use std::fs;
use std::io;
use std::path::Path;

use serde_json::{Map, Value};

use super::{refused, said_field};

/// `_entered(home, said)`: `said` holds `named`, the entry's name, and `entry`, what it holds.
pub fn entered(home: &Path, said: &Value) -> io::Result<()> {
    let named = said_field(said, "named")?
        .as_str()
        .ok_or_else(|| refused("grok: `named` is not a string"))?;
    let entry = said_field(said, "entry")?
        .as_object()
        .ok_or_else(|| refused("grok: `entry` is not a table"))?;
    let at = home.join("config.toml");
    let text = match fs::read(&at) {
        Ok(bytes) => String::from_utf8(bytes).map_err(|error| unreadable(&at, &error))?,
        Err(error) if error.kind() == io::ErrorKind::NotFound => String::new(),
        Err(error) => return Err(error),
    };
    // Universal newlines, as `read_text` reads a file.
    let text = text.replace("\r\n", "\n").replace('\r', "\n");
    let written = with_entry(&text, named, entry).map_err(|error| unreadable(&at, &error))?;
    fs::write(&at, written)
}

/// The refusal `_reading` raises for a file that is not TOML.
fn unreadable(at: &Path, error: &dyn std::fmt::Display) -> io::Error {
    refused(format!(
        "{} cannot be read as TOML ({error}): correct it",
        at.display()
    ))
}

/// The text of a `config.toml` (its lines ending in `\n`) with the entry `named` in its
/// `model` table.
pub fn with_entry(text: &str, named: &str, entry: &Map<String, Value>) -> Result<String, String> {
    let scanned = scan(text, named)?;
    match scanned.top_model {
        Some(TopModel::Inline) => {
            return Err("its `model` is an inline table, which Humanize does not add to".into());
        }
        Some(TopModel::Other) => return Err("its `model` is not a table".into()),
        _ => {}
    }
    if scanned.names_entry {
        return Err(format!(
            "it says `model.{named}` as a key, which Humanize does not write over"
        ));
    }
    let ours = |header: &Header| header.path.first().is_some_and(|one| one == "model");
    if scanned.headers.iter().any(|one| ours(one) && one.array) {
        return Err("its `model` is an array of tables".into());
    }
    let first = scanned.headers.iter().position(ours);
    let prefix = first.map_or("model", |index| scanned.headers[index].first_raw.as_str());
    let table = table(prefix, named, entry)?;
    let entry_or_under = |header: &Header| {
        header.path.len() >= 2 && header.path[0] == "model" && header.path[1] == named
    };
    // An entry of that name already there is replaced where it is, its subtables with it.
    if let Some(index) = scanned
        .headers
        .iter()
        .position(|one| one.path.len() == 2 && entry_or_under(one))
    {
        let start = scanned.headers[index].start;
        let mut last = index;
        while scanned.headers.get(last + 1).is_some_and(entry_or_under) {
            last += 1;
        }
        let end = scanned
            .headers
            .get(last + 1)
            .map_or(text.len(), |next| next.start);
        // The blank lines after it are kept, unless it had subtables, which go with them.
        let trailing = if last == index {
            let section = &text[start..end];
            let content = section.trim_end_matches([' ', '\t', '\n']);
            match section[content.len()..].find('\n') {
                Some(at) => &section[content.len() + at + 1..],
                None => "",
            }
        } else {
            ""
        };
        return Ok(format!(
            "{}{table}{trailing}{}",
            &text[..start],
            &text[end..]
        ));
    }
    let at = match (first, scanned.dotted_end) {
        // After the first run of `model` tables: before the line of the next table's header.
        (Some(index), _) => {
            let mut after = index;
            while scanned.headers.get(after + 1).is_some_and(ours) {
                after += 1;
            }
            scanned
                .headers
                .get(after + 1)
                .map_or(text.len(), |next| next.start)
        }
        // After the line of its last top-level `model.x = ...`.
        (None, Some(end)) => end,
        (None, None) => text.len(),
    };
    let before = &text[..at];
    Ok(format!(
        "{before}{}{table}{}",
        separator(before),
        &text[at..]
    ))
}

/// What `tomlkit` puts between what is already there and a table appended after it.
///
/// The whitespace after the last line with anything on it, less that line's own ending, is
/// an item of its own to `tomlkit`; a table after one ending a line follows it directly, and
/// one after nothing (or a line of spaces, which it takes for the table's indentation) too.
/// Otherwise it starts a line of its own after a blank one.
fn separator(before: &str) -> &'static str {
    if before.is_empty() {
        return "";
    }
    let content = before.trim_end_matches([' ', '\t', '\n']);
    let tail = &before[content.len()..];
    let item = if content.is_empty() {
        tail
    } else {
        match tail.find('\n') {
            Some(at) => &tail[at + 1..],
            None => "",
        }
    };
    if item.is_empty() {
        return "\n";
    }
    if item.ends_with('\n') {
        return "";
    }
    let last = item.rsplit('\n').next().unwrap_or("");
    if last.chars().all(|one| one == ' ') {
        ""
    } else {
        "\n"
    }
}

/// The table `[<prefix>.<named>]` holding `entry`, as `tomlkit` writes one made of a dict.
fn table(prefix: &str, named: &str, entry: &Map<String, Value>) -> Result<String, String> {
    let mut out = format!("[{prefix}.{}]\n", key(named));
    for (name, value) in entry {
        let value = match value {
            Value::String(text) => string(text),
            Value::Bool(true) => "true".to_owned(),
            Value::Bool(false) => "false".to_owned(),
            Value::Number(number) if number.is_i64() || number.is_u64() => number.to_string(),
            _ => {
                return Err(format!(
                    "the entry's {name} is not a string, a boolean or an integer"
                ));
            }
        };
        out.push_str(&format!("{} = {value}\n", key(name)));
    }
    Ok(out)
}

/// A key as `tomlkit` writes it: bare where it can be, a basic string where not.
fn key(name: &str) -> String {
    if !name.is_empty()
        && name
            .chars()
            .all(|one| one.is_ascii_alphanumeric() || one == '-' || one == '_')
    {
        name.to_owned()
    } else {
        string(name)
    }
}

/// A basic string as `tomlkit` escapes one, `\e` (TOML 1.1) among its escapes.
fn string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for one in text.chars() {
        match one {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\u{c}' => out.push_str("\\f"),
            '\r' => out.push_str("\\r"),
            '\u{1b}' => out.push_str("\\e"),
            '\u{0}'..='\u{1f}' | '\u{7f}' => out.push_str(&format!("\\u{:04x}", one as u32)),
            _ => out.push(one),
        }
    }
    out.push('"');
    out
}

/// What a `config.toml` says at its top level of `model`, before any table.
#[derive(Debug, PartialEq)]
enum TopModel {
    /// `model.x = ...`: dotted keys, after the last of which `tomlkit` puts the table.
    Dotted,
    /// `model = { ... }`.
    Inline,
    /// `model = <anything else>`.
    Other,
}

/// One table header: where its line starts, its key path, and its first key as written.
#[derive(Debug)]
struct Header {
    start: usize,
    path: Vec<String>,
    first_raw: String,
    array: bool,
}

#[derive(Debug, Default)]
struct Scanned {
    headers: Vec<Header>,
    top_model: Option<TopModel>,
    /// Where the line of the last top-level `model.x = ...` ends.
    dotted_end: Option<usize>,
    /// Whether the entry's name is said as a key: `model.<named>... = ` at the top level, or
    /// `<named>... = ` in `[model]`.
    names_entry: bool,
}

/// Reads a TOML document as far as its headers and keys, refusing what is plainly not TOML:
/// a line that is neither a header, a key and its value, a comment nor blank; a string, array
/// or inline table left open; a value that is none; a key or a table said twice.
fn scan(text: &str, named: &str) -> Result<Scanned, String> {
    let mut scanned = Scanned::default();
    let mut tables: HashSet<Vec<String>> = HashSet::new();
    let mut keys: HashSet<(usize, Vec<String>)> = HashSet::new();
    let mut table: Vec<String> = Vec::new();
    let bytes = text.as_bytes();
    let mut at = 0;
    let mut line = 1;
    while at < bytes.len() {
        let start = at;
        skip_space(bytes, &mut at);
        let wrong = |why: String| format!("{why} at line {line}");
        match bytes.get(at) {
            None => break,
            Some(b'\n') => {
                at += 1;
                line += 1;
            }
            Some(b'#') => skip_comment(bytes, &mut at),
            Some(b'[') => {
                at += 1;
                let array = bytes.get(at) == Some(&b'[');
                if array {
                    at += 1;
                }
                let raw_start = at;
                let (path, first_end) = key_path(text, &mut at).map_err(wrong)?;
                let first_raw = text[raw_start..first_end].to_owned();
                let closing: &[u8] = if array { b"]]" } else { b"]" };
                if !bytes[at..].starts_with(closing) {
                    return Err(wrong("a table header is not closed".into()));
                }
                at += closing.len();
                end_of_line(bytes, &mut at).map_err(wrong)?;
                if !array && !tables.insert(path.clone()) {
                    return Err(wrong(format!("the table {path:?} is said twice")));
                }
                table.clone_from(&path);
                scanned.headers.push(Header {
                    start,
                    path,
                    first_raw,
                    array,
                });
            }
            Some(_) => {
                let (path, _) = key_path(text, &mut at).map_err(wrong)?;
                skip_space(bytes, &mut at);
                if bytes.get(at) != Some(&b'=') {
                    return Err(wrong("expected `=` after a key".into()));
                }
                at += 1;
                skip_space(bytes, &mut at);
                let value_start = at;
                let lines = value(text, &mut at).map_err(wrong)?;
                end_of_line(bytes, &mut at).map_err(wrong)?;
                // Keys are told apart per table, each header (an array's each) a table.
                if !keys.insert((scanned.headers.len(), path.clone())) {
                    return Err(wrong(format!("the key {path:?} is said twice")));
                }
                if scanned.headers.is_empty() && path[0] == "model" {
                    scanned.top_model = Some(if path.len() > 1 {
                        scanned.dotted_end = Some((at + 1).min(bytes.len()));
                        scanned.names_entry |= path[1] == named;
                        TopModel::Dotted
                    } else if bytes[value_start] == b'{' {
                        TopModel::Inline
                    } else {
                        TopModel::Other
                    });
                }
                if table == ["model"] && path[0] == named {
                    scanned.names_entry = true;
                }
                line += lines;
            }
        }
    }
    Ok(scanned)
}

fn skip_space(bytes: &[u8], at: &mut usize) {
    while matches!(bytes.get(*at), Some(b' ' | b'\t')) {
        *at += 1;
    }
}

fn skip_comment(bytes: &[u8], at: &mut usize) {
    while !matches!(bytes.get(*at), None | Some(b'\n')) {
        *at += 1;
    }
}

/// What may follow a header or a value on its line: spaces, a comment, the line's end.
fn end_of_line(bytes: &[u8], at: &mut usize) -> Result<(), String> {
    skip_space(bytes, at);
    if bytes.get(*at) == Some(&b'#') {
        skip_comment(bytes, at);
    }
    if bytes.get(*at) == Some(&b'\r') {
        *at += 1;
    }
    match bytes.get(*at) {
        None => Ok(()),
        Some(b'\n') => Ok(()),
        Some(_) => Err("unexpected text after a value".into()),
    }
}

/// A basic string at `at`, single-line, its escapes read.
fn basic(text: &str, at: &mut usize) -> Result<String, String> {
    let bytes = text.as_bytes();
    *at += 1;
    let mut out = String::new();
    loop {
        match bytes.get(*at) {
            None | Some(b'\n') => return Err("a string is not closed".into()),
            Some(b'"') => {
                *at += 1;
                return Ok(out);
            }
            Some(b'\\') => {
                let escaped = bytes.get(*at + 1).copied();
                *at += 2;
                match escaped {
                    Some(b'b') => out.push('\u{8}'),
                    Some(b't') => out.push('\t'),
                    Some(b'n') => out.push('\n'),
                    Some(b'f') => out.push('\u{c}'),
                    Some(b'r') => out.push('\r'),
                    Some(b'e') => out.push('\u{1b}'),
                    Some(b'"') => out.push('"'),
                    Some(b'\\') => out.push('\\'),
                    Some(kind @ (b'u' | b'U' | b'x')) => {
                        let width = match kind {
                            b'u' => 4,
                            b'U' => 8,
                            _ => 2,
                        };
                        let digits = text
                            .get(*at..*at + width)
                            .ok_or("a string's escape is cut short")?;
                        let code = u32::from_str_radix(digits, 16)
                            .map_err(|_| "a bad escape in a string")?;
                        out.push(char::from_u32(code).ok_or("a bad escape in a string")?);
                        *at += width;
                    }
                    _ => return Err("a bad escape in a string".into()),
                }
            }
            Some(_) => {
                let rest = &text[*at..];
                let one = rest.chars().next().unwrap_or('\0');
                out.push(one);
                *at += one.len_utf8();
            }
        }
    }
}

/// A literal string at `at`, single-line.
fn literal(text: &str, at: &mut usize) -> Result<String, String> {
    let begin = *at + 1;
    match text[begin..].find(['\'', '\n']) {
        Some(end) if text.as_bytes()[begin + end] == b'\'' => {
            *at = begin + end + 1;
            Ok(text[begin..begin + end].to_owned())
        }
        _ => Err("a string is not closed".into()),
    }
}

/// A dotted key, its parts unquoted; and where its first part's spelling ends, the spaces
/// after it included: at the first dot, or the key's end.
fn key_path(text: &str, at: &mut usize) -> Result<(Vec<String>, usize), String> {
    let bytes = text.as_bytes();
    let mut path = Vec::new();
    let mut first_end = None;
    loop {
        skip_space(bytes, at);
        let part = match bytes.get(*at) {
            Some(b'"') => basic(text, at)?,
            Some(b'\'') => literal(text, at)?,
            Some(one) if bare(*one) => {
                let begin = *at;
                while bytes.get(*at).is_some_and(|one| bare(*one)) {
                    *at += 1;
                }
                text[begin..*at].to_owned()
            }
            _ => return Err("expected a key".into()),
        };
        path.push(part);
        skip_space(bytes, at);
        let end = *first_end.get_or_insert(*at);
        if bytes.get(*at) != Some(&b'.') {
            return Ok((path, end));
        }
        *at += 1;
    }
}

/// Whether a byte may be part of a bare key.
fn bare(one: u8) -> bool {
    one.is_ascii_alphanumeric() || one == b'-' || one == b'_'
}

/// Skips one value, however many lines it spans, and says how many line breaks it crossed.
fn value(text: &str, at: &mut usize) -> Result<usize, String> {
    let bytes = text.as_bytes();
    match bytes.get(*at) {
        Some(b'"' | b'\'') if multi(bytes, *at) => multiline(text, at),
        Some(b'"') => basic(text, at).map(|_| 0),
        Some(b'\'') => literal(text, at).map(|_| 0),
        Some(b'[' | b'{') => {
            let mut depth = 0usize;
            let mut lines = 0;
            loop {
                match bytes.get(*at) {
                    None => return Err("an array or inline table is not closed".into()),
                    Some(b'"' | b'\'') if multi(bytes, *at) => lines += multiline(text, at)?,
                    Some(b'"') => {
                        basic(text, at)?;
                    }
                    Some(b'\'') => {
                        literal(text, at)?;
                    }
                    Some(b'#') => skip_comment(bytes, at),
                    Some(b'\n') => {
                        lines += 1;
                        *at += 1;
                    }
                    Some(b'[' | b'{') => {
                        depth += 1;
                        *at += 1;
                    }
                    Some(b']' | b'}') => {
                        depth -= 1;
                        *at += 1;
                        if depth == 0 {
                            return Ok(lines);
                        }
                    }
                    Some(_) => *at += 1,
                }
            }
        }
        _ => {
            // A number, a boolean, a date or a time: up to a comment or the line's end.
            let begin = *at;
            while !matches!(bytes.get(*at), None | Some(b'#' | b'\n')) {
                *at += 1;
            }
            let token = text[begin..*at].trim_end_matches([' ', '\t', '\r']);
            *at = begin + token.len();
            if token.is_empty() {
                return Err("a key has no value".into());
            }
            if scalar(token) {
                Ok(0)
            } else {
                Err(format!("{token:?} is not a value"))
            }
        }
    }
}

/// Whether a bare value is one TOML has: a boolean, a number (`inf` and `nan` among them),
/// or a date and time, which alone may hold a space (`1979-05-27 07:32:00`).
fn scalar(token: &str) -> bool {
    if matches!(
        token,
        "true" | "false" | "inf" | "+inf" | "-inf" | "nan" | "+nan" | "-nan"
    ) {
        return true;
    }
    let digits = token.strip_prefix(['+', '-']).unwrap_or(token);
    if !digits.starts_with(|one: char| one.is_ascii_digit()) {
        return false;
    }
    if let Some((date, time)) = token.split_once(' ') {
        let dated = |said: &str, at: &[usize]| {
            at.iter()
                .all(|index| said.as_bytes().get(*index).is_some_and(u8::is_ascii_digit))
        };
        return date.len() == 10
            && dated(date, &[0, 1, 2, 3, 5, 6, 8, 9])
            && time.len() >= 8
            && !time.contains(' ')
            && dated(time, &[0, 1, 3, 4, 6, 7]);
    }
    token
        .bytes()
        .all(|one| one.is_ascii_alphanumeric() || b"+-.:_".contains(&one))
}

/// Whether a multi-line string starts at `at`.
fn multi(bytes: &[u8], at: usize) -> bool {
    bytes[at..].starts_with(b"\"\"\"") || bytes[at..].starts_with(b"'''")
}

/// Skips a multi-line string, saying how many line breaks it crossed.
fn multiline(text: &str, at: &mut usize) -> Result<usize, String> {
    let bytes = text.as_bytes();
    let quote = bytes[*at];
    let closing = if quote == b'"' { "\"\"\"" } else { "'''" };
    let begin = *at + 3;
    let mut from = begin;
    loop {
        let Some(found) = text[from..].find(closing) else {
            return Err("a multi-line string is not closed".into());
        };
        let close = from + found;
        if quote == b'"' && escaped(bytes, begin, close) {
            from = close + 1;
            continue;
        }
        // Up to two quotes of its own may come right before the closing three.
        let mut end = close + 3;
        while end < close + 5 && bytes.get(end) == Some(&quote) {
            end += 1;
        }
        let lines = text[*at..end].matches('\n').count();
        *at = end;
        return Ok(lines);
    }
}

/// Whether the quote at `at` is escaped by an odd run of backslashes since `begin`.
fn escaped(bytes: &[u8], begin: usize, at: usize) -> bool {
    let mut count = 0;
    let mut index = at;
    while index > begin && bytes[index - 1] == b'\\' {
        count += 1;
        index -= 1;
    }
    count % 2 == 1
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn entry() -> Map<String, Value> {
        json!({"model": "grok-4", "base_url": "https://x/y", "api_backend": "anthropic",
               "env_key": "K", "hidden": true})
        .as_object()
        .cloned()
        .unwrap_or_default()
    }

    const BODY: &str = "model = \"grok-4\"\nbase_url = \"https://x/y\"\napi_backend = \"anthropic\"\nenv_key = \"K\"\nhidden = true\n";

    /// Each as `tomlkit` 0.13 wrote it (`uv run python` against `_entered`'s own calls).
    #[test]
    fn an_entry_lands_where_tomlkit_puts_it() {
        let t = format!("[model.\"hmz-1/grok-4\"]\n{BODY}");
        for (given, wanted) in [
            ("", t.clone()),
            ("a = 1\n", format!("a = 1\n\n{t}")),
            ("a = 1", format!("a = 1\n{t}")),
            ("a = 1\n\n", format!("a = 1\n\n{t}")),
            ("a = 1\n   ", format!("a = 1\n   {t}")),
            ("a = 1\n\t", format!("a = 1\n\t\n{t}")),
            ("\n", format!("\n{t}")),
            ("# hi", format!("# hi\n{t}")),
            (
                "a = 1\n\n[ui]\ntheme = \"dark\"\n",
                format!("a = 1\n\n[ui]\ntheme = \"dark\"\n\n{t}"),
            ),
            (
                "# c\n[model.foo]\nmodel = \"x\"\n\n[ui]\nx=1\n",
                format!("# c\n[model.foo]\nmodel = \"x\"\n\n{t}[ui]\nx=1\n"),
            ),
            (
                "[model]\ndefault = \"x\"\n[ui]\ny=2\n",
                format!("[model]\ndefault = \"x\"\n\n{t}[ui]\ny=2\n"),
            ),
            (
                "[model.a]\nx=1\n[ui]\ny=1\n[model.b]\nz=1\n",
                format!("[model.a]\nx=1\n\n{t}[ui]\ny=1\n[model.b]\nz=1\n"),
            ),
            (
                "model.foo.model = \"x\"\n",
                format!("model.foo.model = \"x\"\n\n{t}"),
            ),
            (
                "[model.\"hmz-1/grok-4\"]\nmodel = \"old\"\n\n[ui]\nx=1\n",
                format!("{t}\n[ui]\nx=1\n"),
            ),
            (
                "[model.a]\nx=1\n  \n  [ui]\n",
                format!("[model.a]\nx=1\n  \n{t}  [ui]\n"),
            ),
            (
                "a = \"\"\"\n[model.x]\n\"\"\"\n",
                format!("a = \"\"\"\n[model.x]\n\"\"\"\n\n{t}"),
            ),
            (
                "a=1\nmodel.foo.x = 1\n# c\n[ui]\nz=1\n",
                format!("a=1\nmodel.foo.x = 1\n\n{t}# c\n[ui]\nz=1\n"),
            ),
            (
                "[model.\"hmz-1/grok-4\"]\nx=1\n\n[model.\"hmz-1/grok-4\".sub]\ny=2\n\n[ui]\n",
                format!("{t}[ui]\n"),
            ),
            (
                "[model.\"hmz-1/grok-4\"]\nx=1\n# c\n\n[ui]\n",
                format!("{t}\n[ui]\n"),
            ),
            (
                "d = 1979-05-27 07:32:00Z\nn = -1_000.5e3\n",
                format!("d = 1979-05-27 07:32:00Z\nn = -1_000.5e3\n\n{t}"),
            ),
        ] {
            assert_eq!(
                with_entry(given, "hmz-1/grok-4", &entry()).as_deref(),
                Ok(wanted.as_str()),
                "{given:?}"
            );
        }
        let spaced = with_entry("[ \"model\" . a ]\nx=1\n", "k", &entry());
        assert_eq!(
            spaced,
            Ok(format!("[ \"model\" . a ]\nx=1\n\n[ \"model\" .k]\n{BODY}"))
        );
    }

    #[test]
    fn what_is_not_toml_or_not_a_table_is_refused() {
        for given in [
            "model = \"grok\"\n",
            "[[model]]\nx=1\n",
            "a = \n",
            "[ui\n",
            "a = \"open\n",
            "a = [1,\n",
            "a = foo bar\n",
            "a = foo\n",
            "a=1\na=2\n",
            "[ui]\n[ui]\n",
            "[model]\nk = {x=1}\n",
            "model.k.x = 1\n",
        ] {
            assert!(with_entry(given, "k", &entry()).is_err(), "{given:?}");
        }
    }

    #[test]
    fn strings_are_escaped_as_tomlkit_escapes_them() {
        assert_eq!(
            string("\u{1b}\u{8}\u{c}\r\"\\é\u{1}\u{7f}"),
            "\"\\e\\b\\f\\r\\\"\\\\é\\u0001\\u007f\""
        );
        assert_eq!(key("plain_key-1"), "plain_key-1");
        assert_eq!(key("a b"), "\"a b\"");
    }
}
