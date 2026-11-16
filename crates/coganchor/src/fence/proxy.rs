//! The one way out of a fence that cuts the network: an HTTP proxy on loopback passing only
//! the hosts the fence names. Port of `hmz.coganchor.fence.proxy`. [Unit 5]
//!
//! A fenced child may open a TCP connection to this proxy's port and to nothing else, and is
//! handed it as `HTTPS_PROXY`; every byte that leaves the machine leaves through here, which
//! is where the hostname is read. Two kinds of request are served: `CONNECT host:port`, how
//! every HTTPS client asks for a tunnel, and an absolute-form `GET http://host/...`, how a
//! plain HTTP one asks for a page. Either passes only when [`Proxy::permits`] says so, and is
//! otherwise answered `403` with the host named in the body, so that a turn refused by the
//! fence says so rather than failing as a network that happened to be down.
//!
//! The name is resolved here rather than by the child, which cannot: that is what makes the
//! allow-list a list of names rather than of addresses. An IP literal is refused unless that
//! literal is itself listed.
//!
//! Where the process this one runs in reaches the network through a proxy of its own
//! (`HTTPS_PROXY`, `HTTP_PROXY` or `ALL_PROXY`, read once at [`Proxy::start`]), an allowed host
//! is reached through that proxy with a `CONNECT` tunnel, unless `NO_PROXY` names it -- a
//! plain HTTP request too, sent through the tunnel as it would be sent direct, never handed
//! to it as a request it reads. What is refused is refused here first either way.
//!
//! Each connection is held by one thread per direction, at most [`LIMIT`] at once, and a side
//! that closes its writing half has that passed on rather than taken for the end.

use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::net::{IpAddr, Shutdown, TcpListener, TcpStream, ToSocketAddrs};
use std::os::fd::AsRawFd;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::{self, JoinHandle};
use std::time::Duration;

use crate::proto::CHUNK_SIZE;

/// The ports a listed host may be reached on unless the entry names its own: HTTPS and HTTP.
/// (`PORTS` in the Python.)
pub const PORTS: [u16; 2] = [443, 80];

/// How many connections are held at once before another is turned away. (`LIMIT`.)
pub const LIMIT: usize = 256;

/// The most a request's head may be before it is refused. (`_HEAD`.)
const HEAD: usize = 64 * 1024;

/// How long a client may take to finish asking, and an upstream to answer a connect. (`_WAIT`.)
const WAIT: Duration = Duration::from_secs(30);

/// How often the accepting thread looks up to see whether it was stopped (`serve_forever(0.1)`).
const POLL: Duration = Duration::from_millis(100);

/// A proxy serving from a thread of its own. Stopped by [`Proxy::stop`] or by being dropped.
pub struct Proxy {
    /// The loopback port it listens on.
    pub port: u16,
    shared: Arc<Shared>,
    thread: Option<JoinHandle<()>>,
}

/// What the accepting thread and every connection's threads share.
struct Shared {
    allowed: Vec<String>,
    ports: Vec<u16>,
    upstream: Upstream,
    stopped: AtomicBool,
    room: AtomicUsize,
    limit: usize,
    next: AtomicU64,
    /// Every socket still open, so that stopping cuts them all (`_Server.sever`).
    held: Mutex<HashMap<u64, TcpStream>>,
}

impl Proxy {
    /// Starts a proxy on `127.0.0.1:0` passing `hosts` (exact, `*.suffix`, or `host:port`;
    /// ports 443 and 80 where none is named), chaining through this process's own proxy
    /// variables where they apply.
    pub fn start(hosts: &[String]) -> io::Result<Proxy> {
        Proxy::start_with(hosts, &PORTS, LIMIT)
    }

    /// [`Proxy::start`] with the ports an entry naming none passes, and the most connections
    /// held at once, given (`Proxy(allowed, ports=, limit=)`).
    pub fn start_with(hosts: &[String], ports: &[u16], limit: usize) -> io::Result<Proxy> {
        Proxy::start_upstream(hosts, ports, limit, Upstream::from_env())
    }

