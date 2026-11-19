//! A session's settings, checked. Port of `AnchorConfig` and `argv.settings` in
//! `hmz.coganchor.{anchor,argv}`. [Unit 12]
//!
//! What the command line says is read here and refused here, as `AnchorConfig.__post_init__`
//! refuses it (anchor.py:276-371): settings no session could run under are bad arguments, and
//! [`crate::cog::run`] exits 2 with usage for them, as argparse does.

use std::ffi::OsString;
use std::io;

use crate::cli::CogArgs;
use crate::cog::homes::Virtual;
use crate::fence::Fence;
use crate::transport::Target;

/// Everything a cog session is told, validated as `AnchorConfig.__post_init__` validates it.
#[derive(Clone, Debug)]
pub struct AnchorConfig {
    pub target: Target,
    pub harness: String,
    pub broker: String,
    /// The workspace as the target names it (absolute; this directory by default).
    pub workspace: String,
    pub chdir: Option<String>,
    pub remote_path: Option<String>,
    pub shadow: Option<String>,
    pub local_paths: Vec<String>,
    pub local_execs: Vec<String>,
    pub private: Vec<String>,
    pub redirects: Vec<(String, String)>,
    pub net_remote: bool,
    pub net_allow: Vec<String>,
    pub token: Option<String>,
    pub force: bool,
    pub native: bool,
    pub hushes: Vec<String>,
    pub projects: Vec<(String, String)>,
    pub home: Option<Virtual>,
    pub brings: Vec<(String, String)>,
    pub tell: String,
    pub installs: String,
    pub fence: Option<Fence>,
    pub check: bool,
    pub command: Vec<OsString>,
}

/// Why a command line gives no settings.
#[derive(Debug, PartialEq, Eq)]
pub enum Refusal {
    /// Settings no session could run under: exit 2 with usage, as argparse's own rejections.
    Usage(String),
    /// Something of this machine failed while reading them (the token file): exit 1, as the
    /// `OSError` Python raises out of `argv.settings` does.
    Failed(String),
}

impl AnchorConfig {
    /// The settings a command line gives, or why they are refused (exit 2 with usage).
    pub fn from_args(args: &CogArgs) -> Result<AnchorConfig, String> {
        AnchorConfig::settle(args).map_err(|refusal| match refusal {
            Refusal::Usage(said) | Refusal::Failed(said) => said,
        })
    }

    /// [`AnchorConfig::from_args`], telling a refusal from a failure to read the token file.
    ///
    /// In the order Python reads them: `argv.settings` reads the token file, then `--home` and
    /// `--fence`, then `__post_init__` parses the target and the harness and checks the rest.
    pub fn settle(args: &CogArgs) -> Result<AnchorConfig, Refusal> {
        // `_secret(args.token_file) if args.token_file else args.token`: read verbatim.
        let token_file = args
            .token_file
            .as_deref()
            .filter(|path| !path.as_os_str().is_empty());
        let token = crate::cli::secret(args.token.as_deref(), token_file).map_err(|why| {
            Refusal::Failed(os_said(
                &why,
                token_file.map(|path| path.to_string_lossy()).as_deref(),
            ))
        })?;
        let home = given(&args.home)
            .map(Virtual::loads)
            .transpose()
            .map_err(Refusal::Usage)?;
        let fence = given(&args.fence)
            .map(Fence::loads)
            .transpose()
            .map_err(Refusal::Usage)?;
        let target = Target::parse(&args.target).map_err(Refusal::Usage)?;
        // `os.path.abspath(self.workspace or os.getcwd())`: this directory only where needed.
        let workspace = match given(&args.workspace) {
            Some(workspace) => abspath(workspace),
            None => std::env::current_dir().map(|cwd| normpath(&cwd.to_string_lossy())),
        }
        .map_err(|why| Refusal::Failed(os_said(&why, None)))?;
        let config = AnchorConfig {
            target,
            harness: args.harness.clone(),
            broker: args.broker.clone(),
            workspace,
            chdir: given(&args.chdir).map(str::to_owned),
            remote_path: given(&args.remote_path).map(str::to_owned),
            shadow: given(&args.shadow).map(str::to_owned),
            local_paths: args.local_paths.clone(),
            local_execs: args.local_execs.clone(),
            private: args.private.clone(),
            redirects: args.redirects.iter().map(|said| pair(said)).collect(),
            net_remote: args.net == "remote",
            net_allow: args.net_allow.clone(),
            token,
            force: args.force,
            native: args.native,
            hushes: args.hushes.clone(),
            projects: args.projects.iter().map(|said| pair(said)).collect(),
            home,
            brings: args.brings.iter().map(|said| pair(said)).collect(),
            tell: args.tell.clone(),
            installs: args.installs.clone(),
            fence,
            check: args.check,
            command: args.command.clone(),
        };
        let harness = config.harnessed().map_err(Refusal::Usage)?;
        refused(&config, &harness, &args.net).map_err(Refusal::Usage)?;
        Ok(config)
    }

