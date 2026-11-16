//! `--native`: the CLI installed on the target runs, and this side carries its streams. Port
//! of `drive` and its helpers in `hmz.coganchor.anchor` (lines 885-1692). [Unit 13]
//!
//! Nothing runs here: the CLI is started on the target, in the target's own copy of the
//! workspace, and this process is a pipe. Three things do not ride along on their own, and
//! each is answered here, in this order:
//!
//! 1. The environment is composed on the target, so what a provider hushes is taken off there
//!    with `env -u`, and what moves a home is set there with `env NAME=VALUE` ([`wrapping`]).
//!    Only names and paths go on that line; the account itself is the environment the CLI is
//!    given, which is no command line.
//! 2. Credentials go into a directory of the turn's own that only the target's user may enter
//!    (`mktemp -d`, `0700`; protocol/core.md 6.5.3.2, 5.7.1.3), a file at a time through the
//!    command writing it, their contents on its stdin; they are named to the CLI by variable,
//!    and taken away whatever happens. A sign-in that refreshes itself is lent to one turn at
//!    a time and its refreshed copy is written back over the original first.
//! 3. The flow's skills go into the virtual home the CLI is started in, never the workspace.
//!
//! Before any of that the CLI is looked for: a turn that cannot run leaves nothing behind it,
//! and exits 127 with the line that installs it.

mod local;
mod remote;
mod scripts;
#[cfg(test)]
mod tests;
mod untar;

use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde_json::Value;
use tracing::{info, warn};

use crate::client::RemoteClient;
use crate::cog::config::AnchorConfig;
use crate::cog::lending;
use crate::fence::Fence;
use crate::proto::{Meta, RemoteError, hello_fences, json};
use crate::transport;

use local::{join, joined, normpath};
use remote::{Interrupted, Io, Remote, SETTLING, Signals, Watched, drives, exchanged, ran};
use scripts::{BACK, FIND_PROGRAM, MAKE_SESSION, PACK, READ_BACK, SCRIPT, SWEEP, Spec};
use scripts::{WRITE_PRIVATELY, WRITE_WHOLE, sh};

/// How long the end of a turn may spend bringing back what it wrote in a projected directory
/// (`_BRINGING`).
const BRINGING: Duration = Duration::from_secs(30);

/// What `~` is said as in what the target is told of a fence (`abroad.HOME`).
const TILDE: &str = "~/";

/// The CLI a native turn was to run is not on the target (`NotInstalled`): the one failure
/// that means *install this there*, and so the one answered with 127.
#[derive(Debug, thiserror::Error)]
#[error("{0}")]
struct NotInstalled(String);

/// Runs `command` natively on the target, returning its status (127 where it is not installed
/// there, having said so; 130 where it was given up on from the keyboard).
pub fn drive(config: &AnchorConfig, command: &[OsString]) -> anyhow::Result<i32> {
    let started_in = settled(config, command)?;
    // A sign-in that refreshes itself is held for the whole turn before anything is reached:
    // one copy of it out at a time, and that copy brought back over the original at the end.
    let refreshing = local::refreshing(config.projects.iter().map(|(_, whence)| whence.as_str()));
    let _held = if refreshing.is_empty() {
        None
    } else {
        Some(lending::lent(
            &refreshing.iter().cloned().collect::<Vec<_>>(),
            true,
        )?)
    };
    // Taken before the target is reached: a `^C` from here on gives the turn up tidied.
    let signals = Signals::taken()?;
    let link = transport::connect(&config.target, &[config.export()], config.token.as_deref())?;
    let client = RemoteClient::new(link.channel.clone());
    let (mut stdout, mut stderr) = (std::io::stdout(), std::io::stderr());
    let mut io = Io {
        stdin: libc::STDIN_FILENO,
        stdout: &mut stdout,
        stderr: &mut stderr,
    };
    let said = driven(
        &Watched {
            remote: &client,
            signals: &signals,
        },
        config,
        command,
        &started_in,
        &config.target.describe(),
        &refreshing,
        environ(),
        &home(),
        &mut io,
    );
    client.close();
    link.close();
    said
}

/// Where the CLI starts, having checked there is a CLI and that it starts in the workspace.
fn settled(config: &AnchorConfig, command: &[OsString]) -> anyhow::Result<String> {
    if command.is_empty() {
        anyhow::bail!("no agent given");
    }
    let workspace = &config.workspace;
    let started_in = config.chdir.clone().unwrap_or_else(|| workspace.clone());
    if started_in != *workspace && !started_in.starts_with(&format!("{workspace}/")) {
        anyhow::bail!("{started_in} is not inside {workspace}");
    }
    Ok(started_in)
}

