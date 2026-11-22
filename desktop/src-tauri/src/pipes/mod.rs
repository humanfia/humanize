//! Pipes the app opens for the page (Section 3.12 of [DESKTOP]): one carrier to one daemon per
//! pipe, opened as its route says (Section 3.4 of [WIRE]), inside mutual TLS as the app's own
//! device where the carrier is untrusted, and its bytes carried both ways unchanged and in
//! order. The page opens, writes and closes one with `pipe_open`, `pipe_send` and
//! `pipe_close`, answers what one asks with `pipe_answer`, and is told how it stands and what
//! it carries by the events `pipe_state`, `pipe_data` and `pipe_closed`.

mod easytier;
mod identity;
mod route;
mod stdio;
mod tls;
mod ws;

use std::collections::HashMap;
use std::future::Future;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use base64::Engine;
use base64::engine::general_purpose::STANDARD as BASE64;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use tokio::net::TcpStream;
use tokio::sync::mpsc;
use tokio::time::Instant;

use crate::lock;
use route::Route;
use stdio::{Kids, Said};

/// A carrier, or the TLS inside one: bytes both ways.
pub trait Io: AsyncRead + AsyncWrite + Unpin + Send {}
impl<T: AsyncRead + AsyncWrite + Unpin + Send> Io for T {}
pub type Stream = Box<dyn Io>;

/// How long a carrier and its TLS may take to open (Section 3.4.9 of [WIRE]); installing is
/// not counted, nor is asking.
const OPENING: Duration = Duration::from_secs(30);

/// What the page is told.
#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum Event {
    State {
        pipe: String,
        state: &'static str,
        detail: String,
    },
    Data {
        pipe: String,
        data: String,
    },
    Closed {
        pipe: String,
        why: String,
    },
}

impl Event {
    /// The event's name.
    pub fn name(&self) -> &'static str {
        match self {
            Event::State { .. } => "pipe_state",
            Event::Data { .. } => "pipe_data",
            Event::Closed { .. } => "pipe_closed",
        }
    }
}

/// Where the page is told.
pub type Tell = Arc<dyn Fn(Event) + Send + Sync>;

/// What opening a pipe needs of the app.
#[derive(Clone, Default)]
pub struct Context {
    /// The data directory, where the identity and EasyTier are kept.
    pub data: PathBuf,
    /// The app's version as PyPI has hmz's, None for a development build.
    pub hmz: Option<String>,
    /// The login shell's environment `stdio:local` is run in, where an `hmz` is found in it.
    #[cfg(unix)]
    pub local: Option<crate::shell_env::Env>,
    /// The `hmz` in WSL `stdio:wsl` runs, as the app chose it (Section 3.4 of [DESKTOP]).
    #[cfg(windows)]
    pub wsl: Option<String>,
}

/// An open pipe, as the page reaches it.
struct Pipe {
    /// Where what the page sends goes, once the carrier is up; dropped to close it.
    sending: Option<mpsc::UnboundedSender<Vec<u8>>>,
    /// Where the page's answer goes, while the pipe is `asking` (Section 3.12.12 of
    /// [DESKTOP]); dropped with the pipe, which is a no.
    asking: Option<std::sync::mpsc::Sender<bool>>,
    /// Dropped to close it before then.
    _closing: mpsc::UnboundedSender<Vec<u8>>,
}

static PIPES: Mutex<Option<HashMap<String, Pipe>>> = Mutex::new(None);
static NEXT: AtomicU64 = AtomicU64::new(1);

/// The page pipes are opened for: one more each time every pipe is closed, so that a pipe the
/// page that went asked for is not opened after it.
static PAGE: AtomicU64 = AtomicU64::new(0);

/// The page pipes are opened for now.
fn page() -> u64 {
    PAGE.load(Ordering::SeqCst)
}

