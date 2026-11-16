//! A half's side of a meeting. Port of `dial` in `hmz.coganchor.rendezvous`. [Unit 3]

use std::io;
use std::net::TcpStream;
use std::time::Duration;

use crate::broker::{Meeting, Role};

/// Meets the other half through the broker, returning a blocking, `TCP_NODELAY` socket that is
/// either a direct connection to it or the broker relaying for both.
pub fn dial(meeting: &Meeting, role: Role, timeout: Duration) -> io::Result<TcpStream> {
    todo!("unit 3")
}
