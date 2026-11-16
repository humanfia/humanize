//! Translating the virtual paths a cog speaks into real paths here. Port of
//! `hmz.coganchor.serve.exports`. [Unit 1]

use std::path::PathBuf;

use serde_json::Value;

use crate::proto::RemoteError;

/// One exported directory: what the client calls it, and where it is here.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Export {
    pub virtual_path: String,
    pub real: PathBuf,
}

/// Every export of a session, longest virtual path first; also this machine's authorisation
/// boundary, since a path no export holds is refused.
#[derive(Clone, Debug)]
pub struct ExportTable {
    exports: Vec<Export>,
    fold_case: bool,
}

impl ExportTable {
    /// Reads `--export VIRTUAL[:REAL]` specs (split at the first `:`), sorted longest
    /// `path_key(virtual)` first, stably. The message of the error is what `hmz: ` prefixes.
    pub fn parse(specs: &[String]) -> Result<ExportTable, String> {
        todo!("unit 1")
    }

    /// The exports in the order the table holds them, which is the order `HELLO` lists them.
    pub fn exports(&self) -> &[Export] {
        &self.exports
    }

    /// Whether this machine's filesystem ignores case (a Mac's does).
    pub fn fold_case(&self) -> bool {
        self.fold_case
    }

    /// The real path a virtual one names; `EACCES` "path is outside every export" otherwise.
    pub fn resolve(&self, virtual_path: &str) -> Result<PathBuf, RemoteError> {
        todo!("unit 1")
    }

    /// `text` with every export's virtual prefix (and its `/private` spelling) rewritten to
    /// its real one, export by export, as `ExportTable.rewrite` does.
    pub fn rewrite(&self, text: &str) -> String {
        todo!("unit 1")
    }

    /// The `exports` list of a `HELLO` reply: `[{"virtual": .., "real": ..}, ...]`.
    pub fn hello(&self) -> Value {
        todo!("unit 1")
    }
}
