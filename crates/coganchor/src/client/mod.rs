//! The cog's client of an anchor. Port of `hmz.coganchor.remote`. [Unit 7]
//!
//! One reader thread demultiplexes replies by message id. Filesystem calls block (the traced
//! process is stopped anyway); commands and tunnels are asynchronous: their frames arrive as
//! [`Event`]s on a channel, so a command running for minutes never stalls the supervisor.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::Duration;

use serde_json::Value;

use crate::proto::{
    CHUNK_SIZE, Channel, Frame, Kind, Meta, Op, PROTOCOL_VERSION, RemoteError, Stream,
};

/// How long a call may take before the target is presumed dead. `remote.DEFAULT_TIMEOUT`.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);

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

/// One exchange in flight. `remote._Pending`.
enum Pending {
    /// A call someone is waiting on, collecting whatever `CHUNK`s it brings (a `read`'s).
    Call {
        body: Vec<u8>,
        reply: Sender<Result<(Meta, Vec<u8>), RemoteError>>,
    },
    /// A command or tunnel, whose frames go on as they come.
    Stream(Sender<Event>),
}

impl Pending {
    /// Ends it with `outcome`.
    fn finish(self, outcome: Result<Meta, RemoteError>) {
        match self {
            Pending::Call { body, reply } => {
                let _ = reply.send(outcome.map(|meta| (meta, body)));
            }
            Pending::Stream(events) => {
                let _ = events.send(Event::Done(outcome));
            }
        }
    }
}

/// What the client and every exchange it opened share.
struct Shared {
    channel: Arc<Channel>,
    timeout: Duration,
    /// The next message id: monotonically increasing, from 1.
    ids: AtomicU64,
    /// The exchanges in flight, and whether the connection is closed.
    pending: Mutex<(bool, HashMap<u64, Pending>)>,
    info: Mutex<Meta>,
    reader: Mutex<Option<JoinHandle<()>>>,
}

impl Shared {
    /// Opens an exchange. `remote._register`.
    fn register(&self, pending: Pending) -> Result<u64, RemoteError> {
        let id = self.ids.fetch_add(1, Ordering::SeqCst);
        let mut state = self.pending.lock().unwrap();
        if state.0 {
            return Err(RemoteError::new(
                libc::EPIPE,
                "the connection to the target is closed",
            ));
        }
        state.1.insert(id, pending);
        Ok(id)
    }

    /// Forgets an exchange nobody is waiting on any more. `remote._discard`.
    fn discard(&self, id: u64) {
        self.pending.lock().unwrap().1.remove(&id);
    }

    /// Sends a frame, a closed connection being an `EPIPE`. `remote._send`.
    fn send(&self, frame: &Frame) -> Result<(), RemoteError> {
        self.channel
            .send(frame)
            .map_err(|error| RemoteError::new(libc::EPIPE, error.0))
    }

    /// Issues a request and blocks until the target replies. `remote.call`.
    fn call(&self, op: Op, request: Meta, body: Vec<u8>) -> Result<(Meta, Vec<u8>), RemoteError> {
        let (reply, answer) = mpsc::channel();
        let id = self.register(Pending::Call {
            body: Vec::new(),
            reply,
        })?;
        if let Err(error) = self.send(&Frame::request(id, op, request, body)) {
            self.discard(id);
            return Err(error);
        }
        self.wait(id, &answer)
    }

    /// Waits for a call's reply, for at most the timeout. `remote._await`.
    fn wait(
        &self,
        id: u64,
        answer: &Receiver<Result<(Meta, Vec<u8>), RemoteError>>,
    ) -> Result<(Meta, Vec<u8>), RemoteError> {
        match answer.recv_timeout(self.timeout) {
            Ok(outcome) => outcome,
            Err(RecvTimeoutError::Timeout) => {
                self.discard(id);
                Err(RemoteError::new(
                    libc::ETIMEDOUT,
                    format!(
                        "the target did not reply within {}s",
                        self.timeout.as_secs_f64()
                    ),
                ))
            }
            Err(RecvTimeoutError::Disconnected) => Err(RemoteError::new(
                libc::EPIPE,
                "the connection to the target is closed",
            )),
        }
    }