/// This process's environment, which the CLI runs with on top of the target's own.
fn environ() -> Meta {
    std::env::vars_os()
        .map(|(name, value)| (json::from_os(&name), Value::from(json::from_os(&value))))
        .collect()
}

/// This machine's home, as `os.path.expanduser("~")` finds it.
fn home() -> String {
    match std::env::var_os("HOME") {
        Some(home) if home.is_empty() => "/".into(),
        Some(home) => json::from_os(&home),
        None => nix::unistd::User::from_uid(nix::unistd::getuid())
            .ok()
            .flatten()
            .map_or_else(|| "/".into(), |user| json::from_os(user.dir.as_os_str())),
    }
}

/// A sign-in that refreshes itself, as it was put on the target for one turn (`_Lent`).
#[derive(Clone, Debug)]
struct Lent {
    /// The file on this machine it is a copy of.
    here: PathBuf,
    /// Where the copy is on the target.
    there: String,
    /// What the copy held as it was sent, which the original must still hold for the copy to
    /// be brought back over it.
    sent: Vec<u8>,
}

/// What a turn put on the target and here, for the end of it to take away again.
#[derive(Default)]
struct Left {
    lent: Vec<Lent>,
    session: String,
    /// Where each projected variable landed, in the order projected.
    projected: Vec<(String, String)>,
    /// The file here naming where they landed, for the turn's `--tell`.
    told: String,
}

/// The turn, against a connection, then everything it left taken away whatever became of it
/// (the `try`/`finally` of `drive`).
#[allow(clippy::too_many_arguments)]
fn driven(
    remote: &dyn Remote,
    config: &AnchorConfig,
    command: &[OsString],
    started_in: &str,
    whence: &str,
    refreshing: &BTreeSet<PathBuf>,
    environ: Meta,
    home: &str,
    io: &mut Io<'_>,
) -> anyhow::Result<i32> {
    let mut left = Left::default();
    let ran = turn(
        remote, config, command, started_in, whence, refreshing, environ, home, io, &mut left,
    );
    // Inside the channel rather than beside it: what this takes off the target is taken off
    // through it. And a refreshed sign-in is read back before the copy it is in is taken away.
    brought_back(remote, &left.lent, &config.workspace);
    brought_home(remote, &config.brings, &left.projected, &config.workspace);
    if !left.session.is_empty()
        && let Some(virtual_home) = &config.home
    {
        written_back(remote, &left.session, virtual_home, &config.workspace);
    }
    if !left.told.is_empty() {
        let _ = std::fs::remove_file(&left.told);
    }
    swept(remote, &left.session, &config.workspace);
    match ran {
        Err(why) if why.is::<NotInstalled>() => {
            crate::log::say(&why);
            Ok(crate::exit::NOT_INSTALLED)
        }
        Err(why) if why.is::<Interrupted>() => Ok(crate::exit::INTERRUPTED),
        other => other,
    }
}

/// Everything up to and including the CLI's run, noting in `left` what it put anywhere.
#[allow(clippy::too_many_arguments)]
fn turn(
    remote: &dyn Remote,
    config: &AnchorConfig,
    command: &[OsString],
    started_in: &str,
    whence: &str,
    refreshing: &BTreeSet<PathBuf>,
    environ: Meta,
    home: &str,
    io: &mut Io<'_>,
    left: &mut Left,
) -> anyhow::Result<i32> {
    let workspace = &config.workspace;
    remote.start(config.token.as_deref())?;
    if remote.interrupts() > 0 {
        return Err(Interrupted.into());
    }
    let program = installed(
        remote,
        &json::from_os(&command[0]),
        workspace,
        config,
        whence,
    )?;
    let mut said = BTreeMap::from([
        ("HUMANIZE".to_owned(), env!("CARGO_PKG_VERSION").to_owned()),
        ("HUMANIZE_TARGET".to_owned(), whence.to_owned()),
        // Agents surface this to the model; being explicit beats it guessing.
        ("HUMANIZE_WORKSPACE".to_owned(), workspace.clone()),
    ]);
    let mut fence = fenced(remote, config.fence.as_ref(), home)?;
    if !config.projects.is_empty() || config.home.is_some() {
        left.session = session(remote, workspace)?;
    }
    if !config.projects.is_empty() {
        // Noted only once every one has landed, as the Python's `projected` is: a turn that
        // failed half way brings nothing home.
        left.projected = projected(
            remote,
            &config.projects,
            &left.session,
            workspace,
            refreshing,
            &mut left.lent,
        )?;
        said.extend(left.projected.iter().cloned());
        if !config.tell.is_empty() {
            // Nobody told is a session copied as the turn ends rather than as it goes.
            let whose = hex::encode(rand::random::<[u8; 16]>());
            left.told = join(&config.tell, &whose);
            let lines: String = left
                .projected
                .iter()
                .map(|(name, landed)| format!("{name}={landed}\n"))
                .collect();
            let _ = local::writes(Path::new(&left.told), lines.as_bytes());
        }
    }
    if let Some(virtual_home) = &config.home {
        let spec = Spec::of(virtual_home)?;
        said.extend(homed(
            remote,
            &spec,
            &left.session,
            workspace,
            &left.projected,
        )?);
    }
    if !left.session.is_empty()
        && let Some(Value::Array(write)) = fence.as_mut().and_then(|told| told.get_mut("write"))
    {
        write.push(Value::from(left.session.clone()));
    }
    info!("driving {program} on {whence}");
    let mut argv = wrapping(&config.hushes, &said);
    argv.push(program);
    argv.extend(command[1..].iter().map(|word| json::from_os(word)));
    drives(remote, &argv, started_in, environ, fence.as_ref(), io)
}

