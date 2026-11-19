//! Request dispatch for one connection. Port of `hmz.coganchor.serve.server`. [Unit 1]
//!
//! The handshake (`HELLO`: version, token, and the reply naming this machine, its exports and
//! what it can fence), routing `CHUNK`/`END`/`SIGNAL` to the [`Sink`] of their exchange, and
//! the mapping of failures onto errnos (`ENOSYS` for an unknown op, `EACCES` before the
//! handshake, `EINVAL` for a malformed request, `EIO` otherwise).
//!
//! The reader loop owns the channel: it decodes frames, runs short filesystem operations
//! inline, and hands long-lived work (a file being written, a command, a tunnel) to a sink, so
//! the loop never stalls on it. A sink that has closed its exchange is forgotten the next time
//! the loop looks, which is where the Python server's reaper threads forgot theirs.

use std::collections::HashMap;
use std::panic::{self, AssertUnwindSafe};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, MutexGuard, OnceLock};

use serde_json::Value;

use crate::anchor::{ExportTable, Outbox, Sink, fsops, sessions, tunnel};
use crate::fence::Able;
use crate::meta;
use crate::proto::{Channel, Frame, Kind, Meta, Op, PROTOCOL_VERSION, RemoteError};

/// The sinks of one connection, by the exchange they serve.
type Sinks = Arc<Mutex<HashMap<u64, Box<dyn Sink>>>>;

/// Every connection being served in this process, so that an interrupted anchor can stop what
/// each started on its way out (see [`close_all`]).
static LIVE: Mutex<Vec<(u64, Sinks)>> = Mutex::new(Vec::new());
static SERVED: AtomicU64 = AtomicU64::new(0);

fn locked<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// One connection being served.
pub struct Server {
    channel: Arc<Channel>,
    exports: Arc<ExportTable>,
    token: Option<String>,
    authenticated: bool,
    /// Set once the handshake named another protocol: the connection goes with it.
    refused: bool,
    sinks: Sinks,
}

impl Server {
    /// A server for one connection; requests are refused until a `HELLO` presents `token`
    /// (none needed when `token` is `None`). On a channel carried inside TLS the `HELLO`
    /// proves the key the channel is bound to instead, and `token` is not asked about.
    pub fn new(channel: Arc<Channel>, exports: Arc<ExportTable>, token: Option<String>) -> Server {
        let keyed = match channel.bound() {
            Some(bound) => bound.key.is_some(),
            None => token.is_some(),
        };
        Server {
            channel,
            exports,
            authenticated: !keyed,
            token,
            refused: false,
            sinks: Arc::default(),
        }
    }

    /// Serves until the client goes, then shuts down every sink, killing what they started.
    pub fn run(mut self) {
        let key = SERVED.fetch_add(1, Ordering::Relaxed);
        locked(&LIVE).push((key, self.sinks.clone()));
        while !self.refused {
            match self.channel.recv() {
                Ok(Some(frame)) => self.dispatch(frame),
                Ok(None) => break,
                Err(error) => {
                    tracing::warn!("connection dropped: {error}");
                    break;
                }
            }
        }
        locked(&LIVE).retain(|(k, _)| *k != key);
        shut(&self.sinks);
    }

    fn dispatch(&mut self, frame: Frame) {
        match frame.kind {
            Kind::Req => {
                // Exchanges that have closed since the last request are forgotten here, so a
                // `SIGNAL` never reaches a command already reaped.
                locked(&self.sinks).retain(|_, sink| !sink.is_done());
                self.request(frame)
            }
            Kind::Chunk | Kind::End => self.route(frame),
            other => tracing::debug!("ignoring unexpected {other:?} frame"),
        }
    }

    /// A `CHUNK` or `END` for the sink of its exchange; one for no exchange is dropped.
    ///
    /// The sink is taken out of the table while it is fed, since feeding may block (a command
    /// not reading its input), and the table must stay free for [`close_all`] meanwhile.
    fn route(&self, frame: Frame) {
        let Some(mut sink) = locked(&self.sinks).remove(&frame.id) else {
            return;
        };
        let stream = frame.stream();
        let fed = match frame.kind {
            Kind::Chunk => sink.feed(stream, &frame.body),
            _ => sink.end(stream),
        };
        match fed {
            Ok(()) if sink.is_done() => {}
            Ok(()) => {
                locked(&self.sinks).insert(frame.id, sink);
            }
            Err(error) => {
                // Torn down before it is dropped: a half-written file would otherwise keep
                // its temporary sibling for good.
                sink.shutdown();
                self.fail(frame.id, &error);
            }
        }
    }