/// Opens the carrier `route` names, to the daemon `id` pins where it is untrusted, for the page
/// `page` says -- refused where every pipe was closed since; answers the pipe at once, and tells
/// the page how it stands from then on.
fn open_for(
    page: u64,
    route: &str,
    id: Option<&str>,
    context: Context,
    tell: Tell,
) -> Result<String, String> {
    let parsed = Route::parse(route)?;
    if !parsed.offered() {
        return Err(format!("{route} cannot be reached from here."));
    }
    let id = id.filter(|id| !id.is_empty()).map(str::to_owned);
    if !parsed.trusted() && id.is_none() {
        return Err(format!("{route} needs the id of the daemon it reaches."));
    }
    let pipe = format!("pipe-{}", NEXT.fetch_add(1, Ordering::Relaxed));
    let (closing, closed) = mpsc::unbounded_channel();
    {
        let mut pipes = lock(&PIPES);
        if PAGE.load(Ordering::SeqCst) != page {
            return Err("The page went.".into());
        }
        pipes.get_or_insert_default().insert(
            pipe.clone(),
            Pipe {
                sending: None,
                asking: None,
                _closing: closing,
            },
        );
    }
    log::info!("{pipe} opens {route}");
    let carried = Carried {
        pipe: pipe.clone(),
        route: route.to_owned(),
        tell,
    };
    tokio::spawn(carried.run(parsed, id, context, closed));
    Ok(pipe)
}

/// Sends bytes, in base64, down an open pipe.
pub fn send(pipe: &str, data: &str) -> Result<(), String> {
    let bytes = BASE64
        .decode(data)
        .map_err(|_| "data is not base64.".to_owned())?;
    let pipes = lock(&PIPES);
    let sending = pipes
        .as_ref()
        .and_then(|pipes| pipes.get(pipe))
        .ok_or_else(|| format!("There is no pipe {pipe}."))?
        .sending
        .as_ref()
        .ok_or_else(|| format!("{pipe} is not up."))?;
    sending
        .send(bytes)
        .map_err(|_| format!("There is no pipe {pipe}."))
}

/// Closes a pipe, stopping what it started; nothing where it is closed already.
pub fn close(pipe: &str) {
    lock(&PIPES).as_mut().and_then(|pipes| pipes.remove(pipe));
}

/// Has a pipe ask; answers where its answer comes, which is no answer once it is closed.
fn asking(pipe: &str) -> std::sync::mpsc::Receiver<bool> {
    let (answering, answered) = std::sync::mpsc::channel();
    if let Some(pipe) = lock(&PIPES).as_mut().and_then(|pipes| pipes.get_mut(pipe)) {
        pipe.asking = Some(answering);
    }
    answered
}

/// Gives a pipe that is asking the page's answer; nothing where there is no such pipe or it
/// is not asking.
pub fn answer(pipe: &str, install: bool) {
    let answering = lock(&PIPES)
        .as_mut()
        .and_then(|pipes| pipes.get_mut(pipe))
        .and_then(|pipe| pipe.asking.take());
    if let Some(answering) = answering {
        let _ = answering.send(install);
    }
}

/// Closes every pipe: the page went, or is loaded again (Section 3.12.8 of [DESKTOP]).
pub fn close_all() {
    let mut pipes = lock(&PIPES);
    PAGE.fetch_add(1, Ordering::SeqCst);
    pipes.take();
}

/// The PEP 440 version of the app's SemVer one, as PyPI has the same release: `0.5.0-rc.1` is
/// `0.5.0rc1`. None for a development build's `0.0.0`, and for what is no release.
pub fn pep440(semver: &str) -> Option<String> {
    let semver = semver.split('+').next().unwrap_or_default();
    let (release, pre) = match semver.split_once('-') {
        Some((release, pre)) => (release, Some(pre)),
        None => (semver, None),
    };
    let numbers: Vec<u64> = release
        .split('.')
        .map(|n| n.parse().ok())
        .collect::<Option<_>>()?;
    if numbers.len() != 3 || numbers == [0, 0, 0] {
        return None;
    }
    let mut version = format!("{}.{}.{}", numbers[0], numbers[1], numbers[2]);
    if let Some(pre) = pre {
        let n = pre.trim_start_matches(|c: char| !c.is_ascii_digit());
        let kind = match pre[..pre.len() - n.len()].trim_end_matches('.') {
            "alpha" | "a" => "a",
            "beta" | "b" => "b",
            "rc" | "c" => "rc",
            _ => return None,
        };
        let n: u64 = if n.is_empty() { 0 } else { n.parse().ok()? };
        version.push_str(&format!("{kind}{n}"));
    }
    Some(version)
}