    /// Reads frames until the connection ends, then fails whatever is still waiting.
    /// `remote._read_loop`.
    fn read_loop(&self) {
        let failure = loop {
            match self.channel.recv() {
                Ok(Some(frame)) => self.deliver(frame),
                Ok(None) => break RemoteError::new(libc::EPIPE, "the target disconnected"),
                Err(error) => {
                    tracing::warn!("connection to the target lost: {error}");
                    break RemoteError::new(libc::EPIPE, error.0);
                }
            }
        };
        // Nothing is registered after this: a request now would wait for a reply nobody reads.
        self.pending.lock().unwrap().0 = true;
        self.fail_pending(failure);
    }

    /// Hands one frame to the exchange it belongs to. `remote._deliver`.
    fn deliver(&self, frame: Frame) {
        let mut state = self.pending.lock().unwrap();
        match frame.kind {
            Kind::Chunk | Kind::End => {
                let stream = frame.stream();
                match state.1.get_mut(&frame.id) {
                    Some(Pending::Call { body, .. }) if frame.kind == Kind::Chunk => {
                        body.extend_from_slice(&frame.body);
                    }
                    Some(Pending::Stream(events)) => {
                        let _ = events.send(if frame.kind == Kind::Chunk {
                            Event::Chunk(stream, frame.body)
                        } else {
                            Event::End(stream)
                        });
                    }
                    _ => {}
                }
            }
            Kind::Rsp | Kind::Err => {
                let Some(pending) = state.1.remove(&frame.id) else {
                    return;
                };
                drop(state);
                pending.finish(if frame.kind == Kind::Err {
                    Err(RemoteError::from_meta(&frame.meta))
                } else {
                    Ok(frame.meta)
                });
            }
            // A request from the target is nothing this side answers.
            Kind::Req => {}
        }
    }

    /// Ends every exchange in flight with `error`. `remote._fail_pending`.
    fn fail_pending(&self, error: RemoteError) {
        let pending: Vec<Pending> = {
            let mut state = self.pending.lock().unwrap();
            state.1.drain().map(|(_, pending)| pending).collect()
        };
        for one in pending {
            one.finish(Err(error.clone()));
        }
    }
}

/// A connection to an anchor.
pub struct RemoteClient {
    channel: Arc<Channel>,
    shared: Arc<Shared>,
}

impl RemoteClient {
    /// A client over a channel. Nothing is read until [`RemoteClient::start`].
    pub fn new(channel: Arc<Channel>) -> RemoteClient {
        RemoteClient::with_timeout(channel, DEFAULT_TIMEOUT)
    }

    /// A client whose calls wait at most `timeout` for their replies.
    pub fn with_timeout(channel: Arc<Channel>, timeout: Duration) -> RemoteClient {
        RemoteClient {
            channel: channel.clone(),
            shared: Arc::new(Shared {
                channel,
                timeout,
                ids: AtomicU64::new(1),
                pending: Mutex::new((false, HashMap::new())),
                info: Mutex::new(Meta::new()),
                reader: Mutex::new(None),
            }),
        }
    }

    /// Starts the reader thread and shakes hands, presenting `token`; returns the `HELLO`
    /// reply. Never call before a fork whose child must not inherit threads.
    pub fn start(&self, token: Option<&str>) -> Result<Meta, RemoteError> {
        {
            let mut reader = self.shared.reader.lock().unwrap();
            if reader.is_none() {
                let shared = self.shared.clone();
                *reader = Some(
                    std::thread::Builder::new()
                        .name("remote-reader".into())
                        .spawn(move || shared.read_loop())
                        .map_err(|error| RemoteError::from_io(&error, None))?,
                );
            }
        }
        let hello = crate::meta! {
            "version" => PROTOCOL_VERSION,
            "token" => token.map_or(Value::Null, Value::from),
        };
        let info = self.call(Op::Hello, hello)?;
        let version = info.get("version").cloned().unwrap_or(Value::Null);
        if version != PROTOCOL_VERSION {
            return Err(RemoteError::new(
                libc::EPROTO,
                format!(
                    "the target speaks protocol {version}, this Humanize speaks \
                     {PROTOCOL_VERSION}"
                ),
            ));
        }
        *self.shared.info.lock().unwrap() = info.clone();
        Ok(info)
    }

    /// The `HELLO` reply, once started.
    pub fn info(&self) -> Meta {
        self.shared.info.lock().unwrap().clone()
    }

    /// The channel this client speaks over.
    pub fn channel(&self) -> &Arc<Channel> {
        &self.channel
    }

