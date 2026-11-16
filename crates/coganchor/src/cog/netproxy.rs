//! Making the agent's own outbound TCP connections come from the target. Port of
//! `hmz.coganchor.netproxy`. [Unit 11]
//!
//! One loopback listener per destination, so the port a connection arrives on says where it
//! was headed; each accepted connection is relayed through a tunnel out of the target.

use std::io;
use std::net::SocketAddr;
use std::sync::Arc;

use crate::client::RemoteClient;

/// The listeners standing in for remote destinations.
pub struct NetProxy {
    client: Arc<RemoteClient>,
}

impl NetProxy {
    /// A proxy leaving loopback, link-local, unspecified and `allow`ed destinations alone.
    pub fn new(client: Arc<RemoteClient>, allow: &[String]) -> io::Result<NetProxy> {
        todo!("unit 11")
    }

    /// The loopback address to connect to instead of `dest`, or `None` to leave it.
    pub fn redirect(&self, dest: SocketAddr) -> io::Result<Option<SocketAddr>> {
        todo!("unit 11")
    }
}