/// One pipe's carrier, from opening to closing.
struct Carried {
    pipe: String,
    route: String,
    tell: Tell,
}

impl Carried {
    fn state(&self, state: &'static str, detail: &str) {
        (self.tell)(Event::State {
            pipe: self.pipe.clone(),
            state,
            detail: detail.to_owned(),
        });
    }

    async fn run(
        self,
        route: Route,
        id: Option<String>,
        context: Context,
        mut closed: mpsc::UnboundedReceiver<Vec<u8>>,
    ) {
        let kids = Kids::new();
        let said = Said::default();
        self.state("connecting", "");
        let opening = self.opened(route, id, context, &kids, &said);
        let opened = tokio::select! {
            opened = opening => Some(opened),
            _ = closed.recv() => None,
        };
        let why = match opened {
            None => "closed".to_owned(),
            Some(Err(why)) => {
                log::info!("{} could not open {}: {why}", self.pipe, self.route);
                self.state("failed", &why);
                why
            }
            Some(Ok(carrier)) => self.carry(carrier, closed, &said).await,
        };
        lock(&PIPES)
            .as_mut()
            .and_then(|pipes| pipes.remove(&self.pipe));
        let ending = kids.clone();
        let _ = tokio::task::spawn_blocking(move || ending.end()).await;
        log::info!("{} to {} closed: {why}", self.pipe, self.route);
        (self.tell)(Event::Closed {
            pipe: self.pipe,
            why,
        });
    }

    /// Carries the page's bytes to the carrier and the carrier's to the page until either
    /// ends; answers why it ended.
    async fn carry(
        &self,
        carrier: Stream,
        mut closed: mpsc::UnboundedReceiver<Vec<u8>>,
        said: &Said,
    ) -> String {
        let (sending, mut sent) = mpsc::unbounded_channel();
        {
            let mut pipes = lock(&PIPES);
            let Some(pipe) = pipes.as_mut().and_then(|pipes| pipes.get_mut(&self.pipe)) else {
                return "closed".into();
            };
            pipe.sending = Some(sending);
        }
        self.state("up", "");
        let (mut from, mut to) = tokio::io::split(carrier);
        // Each way apart, so that a write waiting on the daemon never stops a read.
        let reading = async {
            let mut chunk = vec![0; 1 << 16];
            loop {
                match from.read(&mut chunk).await {
                    Ok(n @ 1..) => (self.tell)(Event::Data {
                        pipe: self.pipe.clone(),
                        data: BASE64.encode(&chunk[..n]),
                    }),
                    Ok(_) => {
                        let said = lock(said).clone();
                        return if said.is_empty() {
                            "The daemon closed it.".into()
                        } else {
                            said
                        };
                    }
                    Err(why) => return why.to_string(),
                }
            }
        };
        let writing = async {
            while let Some(bytes) = sent.recv().await {
                if let Err(why) = async {
                    to.write_all(&bytes).await?;
                    to.flush().await
                }
                .await
                {
                    return why.to_string();
                }
            }
            "closed".into()
        };
        tokio::select! {
            why = reading => why,
            why = writing => why,
            _ = closed.recv() => "closed".into(),
        }
    }

