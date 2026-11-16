//! Reaching an anchor on a target. Port of the connecting half of
//! `hmz.coganchor.transport`. [Unit 7]
//!
//! Five ways start the anchor and take the pipe they started it down: `local[:REAL]` runs it
//! as a child; `ssh://`, `docker://`, `apple-container://` and `slurm://` run it on the far
//! side through a [`Road`], having shipped this very binary there (the right one for that
//! machine's OS and architecture) if it is not already in its cache. Two ways find one already
//! running: `tcp://HOST:PORT` dials it, and `peer://TICKET@HOST:PORT` meets it through a broker.

pub mod road;
pub mod ship;
pub mod target;

use std::io;
use std::process::Child;
use std::sync::Arc;

pub use road::Road;
pub use target::Target;

use crate::proto::Channel;

/// A connection to an anchor, and the process carrying it where one was started.
pub struct Link {
    pub channel: Arc<Channel>,
    pub child: Option<Child>,
}

impl Link {
    /// Closes the channel, then ends the process: terminate, five seconds, kill.
    pub fn close(self) {
        todo!("unit 7")
    }
}

/// Reaches an anchor serving `exports` on `target`, starting it where the target says to.
pub fn connect(target: &Target, exports: &[String], token: Option<&str>) -> io::Result<Link> {
    todo!("unit 7")
}
