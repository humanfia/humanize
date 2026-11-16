//! Qwen Code's merger: what the run says, over the virtual home's copy of `settings.json`.
//! Port of `hmz.coganchor.agents.qwen._merged`.

use std::fs;
use std::io;
use std::path::Path;

use serde_json::{Map, Value, json};

use super::pyjson::{self, Layout};
use super::{refused, said_field};

/// The user-level settings file under its home (`qwen._SETTINGS`).
const SETTINGS: &str = "settings.json";

/// `qwen._COMMAND`, which its refusals start with.
const COMMAND: &str = "qwen";

/// `_merged(home, given)`: `given` holds `managed`, what the run says, and `headless`,
/// whether to say what an unwatched turn defaults to (`qwen._HEADLESS`) where the user's
/// file says nothing of it.
pub fn merged(home: &Path, given: &Value) -> io::Result<()> {
    let at = home.join(SETTINGS);
    let managed = said_field(given, "managed")?
        .as_object()
        .ok_or_else(|| refused("qwen: `managed` is not an object"))?;
    let headless = pyjson::truthy(said_field(given, "headless")?);
    let raw: Value = match fs::read(&at) {
        Ok(bytes) => {
            let text = String::from_utf8(bytes).map_err(|error| unread(&error))?;
            serde_json::from_str(&text).map_err(|error| unread(&error))?
        }
        // `dict(_VERSION)`: the format Qwen Code has nothing to migrate in.
        Err(error) if error.kind() == io::ErrorKind::NotFound => json!({"$version": 4}),
        Err(error) => return Err(unread(&error)),
    };
    let Value::Object(mut held) = raw else {
        return Err(refused(format!(
            "{COMMAND}: the user's settings.json is not a JSON object"
        )));
    };
    for (key, value) in managed {
        let merged = match (key.as_str(), held.get(key), value) {
            ("hooks", Some(Value::Object(hooks)), ours) => {
                let ours = ours
                    .as_object()
                    .ok_or_else(|| refused("qwen: the run's hooks are not an object"))?;
                let mut joined = hooks.clone();
                for (moment, table) in ours {
                    let table = table
                        .as_array()
                        .ok_or_else(|| refused("qwen: a moment's hooks are not a list"))?;
                    // `[*_listed(hooks.get(moment)), *table]`.
                    let mut listed = match hooks.get(moment) {
                        Some(Value::Array(theirs)) => theirs.clone(),
                        _ => Vec::new(),
                    };
                    listed.extend(table.iter().cloned());
                    joined.insert(moment.clone(), Value::Array(listed));
                }
                Value::Object(joined)
            }
            (_, Some(Value::Object(theirs)), Value::Object(ours)) => {
                Value::Object(union(theirs, ours))
            }
            _ => value.clone(),
        };
        held.insert(key.clone(), merged);
    }
    if headless {
        let defaults = json!({"general": {"preventSystemSleep": false, "enableAutoUpdate": false}});
        for (key, value) in defaults.as_object().into_iter().flatten() {
            let kept = match held.get(key) {
                Some(Value::Object(theirs)) => theirs.clone(),
                _ => Map::new(),
            };
            let ours = value.as_object().cloned().unwrap_or_default();
            held.insert(key.clone(), Value::Object(union(&ours, &kept)));
        }
    }
    if let Some(parent) = at.parent() {
        fs::create_dir_all(parent)?;
    }
    let text = pyjson::dumps(&Value::Object(held), Layout::Indent(2)) + "\n";
    fs::write(&at, text)
}

/// Python's `left | right`: left's keys in their order, right's values over them, right's
/// other keys after.
fn union(left: &Map<String, Value>, right: &Map<String, Value>) -> Map<String, Value> {
    let mut out = left.clone();
    for (key, value) in right {
        out.insert(key.clone(), value.clone());
    }
    out
}

/// The refusal for a user's file that is not plain JSON.
fn unread(error: &dyn std::fmt::Display) -> io::Error {
    refused(format!(
        "{COMMAND}: the user's settings.json cannot be read as plain JSON ({error}), so the \
         run's own settings cannot be merged into a copy of it: take its comments out"
    ))
}