    /// [`Proxy::start_with`], chaining through `upstream` rather than the environment's.
    pub fn start_upstream(
        hosts: &[String],
        ports: &[u16],
        limit: usize,
        upstream: Upstream,
    ) -> io::Result<Proxy> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let port = listener.local_addr()?.port();
        let shared = Arc::new(Shared {
            allowed: hosts.to_vec(),
            ports: ports.to_vec(),
            upstream,
            stopped: AtomicBool::new(false),
            room: AtomicUsize::new(0),
            limit,
            next: AtomicU64::new(0),
            held: Mutex::new(HashMap::new()),
        });
        let serving = Arc::clone(&shared);
        let thread = thread::Builder::new()
            .name("fence-proxy".into())
            .spawn(move || serve(listener, serving))?;
        Ok(Proxy {
            port,
            shared,
            thread: Some(thread),
        })
    }

    /// Whether `host:port` is one the proxy passes.
    ///
    /// An entry is a hostname, matched exactly, or `*.suffix`, matching every name under that
    /// suffix but not the suffix itself. Both sides are compared case-insensitively and
    /// without a trailing dot. An entry passes its host on 443 or 80; one written `host:port`
    /// on that port and no other. An IP literal is compared as an address, and only against
    /// entries that are addresses too (`permits`).
    pub fn permits(hosts: &[String], host: &str, port: u16) -> bool {
        permits(hosts, host, port, &PORTS)
    }

    /// Stops serving and cuts every connection it still holds.
    pub fn stop(self) {
        // Dropping does it.
    }

    fn halt(&mut self) {
        self.shared.stopped.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
        let held = std::mem::take(&mut *lock(&self.shared.held));
        for sock in held.values() {
            let _ = sock.shutdown(Shutdown::Both);
        }
    }
}

impl Drop for Proxy {
    fn drop(&mut self) {
        self.halt();
    }
}

fn lock<T>(mutex: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// A hostname as it is compared: lower case, with no trailing dot and no brackets (`_host`).
fn host_of(name: &str) -> String {
    name.trim()
        .trim_matches(|c| c == '[' || c == ']')
        .trim_end_matches('.')
        .to_lowercase()
}

/// An allow-list entry split into its host and the one port it names, if it names one
/// (`_entry`).
fn entry(written: &str) -> (String, Option<u64>) {
    let written = written.trim();
    let (host, port) = if let Some(bracketed) = written.strip_prefix('[') {
        let (host, rest) = bracketed.split_once(']').unwrap_or((bracketed, ""));
        (host, rest.strip_prefix(':').unwrap_or(rest))
    } else if written.matches(':').count() == 1 {
        written.split_once(':').unwrap_or((written, ""))
    } else {
        (written, "")
    };
    let port = if !port.is_empty() && port.bytes().all(|b| b.is_ascii_digit()) {
        // Beyond any port, as Python's unbounded int would be: it then matches none.
        Some(port.parse().unwrap_or(u64::MAX))
    } else {
        None
    };
    (host_of(host), port)
}

/// Whether `host:port` is one `allowed` names, an entry naming no port passing `ports`
/// (`permits`).
pub fn permits(allowed: &[String], host: &str, port: u16, ports: &[u16]) -> bool {
    let host = host_of(host);
    if host.is_empty() {
        return false;
    }
    let address = host.parse::<IpAddr>().ok();
    for written in allowed {
        let (entry, only) = entry(written);
        let passes_port = match only {
            Some(only) => only == u64::from(port),
            None => ports.contains(&port),
        };
        if !passes_port {
            continue;
        }
        if let Some(address) = address {
            if entry.parse::<IpAddr>().ok() == Some(address) {
                return true;
            }
        } else if entry.starts_with("*.") {
            let suffix = &entry[1..];
            if host.ends_with(suffix) && host.len() > suffix.len() {
                return true;
            }
        } else if entry == host {
            return true;
        }
    }
    false
}

/// The proxy this one chains through: what `urllib.request.getproxies_environment` reads, and
/// `NO_PROXY` as `proxy_bypass_environment` reads it.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Upstream {
    /// `https_proxy`, which carries a `CONNECT`.
    pub https: Option<String>,
    /// `http_proxy`, which carries a plain HTTP request.
    pub http: Option<String>,
    /// `all_proxy`, which carries either.
    pub all: Option<String>,
    /// `no_proxy`.
    pub no: Option<String>,
}

