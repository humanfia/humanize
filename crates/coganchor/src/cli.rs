//! The command line: `coganchor cog | anchor | broker | internal {fence, cred}`.
//!
//! `cog` takes every option `hmz internal anchor` takes, with the same defaults read from the
//! same variables; `anchor` is `hmz internal anchor serve`; `broker` is `hmz internal anchor
//! rendezvous`. `hmz` keeps those older spellings as aliases that run this program.

use std::ffi::OsString;
use std::path::PathBuf;

use clap::{Args, Parser, Subcommand};

/// Running a coding agent on one machine with its work landing on another.
#[derive(Debug, Parser)]
#[command(name = "coganchor", version, about, disable_help_subcommand = true)]
pub struct Cli {
    #[command(subcommand)]
    pub mode: Mode,
}

/// The parts of a session, each where it runs.
#[derive(Debug, Subcommand)]
#[allow(clippy::large_enum_variant)] // parsed once, at start-up
pub enum Mode {
    /// Beside the agent, on its harness machine: run PROGRAM with its work landing on the target.
    Cog(CogArgs),
    /// On the machine the work lands on: carry out what a cog asks for.
    Anchor(AnchorArgs),
    /// Where both halves can reach: introduce a cog and an anchor that cannot dial each other.
    Broker(BrokerArgs),
    /// Programs coganchor and Humanize start for themselves.
    #[command(hide = true, subcommand)]
    Internal(Internal),
}

/// The programs coganchor starts for itself.
#[derive(Debug, Subcommand)]
pub enum Internal {
    /// Run a program held to what its flow permits.
    Fence(FenceArgs),
    /// Run a program with credentials from an account.
    Cred(CredArgs),
    /// Say what this machine can fence, as `{"fs": bool, "net": bool}`; with --policy, also
    /// why it cannot hold what that fence carves out of its grants, as `"unheld"`.
    Able(AbleArgs),
}

/// `coganchor cog`: the options of `hmz internal anchor`.
#[derive(Clone, Debug, Default, Args)]
pub struct CogArgs {
    /// Where the work lands: ssh://[USER@]HOST[:PORT], docker://CONTAINER[@ENDPOINT],
    /// apple-container://NAME, slurm://JOBID, tcp://HOST:PORT, peer://TICKET@HOST:PORT, or
    /// local[:DIR].
    #[arg(
        long,
        env = "HUMANIZE_TARGET",
        default_value = "local",
        value_name = "URL"
    )]
    pub target: String,
    /// Where the harness runs: local, or a target URL of its own.
    #[arg(
        long,
        env = "HUMANIZE_HARNESS",
        default_value = "local",
        value_name = "WHERE"
    )]
    pub harness: String,
    /// Where the two halves meet when harness and target differ.
    #[arg(
        long,
        env = "HUMANIZE_RENDEZVOUS",
        default_value = "",
        value_name = "HOST"
    )]
    pub broker: String,
    /// The project directory as it exists on the target (default: this directory).
    #[arg(long, value_name = "PATH")]
    pub workspace: Option<String>,
    /// The directory standing in for the target's copy of the workspace.
    #[arg(long, value_name = "PATH")]
    pub remote_path: Option<String>,
    /// Mirror directory on the harness's machine (default: the workspace).
    #[arg(long, env = "HUMANIZE_SHADOW", value_name = "PATH")]
    pub shadow: Option<String>,
    /// A path that stays on this machine; repeatable.
    #[arg(long = "local-path", value_name = "PATH")]
    pub local_paths: Vec<String>,
    /// A program that runs on this machine; repeatable.
    #[arg(long = "local-exec", value_name = "PATH")]
    pub local_execs: Vec<String>,
    /// Answer absolute path FROM with TO; repeatable.
    #[arg(long = "redirect", value_name = "FROM=TO")]
    pub redirects: Vec<String>,
    /// Where the agent starts (default: the workspace).
    #[arg(long, value_name = "PATH")]
    pub chdir: Option<String>,
    /// A variable not passed to commands run on the target; repeatable.
    #[arg(long = "private", value_name = "NAME")]
    pub private: Vec<String>,
    /// Where the agent's own TCP connections go.
    #[arg(long, default_value = "local", value_parser = ["local", "remote"])]
    pub net: String,
    /// A host whose connections stay local under --net=remote; repeatable.
    #[arg(long = "net-allow", value_name = "HOST[:PORT]")]
    pub net_allow: Vec<String>,
    /// Shared secret expected by the target.
    #[arg(long, env = "HUMANIZE_TOKEN", hide_env_values = true)]
    pub token: Option<String>,
    /// A file holding the shared secret, read verbatim.
    #[arg(long, value_name = "FILE")]
    pub token_file: Option<PathBuf>,
    /// Use the mirror directory even if it holds something else.
    #[arg(long)]
    pub force: bool,
    /// Run the CLI installed on the target rather than this one.
    #[arg(long)]
    pub native: bool,
    /// A file of the CLI's home not carried to the target (native); repeatable.
    #[arg(long = "hush", value_name = "NAME")]
    pub hushes: Vec<String>,
    /// A project directory to keep for the CLI (native); repeatable.
    #[arg(long = "project", value_name = "NAME=DIR")]
    pub projects: Vec<String>,
    /// A file to bring back from the target (native); repeatable.
    #[arg(long = "bring", value_name = "NAME/PATH=DIR")]
    pub brings: Vec<String>,
    /// Where to tell the target's CLI its state is kept (native).
    #[arg(long, default_value = "", value_name = "DIR")]
    pub tell: String,
    /// The CLI's virtual home, as JSON.
    #[arg(long, value_name = "JSON")]
    pub home: Option<String>,
    /// The shell line that installs what the CLI needs on the target (native).
    #[arg(long, default_value = "", value_name = "LINE")]
    pub installs: String,
    /// The fence the agent is held to, as JSON.
    #[arg(long, value_name = "JSON")]
    pub fence: Option<String>,
    /// Only ask the target what it is.
    #[arg(long)]
    pub check: bool,
    /// One of debug, info, warning, error (default: $HUMANIZE_LOG, else warning).
    #[arg(long, value_parser = crate::log::LEVELS)]
    pub log_level: Option<String>,
    /// The agent to run and its arguments.
    #[arg(
        trailing_var_arg = true,
        allow_hyphen_values = true,
        value_name = "PROGRAM"
    )]
    pub command: Vec<OsString>,
}