    fn request(&mut self, frame: Frame) {
        let Some(op) = frame.op() else {
            self.fail(
                frame.id,
                &RemoteError::new(libc::ENOSYS, "unknown or missing operation"),
            );
            return;
        };
        if op == Op::Hello {
            self.hello(&frame);
            return;
        }
        if !self.authenticated {
            self.fail(
                frame.id,
                &RemoteError::new(libc::EACCES, "not authenticated"),
            );
            return;
        }
        let outcome = panic::catch_unwind(AssertUnwindSafe(|| self.carry_out(op, &frame)));
        let failed = match outcome {
            Ok(Ok(())) => return,
            Ok(Err(error)) => error,
            Err(panicked) => {
                let said = panicked
                    .downcast_ref::<String>()
                    .cloned()
                    .or_else(|| panicked.downcast_ref::<&str>().map(|s| (*s).to_owned()))
                    .unwrap_or_else(|| "internal error".into());
                tracing::error!("unhandled error serving {}: {said}", op.as_str());
                RemoteError::new(libc::EIO, said)
            }
        };
        self.fail(frame.id, &failed);
    }

    fn carry_out(&self, op: Op, frame: &Frame) -> Result<(), RemoteError> {
        let outbox = || self.channel.clone() as Arc<dyn Outbox>;
        let sink = match op {
            Op::Read => return fsops::read(frame.id, &frame.meta, &self.exports, &*self.channel),
            Op::Signal => return self.signal(frame),
            Op::Resize => return self.resize(frame),
            Op::Hold => return self.hold(frame),
            Op::Write => fsops::write(frame.id, &frame.meta, &frame.body, &self.exports, outbox())?,
            Op::Exec => sessions::exec(frame.id, &frame.meta, self.exports.clone(), outbox())?,
            Op::Connect => tunnel::connect(frame.id, &frame.meta, outbox())?,
            _ => {
                let reply = fsops::run(op, &frame.meta, &self.exports)?;
                let _ = self
                    .channel
                    .send(&Frame::reply(frame.id, reply, Vec::new()));
                return Ok(());
            }
        };
        locked(&self.sinks).insert(frame.id, sink);
        Ok(())
    }

    /// `SIGNAL {target, sig}`: passed to the command of exchange `target`, if it still runs;
    /// answered either way.
    fn signal(&self, frame: &Frame) -> Result<(), RemoteError> {
        // As the Python server reads it: `int(meta["target"])` always, `int(meta["sig"])` only
        // once there is a command to send it to.
        let number = |key: &str| number(frame, "signal", key);
        let target = number("target")?;
        let mut sinks = locked(&self.sinks);
        if let Some(sink) = sinks.get_mut(&(target as u64)) {
            sink.signal(number("sig")? as i32);
        }
        drop(sinks);
        let _ = self
            .channel
            .send(&Frame::reply(frame.id, Meta::new(), Vec::new()));
        Ok(())
    }

    /// `RESIZE {target, rows, cols}`: the terminal of the command of exchange `target` is
    /// given that window, if the command still runs under one; answered either way.
    fn resize(&self, frame: &Frame) -> Result<(), RemoteError> {
        let size = |key: &str| -> Result<u16, RemoteError> {
            u16::try_from(number(frame, "resize", key)?).map_err(|_| {
                RemoteError::new(
                    libc::EINVAL,
                    format!("malformed resize request: {key} must fit 16 bits"),
                )
            })
        };
        let (target, rows, cols) = (
            number(frame, "resize", "target")?,
            size("rows")?,
            size("cols")?,
        );
        if let Some(sink) = locked(&self.sinks).get_mut(&(target as u64)) {
            sink.resize(rows, cols);
        }
        let _ = self
            .channel
            .send(&Frame::reply(frame.id, Meta::new(), Vec::new()));
        Ok(())
    }

