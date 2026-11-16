//! The mergers a virtual home names: each folds what a driver manages into the copy of a CLI's
//! configuration in the home just built. Ports of the `@merger` functions in
//! `hmz.coganchor.agents.{agy,grok,codex,pi,qwen}`. [Unit 14]
//!
//! Python finds a merger by its module and its name, importing the module where nothing has
//! yet (`homes._merging`); here the same names are matched, so a `Virtual` said by `hmz`
//! names the same merger on either side. Each writes the bytes its Python one writes.

mod agy;
mod codex;
mod grok;
mod pi;
pub(crate) mod pyjson;
mod qwen;

use std::io;
use std::path::Path;

use serde_json::Value;

/// Every merger's name, as `homes.merger` registers it: `<module>:<qualified name>`.
pub const NAMES: [&str; 5] = [
    "hmz.coganchor.agents.agy:_agents",
    "hmz.coganchor.agents.codex:_ruled",
    "hmz.coganchor.agents.grok:_entered",
    "hmz.coganchor.agents.pi:_declare",
    "hmz.coganchor.agents.qwen:_merged",
];

/// Runs the merger `name` on the virtual home `home`, built moments ago and not yet started
/// in, with `said`: its argument, as `homes.merged` said it (JSON, read back).
///
/// # Errors
///
/// `InvalidInput` for a name no merger has (Python's `ValueError("no merger ...")`), and
/// whatever the merger could not merge: `InvalidData` for a file of the user's it refuses to
/// write over (Python's `Unrecoverable` or `ValueError`), any other for the file system's.
pub fn merge(name: &str, home: &Path, said: &Value) -> io::Result<()> {
    match name {
        "hmz.coganchor.agents.agy:_agents" => agy::agents(home),
        "hmz.coganchor.agents.codex:_ruled" => codex::ruled(home, said),
        "hmz.coganchor.agents.grok:_entered" => grok::entered(home, said),
        "hmz.coganchor.agents.pi:_declare" => pi::declare(home, said),
        "hmz.coganchor.agents.qwen:_merged" => qwen::merged(home, said),
        _ => Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("no merger {name:?}"),
        )),
    }
}

/// A merger's refusal of what it was given or found: Python's `ValueError`/`Unrecoverable`.
pub(crate) fn refused(said: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, said.into())
}

/// `said[field]`, as Python reads a merger's argument, refusing what is not there.
pub(crate) fn said_field<'a>(said: &'a Value, field: &str) -> io::Result<&'a Value> {
    said.get(field)
        .ok_or_else(|| refused(format!("a merge was not given {field:?}")))
}

/// Replaces the link `into` (to the user's own directory) with a directory of the home's own
/// holding a link to each of that directory's entries but `ours`: what `agy._agents` and
/// `codex._ruled` both do before writing their own files beside them.
///
/// Returns nothing; the directory is there after it, the user's own untouched.
pub(crate) fn owned(into: &Path, ours: &[String]) -> io::Result<()> {
    use std::fs;
    // `into.resolve() if into.is_symlink() else None`.
    let theirs = if fs::symlink_metadata(into).is_ok_and(|one| one.file_type().is_symlink()) {
        Some(crate::cog::homes::realpath(into))
    } else {
        None
    };
    if theirs.is_some() {
        fs::remove_file(into)?;
    }
    // `mkdir(exist_ok=True)`: a directory already there is kept; anything else is refused.
    if let Err(error) = fs::create_dir(into)
        && !(error.kind() == io::ErrorKind::AlreadyExists && into.is_dir())
    {
        return Err(error);
    }
    if let Some(theirs) = theirs.filter(|one| one.is_dir()) {
        for entry in fs::read_dir(&theirs)? {
            let entry = entry?;
            let name = entry.file_name();
            if ours.iter().any(|one| *one.as_str() == *name) {
                continue;
            }
            std::os::unix::fs::symlink(theirs.join(&name), into.join(&name))?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_name_no_merger_has_is_refused() {
        let home = tempfile::tempdir().expect("a directory");
        let error = merge("hmz.nowhere:_merge", home.path(), &Value::Null).expect_err("refused");
        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        assert!(error.to_string().contains("no merger"));
    }
}
