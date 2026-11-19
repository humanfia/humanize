//! The anchor: on the machine the work lands on, carrying out what a cog asks for.
//!
//! Port of `hmz.coganchor.serve` and `hmz internal anchor serve`. One [`server::Server`] per
//! connection reads frames, runs short filesystem operations inline, and hands long-lived work
//! (commands, tunnels) to [`Sink`]s that stream their output back through an [`Outbox`] from
//! threads of their own, so the reader never stalls.

pub mod exports;
pub mod fsops;
pub mod listen;
pub mod server;
pub mod sessions;
pub mod tunnel;

pub use exports::{Export, ExportTable};

use crate::cli::AnchorArgs;
use crate::proto::{Channel, Frame, ProtocolError, RemoteError, Stream};

/// Where a long-lived exchange sends its frames: the connection's writing half.
pub trait Outbox: Send + Sync {
    /// Sends one frame; fails once the connection has gone.
    fn send(&self, frame: Frame) -> Result<(), ProtocolError>;
}

impl Outbox for Channel {
    fn send(&self, frame: Frame) -> Result<(), ProtocolError> {
        Channel::send(self, &frame)
    }
}

/// A long-lived exchange the client feeds: a file being written, a command, a tunnel.
pub trait Sink: Send {
    /// A `CHUNK` the client sent on this exchange.
    fn feed(&mut self, stream: Stream, body: &[u8]) -> Result<(), RemoteError>;
    /// An `END` the client sent on this exchange.
    fn end(&mut self, stream: Stream) -> Result<(), RemoteError>;
    /// A `SIGNAL` naming this exchange. Only commands take one.
    fn signal(&mut self, _signal: i32) {}
    /// A `RESIZE` naming this exchange: the window of its terminal is now `rows` by `cols`.
    /// Only a command run under a pty takes one.
    fn resize(&mut self, _rows: u16, _cols: u16) {}
    /// A `HOLD` naming this exchange: its output is read no further while `held`, so that
    /// what it writes waits in it. Only commands take one.
    fn hold(&mut self, _held: bool) {}
    /// Whether the exchange has closed (its `RSP` or `ERR` sent), so it can be forgotten.
    fn is_done(&self) -> bool {
        false
    }
    /// The connection has gone: stop, killing whatever was started.
    fn shutdown(&mut self);
}

/// `coganchor anchor`: serve sessions on stdio, a port, or through a broker.
pub fn main(args: AnchorArgs) -> i32 {
    listen::main(args)
}