    /// The `--export` spec of the workspace: `WS:REAL` for a `local:REAL` target, else `WS`.
    ///
    /// `REAL` is `--remote-path` where given, whatever the target; a `local:` target's own
    /// path otherwise, since any other target's path is something else of its own -- a
    /// ticket, a container's daemon (`AnchorConfig.mount`, anchor.py:468-485).
    pub fn export(&self) -> String {
        let real = self
            .remote_path
            .clone()
            .filter(|real| !real.is_empty())
            .or_else(|| {
                (self.target.scheme == "local")
                    .then(|| self.target.path.clone())
                    .flatten()
            });
        match real.filter(|real| !real.is_empty()) {
            Some(real) => format!("{}:{real}", self.workspace),
            None => self.workspace.clone(),
        }
    }

    /// The machine the harness runs on, as a target of its own: `same` is the target's
    /// (`elsewhere.harnessed`).
    pub fn harnessed(&self) -> Result<Target, String> {
        if self.harness == "same" {
            Ok(self.target.clone())
        } else {
            Target::parse(&self.harness)
        }
    }

    /// Whether the harness runs on another machine (`elsewhere.elsewhere`), which `hmz`
    /// places before it spawns this program.
    pub fn elsewhere(&self) -> Result<bool, String> {
        Ok(self.harness != "local" && self.harnessed()?.scheme != "local")
    }
}

/// Refuses what `AnchorConfig.__post_init__` refuses (anchor.py:276-346), `harness` being
/// [`AnchorConfig::harnessed`] and `net` the `--net` as written.
pub fn refused(config: &AnchorConfig, harness: &Target, net: &str) -> Result<(), String> {
    if config.native && harness.scheme != "local" {
        return Err(
            "a native session has no harness to put anywhere: the CLI on the target is the one \
             that runs, so --harness and --native ask for opposite things"
                .into(),
        );
    }
    if config.harness != "local" && config.target.scheme == "peer" {
        return Err(
            "a peer:// target is a meeting Humanize books for a harness it is placing; naming \
             both is naming the same introduction twice"
                .into(),
        );
    }
    if harness.scheme != "local" && config.target.scheme == "tcp" {
        return Err(
            "a tcp:// target is a serving half somebody else left listening, which Humanize \
             can start nothing beside; a harness on another machine has no way to be \
             introduced to it"
                .into(),
        );
    }
    if net != "local" && net != "remote" {
        return Err(format!(
            "unsupported net {}; expected local or remote",
            py_repr(net)
        ));
    }
    for (named, instead) in &config.redirects {
        // Absolute both ways: what the agent names is resolved before it is looked up, and a
        // relative answer would be read against wherever the turn happens to be.
        if !named.starts_with('/') || !instead.starts_with('/') {
            return Err(format!(
                "unsupported redirect {}; expected two absolute paths",
                py_repr(&format!("{named}={instead}"))
            ));
        }
    }
    for name in &config.hushes {
        // `env -u NAME` refuses a name with an `=` in it.
        if name.is_empty() || name.contains('=') {
            return Err(format!(
                "unsupported hush {}; expected a variable name",
                py_repr(name)
            ));
        }
    }
    for (name, whence) in &config.projects {
        if name.is_empty() || name.contains('=') || !whence.starts_with('/') {
            return Err(format!(
                "unsupported projection {name}={}; expected a variable name and an absolute path",
                py_repr(whence)
            ));
        }
    }
    if let Some(fence) = &config.fence
        && !fence.open()
    {
        fenceable(fence, &harness.scheme, config.net_remote || net == "remote")?;
    }
    if !config.tell.is_empty() && !config.tell.starts_with('/') {
        return Err(format!(
            "unsupported tell {}; expected an absolute path",
            py_repr(&config.tell)
        ));
    }
    for (named, into) in &config.brings {
        let (variable, under) = named.split_once('/').unwrap_or((named, ""));
        let projected = config.projects.iter().any(|(name, _)| name == variable);
        if !projected
            || under.is_empty()
            || under.starts_with('/')
            || under.split('/').any(|part| part == "..")
            || !into.starts_with('/')
        {
            return Err(format!(
                "unsupported bring {named}={}; expected a projected VARIABLE, a PATH inside it \
                 and an absolute path",
                py_repr(into)
            ));
        }
    }
    Ok(())
}

