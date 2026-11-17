//! Running a cog session end to end. Port of `connect`, `check` and `_supervised` in
//! `hmz.coganchor.anchor`, and the agent half of `hmz.cli.anchor`. [Unit 12]
//!
//! `--check` prints what the target is and exits 0; `--native` hands over to [`drive`];
//! otherwise: build the virtual home, resolve the agent and its state paths, prepare the
//! mirror, connect, and run the agent under the supervisor inside the lent credentials,
//! walled where a fence is asked for. Exit statuses: the agent's own; 1 (`hmz: <reason>`) on a
//! connection, protocol, OS or value error; 127 where the native CLI is missing; 130 on ^C.
//!
//! [`drive`]: crate::cog::drive

use std::io::{self, Write};

use serde_json::Value;

use crate::cli::CogArgs;
use crate::client::RemoteClient;
use crate::cog::config::{AnchorConfig, Refusal, os_said};
use crate::exit;
use crate::proto::{Meta, Op, RemoteError};
use crate::transport;

/// What a copy of the workspace that could not be made is said as (`UNMIRRORED`), which is
/// also what a turn that failed for one is known by (`hmz.coganchor.backends.SIGNS`).
pub const UNMIRRORED: &str = "cannot keep the local copy of the work at";

/// What a harness on a machine other than Linux on x86-64 or aarch64 is refused with
/// (protocol/core.md 6.3.2.1).
pub const UNSUPERVISABLE: &str = "a mirrored session needs Linux on x86-64 or aarch64";

/// Runs `coganchor cog`.
pub fn main(args: CogArgs) -> i32 {
    crate::log::init(args.log_level.as_deref(), "warning");
    if args.command.is_empty() && !args.check {
        return usage("no agent given; try `hmz internal anchor claude`");
    }
    let config = match AnchorConfig::settle(&args) {
        Ok(config) => config,
        // Settings a session could not be run under are bad arguments, not failed sessions,
        // so they exit 2 the way argparse's own rejections do (cli/anchor.py:107-112).
        Err(Refusal::Usage(said)) => return usage(&said),
        Err(Refusal::Failed(said)) => return exit::failed(said),
    };
    let outcome = if config.check {
        check(&config).map(|found| {
            let mut out = io::stdout().lock();
            let _ = out.write_all(found.as_bytes());
            let _ = out.flush();
            0
        })
    } else {
        connect(&config)
    };
    match outcome {
        Ok(status) => status,
        Err(why) => answered(&why),
    }
}

/// The status an error ends the session with: 130 for an interruption, else 1 with
/// `hmz: <reason>`, said as Python says the exception (cli/anchor.py:127-145).
fn answered(why: &anyhow::Error) -> i32 {
    let io = why.downcast_ref::<io::Error>();
    let inner = io.and_then(io::Error::get_ref);
    if why.is::<Interrupted>() || inner.is_some_and(|inner| inner.is::<Interrupted>()) {
        return exit::INTERRUPTED;
    }
    match io {
        Some(error) => exit::failed(os_said(error, None)),
        None => exit::failed(why),
    }
}

/// The session was interrupted from the keyboard (Python's `KeyboardInterrupt`): what the
/// supervisor returns, bare or inside an `io::Error`, for the session to exit 130. Its own
/// kind rather than `EINTR`, which any call may return without anybody pressing ^C.
#[derive(Debug, thiserror::Error)]
#[error("interrupted")]
pub struct Interrupted;

/// Writes `error: <said>` and usage to standard error, as argparse's `parser.error` does, and
/// returns 2.
fn usage(said: &str) -> i32 {
    use clap::CommandFactory;
    let mut line = crate::cli::Cli::command();
    line.build();
    let error = match line.find_subcommand_mut("cog") {
        Some(cog) => cog.error(clap::error::ErrorKind::ValueValidation, said),
        None => line.error(clap::error::ErrorKind::ValueValidation, said),
    };
    let _ = error.print();
    exit::USAGE
}

