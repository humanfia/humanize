//! The broker's side of a meeting. Port of `Broker` in `hmz.coganchor.rendezvous`. [Unit 3]

use std::io;
use std::net::SocketAddr;
use std::time::Duration;

use crate::cli::BrokerArgs;

/// A broker listening for halves.
pub struct Broker {
    addr: SocketAddr,
}

impl Broker {
    /// Binds `host:port` (IPv4), giving halves `punching` to reach each other directly.
    pub fn bind(host: &str, port: u16, punching: Duration) -> io::Result<Broker> {
        todo!("unit 3")
    }

    /// The address it is bound to.
    pub fn local_addr(&self) -> SocketAddr {
        self.addr
    }

    /// Holds meetings until the process ends.
    pub fn serve_forever(self) -> io::Result<()> {
        todo!("unit 3")
    }
}

/// `coganchor broker`, writing `hmz internal anchor rendezvous listening BOUND LANDED`.
pub fn main(args: BrokerArgs) -> i32 {
    todo!("unit 3")
}
