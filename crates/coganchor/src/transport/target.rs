//! Target spellings. Port of `Target`, `Endpoint` and `describe` in
//! `hmz.coganchor.transport` (protocol/core.md 6.9). [Unit 7]

/// A target, as one of the spellings of protocol/core.md 6.9.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    /// `local`, `ssh`, `docker`, `apple-container`, `slurm`, `tcp` or `peer`.
    pub scheme: String,
    pub user: Option<String>,
    pub host: String,
    pub port: Option<u16>,
    /// `local:DIR`'s directory, a docker target's endpoint, ...
    pub path: Option<String>,
    /// The `?KEY=VALUE&...` options, in the order written.
    pub options: Vec<(String, String)>,
}

impl Target {
    /// Reads a target; any other spelling is an error naming every accepted one.
    pub fn parse(said: &str) -> Result<Target, String> {
        todo!("unit 7")
    }

    /// The target spelled back, options included, as `Target.describe` spells it.
    pub fn describe(&self) -> String {
        todo!("unit 7")
    }
}