/// `check`: asks the target what it is, without running anything on it, and says it as
/// `hmz internal anchor --check` prints it (cli/anchor.py:119-125).
pub fn check(config: &AnchorConfig) -> anyhow::Result<String> {
    let link = transport::connect(&config.target, &[config.export()], config.token.as_deref())?;
    let client = RemoteClient::new(link.channel.clone());
    let asked = (|| -> Result<(Meta, usize), RemoteError> {
        let hello = client.start(config.token.as_deref())?;
        let mut request = Meta::new();
        request.insert("path".into(), Value::from(config.workspace.clone()));
        let listed = client.call(Op::Listdir, request)?;
        let entries = match listed.get("entries") {
            Some(Value::Array(entries)) => entries.len(),
            Some(Value::Object(entries)) => entries.len(),
            _ => 0,
        };
        Ok((hello, entries))
    })();
    client.close();
    link.close();
    let (hello, entries) = asked?;
    Ok(found(
        &config.target.describe(),
        &hello,
        &config.workspace,
        entries,
    ))
}

/// The lines `--check` prints, from the `HELLO` reply.
pub fn found(target: &str, hello: &Meta, workspace: &str, entries: usize) -> String {
    let mut said = format!("target      {target}\n");
    said += &format!("hostname    {}\n", py_str(hello.get("hostname")));
    said += &format!(
        "python      {} (pid {})\n",
        py_str(hello.get("python")),
        py_str(hello.get("pid"))
    );
    if let Some(Value::Array(exports)) = hello.get("exports") {
        for export in exports {
            said += &format!(
                "export      {} -> {}\n",
                py_str(export.get("virtual")),
                py_str(export.get("real"))
            );
        }
    }
    said += &format!("workspace   {workspace} ({entries} entries)\n");
    said
}

/// A JSON value as Python's `str` of what `json.loads` made of it.
fn py_str(value: Option<&Value>) -> String {
    match value {
        None | Some(Value::Null) => "None".into(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(Value::String(text)) => text.clone(),
        Some(other) => other.to_string(),
    }
}

/// `connect`: runs the agent, returning its own status.
pub fn connect(config: &AnchorConfig) -> anyhow::Result<i32> {
    // Answered before a mirror is so much as looked at: driving the CLI on the target needs
    // no ptrace and no shadow.
    if config.native {
        return crate::cog::drive::drive(config, &config.command);
    }
    // A harness on another machine is placed by `hmz` (`elsewhere.afar`) before it spawns
    // this program, which then runs there with `--harness=local`; nothing of that is here.
    if config.elsewhere().map_err(anyhow::Error::msg)? {
        anyhow::bail!(
            "the harness must be local here: hmz places a harness on another machine before \
             it runs coganchor there"
        );
    }
    supervise(config)
}

#[cfg(not(all(
    target_os = "linux",
    any(target_arch = "x86_64", target_arch = "aarch64")
)))]
fn supervise(_: &AnchorConfig) -> anyhow::Result<i32> {
    anyhow::bail!(UNSUPERVISABLE)
}

/// Builds the virtual home, runs the supervised turn in it, and takes it away again whatever
/// became of the turn.
#[cfg(all(
    target_os = "linux",
    any(target_arch = "x86_64", target_arch = "aarch64")
))]
fn supervise(config: &AnchorConfig) -> anyhow::Result<i32> {
    use crate::cog::homes;

    let home = config.home.as_ref().map(homes::build).transpose()?;
    let ran = supervised::supervised(config, home.as_ref());
    if let Some(home) = home
        && let Err(why) = home.drop_home()
    {
        if ran.is_ok() {
            return Err(why.into());
        }
        tracing::warn!("cannot take the virtual home away: {why}");
    }
    ran
}

/// What the supervised arrangement needs, which is Linux's alone.
#[cfg(all(
    target_os = "linux",
    any(target_arch = "x86_64", target_arch = "aarch64")
))]
mod supervised {
    use std::ffi::OsString;
    use std::io;
    use std::path::{Path, PathBuf};
    use std::sync::Arc;

    use super::{UNMIRRORED, os_said};
    use crate::client::RemoteClient;
    use crate::cog::config::{AnchorConfig, abspath};
    use crate::cog::homes::Home;
    use crate::cog::lending;
    use crate::cog::netproxy::NetProxy;
    use crate::cog::policy::head;
    use crate::cog::router::{Layout, Router, RouterConfig};
    use crate::cog::shadow::{ShadowTree, prepare_shadow_root};
    use crate::cog::statepaths;
    use crate::cog::supervisor::{Launch, Options, Supervisor};
    use crate::cog::walls::{Walls, overlay};
    use crate::proto::path_within;
    use crate::transport;