    /// `HOLD {target, held}`: the output of the command of exchange `target` is read no
    /// further while `held`, if the command still runs; answered either way.
    fn hold(&self, frame: &Frame) -> Result<(), RemoteError> {
        let target = number(frame, "hold", "target")?;
        let held = frame
            .meta
            .get("held")
            .and_then(Value::as_bool)
            .ok_or_else(|| {
                RemoteError::new(
                    libc::EINVAL,
                    "malformed hold request: held must be a boolean",
                )
            })?;
        if let Some(sink) = locked(&self.sinks).get_mut(&(target as u64)) {
            sink.hold(held);
        }
        let _ = self
            .channel
            .send(&Frame::reply(frame.id, Meta::new(), Vec::new()));
        Ok(())
    }

    /// `HELLO {version, token}`, or inside TLS `HELLO {version, proof}`: checked, then
    /// answered with what this machine is (and inside TLS this side's proof). One accepted
    /// may be repeated; another token, proof or version ends the connection.
    fn hello(&mut self, frame: &Frame) {
        let invalid = RemoteError::new(libc::EACCES, "invalid token");
        let mut proof = None;
        match self.channel.bound() {
            Some(bound) if bound.key.is_some() => {
                let said = frame.meta.get("proof").and_then(Value::as_str);
                match said.and_then(|said| bound.cog_proved(said)) {
                    Some(cog) => proof = bound.anchor_proof(&cog).map(hex::encode),
                    None => return self.refuse(frame.id, &invalid),
                }
            }
            Some(_) => {}
            None => {
                if let Some(token) = &self.token
                    && frame.meta.get("token").and_then(Value::as_str) != Some(token.as_str())
                {
                    return self.refuse(frame.id, &invalid);
                }
            }
        }
        let version = frame.meta.get("version").cloned().unwrap_or(Value::Null);
        if !speaks_ours(&version) {
            // Both ends check, because either may be the older build. The connection goes
            // with it: an untokened session starts out authenticated, so merely failing the
            // handshake would leave every following request working.
            return self.refuse(
                frame.id,
                &RemoteError::new(
                    libc::EPROTO,
                    format!(
                        "client speaks protocol {}, this Humanize speaks {PROTOCOL_VERSION}",
                        python_str(&version)
                    ),
                ),
            );
        }
        self.authenticated = true;
        let able = fences();
        let mut reply = meta! {
            "version" => PROTOCOL_VERSION,
            "hostname" => nix::unistd::gethostname()
                .map(|h| h.to_string_lossy().into_owned())
                .unwrap_or_default(),
            "platform" => crate::proto::this_platform(),
            "python" => concat!("coganchor ", env!("CARGO_PKG_VERSION")),
            "pid" => std::process::id(),
            "exports" => self.exports.hello(),
            "fence" => serde_json::json!({"fs": able.fs, "net": able.net}),
            // What this anchor serves beyond what the version promises, so that a client
            // asks only one that does.
            "resize" => true,
            "hold" => true,
        };
        if self.channel.bound().is_some() {
            reply.insert("proof".into(), proof.map_or(Value::Null, Value::from));
        }
        let _ = self
            .channel
            .send(&Frame::reply(frame.id, reply, Vec::new()));
    }

    fn fail(&self, id: u64, error: &RemoteError) {
        let _ = self.channel.send(&Frame::error(id, error));
    }

    /// A handshake refused: answered with `error`, and the connection closed.
    fn refuse(&mut self, id: u64, error: &RemoteError) {
        self.fail(id, error);
        self.channel.close();
        self.refused = true;
    }
}

/// An integer field of a request `op` names, as Python's `int()` reads it.
fn number(frame: &Frame, op: &str, key: &str) -> Result<i64, RemoteError> {
    let why = match frame.meta.get(key) {
        None => format!("'{key}'"),
        Some(value) => match python_int(value) {
            Some(number) => return Ok(number),
            None => format!("{key} must be an integer"),
        },
    };
    Err(RemoteError::new(
        libc::EINVAL,
        format!("malformed {op} request: {why}"),
    ))
}

/// Whether a `HELLO`'s `version` equals ours as Python's `==` judges it (`1.0` and `true` do).
fn speaks_ours(version: &Value) -> bool {
    match version {
        Value::Number(n) => n.as_f64() == Some(PROTOCOL_VERSION as f64),
        Value::Bool(b) => u64::from(*b) == PROTOCOL_VERSION,
        _ => false,
    }
}