impl Upstream {
    /// Read from this process's environment.
    pub fn from_env() -> Upstream {
        Upstream::from_vars(std::env::vars_os().filter_map(|(name, value)| {
            Some((name.into_string().ok()?, value.into_string().ok()?))
        }))
    }

    /// Read from variables as `getproxies_environment` reads them: any `*_PROXY` in any
    /// case, then the lower-case spelling over it (an empty one removing it), and
    /// `HTTP_PROXY` ignored in a CGI process (`REQUEST_METHOD` set).
    pub fn from_vars(vars: impl IntoIterator<Item = (String, String)>) -> Upstream {
        let vars: Vec<(String, String)> = vars.into_iter().collect();
        let mut proxies: HashMap<String, String> = HashMap::new();
        for (name, value) in &vars {
            if name.len() > 5
                && name.is_char_boundary(name.len() - 6)
                && name[name.len() - 6..].eq_ignore_ascii_case("_proxy")
                && !value.is_empty()
            {
                proxies.insert(name[..name.len() - 6].to_lowercase(), value.clone());
            }
        }
        if vars.iter().any(|(name, _)| name == "REQUEST_METHOD") {
            proxies.remove("http");
        }
        for (name, value) in &vars {
            if let Some(key) = name.strip_suffix("_proxy") {
                let key = key.to_lowercase();
                if value.is_empty() {
                    proxies.remove(&key);
                } else {
                    proxies.insert(key, value.clone());
                }
            }
        }
        Upstream {
            https: proxies.remove("https"),
            http: proxies.remove("http"),
            all: proxies.remove("all"),
            no: proxies.remove("no"),
        }
    }

    /// Whether `NO_PROXY` exempts `spelled` (`host:port`) (`proxy_bypass_environment`).
    fn bypassed(&self, spelled: &str) -> bool {
        let Some(no) = &self.no else {
            return false;
        };
        if no == "*" {
            return true;
        }
        let host = spelled.to_lowercase();
        // `_splitport`: the port is the digits after the last colon.
        let only = match host.rsplit_once(':') {
            Some((only, port)) if port.bytes().all(|b| b.is_ascii_digit()) => only.to_owned(),
            _ => host.clone(),
        };
        for name in no.split(',') {
            let name = name.trim();
            if name.is_empty() {
                continue;
            }
            let name = name.trim_start_matches('.').to_lowercase();
            if only == name || host == name {
                return true;
            }
            let dotted = format!(".{name}");
            if only.ends_with(&dotted) || host.ends_with(&dotted) {
                return true;
            }
        }
        false
    }

    /// The proxy a request for `host:port` is sent on through, or None to go direct: its host,
    /// its port, and the header that signs in to it where it is named with a user (`via`).
    fn via(&self, host: &str, port: u16, tunnel: bool) -> Option<Via> {
        let named = if tunnel { &self.https } else { &self.http }
            .as_ref()
            .or(self.all.as_ref())?;
        if self.bypassed(&spelled(host, port)) {
            return None;
        }
        let url = if named.contains("://") {
            named.clone()
        } else {
            format!("http://{named}")
        };
        if let Ok(split) = Split::parse(&url)
            && split.scheme.eq_ignore_ascii_case("http")
            && let Ok(Some(hostname)) = split.hostname()
            && let Ok(port) = split.port()
        {
            return Some(Via {
                host: hostname,
                port: port.filter(|&port| port != 0).unwrap_or(80),
                auth: split.credentials(),
            });
        }
        tracing::warn!("fence proxy: {named} is not an http:// proxy; going direct");
        None
    }
}

/// A proxy upstream of this one.
struct Via {
    host: String,
    port: u16,
    auth: Option<String>,
}