/// `AnchorConfig._fenceable` (anchor.py:348-371): a fence this session could not hold.
fn fenceable(fence: &Fence, harness: &str, net_remote: bool) -> Result<(), String> {
    if fence.drawn.is_empty() {
        return Err(
            "a fence drawn path by path cannot be held on another machine; draw it from its \
             rules with Fence.of"
                .into(),
        );
    }
    if harness != "local" {
        return Err(
            "a fence is drawn around this machine's paths, and cannot hold a harness on another \
             machine"
                .into(),
        );
    }
    if net_remote && !fence.online {
        return Err(
            "a fence that cuts the network keeps the agent's own connections here; --net remote \
             would send them past it"
                .into(),
        );
    }
    Ok(())
}

/// `argv._pair`: one `FROM=TO` split at its first `=`; one with none is half a pair, refused
/// by [`refused`] with everything else.
pub fn pair(said: &str) -> (String, String) {
    let (named, instead) = said.split_once('=').unwrap_or((said, ""));
    (named.to_owned(), instead.to_owned())
}

/// An option given and not empty, as Python reads an empty one: as not given.
fn given(option: &Option<String>) -> Option<&str> {
    option.as_deref().filter(|said| !said.is_empty())
}

/// `os.path.abspath`: `path` against this directory, normalised.
pub fn abspath(path: &str) -> io::Result<String> {
    if path.starts_with('/') {
        return Ok(normpath(path));
    }
    let cwd = std::env::current_dir()?;
    Ok(abspath_from(path, &cwd.to_string_lossy()))
}

/// `os.path.abspath` against `cwd`.
pub fn abspath_from(path: &str, cwd: &str) -> String {
    if path.starts_with('/') {
        normpath(path)
    } else {
        normpath(&format!("{cwd}/{path}"))
    }
}

/// `os.path.normpath` of an absolute path: no `.`, no `..`, no doubled or trailing `/`.
pub fn normpath(path: &str) -> String {
    let rooted = path.starts_with('/');
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
            "" | "." => {}
            // Above the root is the root; above a relative path's start is kept.
            ".." if rooted || parts.last().is_some_and(|last| *last != "..") => {
                parts.pop();
            }
            name => parts.push(name),
        }
    }
    match (rooted, parts.is_empty()) {
        (true, _) => format!("/{}", parts.join("/")),
        (false, true) => ".".into(),
        (false, false) => parts.join("/"),
    }
}

/// An `OSError` as Python says it: `[Errno N] message: 'file'`, or the message alone where it
/// has no errno.
pub fn os_said(why: &io::Error, filename: Option<&str>) -> String {
    let Some(errno) = why.raw_os_error() else {
        return why.to_string();
    };
    let full = why.to_string();
    let message = full
        .rfind(" (os error ")
        .map_or(full.as_str(), |cut| &full[..cut]);
    match filename {
        Some(name) => format!("[Errno {errno}] {message}: {}", py_repr(name)),
        None => format!("[Errno {errno}] {message}"),
    }
}

