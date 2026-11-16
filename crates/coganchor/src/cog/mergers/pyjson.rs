//! JSON spelled as Python's `json.dumps` spells it: every non-ASCII character escaped
//! (`ensure_ascii`), floats as `repr` writes them, and the separators and indentation it was
//! given. What a merger writes and what `Virtual.dumps` says must be the bytes the Python ones
//! write, so that a file is the same whichever side built the home.

use std::fmt::Write as _;

use serde_json::Value;

/// How to lay it out, as `json.dumps`'s `indent` and `separators` say it.
#[derive(Clone, Copy, Debug)]
pub enum Layout {
    /// `json.dumps(said)`: `", "` and `": "`, on one line.
    Default,
    /// `json.dumps(said, separators=(",", ":"))`.
    Compact,
    /// `json.dumps(said, indent=n)`: `","` at each line's end and `": "`.
    Indent(usize),
}

/// `json.dumps(value, ...)` with the given layout.
pub fn dumps(value: &Value, layout: Layout) -> String {
    let mut out = String::new();
    write_value(&mut out, value, layout, 0);
    out
}

fn write_value(out: &mut String, value: &Value, layout: Layout, depth: usize) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(true) => out.push_str("true"),
        Value::Bool(false) => out.push_str("false"),
        Value::Number(number) => {
            if let Some(n) = number.as_i64() {
                let _ = write!(out, "{n}");
            } else if let Some(n) = number.as_u64() {
                let _ = write!(out, "{n}");
            } else {
                out.push_str(&float_repr(number.as_f64().unwrap_or(f64::NAN)));
            }
        }
        Value::String(text) => out.push_str(&string(text)),
        Value::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (index, item) in items.iter().enumerate() {
                separate(out, layout, depth + 1, index == 0);
                write_value(out, item, layout, depth + 1);
            }
            close(out, layout, depth);
            out.push(']');
        }
        Value::Object(map) => {
            if map.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (index, (key, item)) in map.iter().enumerate() {
                separate(out, layout, depth + 1, index == 0);
                out.push_str(&string(key));
                out.push_str(match layout {
                    Layout::Compact => ":",
                    _ => ": ",
                });
                write_value(out, item, layout, depth + 1);
            }
            close(out, layout, depth);
            out.push('}');
        }
    }
}

/// What goes before an item of a container: the item separator, then the indentation.
fn separate(out: &mut String, layout: Layout, depth: usize, first: bool) {
    match layout {
        Layout::Default if !first => out.push_str(", "),
        Layout::Compact if !first => out.push(','),
        Layout::Indent(by) => {
            if !first {
                out.push(',');
            }
            out.push('\n');
            out.push_str(&" ".repeat(by * depth));
        }
        _ => {}
    }
}

/// What goes before a container's closing bracket.
fn close(out: &mut String, layout: Layout, depth: usize) {
    if let Layout::Indent(by) = layout {
        out.push('\n');
        out.push_str(&" ".repeat(by * depth));
    }
}

/// A string as `json.dumps` quotes it with `ensure_ascii`: everything outside `' '..='~'`
/// escaped, characters past the BMP as surrogate pairs.
pub fn string(text: &str) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    out.push('"');
    for one in text.chars() {
        match one {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' => out.push(one),
            _ => {
                let mut units = [0u16; 2];
                for unit in one.encode_utf16(&mut units) {
                    let _ = write!(out, "\\u{unit:04x}");
                }
            }
        }
    }
    out.push('"');
    out
}

/// A float as Python's `repr` writes it: the shortest digits that read back as it, in
/// positional notation for a decimal exponent from -4 to 15 and in scientific outside that,
/// and `NaN`/`Infinity` as `json.dumps` allows them.
pub fn float_repr(value: f64) -> String {
    if value.is_nan() {
        return "NaN".to_owned();
    }
    if value.is_infinite() {
        return if value > 0.0 { "Infinity" } else { "-Infinity" }.to_owned();
    }
    // Rust's `{:e}` is the shortest round-tripping spelling, as Python's `repr` is.
    let spelled = format!("{:e}", value.abs());
    let (mantissa, exponent) = spelled.split_once('e').unwrap_or((&spelled, "0"));
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let point = exponent + 1; // where the decimal point is, counted from the first digit
    let sign = if value.is_sign_negative() { "-" } else { "" };
    let count = digits.len() as i32;
    if !(-4 < point && point <= 16) {
        let (first, rest) = digits.split_at(1);
        let rest = if rest.is_empty() {
            String::new()
        } else {
            format!(".{rest}")
        };
        let sign_exp = if exponent < 0 { '-' } else { '+' };
        return format!("{sign}{first}{rest}e{sign_exp}{:02}", exponent.abs());
    }
    if point <= 0 {
        format!("{sign}0.{}{digits}", "0".repeat((-point) as usize))
    } else if point >= count {
        format!("{sign}{digits}{}.0", "0".repeat((point - count) as usize))
    } else {
        let (whole, part) = digits.split_at(point as usize);
        format!("{sign}{whole}.{part}")
    }
}

/// Whether Python would take it as true: `bool(value)`.
pub fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(said) => *said,
        Value::Number(number) => number.as_f64().is_some_and(|n| n != 0.0),
        Value::String(text) => !text.is_empty(),
        Value::Array(items) => !items.is_empty(),
        Value::Object(map) => !map.is_empty(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn floats_are_spelled_as_python_spells_them() {
        for (value, said) in [
            (1.0, "1.0"),
            (0.1, "0.1"),
            (1e16, "1e+16"),
            (1e15, "1000000000000000.0"),
            (1.5e-5, "1.5e-05"),
            (0.0001, "0.0001"),
            (-2.5, "-2.5"),
            (123456.789, "123456.789"),
            (1.7976931348623157e308, "1.7976931348623157e+308"),
            (-0.0, "-0.0"),
        ] {
            assert_eq!(float_repr(value), said, "{value}");
        }
    }

    #[test]
    fn strings_and_layouts_are_pythons() {
        let value = json!({"a": [1, {"b": "é😀\u{1}\u{7f}"}], "c": {}, "d": []});
        assert_eq!(
            dumps(&value, Layout::Default),
            r#"{"a": [1, {"b": "\u00e9\ud83d\ude00\u0001\u007f"}], "c": {}, "d": []}"#
        );
        assert_eq!(
            dumps(&value, Layout::Compact),
            r#"{"a":[1,{"b":"\u00e9\ud83d\ude00\u0001\u007f"}],"c":{},"d":[]}"#
        );
        assert_eq!(
            dumps(&value, Layout::Indent(2)),
            "{\n  \"a\": [\n    1,\n    {\n      \"b\": \"\\u00e9\\ud83d\\ude00\\u0001\\u007f\"\n    }\n  ],\n  \"c\": {},\n  \"d\": []\n}"
        );
    }
}