    /// `_supervised` (anchor.py:599-750): the agent here, supervised.
    pub fn supervised(config: &AnchorConfig, home: Option<&Home>) -> anyhow::Result<i32> {
        let workspace = config.workspace.as_str();
        // Named on the command line right after the CLI's own name, for one no variable moves.
        let Some((program, arguments)) = config.command.split_first() else {
            anyhow::bail!("no agent given");
        };
        let mut line: Vec<OsString> = vec![program.clone()];
        line.extend(home.map(Home::argv).unwrap_or_default());
        line.extend_from_slice(arguments);
        let agent = statepaths::resolve(&line)?;
        let kept: Vec<String> = home
            .map(|home| vec![home.dir().to_string_lossy().into_owned()])
            .unwrap_or_default();
        // By the name the kernel has for it: where a process is, is read back as that name,
        // and a command started in a mirror named otherwise would land outside it. The name
        // it was given is the other name it answers to.
        let named = abspath(config.shadow.as_deref().unwrap_or(workspace))?;
        let shadow_root = realpath(&named);
        let started_in = started_in(config, &shadow_root)?;
        let redirects: Vec<(String, String)> = config
            .redirects
            .iter()
            .map(|(named, instead)| Ok((abspath(named)?, abspath(instead)?)))
            .collect::<io::Result<_>>()?;
        let router = Arc::new(Router::new(RouterConfig {
            layouts: vec![Layout {
                shadow: PathBuf::from(&shadow_root),
                workspace: workspace.to_owned(),
            }],
            aliases: aliases(config, &shadow_root, workspace, &named),
            local_paths: agent
                .state
                .iter()
                .chain(&kept)
                .cloned()
                .chain(
                    config
                        .local_paths
                        .iter()
                        .map(|path| abspath(path))
                        .collect::<io::Result<Vec<_>>>()?,
                )
                // What a path is answered with is this machine's business; a pattern's is the
                // directory it is in, which every path it answers is under.
                .chain(redirects.iter().map(|(_, instead)| {
                    let at = head(instead);
                    if at == *instead { at } else { dirname(&at) }
                }))
                .collect(),
            local_programs: agent
                .programs
                .iter()
                .chain(&kept)
                .cloned()
                .chain(
                    config
                        .local_execs
                        .iter()
                        .map(|path| abspath(path))
                        .collect::<io::Result<Vec<_>>>()?,
                )
                .collect(),
            redirects: redirects.clone(),
        }));
        // The machine it mirrors, by its destination: what ssh is told on the way there is
        // not another machine, and a mirror is not refused for being told it.
        let mut destination = config.target.clone();
        destination.options.clear();
        prepare_shadow_root(
            Path::new(&shadow_root),
            config.force,
            &destination.describe(),
        )
        .map_err(|why| {
            // A directory that is somebody's, or another target's mirror, says what to do
            // about it in its own words; anything else is this machine's filesystem.
            if why.kind() == io::ErrorKind::AlreadyExists {
                anyhow::Error::from(why)
            } else {
                anyhow::anyhow!(unmirrored(&shadow_root, &why))
            }
        })?;

        let link = transport::connect(&config.target, &[config.export()], config.token.as_deref())?;
        let client = Arc::new(RemoteClient::new(link.channel.clone()));
        let ran = turn(
            config,
            &agent,
            home,
            &client,
            router,
            &shadow_root,
            &started_in,
            &redirects,
        );
        client.close();
        link.close();
        ran
    }