/// A string as Python's `repr` writes it: single quotes unless it holds one and no double.
pub fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for one in text.chars() {
        match one {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ if one == quote => {
                out.push('\\');
                out.push(one);
            }
            _ if (one as u32) < 0x20 || one as u32 == 0x7f => {
                out.push_str(&format!("\\x{:02x}", one as u32));
            }
            _ => out.push(one),
        }
    }
    out.push(quote);
    out
}

#[cfg(test)]
mod tests {
    //! The validation, `export()` and pair cases of `tests/unit/coganchor/test_anchor.py` and
    //! `test_argv.py`. Targets are written out rather than parsed, `Target::parse` being
    //! unit 7's; the cases that go through it are ignored until it lands.

    use super::*;

    fn target(scheme: &str, host: &str, path: Option<&str>) -> Target {
        Target {
            scheme: scheme.into(),
            user: None,
            host: host.into(),
            port: None,
            path: path.map(str::to_owned),
            options: Vec::new(),
        }
    }

    fn local() -> Target {
        target("local", "", None)
    }

    fn config() -> AnchorConfig {
        AnchorConfig {
            target: local(),
            harness: "local".into(),
            broker: String::new(),
            workspace: "/w".into(),
            chdir: None,
            remote_path: None,
            shadow: None,
            local_paths: Vec::new(),
            local_execs: Vec::new(),
            private: Vec::new(),
            redirects: Vec::new(),
            net_remote: false,
            net_allow: Vec::new(),
            token: None,
            force: false,
            native: false,
            hushes: Vec::new(),
            projects: Vec::new(),
            home: None,
            brings: Vec::new(),
            tell: String::new(),
            installs: String::new(),
            fence: None,
            check: false,
            command: Vec::new(),
        }
    }

    fn fence(rules: &[(&str, &str)], online: bool) -> Fence {
        Fence {
            write: vec!["/w".into()],
            online,
            drawn: rules
                .iter()
                .map(|(path, access)| ((*path).to_owned(), (*access).to_owned()))
                .collect(),
            ..Fence::default()
        }
    }

    const RULES: [(&str, &str); 3] = [("/", "read"), ("~", "read"), (".", "write")];

    fn levelled() -> Fence {
        fence(&RULES, true)
    }

    fn cut() -> Fence {
        fence(&RULES, false)
    }

    /// `refused`, with the harness the config names (`ssh://box` and `same` spelled out).
    fn check(config: &AnchorConfig, net: &str) -> Result<(), String> {
        let harness = match config.harness.as_str() {
            "local" => local(),
            "same" => config.target.clone(),
            other => {
                let (scheme, host) = other.split_once("://").unwrap();
                target(scheme, host, None)
            }
        };
        refused(config, &harness, net)
    }

    fn refuses(config: AnchorConfig, says: &str) {
        let net = if config.net_remote { "remote" } else { "local" };
        let said = check(&config, net).expect_err(says);
        assert!(said.contains(says), "{said:?} does not say {says:?}");
    }