/// What the target is told to hold a native CLI to, having said it can (`_fenced`): None for
/// a session held to nothing.
fn fenced(remote: &dyn Remote, fence: Option<&Fence>, home: &str) -> anyhow::Result<Option<Meta>> {
    let Some(fence) = fence else {
        return Ok(None);
    };
    if fence.open() {
        return Ok(None);
    }
    if !hello_fences(&remote.info(), !fence.online) {
        let more = if fence.online {
            ""
        } else {
            " ABI 4 and seccomp"
        };
        return Err(RemoteError::new(
            libc::EPERM,
            format!("the target cannot fence the CLI: it needs Landlock{more}"),
        )
        .into());
    }
    told(fence, home).map(Some)
}

/// What the target is told of a fence for a CLI that runs there (`abroad.told`, native): the
/// rules, each `[path, access]` in the order they are said, `online`, the model's `hosts`, the state the CLI writes under this machine's home
/// as `~/...`, `programs`, and the ports it may `listen` on where it names any.
fn told(fence: &Fence, home: &str) -> anyhow::Result<Meta> {
    if fence.drawn.is_empty() {
        anyhow::bail!("a fence drawn path by path cannot be drawn again on another machine");
    }
    let root = normpath(home);
    let under = format!("{}/", root.trim_end_matches('/'));
    let write: Vec<String> = fence
        .write
        .iter()
        .filter(|one| one.starts_with(&under))
        .map(|one| format!("{TILDE}{}", local::relpath(one, &root)))
        .collect();
    let mut said = Meta::new();
    said.insert("rules".into(), serde_json::json!(fence.drawn));
    said.insert("online".into(), Value::from(fence.online));
    said.insert("hosts".into(), Value::from(fence.hosts.clone()));
    said.insert("write".into(), Value::from(write));
    said.insert("programs".into(), Value::Bool(true));
    if !fence.listen.is_empty() {
        said.insert("listen".into(), Value::from(fence.listen.clone()));
    }
    Ok(said)
}

/// Finds the CLI on the target before anything is put there on its behalf (`_installed`): as
/// named, then by its last component, on the target's own `PATH`.
fn installed(
    remote: &dyn Remote,
    named: &str,
    workspace: &str,
    config: &AnchorConfig,
    whence: &str,
) -> anyhow::Result<String> {
    let base = named.rsplit('/').next().unwrap_or(named);
    let mut candidates = vec![named];
    if base != named {
        candidates.push(base);
    }
    for candidate in candidates {
        let (status, found) = ran(remote, &sh(FIND_PROGRAM, &[candidate]), workspace, b"")?;
        if status == 0 && !found.is_empty() {
            return Ok(found);
        }
    }
    let fix = if config.installs.is_empty() {
        String::new()
    } else {
        format!("; install it there with `{}`", config.installs)
    };
    Err(NotInstalled(format!("{named} is not installed on {whence}{fix}")).into())
}

/// Makes the directory this turn keeps its credentials and home in on the target, which only
/// its owner may enter, under the target's temporary directory (`_session`).
fn session(remote: &dyn Remote, workspace: &str) -> anyhow::Result<String> {
    let (status, made) = ran(remote, &sh(MAKE_SESSION, &[]), workspace, b"")?;
    if status != 0 || !made.starts_with('/') {
        let mut why = RemoteError::new(
            libc::EACCES,
            "could not make a private directory on the target",
        );
        if !made.is_empty() {
            why = why.with_filename(made);
        }
        return Err(why.into());
    }
    Ok(made)
}