/// A host and port as a request line names them, an IPv6 address in brackets (`_spelled`).
fn spelled(host: &str, port: u16) -> String {
    let host = host_of(host);
    if host.contains(':') {
        format!("[{host}]:{port}")
    } else {
        format!("{host}:{port}")
    }
}

/// A URL split as `urllib.parse.urlsplit` splits it, as far as a proxy needs.
#[derive(Debug, Default)]
struct Split {
    scheme: String,
    netloc: String,
    path: String,
    query: String,
}

impl Split {
    fn parse(url: &str) -> Result<Split, String> {
        let mut rest = url;
        let mut split = Split::default();
        if let Some((scheme, after)) = url.split_once(':') {
            let mut chars = scheme.chars();
            if chars.next().is_some_and(|c| c.is_ascii_alphabetic())
                && chars.all(|c| c.is_ascii_alphanumeric() || "+-.".contains(c))
            {
                split.scheme = scheme.to_lowercase();
                rest = after;
            }
        }
        if let Some(after) = rest.strip_prefix("//") {
            let end = after.find(['/', '?', '#']).unwrap_or(after.len());
            split.netloc = after[..end].to_owned();
            rest = &after[end..];
            if split.netloc.contains('[') != split.netloc.contains(']') {
                return Err("Invalid IPv6 URL".into());
            }
            if split.netloc.contains('[') {
                bracketed(&split.netloc)?;
            }
        }
        let rest = rest.split_once('#').map_or(rest, |(before, _)| before);
        let (path, query) = rest.split_once('?').unwrap_or((rest, ""));
        split.path = path.to_owned();
        split.query = query.to_owned();
        Ok(split)
    }

    /// The host and port part, past any user.
    fn hostinfo(&self) -> &str {
        self.netloc
            .rsplit_once('@')
            .map_or(&self.netloc, |(_, h)| h)
    }

    fn host_and_port(&self) -> (&str, &str) {
        let info = self.hostinfo();
        if let Some((_, bracketed)) = info.split_once('[') {
            let (host, after) = bracketed.split_once(']').unwrap_or((bracketed, ""));
            (host, after.split_once(':').map_or("", |(_, port)| port))
        } else {
            info.split_once(':').unwrap_or((info, ""))
        }
    }

    fn hostname(&self) -> Result<Option<String>, String> {
        let (host, _) = self.host_and_port();
        Ok((!host.is_empty()).then(|| host.to_lowercase()))
    }

    fn port(&self) -> Result<Option<u16>, String> {
        let (_, port) = self.host_and_port();
        if port.is_empty() {
            return Ok(None);
        }
        if !port.bytes().all(|b| b.is_ascii_digit()) {
            return Err(format!(
                "Port could not be cast to integer value as '{port}'"
            ));
        }
        port.parse::<u16>()
            .map(Some)
            .map_err(|_| "Port out of range 0-65535".into())
    }

    /// The `Proxy-Authorization` value signing in as the user named, or none (`_credentials`).
    fn credentials(&self) -> Option<String> {
        let (user, _) = self.netloc.rsplit_once('@')?;
        let said = if user.contains(':') {
            user.to_owned()
        } else {
            format!("{user}:")
        };
        Some(format!("Basic {}", base64(&unquote(&said))))
    }
}

/// What `urlsplit` checks of a netloc holding a bracket (`_check_bracketed_netloc`): the
/// bracket first, then only a port after it, and an IPv6 address (or an IPvFuture) within.
fn bracketed(netloc: &str) -> Result<(), String> {
    let info = netloc.rsplit_once('@').map_or(netloc, |(_, h)| h);
    let host = match info.split_once('[') {
        Some((before, inside)) => {
            if !before.is_empty() {
                return Err("Invalid IPv6 URL".into());
            }
            let (host, port) = inside.split_once(']').unwrap_or((inside, ""));
            if !port.is_empty() && !port.starts_with(':') {
                return Err("Invalid IPv6 URL".into());
            }
            host
        }
        None => info.split_once(':').map_or(info, |(host, _)| host),
    };
    if let Some(future) = host.strip_prefix('v') {
        let valid = future.split_once('.').is_some_and(|(version, rest)| {
            !version.is_empty()
                && version.bytes().all(|b| b.is_ascii_hexdigit())
                && !rest.is_empty()
        });
        return if valid {
            Ok(())
        } else {
            Err("IPvFuture address is invalid".into())
        };
    }
    match host.parse::<IpAddr>() {
        Ok(IpAddr::V6(_)) => Ok(()),
        Ok(IpAddr::V4(_)) => Err("An IPv4 address cannot be in brackets".into()),
        Err(_) => Err(format!(
            "'{host}' does not appear to be an IPv4 or IPv6 address"
        )),
    }
}