    #[test]
    fn what_the_command_line_refuses_the_settings_refuse() {
        refuses(
            AnchorConfig {
                native: true,
                harness: "ssh://box".into(),
                ..config()
            },
            "native session has no harness",
        );
        refuses(
            AnchorConfig {
                harness: "same".into(),
                target: target("peer", "h", None),
                ..config()
            },
            "peer:// target",
        );
        for harness in ["ssh://box", "same"] {
            refuses(
                AnchorConfig {
                    harness: harness.into(),
                    target: target("tcp", "h:1", None),
                    ..config()
                },
                "tcp:// target",
            );
        }
        let said = check(&config(), "both").unwrap_err();
        assert_eq!(said, "unsupported net 'both'; expected local or remote");
        for (named, instead) in [("/a", "b"), ("a", "/b"), ("/only-half", "")] {
            refuses(
                AnchorConfig {
                    redirects: vec![(named.into(), instead.into())],
                    ..config()
                },
                "unsupported redirect",
            );
        }
        for name in ["", "A=B"] {
            refuses(
                AnchorConfig {
                    hushes: vec![name.into()],
                    ..config()
                },
                "unsupported hush",
            );
        }
        for (name, whence) in [("", "/c"), ("A=B", "/c"), ("A", "c")] {
            refuses(
                AnchorConfig {
                    projects: vec![(name.into(), whence.into())],
                    ..config()
                },
                "unsupported projection",
            );
        }
        refuses(
            AnchorConfig {
                fence: Some(fence(&[], true)),
                ..config()
            },
            "drawn path by path",
        );
        refuses(
            AnchorConfig {
                fence: Some(levelled()),
                harness: "ssh://box".into(),
                ..config()
            },
            "cannot hold a harness",
        );
        refuses(
            AnchorConfig {
                fence: Some(cut()),
                net_remote: true,
                ..config()
            },
            "past it",
        );
        refuses(
            AnchorConfig {
                tell: "relative".into(),
                ..config()
            },
            "unsupported tell",
        );
        let projected = || vec![("CODEX_HOME".to_owned(), "/creds".to_owned())];
        for (named, into) in [
            ("CODEX_HOME", "/epic"),
            ("CODEX_HOME/../x", "/epic"),
            ("CODEX_HOME/sessions", "relative"),
            ("CODEX_HOME//abs", "/epic"),
            ("OTHER/sessions", "/epic"),
        ] {
            refuses(
                AnchorConfig {
                    projects: projected(),
                    brings: vec![(named.into(), into.into())],
                    ..config()
                },
                "unsupported bring",
            );
        }
    }

    #[test]
    fn what_is_well_written_is_taken() {
        let taken = [
            AnchorConfig {
                redirects: vec![("/a".into(), "/b".into())],
                hushes: vec!["OPENAI_API_KEY".into()],
                ..config()
            },
            AnchorConfig {
                projects: vec![("CODEX_HOME".into(), "/c".into())],
                brings: vec![("CODEX_HOME/sessions".into(), "/epic/codex".into())],
                tell: "/tmp/homes".into(),
                ..config()
            },
            AnchorConfig {
                fence: Some(Fence {
                    write: vec!["/".into()],
                    online: true,
                    ..Fence::default()
                }),
                ..config()
            },
            AnchorConfig {
                fence: Some(levelled()),
                ..config()
            },
            AnchorConfig {
                fence: Some(cut()),
                ..config()
            },
            AnchorConfig {
                native: true,
                target: target("ssh", "box", None),
                ..config()
            },
            AnchorConfig {
                harness: "ssh://h".into(),
                target: target("docker", "c", None),
                ..config()
            },
            AnchorConfig {
                harness: "same".into(),
                ..config()
            },
        ];
        for one in taken {
            check(&one, "local").unwrap();
        }
    }

    #[test]
    fn the_export_names_where_the_work_really_is() {
        for (target, remote_path, export) in [
            (target("local", "", Some("/real")), None, "/w:/real"),
            (
                target("local", "", Some("/real")),
                Some("/other"),
                "/w:/other",
            ),
            (target("ssh", "box", None), None, "/w"),
            (target("ssh", "box", None), Some("/srv/w"), "/w:/srv/w"),
            (target("peer", "h", Some("ticket")), None, "/w"),
            (local(), None, "/w"),
            (local(), Some(""), "/w"),
        ] {
            let config = AnchorConfig {
                target,
                remote_path: remote_path.map(str::to_owned),
                ..config()
            };
            assert_eq!(config.export(), export);
        }
    }