/// Sets `name` to `value` in an ordered map kept as pairs, as a `dict` assignment does.
fn put(pairs: &mut Vec<(String, String)>, name: &str, value: String) {
    match pairs.iter_mut().find(|(one, _)| one == name) {
        Some(pair) => pair.1 = value,
        None => pairs.push((name.to_owned(), value)),
    }
}

/// Puts this turn's credentials on the target, one file at a time through the command that
/// writes it, the contents on its stdin and never in an argument (`_projected`). Each sign-in
/// that refreshes itself is noted in `lent` as it lands, so it is brought back however the
/// turn ends; answers where each variable landed.
fn projected(
    remote: &dyn Remote,
    projects: &[(String, String)],
    session: &str,
    workspace: &str,
    refreshing: &BTreeSet<PathBuf>,
    lent: &mut Vec<Lent>,
) -> anyhow::Result<Vec<(String, String)>> {
    let mut named = Vec::new();
    for (variable, whence) in projects {
        let landed = join(session, &variable.to_lowercase());
        for (one, parts) in local::files(whence) {
            let at = joined(&landed, parts.iter().map(String::as_str));
            let sent = std::fs::read(&one)?;
            let (status, said) = ran(remote, &sh(WRITE_PRIVATELY, &[&at]), workspace, &sent)?;
            if status != 0 {
                return Err(RemoteError::new(
                    libc::EACCES,
                    format!("could not put {variable} on the target: {said}"),
                )
                .with_filename(at)
                .into());
            }
            if refreshing.contains(&one) {
                lent.push(Lent {
                    here: one,
                    there: at,
                    sent,
                });
            }
        }
        put(&mut named, variable, landed);
    }
    Ok(named)
}

/// Builds the CLI's virtual home in the turn's directory on the target and writes the flow's
/// skills into it (`_homed`), answering the variables to start the CLI with.
fn homed(
    remote: &dyn Remote,
    spec: &Spec,
    session: &str,
    workspace: &str,
    projected: &[(String, String)],
) -> anyhow::Result<Vec<(String, String)>> {
    let landed = join(session, &spec.variable.to_lowercase());
    let words = spec.words();
    let mut args = vec![
        landed.as_str(),
        spec.variable.as_str(),
        spec.default.as_str(),
        spec.lodges.as_str(),
    ];
    args.extend(words.iter().map(String::as_str));
    let (status, moved) = ran(remote, &sh(SCRIPT, &args), workspace, b"")?;
    if status != 0 {
        return Err(RemoteError::new(
            libc::EACCES,
            format!("could not build {} on the target: {moved}", spec.variable),
        )
        .into());
    }
    for (name, whence) in &spec.skills {
        for (one, parts) in local::files(whence) {
            let at = joined(
                &landed,
                [spec.lodges.as_str(), name.as_str()]
                    .into_iter()
                    .chain(parts.iter().map(String::as_str)),
            );
            // Its owner's bits alone, a script's among them: the target need not be one user's.
            let mode = format!(
                "{:o}",
                std::fs::metadata(&one)?.permissions().mode() & 0o700
            );
            let feeding = std::fs::read(&one)?;
            let (status, said) = ran(remote, &sh(WRITE_WHOLE, &[&at, &mode]), workspace, &feeding)?;
            if status != 0 {
                // A skill that could not be written is a turn that runs without it, and
                // without all of it rather than half.
                warn!("could not carry {whence} to {at}: {said}");
                let half = joined(&landed, [spec.lodges.as_str(), name.as_str()]);
                let _ = ran(remote, &sh(SWEEP, &[&half]), workspace, b"");
                break;
            }
        }
    }
    let mut told = vec![(spec.variable.clone(), landed.clone())];
    if !spec.secures.is_empty() {
        let projected_here = projected.iter().any(|(one, _)| *one == spec.variable);
        told.push((
            spec.secures.clone(),
            if projected_here { landed } else { moved },
        ));
    }
    Ok(told)
}

