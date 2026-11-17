//! Codex's merger: an execpolicy file of Humanize's in the virtual home's `rules/`. Port of
//! `hmz.coganchor.agents.codex._ruled`.

use std::fs;
use std::io;
use std::path::Path;

use serde_json::Value;

use super::pyjson::{self, Layout};
use super::{owned, refused};

/// The execpolicy file of Humanize's in a virtual home's `rules/` (`codex._RULES`).
pub const RULES: &str = "hmz.rules";

/// `_ruled(home, names)`: lets Codex run each fake command line named outside its sandbox.
pub fn ruled(home: &Path, said: &Value) -> io::Result<()> {
    let names = said
        .as_array()
        .ok_or_else(|| refused("codex: the names to rule are not a list"))?;
    let into = home.join("rules");
    owned(&into, &[RULES.to_owned()])?;
    let text: String = names
        .iter()
        .map(|name| {
            format!(
                "prefix_rule(pattern=[{}], decision=\"allow\")\n",
                pyjson::dumps(name, Layout::Default)
            )
        })
        .collect();
    fs::write(into.join(RULES), text)
}
