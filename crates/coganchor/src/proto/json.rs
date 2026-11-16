//! JSON as Python's `json` module writes it for this protocol, non-UTF-8 paths included.
//!
//! Python reads a file name that is not UTF-8 with `surrogateescape`: each byte that does not
//! decode, always `0x80`-`0xFF`, becomes the lone surrogate `U+DC80`-`U+DCFF`, and `json.dumps`
//! writes that as the escape `\udcXX`. Rust strings cannot hold a lone surrogate, and
//! `serde_json` refuses to read one, so on this side each such byte is stood in for by a
//! private-use character, `U+10FD80`-`U+10FDFF` ([`ESCAPED`] plus the byte). [`decode`] turns
//! the wire's escapes into those characters and [`encode`] turns them back; [`to_os`] and
//! [`from_os`] are where a string meets the filesystem.
//!
//! A file name that really holds one of those 128 characters of plane 16's private-use area
//! would be read as the bytes they stand for. Nothing writes them.

use std::ffi::{OsStr, OsString};
use std::os::unix::ffi::{OsStrExt, OsStringExt};

use serde_json::Value;

/// The private-use character standing in for byte `0x00`; byte `b` is `ESCAPED + b`.
pub const ESCAPED: u32 = 0x10FD00;

/// The character standing in for an undecodable byte, if `byte` is one.
fn stand_in(byte: u8) -> Option<char> {
    (byte >= 0x80).then(|| char::from_u32(ESCAPED + u32::from(byte)).unwrap())
}

/// The byte a character stands in for, if it is a stand-in.
fn stood_for(c: char) -> Option<u8> {
    let point = u32::from(c);
    (ESCAPED + 0x80..=ESCAPED + 0xFF)
        .contains(&point)
        .then(|| (point - ESCAPED) as u8)
}

/// Reads JSON text whose strings may hold `\udcXX` escapes for undecodable bytes.
pub fn decode(text: &[u8]) -> serde_json::Result<Value> {
    if !text.windows(3).any(|w| w.eq_ignore_ascii_case(b"\\ud")) {
        return serde_json::from_slice(text);
    }
    serde_json::from_slice(&unescape(text))
}

/// Writes a value as compact JSON, each stand-in character as the `\udcXX` Python reads back.
pub fn encode(value: &Value) -> Vec<u8> {
    let plain = serde_json::to_vec(value).expect("a JSON value always serialises");
    if !plain.contains(&0xF4) {
        return plain;
    }
    let text = String::from_utf8(plain).expect("serde_json writes UTF-8");
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match stood_for(c) {
            Some(byte) => out.push_str(&format!("\\udc{byte:02x}")),
            None => out.push(c),
        }
    }
    out.into_bytes()
}

/// The JSON text with every lone low-surrogate escape for a byte replaced by its stand-in.
fn unescape(text: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(text.len());
    let mut i = 0;
    let mut after_high = false;
    while i < text.len() {
        if text[i] != b'\\' || i + 1 >= text.len() {
            out.push(text[i]);
            after_high = false;
            i += 1;
            continue;
        }
        if text[i + 1] != b'u' || i + 6 > text.len() {
            out.extend_from_slice(&text[i..i + 2]);
            after_high = false;
            i += 2;
            continue;
        }
        let hex = std::str::from_utf8(&text[i + 2..i + 6]).ok();
        let unit = hex.and_then(|h| u16::from_str_radix(h, 16).ok());
        match unit {
            Some(unit @ 0xDC80..=0xDCFF) if !after_high => {
                let c = stand_in((unit & 0xFF) as u8).unwrap();
                let mut buf = [0u8; 4];
                out.extend_from_slice(c.encode_utf8(&mut buf).as_bytes());
                after_high = false;
            }
            Some(unit) => {
                out.extend_from_slice(&text[i..i + 6]);
                after_high = (0xD800..=0xDBFF).contains(&unit);
            }
            None => {
                out.extend_from_slice(&text[i..i + 6]);
                after_high = false;
            }
        }
        i += 6;
    }
    out
}

/// The bytes a wire string names on this machine.
pub fn to_os(said: &str) -> OsString {
    if !said.bytes().any(|b| b == 0xF4) {
        return OsString::from(said);
    }
    let mut bytes = Vec::with_capacity(said.len());
    for c in said.chars() {
        match stood_for(c) {
            Some(byte) => bytes.push(byte),
            None => {
                let mut buf = [0u8; 4];
                bytes.extend_from_slice(c.encode_utf8(&mut buf).as_bytes());
            }
        }
    }
    OsString::from_vec(bytes)
}

/// A file name as the wire spells it: UTF-8, with each undecodable byte stood in for.
pub fn from_os(name: &OsStr) -> String {
    from_bytes(name.as_bytes())
}

/// Bytes as the wire spells them: UTF-8, with each undecodable byte stood in for.
pub fn from_bytes(mut bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len());
    loop {
        match std::str::from_utf8(bytes) {
            Ok(rest) => {
                out.push_str(rest);
                return out;
            }
            Err(error) => {
                let good = error.valid_up_to();
                out.push_str(std::str::from_utf8(&bytes[..good]).unwrap());
                let bad = error.error_len().unwrap_or(bytes.len() - good);
                for &byte in &bytes[good..good + bad] {
                    // A byte below 0x80 never fails to decode on its own.
                    out.push(stand_in(byte).unwrap_or(char::REPLACEMENT_CHARACTER));
                }
                bytes = &bytes[good + bad..];
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `json.dumps({"path": b"/w/\xff".decode(errors="surrogateescape")})` in Python.
    const PYTHON: &[u8] = br#"{"path": "/w/\udcff"}"#;

    #[test]
    fn reads_pythons_escapes() {
        let value = decode(PYTHON).unwrap();
        let path = value["path"].as_str().unwrap();
        assert_eq!(to_os(path).as_bytes(), b"/w/\xff");
    }

    #[test]
    fn writes_them_back() {
        let name = from_os(OsStr::from_bytes(b"/w/\xff\xfe"));
        let blob = encode(&serde_json::json!({ "path": name }));
        assert_eq!(blob, br#"{"path":"/w/\udcff\udcfe"}"#);
    }

    #[test]
    fn leaves_real_pairs_alone() {
        let value = decode(b"{\"s\": \"\\ud800\\udc80\"}").unwrap();
        assert_eq!(value["s"].as_str().unwrap(), "\u{10080}");
    }

    #[test]
    fn utf8_passes_through() {
        assert_eq!(from_os(OsStr::new("/wörk")), "/wörk");
        assert_eq!(to_os("/wörk"), OsString::from("/wörk"));
    }
}