/// A value as Python's `int()` reads it: an integer, a boolean, a float (truncated) or a
/// string of digits.
fn python_int(value: &Value) -> Option<i64> {
    match value {
        Value::Bool(b) => Some(i64::from(*b)),
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f.trunc() as i64)),
        Value::String(s) => s.trim().parse().ok(),
        _ => None,
    }
}

/// A value as Python's `str` spells it in a message.
fn python_str(value: &Value) -> String {
    match value {
        Value::Null => "None".into(),
        Value::Bool(true) => "True".into(),
        Value::Bool(false) => "False".into(),
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

/// What this machine can fence, asked once. A probe that fails says it can fence nothing,
/// rather than taking the handshake down with it.
///
/// The panic hook is silenced for the probe, which is process-wide: `coganchor anchor` asks
/// before it starts a thread of its own, so no other panic can fall into that window.
pub(crate) fn fences() -> Able {
    static ABLE: OnceLock<Able> = OnceLock::new();
    *ABLE.get_or_init(|| {
        // The default hook would write the failed probe to standard error as a crash.
        let hook = panic::take_hook();
        panic::set_hook(Box::new(|_| {}));
        let able = panic::catch_unwind(crate::fence::able).unwrap_or_default();
        panic::set_hook(hook);
        able
    })
}

fn shut(sinks: &Sinks) {
    let drained: Vec<_> = locked(sinks).drain().collect();
    for (_, mut sink) in drained {
        sink.shutdown();
    }
}

/// Shuts down every sink of every connection this process serves, so that an anchor being
/// stopped does not leave commands running here.
pub fn close_all() {
    let live: Vec<Sinks> = locked(&LIVE).iter().map(|(_, s)| s.clone()).collect();
    for sinks in live {
        shut(&sinks);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::net::UnixStream;

    use crate::proto::Stream;

    /// A server on one end of a socket pair, and the client's channel on the other.
    fn pair(token: Option<&str>, dir: &std::path::Path) -> (Channel, std::thread::JoinHandle<()>) {
        let (a, b) = UnixStream::pair().unwrap();
        let exports = ExportTable::parse(&[format!("/w:{}", dir.display())]).unwrap();
        let server = Server::new(
            Arc::new(Channel::from_unix(a).unwrap()),
            Arc::new(exports),
            token.map(str::to_owned),
        );
        let handle = std::thread::spawn(move || server.run());
        (Channel::from_unix(b).unwrap(), handle)
    }

    fn ask(client: &Channel, id: u64, op: Op, meta: Meta) -> Frame {
        client
            .send(&Frame::request(id, op, meta, Vec::new()))
            .unwrap();
        client.recv().unwrap().unwrap()
    }

    #[test]
    fn handshake_and_tokens() {
        let dir = tempfile::tempdir().unwrap();
        let (client, served) = pair(Some("s3cret"), dir.path());
        let early = ask(&client, 1, Op::Stat, meta! {"path" => "/w"});
        assert_eq!(early.kind, Kind::Err);
        assert_eq!(early.meta["strerror"], "not authenticated");
        let wrong = ask(
            &client,
            2,
            Op::Hello,
            meta! {"version" => 1, "token" => "nope"},
        );
        assert_eq!(wrong.meta["errno"], libc::EACCES);
        assert_eq!(wrong.meta["strerror"], "invalid token");
        // Another token ends the connection: the right one is not to be guessed on it.
        assert!(client.recv().unwrap().is_none());
        served.join().unwrap();
        let (client, served) = pair(Some("s3cret"), dir.path());
        let hello = ask(
            &client,
            3,
            Op::Hello,
            meta! {"version" => 1, "token" => "s3cret"},
        );
        assert_eq!(hello.kind, Kind::Rsp);
        assert_eq!(hello.meta["version"], 1);
        assert_eq!(hello.meta["platform"], crate::proto::this_platform());
        assert_eq!(hello.meta["exports"][0]["virtual"], "/w");
        assert!(hello.meta["fence"]["fs"].is_boolean());
        assert_eq!(hello.meta["resize"], true);
        assert_eq!(hello.meta["hold"], true);
        let again = ask(
            &client,
            4,
            Op::Hello,
            meta! {"version" => 1, "token" => "s3cret"},
        );
        assert_eq!(again.kind, Kind::Rsp);
        let stat = ask(&client, 5, Op::Stat, meta! {"path" => "/w"});
        assert_eq!(stat.meta["kind"], "dir");
        let mut odd = Frame::request(6, Op::Stat, Meta::new(), Vec::new());
        odd.meta.insert("op".into(), Value::from("teleport"));
        client.send(&odd).unwrap();
        let unknown = client.recv().unwrap().unwrap();
        assert_eq!(unknown.meta["errno"], libc::ENOSYS);
        assert_eq!(unknown.meta["strerror"], "unknown or missing operation");
        client.close();
        served.join().unwrap();
    }

    #[test]
    fn another_protocol_closes_the_connection() {
        let dir = tempfile::tempdir().unwrap();
        let (client, served) = pair(None, dir.path());
        let refused = ask(&client, 1, Op::Hello, meta! {"version" => 2});
        assert_eq!(refused.meta["errno"], libc::EPROTO);
        assert_eq!(
            refused.meta["strerror"],
            "client speaks protocol 2, this Humanize speaks 1"
        );
        assert!(client.recv().unwrap().is_none());
        served.join().unwrap();
    }

    #[test]
    fn writes_signals_and_strays() {
        let dir = tempfile::tempdir().unwrap();
        let (client, served) = pair(None, dir.path());
        // Unknown exchanges and stray replies are dropped without a word.
        client
            .send(&Frame::chunk(99, Stream::Data, b"x".to_vec()))
            .unwrap();
        client
            .send(&Frame::reply(98, Meta::new(), Vec::new()))
            .unwrap();
        let signalled = ask(&client, 2, Op::Signal, meta! {"target" => 77, "sig" => 15});
        assert_eq!(signalled.kind, Kind::Rsp);
        let resized = ask(
            &client,
            2,
            Op::Resize,
            meta! {"target" => 77, "rows" => 40, "cols" => 120},
        );
        assert_eq!(resized.kind, Kind::Rsp);
        let malformed = ask(&client, 2, Op::Resize, meta! {"target" => 77, "rows" => -1});
        assert_eq!(malformed.meta["errno"], libc::EINVAL);
        assert_eq!(
            malformed.meta["strerror"],
            "malformed resize request: rows must fit 16 bits"
        );
        let held = ask(&client, 2, Op::Hold, meta! {"target" => 77, "held" => true});
        assert_eq!(held.kind, Kind::Rsp);
        let malformed = ask(&client, 2, Op::Hold, meta! {"target" => 77, "held" => 1});
        assert_eq!(malformed.meta["errno"], libc::EINVAL);
        assert_eq!(
            malformed.meta["strerror"],
            "malformed hold request: held must be a boolean"
        );
        client
            .send(&Frame::request(
                3,
                Op::Write,
                meta! {"path" => "/w/f", "mode" => Value::Null},
                b"ab".to_vec(),
            ))
            .unwrap();
        client
            .send(&Frame::chunk(3, Stream::Data, b"cd".to_vec()))
            .unwrap();
        client.send(&Frame::end(3, Stream::Data)).unwrap();
        let written = client.recv().unwrap().unwrap();
        assert_eq!(written.kind, Kind::Rsp);
        assert_eq!(written.meta["size"], 4);
        assert_eq!(std::fs::read(dir.path().join("f")).unwrap(), b"abcd");
        client
            .send(&Frame::request(
                4,
                Op::Read,
                meta! {"path" => "/w/f"},
                Vec::new(),
            ))
            .unwrap();
        let chunk = client.recv().unwrap().unwrap();
        assert_eq!(
            (chunk.kind, chunk.body.as_slice()),
            (Kind::Chunk, &b"abcd"[..])
        );
        assert_eq!(client.recv().unwrap().unwrap().kind, Kind::Rsp);
        let malformed = ask(&client, 5, Op::Write, Meta::new());
        assert_eq!(
            malformed.meta["strerror"],
            "malformed write request: 'path'"
        );
        client.close();
        served.join().unwrap();
    }
}