/// `urllib.parse.unquote`: `%XX` decoded, the bytes read as UTF-8 with replacement.
fn unquote(said: &str) -> Vec<u8> {
    let bytes = said.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut at = 0;
    while at < bytes.len() {
        if bytes[at] == b'%'
            && at + 3 <= bytes.len()
            && bytes[at + 1].is_ascii_hexdigit()
            && bytes[at + 2].is_ascii_hexdigit()
        {
            let hex = std::str::from_utf8(&bytes[at + 1..at + 3]).unwrap_or("00");
            out.push(u8::from_str_radix(hex, 16).unwrap_or(0));
            at += 3;
            continue;
        }
        out.push(bytes[at]);
        at += 1;
    }
    String::from_utf8_lossy(&out).into_owned().into_bytes()
}

/// Standard base64, with padding.
fn base64(data: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let word = (u32::from(chunk[0]) << 16)
            | (u32::from(*chunk.get(1).unwrap_or(&0)) << 8)
            | u32::from(*chunk.get(2).unwrap_or(&0));
        for index in 0..4 {
            if index <= chunk.len() {
                out.push(char::from(
                    ALPHABET[(word >> (18 - 6 * index)) as usize & 63],
                ));
            } else {
                out.push('=');
            }
        }
    }
    out
}

/// The accepting loop: one thread per connection, and no more of them than the limit.
///
/// It waits on the listener for at most [`POLL`] at a time, as `serve_forever(0.1)` waits on
/// its selector, so that a connection is taken as it comes and a stop is seen soon after.
fn serve(listener: TcpListener, shared: Arc<Shared>) {
    while !shared.stopped.load(Ordering::SeqCst) {
        if !readable(&listener) {
            continue;
        }
        let client = match listener.accept() {
            Ok((client, _)) => client,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => continue,
            Err(error) => {
                // Out of descriptors, say: what is waiting stays waiting, so wait rather
                // than spin.
                tracing::warn!("fence proxy: could not accept a connection: {error}");
                thread::sleep(POLL);
                continue;
            }
        };
        if client.set_nonblocking(false).is_err() {
            continue;
        }
        if shared.room.fetch_add(1, Ordering::SeqCst) >= shared.limit {
            shared.room.fetch_sub(1, Ordering::SeqCst);
            tracing::warn!("fence proxy: too many connections; one turned away");
            let _ = client.shutdown(Shutdown::Both);
            continue;
        }
        let handling = Arc::clone(&shared);
        let spawned = thread::Builder::new()
            .name("fence-proxy".into())
            .spawn(move || {
                handle(&handling, client);
                handling.room.fetch_sub(1, Ordering::SeqCst);
            });
        if spawned.is_err() {
            shared.room.fetch_sub(1, Ordering::SeqCst);
        }
    }
}