    /// One short request, waiting for its reply.
    pub fn call(&self, op: Op, request: Meta) -> Result<Meta, RemoteError> {
        self.shared
            .call(op, request, Vec::new())
            .map(|(meta, _)| meta)
    }

    /// A whole file's content and the reply's `{size, mode, mtime_ns}`.
    pub fn read_file(&self, path: &str) -> Result<(Vec<u8>, Meta), RemoteError> {
        let (meta, body) = self
            .shared
            .call(Op::Read, crate::meta! {"path" => path}, Vec::new())?;
        Ok((body, meta))
    }

    /// Writes a whole file, returning its `stat` as the anchor replies it: the request with
    /// its `mode`, the bytes as `CHUNK`s on the data stream, then its `END`.
    pub fn write_file(
        &self,
        path: &str,
        data: &[u8],
        mode: Option<u32>,
    ) -> Result<Meta, RemoteError> {
        let shared = &self.shared;
        let (reply, answer) = mpsc::channel();
        let id = shared.register(Pending::Call {
            body: Vec::new(),
            reply,
        })?;
        let request = crate::meta! {
            "path" => path,
            "mode" => mode.map_or(Value::Null, Value::from),
        };
        let sent = shared
            .send(&Frame::request(id, Op::Write, request, Vec::new()))
            .and_then(|()| {
                for piece in data.chunks(CHUNK_SIZE) {
                    shared.send(&Frame::chunk(id, Stream::Data, piece.to_vec()))?;
                }
                shared.send(&Frame::end(id, Stream::Data))
            });
        if let Err(error) = sent {
            shared.discard(id);
            return Err(error);
        }
        shared.wait(id, &answer).map(|(meta, _)| meta)
    }

    /// Starts a command; `request` is the `EXEC` metadata without `op`.
    pub fn start_exec(&self, request: Meta) -> Result<Exchange, RemoteError> {
        self.open(Op::Exec, request)
    }

    /// Opens a TCP tunnel out of the anchor's machine.
    pub fn open_tunnel(&self, host: &str, port: u16) -> Result<Exchange, RemoteError> {
        self.open(Op::Connect, crate::meta! {"host" => host, "port" => port})
    }

    /// Opens an exchange whose frames arrive as [`Event`]s.
    fn open(&self, op: Op, request: Meta) -> Result<Exchange, RemoteError> {
        let (sender, events) = mpsc::channel();
        let id = self.shared.register(Pending::Stream(sender))?;
        if let Err(error) = self
            .shared
            .send(&Frame::request(id, op, request, Vec::new()))
        {
            self.shared.discard(id);
            return Err(error);
        }
        Ok(Exchange {
            id,
            events,
            client: self.shared.clone(),
        })
    }

    /// Closes the connection; every open exchange receives `Event::Done(Err(..))`.
    pub fn close(&self) {
        {
            let mut state = self.shared.pending.lock().unwrap();
            if state.0 {
                return;
            }
            state.0 = true;
        }
        self.channel.close();
        // The reader is not joined: over a pipe it is woken only when the process at the
        // other end goes, which is its owner's to end. Whatever it still delivers finds
        // nothing waiting.
        self.shared
            .fail_pending(RemoteError::new(libc::EPIPE, "connection closed"));
    }
}

/// A command or tunnel in progress.
pub struct Exchange {
    /// Its message id.
    pub id: u64,
    /// What arrives on it, ending with `Event::Done`.
    pub events: Receiver<Event>,
    client: Arc<Shared>,
}

impl Exchange {
    /// Sends bytes on `stream` (`Stdin` for a command, `Data` for a tunnel).
    pub fn send(&self, stream: Stream, body: &[u8]) -> Result<(), RemoteError> {
        self.client
            .send(&Frame::chunk(self.id, stream, body.to_vec()))
    }

    /// Ends `stream`.
    pub fn end(&self, stream: Stream) -> Result<(), RemoteError> {
        self.client.send(&Frame::end(self.id, stream))
    }

    /// Sends a command's process group `signal` (a `SIGNAL` request naming this exchange).
    pub fn signal(&self, signal: i32) -> Result<(), RemoteError> {
        self.client
            .call(
                Op::Signal,
                crate::meta! {"target" => self.id, "sig" => signal},
                Vec::new(),
            )
            .map(|_| ())
    }
}
