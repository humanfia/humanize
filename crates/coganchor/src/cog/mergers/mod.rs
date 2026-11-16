//! The mergers a virtual home names: each folds a CLI's real configuration file and the one a
//! flow gives into the file the session reads. Ports of the `@merger` functions in
//! `hmz.coganchor.agents.{agy,grok,codex,pi,qwen}`. [Unit 14]

use std::io;
use std::path::Path;

/// Runs the merger `name` (as `homes.merger` registers it), merging `given` over `real` into
/// `into`.
pub fn merge(name: &str, real: Option<&Path>, given: &Path, into: &Path) -> io::Result<()> {
    todo!("unit 14")
}