/// Whether the listener has a connection waiting, waiting up to [`POLL`] for one.
fn readable(listener: &TcpListener) -> bool {
    let mut fd = libc::pollfd {
        fd: listener.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one valid `pollfd`, for a descriptor `listener` holds open throughout.
    let ready = unsafe { libc::poll(&mut fd, 1, POLL.as_millis() as libc::c_int) };
    ready > 0
}

impl Shared {
    /// Remembers a socket so that stopping cuts it; refused once stopped.
    fn hold(&self, sock: &TcpStream) -> Option<u64> {
        let id = self.next.fetch_add(1, Ordering::SeqCst);
        let clone = sock.try_clone().ok()?;
        // Checked under the lock `halt` empties the map under, so nothing is held after.
        let mut held = lock(&self.held);
        if self.stopped.load(Ordering::SeqCst) {
            return None;
        }
        held.insert(id, clone);
        Some(id)
    }

    fn drop_held(&self, id: Option<u64>, sock: &TcpStream) {
        if let Some(id) = id {
            lock(&self.held).remove(&id);
        }
        let _ = sock.shutdown(Shutdown::Both);
    }

    fn passes(&self, host: &str, port: u16) -> bool {
        permits(&self.allowed, host, port, &self.ports)
    }
}

/// One client connection: read what it asks for, decide, then relay or refuse (`_Handler`).
fn handle(shared: &Shared, mut client: TcpStream) {
    let id = shared.hold(&client);
    if id.is_some() {
        serve_one(shared, &mut client);
    }
    shared.drop_held(id, &client);
}

fn serve_one(shared: &Shared, client: &mut TcpStream) {
    // `settimeout(_WAIT)`: for sending as well as receiving.
    if client.set_read_timeout(Some(WAIT)).is_err() || client.set_write_timeout(Some(WAIT)).is_err()
    {
        return;
    }
    let Ok((head, rest)) = read_head(client) else {
        return;
    };
    let (method, target, version, fields) = match parse(&head) {
        Ok(parsed) => parsed,
        Err(error) => return answer(client, 400, "Bad Request", &format!("{error}\n")),
    };
    let (host, port, path) = match destination(&method, &target) {
        Ok(found) => found,
        Err(error) => return answer(client, 400, "Bad Request", &format!("{error}\n")),
    };
    if !shared.passes(&host, port) {
        tracing::info!("fence proxy: refused {host}:{port}");
        return answer(
            client,
            403,
            "Forbidden",
            &format!("hmz: {host}:{port} is not a host this run may reach\n"),
        );
    }
    let tunnel = method == "CONNECT";
    let via = shared.upstream.via(&host, port, tunnel);
    let reached = match &via {
        None => connect(&host_of(&host), port),
        Some(via) => connect(&via.host, via.port),
    };
    let mut upstream = match reached {
        Ok(upstream) => upstream,
        Err(error) => {
            return answer(
                client,
                502,
                "Bad Gateway",
                &format!("hmz: could not reach {host}:{port}: {error}\n"),
            );
        }
    };
    let held = shared.hold(&upstream);
    if held.is_some() {
        match exchange(client, &mut upstream, &via, &host, port, tunnel, || {
            if tunnel {
                rest.clone()
            } else {
                let mut first = forwarded(&method, &path, &version, &fields);
                first.extend_from_slice(&rest);
                first
            }
        }) {
            Err(Failed::Refused(error)) => {
                answer(client, 502, "Bad Gateway", &format!("hmz: {error}\n"));
            }
            Err(Failed::Io) | Ok(()) => {}
        }
    }
    shared.drop_held(held, &upstream);
}

/// Why an exchange ended early.
enum Failed {
    /// The proxy upstream would not open a tunnel (`_RefusedError`).
    Refused(String),
    /// A side went away.
    Io,
}

impl From<io::Error> for Failed {
    fn from(_: io::Error) -> Failed {
        Failed::Io
    }
}

fn exchange(
    client: &mut TcpStream,
    upstream: &mut TcpStream,
    via: &Option<Via>,
    host: &str,
    port: u16,
    tunnel: bool,
    first: impl FnOnce() -> Vec<u8>,
) -> Result<(), Failed> {
    let early = match via {
        None => Vec::new(),
        Some(via) => tunnelled(upstream, &spelled(host, port), via.auth.as_deref())?,
    };
    if tunnel {
        let mut said = b"HTTP/1.1 200 Connection Established\r\n\r\n".to_vec();
        said.extend_from_slice(&early);
        client.write_all(&said)?;
    } else if !early.is_empty() {
        client.write_all(&early)?;
    }
    let first = first();
    if !first.is_empty() {
        upstream.write_all(&first)?;
    }
    for sock in [&*client, &*upstream] {
        sock.set_read_timeout(None)?;
        sock.set_write_timeout(None)?;
    }
    relay(client, upstream)?;
    Ok(())
}

/// Opens a connection to `host:port`, trying each address it resolves to (`create_connection`).
fn connect(host: &str, port: u16) -> io::Result<TcpStream> {
    let mut last = io::Error::new(io::ErrorKind::NotFound, "getaddrinfo returns an empty list");
    for address in (host, port).to_socket_addrs()? {
        match TcpStream::connect_timeout(&address, WAIT) {
            Ok(stream) => {
                stream.set_read_timeout(Some(WAIT))?;
                stream.set_write_timeout(Some(WAIT))?;
                return Ok(stream);
            }
            Err(error) => last = error,
        }
    }
    Err(last)
}

/// Asks the proxy upstream for a tunnel to `target` (`_tunnelled`).
///
/// Returns whatever it sent past the end of its answer, which is the far end's already and so
/// the client's to read.
fn tunnelled(
    upstream: &mut TcpStream,
    target: &str,
    auth: Option<&str>,
) -> Result<Vec<u8>, Failed> {
    let mut head = format!("CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n");
    if let Some(auth) = auth {
        head.push_str(&format!("Proxy-Authorization: {auth}\r\n"));
    }
    head.push_str("\r\n");
    upstream.write_all(head.as_bytes())?;
    let (answer, rest) = match read_head(upstream) {
        Ok(read) => read,
        Err(HeadError::Io(_)) => return Err(Failed::Io),
        Err(error) => {
            return Err(Failed::Refused(format!(
                "the proxy upstream did not answer for {target}: {error}"
            )));
        }
    };
    let line = latin1(&split_crlf(&answer)[0]);
    if !line
        .split_whitespace()
        .nth(1)
        .is_some_and(|status| status.starts_with('2'))
    {
        return Err(Failed::Refused(format!(
            "the proxy upstream refused {target}: {line}"
        )));
    }
    Ok(rest)
}

/// Why a head could not be read.
#[derive(Debug)]
enum HeadError {
    TooLong,
    Closed,
    Io(io::Error),
}

impl std::fmt::Display for HeadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HeadError::TooLong => f.write_str("request head too long"),
            HeadError::Closed => f.write_str("connection closed mid-request"),
            HeadError::Io(error) => write!(f, "{error}"),
        }
    }
}