    /// The turn itself, once the target is reached.
    #[allow(clippy::too_many_arguments)]
    fn turn(
        config: &AnchorConfig,
        agent: &statepaths::Resolved,
        home: Option<&Home>,
        client: &Arc<RemoteClient>,
        router: Arc<Router>,
        shadow_root: &str,
        started_in: &str,
        redirects: &[(String, String)],
    ) -> anyhow::Result<i32> {
        let net = if config.net_remote {
            Some(NetProxy::new(client.clone(), &config.net_allow)?)
        } else {
            None
        };
        // The one directory the mirror cannot be asked about first is the one the agent is
        // started in: the `chdir` happens in the forked child, before anything may talk to the
        // target. So it is made here and left empty, for the agent's first look to fill in.
        std::fs::create_dir_all(started_in)?;
        let mut env: Vec<(OsString, OsString)> = std::env::vars_os().collect();
        if let Some(home) = home {
            for (name, value) in home.environ() {
                overlay(&mut env, name, value);
            }
        }
        for (name, value) in [
            ("HUMANIZE", env!("CARGO_PKG_VERSION").to_owned()),
            ("HUMANIZE_TARGET", config.target.describe()),
            ("PWD", started_in.to_owned()),
            // Agents surface this to the model; being explicit beats it guessing.
            ("HUMANIZE_WORKSPACE", config.workspace.clone()),
        ] {
            overlay(&mut env, name.into(), value.into());
        }
        let walls = config
            .fence
            .as_ref()
            .map(|fence| Walls::around(fence, Path::new(shadow_root)))
            .transpose()?;
        if let Some(walls) = &walls {
            env = walls.environ_over(env);
        }
        let launch = Launch {
            program: agent.program.clone(),
            argv: agent.argv.clone(),
            env,
            cwd: PathBuf::from(started_in),
        };
        let options = Options {
            token: config.token.clone(),
            private: config.private.clone(),
            writes: walls.as_ref().is_none_or(|walls| walls.writes),
            fence: walls.as_ref().map(|walls| walls.told.clone()),
            walls,
        };
        // Shared with every other turn working in the same mirror.
        let shadow = Arc::new(ShadowTree::new(
            client.clone(),
            router.clone(),
            Path::new(shadow_root),
        )?);
        tracing::info!(
            "running {} against {}",
            agent.program.display(),
            config.target.describe()
        );
        // A sign-in that refreshes itself, answered here in place, is held for the turn's
        // length beside every other turn here using it -- and so never while a copy of it is
        // out on another machine. Files only: a directory answered may be the CLI's sessions.
        let answered: Vec<PathBuf> = lending::refreshing(
            &redirects
                .iter()
                .map(|(_, instead)| PathBuf::from(instead))
                .collect::<Vec<_>>(),
            false,
        )
        .into_iter()
        .collect();
        let _held = lending::lent(&answered, false)?;
        let supervisor = Supervisor::new(launch, client.clone(), router, shadow, net, options);
        Ok(supervisor.run()?)
    }

    /// Where the agent starts: the mirror of `--chdir`, which must be inside the workspace.
    fn started_in(config: &AnchorConfig, shadow_root: &str) -> anyhow::Result<String> {
        let workspace = config.workspace.as_str();
        let Some(chdir) = config.chdir.as_deref() else {
            return Ok(shadow_root.to_owned());
        };
        let under = abspath(chdir)?;
        if under == workspace {
            return Ok(shadow_root.to_owned());
        }
        match under.strip_prefix(&format!("{}/", workspace.trim_end_matches('/'))) {
            Some(below) => Ok(format!("{}/{below}", shadow_root.trim_end_matches('/'))),
            None => anyhow::bail!("{under} is not inside {workspace}"),
        }
    }

    /// `_aliases` twice (anchor.py:753-789): the workspace's own path for a `peer://` target,
    /// and the mirror's given name where a link makes it another name than the kernel's;
    /// nothing for one nested in the other.
    fn aliases(
        config: &AnchorConfig,
        shadow_root: &str,
        workspace: &str,
        named: &str,
    ) -> Vec<(String, String)> {
        let apart = |other: &str| {
            path_within(shadow_root, other, false).is_none()
                && path_within(other, shadow_root, false).is_none()
        };
        let mut said: Vec<(String, String)> = Vec::new();
        for (other, applies) in [(workspace, config.target.scheme == "peer"), (named, true)] {
            let alias = (other.to_owned(), shadow_root.to_owned());
            if applies && apart(other) && !said.contains(&alias) {
                said.push(alias);
            }
        }
        said
    }

