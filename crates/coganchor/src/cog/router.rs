//! Where each path an agent names is answered: the mirror (and so the target), or this
//! machine. Port of `Router`/`Layout` in `hmz.coganchor.policy`. [Unit 8]

use std::path::PathBuf;

/// A mirror on this machine and the workspace on the target it stands for.
#[derive(Clone, Debug)]
pub struct Layout {
    pub shadow: PathBuf,
    pub workspace: String,
}

/// What a router is built from.
#[derive(Clone, Debug, Default)]
pub struct RouterConfig {
    pub layouts: Vec<Layout>,
    /// Other names the mirror is reached by (a peer target's, a symlinked mirror's).
    pub aliases: Vec<(String, String)>,
    /// Paths that stay on this machine: the agent's state, its home, `--local-path`s.
    pub local_paths: Vec<String>,
    /// Programs that run on this machine: the agent's own, `--local-exec`s.
    pub local_programs: Vec<String>,
    /// `--redirect FROM=TO`, absolute.
    pub redirects: Vec<(String, String)>,
}

/// Where a path lands.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Place {
    /// In the mirror: its path here, and the path the target knows it by.
    Mirror {
        local: PathBuf,
        virtual_path: String,
    },
    /// On this machine, as named.
    Local,
}

/// The routing decisions of one session.
#[derive(Debug)]
pub struct Router {
    config: RouterConfig,
}

impl Router {
    /// A router; the target's platform is learnt later ([`Router::learn_platform`]).
    pub fn new(config: RouterConfig) -> Router {
        Router { config }
    }

    /// Records the platform the target said at the handshake (a Mac folds case).
    pub fn learn_platform(&self, platform: &str) {
        todo!("unit 8")
    }

    /// The one spelling of an absolute, normalised path that routing compares
    /// (`/private` aliases, mirror aliases, case where the target folds it).
    pub fn canonical(&self, path: &str) -> String {
        todo!("unit 8")
    }

    /// Whether any path can need settling (so a session with none skips the work).
    pub fn settles(&self) -> bool {
        todo!("unit 8")
    }

    /// Where `path` is answered.
    pub fn place(&self, path: &str) -> Place {
        todo!("unit 8")
    }

    /// The path a `--redirect` answers `path` with, if any.
    pub fn swap(&self, path: &str) -> Option<String> {
        todo!("unit 8")
    }

    /// `text` with every mirror path rewritten to the target's (for argv and env sent there).
    pub fn rewrite(&self, text: &str) -> String {
        todo!("unit 8")
    }

    /// Whether the program at `path` runs here rather than on the target.
    pub fn runs_locally(&self, path: &str) -> bool {
        todo!("unit 8")
    }
}