/// Writes what the CLI refreshed each lent sign-in to back over the original (`_brought_back`),
/// only over one still holding exactly what was sent. Never fails: it is the way out.
fn brought_back(remote: &dyn Remote, lent: &[Lent], workspace: &str) {
    for one in lent {
        let here = one.here.display();
        let (status, now) = match exchanged(
            remote,
            &sh(READ_BACK, &[&one.there]),
            workspace,
            b"",
            SETTLING,
        ) {
            Ok(said) => said,
            Err(why) => {
                warn!("could not read {here} back from the target: {why}");
                continue;
            }
        };
        if now == one.sent {
            continue; // not refreshed, which is most turns
        }
        if status != 0
            || !local::refreshes(&now)
            || (local::is_json(&one.sent) && !local::is_json(&now))
        {
            warn!(
                "could not bring {here} back from the target, which left no whole sign-in \
                 there; if the account was refreshed there, it needs signing in again"
            );
            continue;
        }
        match std::fs::read(&one.here) {
            Ok(was) if was != one.sent => warn!(
                "{here} was refreshed both here and on the target during one turn; the vendor \
                 may have revoked it, and the account may need signing in again"
            ),
            Ok(_) => {
                if let Err(why) = local::writes(&one.here, &now) {
                    warn!("could not bring {here} back from the target: {why}");
                }
            }
            Err(why) => warn!("could not bring {here} back from the target: {why}"),
        }
    }
}

/// Brings what a turn wrote under a projected directory back here, one `tar` per directory,
/// in at most [`BRINGING`] all told (`_brought_home`). Never fails.
fn brought_home(
    remote: &dyn Remote,
    brings: &[(String, String)],
    projected: &[(String, String)],
    workspace: &str,
) {
    let mut wanted: Vec<((String, String), Vec<String>)> = Vec::new();
    for (named, into) in brings {
        let (variable, under) = named.split_once('/').unwrap_or((named, ""));
        let Some((_, landed)) = projected.iter().find(|(one, _)| one == variable) else {
            continue;
        };
        let key = (landed.clone(), into.clone());
        match wanted.iter_mut().find(|(one, _)| *one == key) {
            Some((_, paths)) => paths.push(under.to_owned()),
            None => wanted.push((key, vec![under.to_owned()])),
        }
    }
    let until = Instant::now() + BRINGING;
    for ((landed, into), paths) in wanted {
        let left = until.saturating_duration_since(Instant::now());
        if left.is_zero() {
            warn!("ran out of time bringing {into} back from the target");
            return;
        }
        let mut args = vec![landed.as_str()];
        args.extend(paths.iter().map(String::as_str));
        let unpacked =
            exchanged(remote, &sh(PACK, &args), workspace, b"", left).and_then(|(_, packed)| {
                if !packed.is_empty() {
                    untar::extract(&packed, Path::new(&into))?;
                }
                Ok(())
            });
        if let Err(why) = unpacked {
            warn!("could not bring {into} back from the target: {why}");
        }
    }
}

/// Writes back what the CLI replaced of the links in its virtual home ([`BACK`],
/// `_written_back`). Never fails.
fn written_back(
    remote: &dyn Remote,
    session: &str,
    virtual_home: &crate::cog::homes::Virtual,
    workspace: &str,
) {
    let spec = match Spec::of(virtual_home) {
        Ok(spec) => spec,
        Err(why) => {
            warn!("could not write back what the home replaced: {why}");
            return;
        }
    };
    let landed = join(session, &spec.variable.to_lowercase());
    let words = spec.words();
    let mut args = vec![landed.as_str()];
    args.extend(words.iter().map(String::as_str));
    match ran(remote, &sh(BACK, &args), workspace, b"") {
        Err(why) => warn!("could not write back what {landed} replaced: {why}"),
        Ok((status, said)) if status != 0 => {
            warn!("could not write back what {landed} replaced: {said}")
        }
        Ok(_) => {}
    }
}

/// Takes away everything this turn put on the target, its directory whole (`_swept`). Never
/// fails: a turn that failed to tidy up must not turn into a turn that failed.
fn swept(remote: &dyn Remote, session: &str, workspace: &str) {
    if session.is_empty() {
        return;
    }
    match ran(remote, &sh(SWEEP, &[session]), workspace, b"") {
        Err(why) => warn!("could not clear {session} from the target: {why}"),
        Ok((status, said)) if status != 0 => {
            warn!("could not clear {session} from the target: {said}")
        }
        Ok(_) => {}
    }
}

/// The `env` the CLI is started behind on the target (`_wrapping`): `-u NAME` for each hushed
/// variable, then `NAME=VALUE` for each it must have, both sorted. Every one a name or a
/// path, never a secret.
fn wrapping(hushes: &[String], said: &BTreeMap<String, String>) -> Vec<String> {
    let mut hushed = hushes.to_vec();
    hushed.sort();
    let mut argv = vec!["env".to_owned()];
    for name in hushed {
        argv.push("-u".into());
        argv.push(name);
    }
    argv.extend(said.iter().map(|(name, value)| format!("{name}={value}")));
    argv
}