/// `coganchor anchor`: the options of `hmz internal anchor serve`.
#[derive(Clone, Debug, Args)]
#[command(group(clap::ArgGroup::new("how").required(true).args(["stdio", "listen", "peer"])))]
pub struct AnchorArgs {
    /// A directory to serve, VIRTUAL[:REAL]; repeatable, at least one.
    #[arg(long = "export", required = true, value_name = "VIRTUAL[:REAL]")]
    pub exports: Vec<String>,
    /// Serve one session on standard input and output.
    #[arg(long)]
    pub stdio: bool,
    /// Serve sessions on this address.
    #[arg(long, value_name = "[HOST:]PORT")]
    pub listen: Option<String>,
    /// Serve one session met through a broker.
    #[arg(long, value_name = "TICKET@HOST:PORT")]
    pub peer: Option<String>,
    /// The secret a client must present.
    #[arg(long, env = "HUMANIZE_TOKEN", hide_env_values = true)]
    pub token: Option<String>,
    /// A file holding that secret, read verbatim.
    #[arg(long, value_name = "FILE")]
    pub token_file: Option<PathBuf>,
    /// One of debug, info, warning, error (default: $HUMANIZE_LOG, else warning).
    #[arg(long, value_parser = crate::log::LEVELS)]
    pub log_level: Option<String>,
}

/// `coganchor broker`: the options of `hmz internal anchor rendezvous`.
#[derive(Clone, Debug, Args)]
pub struct BrokerArgs {
    /// Where to listen.
    #[arg(long, default_value = "0.0.0.0:0", value_name = "[HOST:]PORT")]
    pub listen: String,
    /// How long two halves try to reach each other directly before being relayed.
    #[arg(long, default_value_t = 4.0, value_name = "SECONDS")]
    pub punching: f64,
    /// One of debug, info, warning, error (default: $HUMANIZE_LOG, else info).
    #[arg(long, value_parser = crate::log::LEVELS)]
    pub log_level: Option<String>,
}

/// `coganchor internal able`: what this machine can fence.
#[derive(Clone, Debug, Default, Args)]
pub struct AbleArgs {
    /// A fence, as JSON or @PATH, whose carve-outs to ask about.
    #[arg(long, value_name = "JSON")]
    pub policy: Option<String>,
}

/// `coganchor internal fence`: the options of `hmz internal fence`.
#[derive(Clone, Debug, Args)]
pub struct FenceArgs {
    /// The fence, as JSON, or @PATH for a file holding it.
    #[arg(long, value_name = "JSON")]
    pub policy: String,
    /// The program to run and its arguments, after --. Not required here: an empty one is
    /// refused by the command itself, with the usage line `hmz internal ...` has always printed.
    #[arg(
        trailing_var_arg = true,
        allow_hyphen_values = true,
        value_name = "COMMAND"
    )]
    pub command: Vec<OsString>,
}

/// `coganchor internal cred`: the options of `hmz internal cred`.
#[derive(Clone, Debug, Args)]
pub struct CredArgs {
    /// Map absolute path FROM to TO; repeatable, and a directory includes everything in it.
    #[arg(long = "map", value_name = "FROM=TO")]
    pub maps: Vec<String>,
    /// As --map, but never by copying; FROM may hold a glob; repeatable.
    #[arg(long = "keep", value_name = "FROM=TO")]
    pub keeps: Vec<String>,
    /// The program to run and its arguments, after --. Not required here: an empty one is
    /// refused by the command itself, with the usage line `hmz internal ...` has always printed.
    #[arg(
        trailing_var_arg = true,
        allow_hyphen_values = true,
        value_name = "COMMAND"
    )]
    pub command: Vec<OsString>,
}

/// Reads a secret from `--token-file` verbatim, else `--token`.
pub fn secret(
    token: Option<&str>,
    file: Option<&std::path::Path>,
) -> std::io::Result<Option<String>> {
    match file {
        Some(path) => std::fs::read_to_string(path).map(Some),
        None => Ok(token.map(str::to_owned)),
    }
}
