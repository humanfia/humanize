//! The cog's client of an anchor. Port of `hmz.coganchor.remote`. [Unit 7]
//!
//! One reader thread demultiplexes replies by message id. Filesystem calls block (the traced
//! process is stopped anyway); commands and tunnels are asynchronous: their frames arrive as
//! [`Event`]s on a channel, so a command running for minutes never stalls the supervisor.

use std::sync::Arc;
use std::sync::mpsc::Receiver;

use crate::proto::{Channel, Meta, Op, RemoteError, Stream};

/// What arrives on a long-lived exchange.
#[derive(Debug)]
pub enum Event {
    /// A piece of one of the exchange's streams.
    Chunk(Stream, Vec<u8>),
    /// The end of one of its streams.
    End(Stream),
    /// The exchange closed: the `RSP` metadata, or the `ERR`. Also sent, as an `EPIPE`-like
    /// error, when the connection is lost.
    Done(Result<Meta, RemoteError>),
}

/// A connection to an anchor.
pub struct RemoteClient {
    channel: Arc<Channel>,
}

impl RemoteClient {
    /// A client over a channel. Nothing is read until [`RemoteClient::start`].
    pub fn new(channel: Arc<Channel>) -> RemoteClient {
        RemoteClient { channel }
    }

    /// Starts the reader thread and shakes hands, presenting `token`; returns the `HELLO`
    /// reply. Never call before a fork whose child must not inherit threads.
    pub fn start(&self, token: Option<&str>) -> Result<Meta, RemoteError> {
        todo!("unit 7")
    }

    /// The `HELLO` reply, once started.
    pub fn info(&self) -> Meta {
        todo!("unit 7")
    }

    /// One short request, waiting for its reply.
    pub fn call(&self, op: Op, request: Meta) -> Result<Meta, RemoteError> {
        todo!("unit 7")
    }

    /// A whole file's content and the reply's `{size, mode, mtime_ns}`.
    pub fn read_file(&self, path: &str) -> Result<(Vec<u8>, Meta), RemoteError> {
        todo!("unit 7")
    }

    /// Writes a whole file, returning its `stat` as the anchor replies it.
    pub fn write_file(
        &self,
        path: &str,
        data: &[u8],
        mode: Option<u32>,
    ) -> Result<Meta, RemoteError> {
        todo!("unit 7")
    }

    /// Starts a command; `request` is the `EXEC` metadata without `op`.
    pub fn start_exec(&self, request: Meta) -> Result<Exchange, RemoteError> {
        todo!("unit 7")
    }

    /// Opens a TCP tunnel out of the anchor's machine.
    pub fn open_tunnel(&self, host: &str, port: u16) -> Result<Exchange, RemoteError> {
        todo!("unit 7")
    }

    /// Closes the connection; every open exchange receives `Event::Done(Err(..))`.
    pub fn close(&self) {
        todo!("unit 7")
    }
}

/// A command or tunnel in progress.
pub struct Exchange {
    /// Its message id.
    pub id: u64,
    /// What arrives on it, ending with `Event::Done`.
    pub events: Receiver<Event>,
    client: Arc<Channel>,
}

impl Exchange {
    /// Sends bytes on `stream` (`Stdin` for a command, `Data` for a tunnel).
    pub fn send(&self, stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        todo!("unit 7")
    }

    /// Ends `stream`.
    pub fn end(&self, stream: Stream) -> Result<(), RemoteError> {
        todo!("unit 7")
    }

    /// Sends a command's process group `signal` (a `SIGNAL` request naming this exchange).
    pub fn signal(&self, signal: i32) -> Result<(), RemoteError> {
        todo!("unit 7")
    }
}
