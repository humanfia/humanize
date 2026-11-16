//! A session's settings, checked. Port of `AnchorConfig` and `argv.settings` in
//! `hmz.coganchor.{anchor,argv}`. [Unit 12]

use std::ffi::OsString;

use crate::cli::CogArgs;
use crate::cog::homes::Virtual;
use crate::fence::Fence;
use crate::transport::Target;

/// Everything a cog session is told, validated as `AnchorConfig.__post_init__` validates it.
#[derive(Clone, Debug)]
pub struct AnchorConfig {
    pub target: Target,
    pub harness: String,
    pub broker: String,
    /// The workspace as the target names it (absolute; this directory by default).
    pub workspace: String,
    pub chdir: Option<String>,
    pub remote_path: Option<String>,
    pub shadow: Option<String>,
    pub local_paths: Vec<String>,
    pub local_execs: Vec<String>,
    pub private: Vec<String>,
    pub redirects: Vec<(String, String)>,
    pub net_remote: bool,
    pub net_allow: Vec<String>,
    pub token: Option<String>,
    pub force: bool,
    pub native: bool,
    pub hushes: Vec<String>,
    pub projects: Vec<(String, String)>,
    pub home: Option<Virtual>,
    pub brings: Vec<(String, String)>,
    pub tell: String,
    pub installs: String,
    pub fence: Option<Fence>,
    pub check: bool,
    pub command: Vec<OsString>,
}

impl AnchorConfig {
    /// The settings a command line gives, or why they are refused (exit 2 with usage).
    pub fn from_args(args: &CogArgs) -> Result<AnchorConfig, String> {
        todo!("unit 12")
    }

    /// The `--export` spec of the workspace: `WS:REAL` for a `local:REAL` target, else `WS`.
    pub fn export(&self) -> String {
        todo!("unit 12")
    }
}