    #[test]
    fn a_harness_elsewhere_is_one_whose_machine_is_not_this_one() {
        assert!(!config().elsewhere().unwrap());
        let same_here = AnchorConfig {
            harness: "same".into(),
            ..config()
        };
        assert!(!same_here.elsewhere().unwrap());
        let same_there = AnchorConfig {
            harness: "same".into(),
            target: target("ssh", "box", None),
            ..config()
        };
        assert!(same_there.elsewhere().unwrap());
    }

    #[test]
    fn pairs_are_read_on_their_first_equals_sign() {
        assert_eq!(pair("/a=/b=c"), ("/a".into(), "/b=c".into()));
        assert_eq!(
            pair("CODEX_HOME=/creds"),
            ("CODEX_HOME".into(), "/creds".into())
        );
        assert_eq!(pair("/only-half"), ("/only-half".into(), String::new()));
    }

    #[test]
    fn paths_are_made_absolute_as_python_makes_them() {
        assert_eq!(abspath_from("sub/../x/./y/", "/w"), "/w/x/y");
        assert_eq!(abspath_from("/a//b/..", "/w"), "/a");
        assert_eq!(abspath_from("..", "/"), "/");
        assert_eq!(normpath("/"), "/");
        assert_eq!(normpath(""), ".");
        assert_eq!(normpath("a/.."), ".");
        assert_eq!(normpath("../a/../../b"), "../../b");
    }

    #[test]
    fn strings_are_quoted_as_python_quotes_them() {
        assert_eq!(py_repr("both"), "'both'");
        assert_eq!(py_repr("it's"), "\"it's\"");
        assert_eq!(py_repr("a'b\"c"), "'a\\'b\"c'");
        assert_eq!(py_repr("a\\b\n"), "'a\\\\b\\n'");
    }

    #[test]
    fn an_os_error_is_said_as_python_says_it() {
        let why = io::Error::from_raw_os_error(libc::ENOENT);
        assert_eq!(
            os_said(&why, Some("/no/such")),
            "[Errno 2] No such file or directory: '/no/such'"
        );
        assert_eq!(os_said(&why, None), "[Errno 2] No such file or directory");
    }

    fn args(argv: &[&str]) -> CogArgs {
        use clap::Parser;
        #[derive(Parser)]
        struct Line {
            #[command(flatten)]
            cog: CogArgs,
        }
        let mut line = vec!["cog"];
        line.extend_from_slice(argv);
        Line::try_parse_from(line).unwrap().cog
    }

    #[test]
    fn the_token_file_is_read_verbatim() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("token");
        std::fs::write(&file, " s3cret\n").unwrap();
        let said = args(&[&format!("--token-file={}", file.display()), "--token=other"]);
        let token = crate::cli::secret(said.token.as_deref(), said.token_file.as_deref());
        assert_eq!(token.unwrap().as_deref(), Some(" s3cret\n"));
    }

    #[test]
    fn a_token_file_that_cannot_be_read_fails_rather_than_refuses() {
        let said = args(&["--token-file=/no/such/token", "claude"]);
        assert_eq!(
            AnchorConfig::settle(&said).unwrap_err(),
            Refusal::Failed("[Errno 2] No such file or directory: '/no/such/token'".into())
        );
    }

    #[test]
    fn the_command_line_is_read_into_settings() {
        let config = AnchorConfig::from_args(&args(&[
            "--target=local",
            "--redirect=/a=/b=c",
            "--project=CODEX_HOME=/creds",
            "--bring=CODEX_HOME/sessions=/epic/codex",
            "--tell=/tmp/homes",
            "--workspace=/w/./x",
            "claude",
            "--model",
            "opus",
        ]))
        .unwrap();
        assert_eq!(config.redirects, vec![("/a".into(), "/b=c".into())]);
        assert_eq!(config.workspace, "/w/x");
        assert_eq!(config.command, ["claude", "--model", "opus"]);
        for bad in [
            "--redirect=relative=/b",
            "--hush=A=B",
            "--project=NAME=relative",
            "--tell=relative",
            "--target=nonsense://x",
            "--harness=nowhere",
        ] {
            AnchorConfig::from_args(&args(&[bad, "claude"])).unwrap_err();
        }
    }
}