    /// `_unmirrored`: the copy of the workspace that could not be made, in words of its own,
    /// since `Permission denied` alone reads like a refused credential.
    fn unmirrored(path: &str, why: &io::Error) -> String {
        let said = os_said(why, None);
        let said = said
            .strip_prefix("[Errno ")
            .and_then(|rest| rest.split_once("] "))
            .map_or(said.as_str(), |(_, message)| message);
        format!("{UNMIRRORED} {path}: {said}")
    }

    /// `os.path.dirname`.
    fn dirname(path: &str) -> String {
        match path.rfind('/') {
            Some(0) => "/".into(),
            Some(cut) => path[..cut].into(),
            None => String::new(),
        }
    }

    /// `os.path.realpath` of an absolute path that need not exist: each link on the way
    /// followed, a dangling one too, and what is not there yet kept as written.
    fn realpath(path: &str) -> String {
        let mut hops = 0;
        resolved(PathBuf::from("/"), Path::new(path), &mut hops)
            .to_string_lossy()
            .into_owned()
    }

    /// `rest` resolved against `at`, link by link; past 40 links one is taken as written.
    fn resolved(mut at: PathBuf, rest: &Path, hops: &mut u32) -> PathBuf {
        use std::path::Component;
        for part in rest.components() {
            match part {
                Component::RootDir => at = PathBuf::from("/"),
                Component::ParentDir => {
                    at.pop();
                }
                Component::Normal(name) => {
                    let next = at.join(name);
                    match std::fs::read_link(&next) {
                        Ok(leads) if *hops < 40 => {
                            *hops += 1;
                            at = resolved(at, &leads, hops);
                        }
                        _ => at = next,
                    }
                }
                Component::CurDir | Component::Prefix(_) => {}
            }
        }
        at
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        fn a_mirror_not_yet_made_is_named_by_what_of_it_is_there() {
            let dir = tempfile::tempdir().unwrap();
            let real = std::fs::canonicalize(dir.path()).unwrap();
            let link = real.join("link");
            std::os::unix::fs::symlink(&real, &link).unwrap();
            let asked = format!("{}/not/yet", link.display());
            assert_eq!(realpath(&asked), format!("{}/not/yet", real.display()));
            // A link to what is not there yet is followed all the same.
            let dangling = real.join("dangling");
            std::os::unix::fs::symlink(real.join("later"), &dangling).unwrap();
            assert_eq!(
                realpath(&format!("{}/m", dangling.display())),
                format!("{}/later/m", real.display())
            );
        }

        #[test]
        fn a_copy_that_cannot_be_made_says_where_and_why() {
            let why = io::Error::from_raw_os_error(libc::EACCES);
            assert_eq!(
                unmirrored("/m", &why),
                "cannot keep the local copy of the work at /m: Permission denied"
            );
            assert_eq!(dirname("/a/b"), "/a");
            assert_eq!(dirname("/a"), "/");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_check_says_what_the_target_is_as_python_prints_it() {
        let hello: Meta = serde_json::from_str(
            r#"{"hostname": "box", "python": "3.12.1", "pid": 42,
                "exports": [{"virtual": "/w", "real": "/srv/w"}]}"#,
        )
        .unwrap();
        assert_eq!(
            found("ssh://box", &hello, "/w", 3),
            "target      ssh://box\n\
             hostname    box\n\
             python      3.12.1 (pid 42)\n\
             export      /w -> /srv/w\n\
             workspace   /w (3 entries)\n"
        );
        assert_eq!(
            found("local", &Meta::new(), "/w", 0),
            "target      local\nhostname    None\npython      None (pid None)\n\
             workspace   /w (0 entries)\n"
        );
    }

    #[test]
    fn an_error_ends_the_session_with_its_status() {
        assert_eq!(
            answered(&anyhow::Error::from(Interrupted)),
            exit::INTERRUPTED
        );
        let inside = io::Error::other(Interrupted);
        assert_eq!(answered(&anyhow::Error::from(inside)), exit::INTERRUPTED);
        let eintr = io::Error::from_raw_os_error(libc::EINTR);
        assert_eq!(answered(&anyhow::Error::from(eintr)), exit::FAILED);
        let refused = anyhow::anyhow!("nope");
        assert_eq!(answered(&refused), exit::FAILED);
    }
}