    /// Opens the carrier, and mutual TLS inside it where it is untrusted.
    async fn opened(
        &self,
        route: Route,
        id: Option<String>,
        context: Context,
        kids: &Arc<Kids>,
        said: &Said,
    ) -> Result<Stream, String> {
        let deadline = Instant::now() + OPENING;
        let carrier: Stream = match &route {
            #[cfg(unix)]
            Route::Local => {
                let env = context
                    .local
                    .as_ref()
                    .ok_or("hmz is not installed on this machine.")?;
                let kid = kids.spawn(&mut stdio::local(env))?;
                stdio::carried(&kid, said, false)?
            }
            #[cfg(windows)]
            Route::Wsl(distro) => {
                // Local's `hmz`, as the app chose it, in the default distribution alone.
                let hmz = context.wsl.as_deref().filter(|_| distro.is_none());
                let kid = kids.spawn(&mut stdio::wsl(distro.as_deref(), hmz))?;
                stdio::carried(&kid, said, true)?
            }
            Route::Ssh(ssh) => {
                let (ssh, kids_, tell, pipe, name) = (
                    ssh.clone(),
                    kids.clone(),
                    self.tell.clone(),
                    self.pipe.clone(),
                    self.route.clone(),
                );
                let hmz = context.hmz.clone();
                // Asking has no deadline: it ends on the page's answer, or with the pipe.
                let kid = tokio::task::spawn_blocking(move || {
                    let answered = Mutex::new(None);
                    let say = |state: &'static str, detail: &str| {
                        // Held asking before the page is told, whose answer may come at once.
                        if state == "asking" {
                            *lock(&answered) = Some(asking(&pipe));
                        }
                        tell(Event::State {
                            pipe: pipe.clone(),
                            state,
                            detail: detail.to_owned(),
                        });
                    };
                    let asked = || {
                        let answered = lock(&answered).take();
                        answered.is_some_and(|answered| answered.recv().unwrap_or(false))
                    };
                    stdio::reach_ssh(&kids_, &ssh, &name, hmz.as_deref(), &say, &asked)
                })
                .await
                .map_err(|why| why.to_string())??;
                stdio::carried(&kid, said, false)?
            }
            Route::Tcp(host, port) => {
                self.within(deadline, async {
                    let tcp = TcpStream::connect((host.as_str(), *port))
                        .await
                        .map_err(|why| format!("{} could not be reached: {why}", self.route))?;
                    let _ = tcp.set_nodelay(true);
                    Ok(Box::new(tcp) as Stream)
                })
                .await?
            }
            Route::Ws(url) => {
                self.within(deadline, async { Ok(ws::carried(ws::open(url).await?)) })
                    .await?
            }
            Route::Relay(url) => {
                let id = id.as_deref().unwrap_or_default();
                self.within(deadline, ws::join(url, id)).await?
            }
            Route::Easytier(name) => return self.easytier(name, &id, &context, kids).await,
            _ => return Err(format!("{} cannot be reached from here.", self.route)),
        };
        match id.filter(|_| !route.trusted()) {
            Some(id) => {
                let me = self.identity(&context).await?;
                let tls = tls::connect(carrier, &me, &id, &self.route);
                let tls = self.within(deadline, tls).await?;
                Ok(Box::new(tls))
            }
            None => Ok(carrier),
        }
    }

    /// The app's device identity, made first where there is none.
    async fn identity(&self, context: &Context) -> Result<identity::Identity, String> {
        let dir = context.data.join("identity");
        tokio::task::spawn_blocking(move || identity::load(&dir))
            .await
            .map_err(|why| why.to_string())?
            .map_err(|why| format!("The device identity could not be made: {why}"))
    }

    /// Joins the EasyTier network of the entry `name`, downloading EasyTier first where it
    /// must, and opens mutual TLS over the port it forwards once the daemon answers there.
    async fn easytier(
        &self,
        name: &str,
        id: &Option<String>,
        context: &Context,
        kids: &Arc<Kids>,
    ) -> Result<Stream, String> {
        let id = id.as_deref().unwrap_or_default();
        let file = context.data.join("easytier.json");
        let entry = easytier::entries(&file)
            .map_err(|why| why.to_string())?
            .remove(name)
            .ok_or_else(|| format!("There is no EasyTier entry {name}."))?;
        let (data, tell, pipe) = (context.data.clone(), self.tell.clone(), self.pipe.clone());
        let core = tokio::task::spawn_blocking(move || {
            easytier::binary(&data, &|detail| {
                tell(Event::State {
                    pipe: pipe.clone(),
                    state: "installing",
                    detail: detail.to_owned(),
                });
            })
        })
        .await
        .map_err(|why| why.to_string())??;
        self.state("connecting", &format!("EasyTier {name}"));
        let local = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .and_then(|listener| listener.local_addr())
            .map_err(|why| why.to_string())?
            .port();
        let joining = kids.spawn(&mut easytier::joining(&core, &entry, local))?;
        let me = self.identity(context).await?;
        // Afresh once EasyTier is downloaded.
        self.within(Instant::now() + OPENING, async {
            // Until the daemon answers through it: EasyTier takes the port before it has
            // found the daemon.
            loop {
                if let Ok(Some(status)) = joining.try_wait() {
                    return Err(format!("EasyTier stopped: {status}"));
                }
                if let Ok(tcp) = TcpStream::connect(("127.0.0.1", local)).await {
                    match tls::connect(tcp, &me, id, &self.route).await {
                        Ok(tls) => return Ok(Box::new(tls) as Stream),
                        Err(why) if why.ends_with(tls::OTHER) => return Err(why),
                        Err(_) => {}
                    }
                }
                tokio::time::sleep(Duration::from_millis(500)).await;
            }
        })
        .await
    }

    /// `opening`, given up at `deadline` (Section 3.4.9 of [WIRE]).
    async fn within<T>(
        &self,
        deadline: Instant,
        opening: impl Future<Output = Result<T, String>>,
    ) -> Result<T, String> {
        tokio::time::timeout_at(deadline, opening)
            .await
            .unwrap_or_else(|_| {
                Err(format!(
                    "{} did not open within {} seconds.",
                    self.route,
                    OPENING.as_secs()
                ))
            })
    }
}

