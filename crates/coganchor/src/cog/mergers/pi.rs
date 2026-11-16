//! pi's merger: one provider into the virtual home's copy of `models.json`. Port of
//! `hmz.coganchor.agents.pi._declare`.

use std::fs;
use std::io;
use std::path::Path;

use serde_json::{Map, Value};

use super::pyjson::{self, Layout};
use super::{refused, said_field};

/// `_declare(home, given)`: `given` holds `named`, what the provider is called, and
/// `declared`, what it is. Everything the file already holds is kept.
pub fn declare(home: &Path, given: &Value) -> io::Result<()> {
    let at = home.join("models.json");
    let named = said_field(given, "named")?
        .as_str()
        .ok_or_else(|| refused("pi: `named` is not a string"))?;
    let declared = said_field(given, "declared")?;
    let said: Value = match fs::read(&at) {
        Ok(bytes) => match std::str::from_utf8(&bytes)
            .ok()
            .and_then(|text| serde_json::from_str(text).ok())
        {
            Some(said) => said,
            None => {
                let url = declared
                    .get("baseUrl")
                    .map(|one| one.as_str().map_or_else(|| one.to_string(), str::to_owned))
                    .unwrap_or_default();
                let mut one = Map::new();
                one.insert(named.to_owned(), declared.clone());
                return Err(refused(format!(
                    "models.json is not JSON Humanize can read (pi takes comments, which \
                     Humanize cannot keep), so the gateway {url} cannot be added to a copy of \
                     it: add {} under its providers by hand",
                    pyjson::dumps(&Value::Object(one), Layout::Default)
                )));
            }
        },
        Err(error) if error.kind() == io::ErrorKind::NotFound => Value::Object(Map::new()),
        Err(error) => return Err(error),
    };
    let Value::Object(mut held) = said else {
        return Err(refused(
            "models.json holds no providers by name to add the gateway to",
        ));
    };
    // `held.setdefault("providers", {})`.
    let providers = held
        .entry("providers")
        .or_insert_with(|| Value::Object(Map::new()));
    let Value::Object(providers) = providers else {
        return Err(refused(
            "models.json holds no providers by name to add the gateway to",
        ));
    };
    providers.insert(named.to_owned(), declared.clone());
    let text = pyjson::dumps(&Value::Object(held), Layout::Indent(2)) + "\n";
    fs::write(&at, text)
}