/// Reads up to the blank line ending a head: the head without it, and whatever came after
/// (`_read_head`).
fn read_head(sock: &mut TcpStream) -> Result<(Vec<u8>, Vec<u8>), HeadError> {
    let mut data = Vec::new();
    let mut chunk = vec![0; CHUNK_SIZE];
    loop {
        if let Some(at) = find(&data, b"\r\n\r\n") {
            let rest = data.split_off(at + 4);
            data.truncate(at);
            return Ok((data, rest));
        }
        if data.len() > HEAD {
            return Err(HeadError::TooLong);
        }
        let read = match sock.read(&mut chunk) {
            Ok(0) => return Err(HeadError::Closed),
            Ok(read) => read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(HeadError::Io(error)),
        };
        data.extend_from_slice(&chunk[..read]);
    }
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn latin1(bytes: &[u8]) -> String {
    bytes.iter().map(|&b| char::from(b)).collect()
}

/// A request's method, target, version and header lines.
type Request = (String, String, String, Vec<Vec<u8>>);

/// A request's head split into its method, target, version and header lines (`_parse`).
fn parse(head: &[u8]) -> Result<Request, String> {
    let mut lines = split_crlf(head);
    let line = latin1(&lines.remove(0));
    let parts: Vec<&str> = line.split_whitespace().collect();
    if parts.len() != 3 || !parts[2].starts_with("HTTP/") {
        return Err("malformed request line".into());
    }
    Ok((
        parts[0].to_uppercase(),
        parts[1].to_owned(),
        parts[2].to_owned(),
        lines,
    ))
}

fn split_crlf(data: &[u8]) -> Vec<Vec<u8>> {
    let mut lines = Vec::new();
    let mut rest = data;
    while let Some(at) = find(rest, b"\r\n") {
        lines.push(rest[..at].to_vec());
        rest = &rest[at + 2..];
    }
    lines.push(rest.to_vec());
    lines
}

/// Where a request is for: its host, its port, and the path to ask that host for
/// (`_destination`).
fn destination(method: &str, target: &str) -> Result<(String, u16, String), String> {
    if method == "CONNECT" {
        let split = Split::parse(&format!("//{target}"))?;
        let (Some(host), Some(port)) = (split.hostname()?, split.port()?) else {
            return Err("CONNECT needs host:port".into());
        };
        return Ok((host, port, String::new()));
    }
    let split = Split::parse(target)?;
    let host = split.hostname()?;
    let Some(host) = host.filter(|_| split.scheme == "http") else {
        return Err("only absolute http:// requests and CONNECT are proxied".into());
    };
    let port = split.port()?.filter(|&port| port != 0).unwrap_or(80);
    let mut path = if split.path.is_empty() {
        "/".to_owned()
    } else {
        split.path.clone()
    };
    if !split.query.is_empty() {
        path = format!("{path}?{}", split.query);
    }
    Ok((host, port, path))
}

/// Headers that describe the hop to this proxy rather than the request (`_HOP`).
const HOP: [&str; 4] = [
    "connection",
    "keep-alive",
    "proxy-connection",
    "proxy-authorization",
];

/// A plain HTTP request's head as the origin server is sent it: in origin form, and closed
/// after one exchange, since a kept-alive connection would carry the client's next request to
/// this host whatever host that request named (`_forwarded`).
fn forwarded(method: &str, path: &str, version: &str, fields: &[Vec<u8>]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::new();
    out.extend(method.chars().chain(" ".chars()).map(|c| c as u8));
    out.extend(path.chars().map(|c| c as u8));
    out.push(b' ');
    out.extend(version.chars().map(|c| c as u8));
    out.extend_from_slice(b"\r\n");
    for field in fields {
        let name = field.split(|&b| b == b':').next().unwrap_or(&[]);
        let name = latin1(name).trim().to_lowercase();
        if !HOP.contains(&name.as_str()) {
            out.extend_from_slice(field);
            out.extend_from_slice(b"\r\n");
        }
    }
    out.extend_from_slice(b"Connection: close\r\n\r\n");
    out
}

/// Answers with a short plain-text page and nothing more (`_answer`).
fn answer(sock: &mut TcpStream, code: u16, reason: &str, body: &str) {
    let said = format!(
        "HTTP/1.1 {code} {reason}\r\nContent-Type: text/plain; charset=utf-8\r\n\
         Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = sock.write_all(said.as_bytes());
}

/// Carries bytes both ways until both sides have finished sending; one direction on a thread
/// of its own, a half-close passed on (`_relay`).
fn relay(client: &TcpStream, upstream: &TcpStream) -> io::Result<()> {
    let (back_from, back_to) = (upstream.try_clone()?, client.try_clone()?);
    let back = thread::Builder::new()
        .name("fence-relay".into())
        .spawn(move || pump(back_from, back_to))?;
    pump(client.try_clone()?, upstream.try_clone()?);
    let _ = back.join();
    Ok(())
}

fn pump(mut source: TcpStream, mut sink: TcpStream) {
    let mut chunk = vec![0; CHUNK_SIZE];
    loop {
        let read = match source.read(&mut chunk) {
            Ok(0) => break,
            Ok(read) => read,
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => return cut(&source, &sink),
        };
        if sink.write_all(&chunk[..read]).is_err() {
            return cut(&source, &sink);
        }
    }
    let _ = sink.shutdown(Shutdown::Write);
}

/// One side is gone: take the other down with it, so the opposite pump ends too.
fn cut(source: &TcpStream, sink: &TcpStream) {
    let _ = source.shutdown(Shutdown::Both);
    let _ = sink.shutdown(Shutdown::Both);
}
