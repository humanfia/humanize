//! The fence around a supervised agent: Landlock plus, where the network is cut, the loopback
//! proxy. Port of `_Walls` in `hmz.coganchor.anchor`. [Unit 12]

use std::io;

use crate::fence::Fence;
use crate::fence::landlock::Ruleset;
use crate::fence::proxy::Proxy;

/// A fence made ready to be put up in the agent's child.
pub struct Walls {
    pub ruleset: Ruleset,
    pub proxy: Option<Proxy>,
    /// Whether the socket and listen filters go up too.
    pub sockets: bool,
}

impl Walls {
    /// Opens what `fence` lets be written and starts its proxy.
    pub fn ready(fence: &Fence) -> io::Result<Walls> {
        todo!("unit 12")
    }

    /// The variables the agent is started with inside the walls (`TMPDIR`, proxy variables).
    pub fn environ(&self) -> Vec<(String, String)> {
        todo!("unit 12")
    }
}