/// What a pipe command needs of the app: its data directory, its version, and, for
/// `stdio:local`, the login shell's environment where an `hmz` is found in it, or for
/// `stdio:wsl`, the `hmz` the app chose there.
async fn context(app: &AppHandle, route: &str) -> Context {
    let data = app.path().app_data_dir().unwrap_or_default();
    let version = app.package_info().version.to_string();
    #[cfg(unix)]
    let local = if route == "stdio:local" {
        let app = app.clone();
        tokio::task::spawn_blocking(move || {
            let env = app
                .state::<crate::Shell>()
                .env
                .get_or_init(crate::shell_env::login)
                .clone();
            crate::hmz::find(&env).map(|_| env)
        })
        .await
        .ok()
        .flatten()
    } else {
        None
    };
    #[cfg(windows)]
    let _ = route;
    #[cfg(windows)]
    let wsl = lock(&app.state::<crate::Shell>().hmz).clone();
    Context {
        data,
        hmz: pep440(&version),
        #[cfg(unix)]
        local,
        #[cfg(windows)]
        wsl,
    }
}

#[derive(Serialize)]
pub struct Opened {
    pipe: String,
}

#[tauri::command]
pub async fn pipe_open(
    app: AppHandle,
    route: String,
    id: Option<String>,
) -> Result<Opened, String> {
    let page = page();
    let context = context(&app, &route).await;
    let tell: Tell = Arc::new(move |event: Event| {
        if let Err(why) = app.emit(event.name(), &event) {
            log::warn!("the page could not be told: {why}");
        }
    });
    open_for(page, &route, id.as_deref(), context, tell).map(|pipe| Opened { pipe })
}

#[tauri::command]
pub fn pipe_send(pipe: String, data: String) -> Result<(), String> {
    send(&pipe, &data)
}

#[tauri::command]
pub fn pipe_close(pipe: String) {
    close(&pipe);
}

#[tauri::command]
pub fn pipe_answer(pipe: String, install: bool) {
    answer(&pipe, install);
}

fn entries_file(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_default()
        .join("easytier.json")
}

#[tauri::command]
pub fn easytier_list(app: AppHandle) -> Result<Vec<easytier::Shown>, String> {
    easytier::list(&entries_file(&app))
}

