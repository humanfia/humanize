//! The ptrace event loop that keeps the agent honest about where it runs. Port of
//! `hmz.coganchor.supervisor`. [Unit 10]
//!
//! The agent is forked under the trap filter (and the fence's filters and walls), stops
//! itself, and only then is the client started and the handshake made: no thread may exist
//! across the fork. The loop never blocks on the target: a remote command is handed to an
//! [`crate::cog::execproxy::ExecProxy`] and the process that asked for it parked as a
//! stand-in until its completion arrives on the wake pipe.

use std::ffi::OsString;
use std::io;
use std::path::PathBuf;
use std::sync::Arc;

use crate::client::RemoteClient;
use crate::cog::netproxy::NetProxy;
use crate::cog::router::Router;
use crate::cog::shadow::ShadowTree;
use crate::cog::walls::Walls;

/// The agent to start.
#[derive(Clone, Debug)]
pub struct Launch {
    pub program: PathBuf,
    pub argv: Vec<OsString>,
    pub env: Vec<(OsString, OsString)>,
    pub cwd: PathBuf,
}

/// How the agent is held.
#[derive(Default)]
pub struct Options {
    /// The secret presented at the handshake.
    pub token: Option<String>,
    /// Variables not passed to commands run on the target.
    pub private: Vec<String>,
    /// False where the fence lets nothing be written: mutations fail `EACCES` unasked.
    pub writes: bool,
    /// The fence's walls, put up in the child.
    pub walls: Option<Walls>,
    /// The fence's `EXEC` levels, sent with every remote command.
    pub fence: Option<serde_json::Value>,
}

/// One supervised agent.
pub struct Supervisor {
    launch: Launch,
    client: Arc<RemoteClient>,
    router: Arc<Router>,
    shadow: Arc<ShadowTree>,
    net: Option<NetProxy>,
    options: Options,
}

impl Supervisor {
    pub fn new(
        launch: Launch,
        client: Arc<RemoteClient>,
        router: Arc<Router>,
        shadow: Arc<ShadowTree>,
        net: Option<NetProxy>,
        options: Options,
    ) -> Supervisor {
        Supervisor {
            launch,
            client,
            router,
            shadow,
            net,
            options,
        }
    }

    /// Runs the agent to its end, returning its status (exit code, or 128 plus its signal).
    pub fn run(self) -> io::Result<i32> {
        todo!("unit 10")
    }
}
