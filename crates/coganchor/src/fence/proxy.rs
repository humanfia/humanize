//! The one way out of a fence that cuts the network: an HTTP proxy on loopback passing only
//! the hosts the fence names. Port of `hmz.coganchor.fence.proxy`. [Unit 5]

use std::io;

/// A proxy serving from a thread of its own.
pub struct Proxy {
    /// The loopback port it listens on.
    pub port: u16,
}

impl Proxy {
    /// Starts a proxy on `127.0.0.1:0` passing `hosts` (exact, `*.suffix`, or `host:port`;
    /// ports 443 and 80 where none is named), chaining through this process's own proxy
    /// variables where they apply.
    pub fn start(hosts: &[String]) -> io::Result<Proxy> {
        todo!("unit 5")
    }

    /// Whether `host:port` is one the proxy passes.
    pub fn permits(hosts: &[String], host: &str, port: u16) -> bool {
        todo!("unit 5")
    }

    /// Stops serving.
    pub fn stop(self) {
        todo!("unit 5")
    }
}