#[tauri::command]
pub fn easytier_set(
    app: AppHandle,
    name: String,
    secret: Option<String>,
    nodes: Vec<String>,
) -> Result<(), String> {
    easytier::set(&entries_file(&app), &name, secret.as_deref(), nodes)
}

#[tauri::command]
pub fn easytier_remove(app: AppHandle, name: String) -> Result<(), String> {
    easytier::remove(&entries_file(&app), &name)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc as std_mpsc;

    /// Opens a pipe for the page there is now.
    fn open(route: &str, id: Option<&str>, context: Context, tell: Tell) -> Result<String, String> {
        open_for(super::page(), route, id, context, tell)
    }

    /// What the page was told, as it was told it.
    fn page() -> (Tell, std_mpsc::Receiver<Event>) {
        let (told, heard) = std_mpsc::channel();
        let told = Mutex::new(told);
        (
            Arc::new(move |event| lock(&told).send(event).unwrap()),
            heard,
        )
    }

    fn next(heard: &std_mpsc::Receiver<Event>) -> Event {
        heard.recv_timeout(Duration::from_secs(20)).unwrap()
    }

    #[test]
    fn says_a_semver_release_as_pypi_does() {
        assert_eq!(pep440("0.5.0").as_deref(), Some("0.5.0"));
        assert_eq!(pep440("0.5.0-rc.1").as_deref(), Some("0.5.0rc1"));
        assert_eq!(pep440("1.2.3-alpha.4").as_deref(), Some("1.2.3a4"));
        assert_eq!(pep440("1.2.3-beta.12").as_deref(), Some("1.2.3b12"));
        assert_eq!(pep440("0.1.0-beta.1+build.7").as_deref(), Some("0.1.0b1"));
        assert_eq!(pep440("1.0.0-rc1").as_deref(), Some("1.0.0rc1"));
        assert_eq!(pep440("0.0.0"), None);
        for nothing in ["", "1.2", "1.2.3.4", "x.1.2", "1.2.3-dev.1", "1.2.3-rc.x"] {
            assert_eq!(pep440(nothing), None, "{nothing}");
        }
    }

    #[test]
    fn refuses_routes_it_does_not_open_and_untrusted_ones_without_an_id() {
        let (tell, _) = page();
        let open =
            |route: &str, id: Option<&str>| open(route, id, Context::default(), tell.clone());
        assert_eq!(open("nope", None).unwrap_err(), "nope is not a route.");
        assert_eq!(
            open("unix:", None).unwrap_err(),
            "unix: cannot be reached from here."
        );
        assert_eq!(
            open("webrtc:wss://r", Some("x")).unwrap_err(),
            "webrtc:wss://r cannot be reached from here."
        );
        #[cfg(not(windows))]
        assert_eq!(
            open("stdio:wsl", None).unwrap_err(),
            "stdio:wsl cannot be reached from here."
        );
        assert_eq!(
            open("stdio:ssh://-oProxyCommand=x", None).unwrap_err(),
            "stdio:ssh://-oProxyCommand=x cannot be reached from here."
        );
        assert_eq!(
            open("tcp://h:0", Some("x")).unwrap_err(),
            "tcp://h:0 is not a route."
        );
        assert_eq!(
            open("tcp://h:1", None).unwrap_err(),
            "tcp://h:1 needs the id of the daemon it reaches."
        );
        assert_eq!(
            open("relay:ws://h", Some("")).unwrap_err(),
            "relay:ws://h needs the id of the daemon it reaches."
        );
        assert_eq!(
            send("pipe-0", "AA==").unwrap_err(),
            "There is no pipe pipe-0."
        );
        assert_eq!(send("pipe-0", "!").unwrap_err(), "data is not base64.");
    }

    #[test]
    fn opens_nothing_for_a_page_that_went() {
        let (tell, _) = page();
        let gone = super::page().wrapping_sub(1);
        assert_eq!(
            open_for(gone, "tcp://h:1", Some("x"), Context::default(), tell).unwrap_err(),
            "The page went."
        );
    }

    #[tokio::test]
    async fn gives_up_on_a_carrier_not_open_in_time() {
        let (tell, _) = page();
        let carried = Carried {
            pipe: "p".into(),
            route: "tcp://h:1".into(),
            tell,
        };
        let opening = std::future::pending::<Result<(), String>>();
        assert_eq!(
            carried.within(Instant::now(), opening).await.unwrap_err(),
            "tcp://h:1 did not open within 30 seconds."
        );
    }

    #[test]
    fn says_its_events_as_the_page_reads_them() {
        let json = |event: &Event| serde_json::to_string(event).unwrap();
        let state = Event::State {
            pipe: "p".into(),
            state: "up",
            detail: "".into(),
        };
        assert_eq!(state.name(), "pipe_state");
        assert_eq!(json(&state), r#"{"pipe":"p","state":"up","detail":""}"#);
        let asking = Event::State {
            pipe: "p".into(),
            state: "asking",
            detail: "hmz is not installed on box.".into(),
        };
        assert_eq!(
            json(&asking),
            r#"{"pipe":"p","state":"asking","detail":"hmz is not installed on box."}"#
        );
        let data = Event::Data {
            pipe: "p".into(),
            data: "AA==".into(),
        };
        assert_eq!(
            (data.name(), json(&data).as_str()),
            ("pipe_data", r#"{"pipe":"p","data":"AA=="}"#)
        );
        let closed = Event::Closed {
            pipe: "p".into(),
            why: "w".into(),
        };
        assert_eq!(
            (closed.name(), json(&closed).as_str()),
            ("pipe_closed", r#"{"pipe":"p","why":"w"}"#)
        );
    }

    /// A pipe held as `open_for` holds one, that opens nothing.
    fn held(pipe: &str) -> mpsc::UnboundedReceiver<Vec<u8>> {
        let (closing, closed) = mpsc::unbounded_channel();
        lock(&PIPES).get_or_insert_default().insert(
            pipe.to_owned(),
            Pipe {
                sending: None,
                asking: None,
                _closing: closing,
            },
        );
        closed
    }

    #[test]
    fn gives_an_asking_pipe_its_answer_once_and_no_other_pipe_any() {
        // A pipe there is not, and one that is not asking: nothing.
        answer("asks-0", true);
        let _closed = held("asks-1");
        answer("asks-1", true);
        for install in [true, false] {
            let answered = asking("asks-1");
            answer("asks-1", install);
            assert_eq!(answered.recv(), Ok(install));
            // Asking no more: a second answer goes nowhere.
            answer("asks-1", !install);
            assert!(answered.recv().is_err());
        }
        // What was answered before it asked again is not its answer.
        let answered = asking("asks-1");
        assert!(answered.try_recv().is_err());
        close("asks-1");
    }

    #[test]
    fn closing_an_asking_pipe_ends_the_wait_as_a_no() {
        let _closed = held("asks-2");
        let answered = asking("asks-2");
        let waiting = std::thread::spawn(move || answered.recv().unwrap_or(false));
        close("asks-2");
        assert!(!waiting.join().unwrap());
        // A pipe closed before it asks takes no for its answer.
        assert!(asking("asks-2").recv().is_err());
        answer("asks-2", true);
    }

    #[tokio::test(flavor = "multi_thread")]
    async fn carries_a_tcp_pipe_inside_mutual_tls_and_closes_it() {
        let dir = tempfile::tempdir().unwrap();
        let daemon = identity::load(&dir.path().join("daemon")).unwrap();
        let id = identity::fingerprint(&daemon.cert).unwrap();
        let at = tls::tests::echoing(daemon).await;
        let context = Context {
            data: dir.path().join("app"),
            ..Context::default()
        };
        let (tell, heard) = page();
        let route = format!("tcp://{at}");
        let pipe = open(&route, Some(&id), context.clone(), tell.clone()).unwrap();
        let state = |state: &'static str| Event::State {
            pipe: pipe.clone(),
            state,
            detail: "".into(),
        };
        // Waited for here, off the runtime's workers, which carry the pipe.
        assert_eq!(
            [next(&heard), next(&heard)],
            [state("connecting"), state("up")]
        );
        send(&pipe, &BASE64.encode(b"ping")).unwrap();
        // The app's own identity, made where the data directory says.
        let me = identity::load(&dir.path().join("app/identity")).unwrap();
        let mine = identity::fingerprint(&me.cert).unwrap();
        let mut data = Vec::new();
        while data.len() < mine.len() + 4 {
            match next(&heard) {
                Event::Data { data: more, .. } => data.extend(BASE64.decode(more).unwrap()),
                other => panic!("{other:?}"),
            }
        }
        assert_eq!(data, format!("{mine}ping").into_bytes());
        close(&pipe);
        let closed = next(&heard);
        assert_eq!(
            closed,
            Event::Closed {
                pipe: pipe.clone(),
                why: "closed".into()
            }
        );
        assert_eq!(
            send(&pipe, "AA==").unwrap_err(),
            format!("There is no pipe {pipe}.")
        );

        // Another daemon than the one pinned: failed, then closed, and nothing carried.
        let other = identity::load(&dir.path().join("other")).unwrap();
        let wrong = identity::fingerprint(&other.cert).unwrap();
        let (tell, heard) = page();
        let pipe = open(&route, Some(&wrong), context, tell).unwrap();
        let events = [next(&heard), next(&heard), next(&heard)];
        let why = format!("{route} is not the daemon it was paired with.");
        assert_eq!(
            events,
            [
                Event::State {
                    pipe: pipe.clone(),
                    state: "connecting",
                    detail: "".into()
                },
                Event::State {
                    pipe: pipe.clone(),
                    state: "failed",
                    detail: why.clone()
                },
                Event::Closed { pipe, why },
            ]
        );
    }

    #[cfg(unix)]
    #[tokio::test(flavor = "multi_thread")]
    async fn carries_a_local_stdio_pipe_until_its_process_ends() {
        let dir = tempfile::tempdir().unwrap();
        let script = |path: &std::path::Path, text: &str| {
            use std::os::unix::fs::PermissionsExt;
            std::fs::create_dir_all(path.parent().unwrap()).unwrap();
            std::fs::write(path, text).unwrap();
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
        };
        // Stands in for hmz, in ~/.local/bin: says the sync line after what a shell printed,
        // echoes what it is sent, says why it stops, and stops.
        script(
            &dir.path().join(".local/bin/hmz"),
            "#!/bin/sh\n[ \"$*\" = 'daemon connect --stdio' ] || exit 2\necho Welcome\necho hmz-stdio/1\nhead -c 5\necho bye >&2\n",
        );
        // A login shell that reads no profile.
        let shell = dir.path().join("shell");
        script(
            &shell,
            "#!/bin/sh\n[ \"$1\" = -lc ] && exec /bin/sh -c \"$2\"\n",
        );
        let env = [
            ("HOME", dir.path().as_os_str()),
            ("PATH", "/usr/bin:/bin".as_ref()),
            ("SHELL", shell.as_os_str()),
        ]
        .into_iter()
        .map(|(key, value)| (key.into(), value.to_owned()))
        .collect();
        let context = Context {
            local: Some(env),
            ..Context::default()
        };
        let (tell, heard) = page();
        let pipe = open("stdio:local", None, context, tell).unwrap();
        let _connecting = next(&heard);
        assert!(matches!(next(&heard), Event::State { state: "up", .. }));
        send(&pipe, &BASE64.encode(b"hello world")).unwrap();
        let mut events = Vec::new();
        while !matches!(events.last(), Some(Event::Closed { .. })) {
            events.push(next(&heard));
        }
        let (closed, data) = events.split_last().unwrap();
        let carried: Vec<u8> = data
            .iter()
            .flat_map(|event| match event {
                Event::Data { data, .. } => BASE64.decode(data).unwrap(),
                other => panic!("{other:?}"),
            })
            .collect();
        assert_eq!(carried, b"hello");
        assert_eq!(
            closed,
            &Event::Closed {
                pipe,
                why: "bye".into()
            }
        );
    }
}
