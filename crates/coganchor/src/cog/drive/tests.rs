//! The native drive against a fake anchor that records every command it is asked to run.
//! Ports the drive cases of `tests/unit/coganchor/test_anchor.py`, and replays the turn
//! `tests/fixtures/unit13_capture.py` captured from Python's `drive` to check this one asks
//! the target exactly the same things in the same order.

use std::collections::BTreeSet;
use std::ffi::OsString;
use std::fs;
use std::os::fd::AsRawFd;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Sender};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{Value, json};

use super::remote::{Feed, Running, exchanged, request, status};
use super::*;
use crate::client::Event;
use crate::cog::homes::Virtual;
use crate::proto::Stream;
use crate::transport::Target;

/// What the fake answers one command with.
#[derive(Clone, Default)]
struct Reply {
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    /// None for a command that never answers.
    done: Option<Result<Meta, RemoteError>>,
    /// Whether what it is fed comes back on its stdout first, as `cat` would.
    echo: bool,
}

fn exits(code: i64) -> Reply {
    Reply {
        done: Some(Ok(meta(json!({"exit_code": code})))),
        ..Reply::default()
    }
}

fn says(code: i64, stdout: &[u8]) -> Reply {
    Reply {
        stdout: stdout.to_vec(),
        ..exits(code)
    }
}

fn meta(value: Value) -> Meta {
    match value {
        Value::Object(map) => map,
        _ => panic!("not an object"),
    }
}

/// One command the fake was asked to run.
#[derive(Clone, Debug, Default)]
struct Asked {
    request: Meta,
    stdin: Vec<u8>,
    ended: bool,
    signals: Vec<i32>,
}

impl Asked {
    fn argv(&self) -> Vec<String> {
        self.request["argv"]
            .as_array()
            .unwrap()
            .iter()
            .map(|one| one.as_str().unwrap().to_owned())
            .collect()
    }

    /// The script it ran, for one run as `/bin/sh -c SCRIPT humanize ...`.
    fn script(&self) -> String {
        self.argv()[2].clone()
    }
}

type Answer = Box<dyn Fn(&Asked, usize) -> Reply + Send + Sync>;

/// An anchor that answers each command as `answer` says, and remembers what it was asked.
struct Fake {
    info: Meta,
    answer: Answer,
    asked: Arc<Mutex<Vec<Asked>>>,
}

impl Fake {
    fn new(answer: impl Fn(&Asked, usize) -> Reply + Send + Sync + 'static) -> Fake {
        Fake {
            info: meta(json!({"version": 1, "hostname": "far", "pid": 7})),
            answer: Box::new(answer),
            asked: Arc::default(),
        }
    }

    fn asked(&self) -> Vec<Asked> {
        self.asked.lock().unwrap().clone()
    }
}

struct FakeFeed {
    index: usize,
    reply: Reply,
    asked: Arc<Mutex<Vec<Asked>>>,
    events: Mutex<Option<Sender<Event>>>,
    /// Kept open for a command that never answers.
    kept: Mutex<Option<Sender<Event>>>,
}

impl Remote for Fake {
    fn start(&self, _: Option<&str>) -> Result<(), RemoteError> {
        Ok(())
    }

    fn info(&self) -> Meta {
        self.info.clone()
    }

    fn exec(&self, request: Meta) -> Result<Running, RemoteError> {
        let asked = Asked {
            request,
            ..Asked::default()
        };
        let index = {
            let mut all = self.asked.lock().unwrap();
            all.push(asked.clone());
            all.len() - 1
        };
        let reply = (self.answer)(&asked, index);
        let (sender, events) = mpsc::channel();
        Ok(Running {
            events,
            feed: Arc::new(FakeFeed {
                index,
                reply,
                asked: self.asked.clone(),
                events: Mutex::new(Some(sender)),
                kept: Mutex::new(None),
            }),
        })
    }
}

impl Feed for FakeFeed {
    fn send(&self, body: &[u8]) -> Result<(), RemoteError> {
        self.asked.lock().unwrap()[self.index]
            .stdin
            .extend_from_slice(body);
        Ok(())
    }

    /// The whole answer comes once the input has ended, as a command reading it would give it.
    fn end(&self) -> Result<(), RemoteError> {
        let fed = {
            let mut all = self.asked.lock().unwrap();
            all[self.index].ended = true;
            all[self.index].stdin.clone()
        };
        let Some(sender) = self.events.lock().unwrap().take() else {
            return Ok(());
        };
        if self.reply.echo {
            let _ = sender.send(Event::Chunk(Stream::Stdout, fed));
        }
        let _ = sender.send(Event::Chunk(Stream::Stdout, self.reply.stdout.clone()));
        let _ = sender.send(Event::Chunk(Stream::Stderr, self.reply.stderr.clone()));
        let _ = sender.send(Event::End(Stream::Stdout));
        match &self.reply.done {
            Some(done) => {
                let _ = sender.send(Event::Done(done.clone()));
            }
            None => *self.kept.lock().unwrap() = Some(sender),
        }
        Ok(())
    }

    fn signal(&self, signal: i32) -> Result<(), RemoteError> {
        self.asked.lock().unwrap()[self.index].signals.push(signal);
        Ok(())
    }
}

/// A target with the CLIs `there` on it, whose private directory is `/tmp/tmp.S`, and whose
/// CLI answers `cli`.
fn target(there: &'static [&'static str], cli: Reply) -> Fake {
    Fake::new(move |asked, _| {
        let argv = asked.argv();
        if argv[0] == "env" {
            return cli.clone();
        }
        match argv[2].as_str() {
            FIND_PROGRAM if there.contains(&argv[4].as_str()) => {
                says(0, format!("{}\n", argv[4]).as_bytes())
            }
            FIND_PROGRAM => exits(127),
            MAKE_SESSION => says(0, b"/tmp/tmp.S"),
            SCRIPT => says(0, b"\n"),
            _ => exits(0),
        }
    })
}

fn config(workspace: &str) -> AnchorConfig {
    AnchorConfig {
        target: Target {
            scheme: "ssh".into(),
            user: None,
            host: "box".into(),
            port: None,
            path: None,
            options: Vec::new(),
        },
        harness: "local".into(),
        broker: String::new(),
        workspace: workspace.into(),
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
        native: true,
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

fn words(said: &[&str]) -> Vec<OsString> {
    said.iter().map(OsString::from).collect()
}

/// What a turn wrote to its streams, and its status.
struct Turned {
    said: anyhow::Result<i32>,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

/// Runs a turn against `fake` with `stdin` as its input.
fn turned(
    fake: &Fake,
    config: &AnchorConfig,
    command: &[&str],
    environ: Meta,
    stdin: &[u8],
) -> Turned {
    let (read, write) = nix::unistd::pipe().unwrap();
    nix::unistd::write(&write, stdin).unwrap();
    drop(write);
    let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
    let said = {
        let mut io = Io {
            stdin: read.as_raw_fd(),
            stdout: &mut stdout,
            stderr: &mut stderr,
        };
        let refreshing =
            local::refreshing(config.projects.iter().map(|(_, whence)| whence.as_str()));
        let command = words(command);
        let started_in = settled(config, &command).unwrap();
        driven(
            fake,
            config,
            &command,
            &started_in,
            "ssh://box",
            &refreshing,
            environ,
            "/home/me",
            &mut io,
        )
    };
    Turned {
        said,
        stdout,
        stderr,
    }
}

// ---------------------------------------------------------------- refused before anything

#[test]
fn driving_nothing_is_refused() {
    let said = drive(&config("/w"), &[]).unwrap_err();
    assert!(said.to_string().contains("no agent given"));
}

#[test]
fn driving_from_outside_the_workspace_is_refused() {
    let mut config = config("/w");
    config.chdir = Some("/w2".into());
    let said = drive(&config, &words(&["claude"])).unwrap_err();
    assert_eq!(said.to_string(), "/w2 is not inside /w");
    config.chdir = Some("/w/sub".into());
    assert_eq!(settled(&config, &words(&["claude"])).unwrap(), "/w/sub");
}

// ---------------------------------------------------------------- the CLI looked for first

#[test]
fn a_cli_the_target_has_not_got_is_not_installed_and_says_how_to_fix_it() {
    let fake = target(&[], exits(0));
    let mut config = config("/w");
    config.installs = "npm i -g claude".into();
    let mut stderr = Vec::new();
    let named = installed(&fake, "/opt/bin/claude", "/w", &config, "ssh://box").unwrap_err();
    assert_eq!(
        named.to_string(),
        "/opt/bin/claude is not installed on ssh://box; install it there with `npm i -g claude`"
    );
    // Looked for as named, then by its last component, from the workspace.
    let asked = fake.asked();
    assert_eq!(
        asked
            .iter()
            .map(|one| one.argv()[4].clone())
            .collect::<Vec<_>>(),
        ["/opt/bin/claude", "claude"]
    );
    assert!(
        asked
            .iter()
            .all(|one| one.request["cwd"] == "/w" && one.ended)
    );
    // As a turn: 127, and nothing put on the target.
    let fake = target(&[], exits(0));
    let turn = turned(&fake, &config, &["/opt/bin/claude", "-p"], Meta::new(), b"");
    assert_eq!(turn.said.unwrap(), crate::exit::NOT_INSTALLED);
    assert_eq!(fake.asked().len(), 2);
    stderr.extend(turn.stderr);
    assert!(
        stderr.is_empty(),
        "said on this process's stderr, not the CLI's"
    );
}

#[test]
fn a_name_is_looked_for_once() {
    let fake = target(&[], exits(0));
    let _ = installed(&fake, "claude", "/w", &config("/w"), "ssh://box");
    assert_eq!(fake.asked().len(), 1);
}

#[test]
fn a_target_that_cannot_be_asked_fails_the_turn() {
    let fake = Fake::new(|_, _| Reply {
        done: Some(Err(RemoteError::new(libc::EPIPE, "gone"))),
        ..Reply::default()
    });
    let turn = turned(&fake, &config("/w"), &["claude"], Meta::new(), b"");
    assert_eq!(turn.said.unwrap_err().to_string(), "[Errno 32] gone");
}

// ---------------------------------------------------------------- the turn itself

#[test]
fn a_turn_answers_with_its_own_status_streams_and_input() {
    let cli = Reply {
        stdout: b"out\n".to_vec(),
        stderr: b"err\n".to_vec(),
        echo: true,
        ..exits(7)
    };
    let fake = target(&["claude"], cli);
    let mut config = config("/w");
    config.chdir = Some("/w/sub".into());
    let environ = meta(json!({"PATH": "/bin", "ANTHROPIC_API_KEY": "sk-secret"}));
    let turn = turned(
        &fake,
        &config,
        &["claude", "--print"],
        environ.clone(),
        b"one\ntwo\n",
    );
    assert_eq!(turn.said.unwrap(), 7);
    assert_eq!(turn.stdout, b"one\ntwo\nout\n");
    assert_eq!(turn.stderr, b"err\n");
    let asked = fake.asked();
    let cli = asked.last().unwrap();
    assert_eq!(
        cli.argv(),
        [
            "env",
            concat!("HUMANIZE=", env!("CARGO_PKG_VERSION")),
            "HUMANIZE_TARGET=ssh://box",
            "HUMANIZE_WORKSPACE=/w",
            "claude",
            "--print"
        ]
    );
    assert_eq!(cli.request["cwd"], "/w/sub");
    // The account is the environment, never a word of the command line.
    assert_eq!(cli.request["env"], Value::Object(environ));
    assert!(!cli.argv().iter().any(|word| word.contains("sk-secret")));
    assert_eq!(cli.request["fence"], Value::Null);
    // Nothing was made on the target, so nothing is swept.
    assert_eq!(asked.len(), 2);
}

#[test]
fn a_signal_that_ended_the_cli_is_its_status() {
    assert_eq!(status(&meta(json!({"exit_code": null, "signal": 15}))), 143);
    assert_eq!(status(&meta(json!({"exit_code": 4, "signal": null}))), 4);
    assert_eq!(status(&Meta::new()), 1);
}

#[test]
fn hushed_variables_are_unset_and_told_ones_set_in_order() {
    let said = BTreeMap::from([
        ("HUMANIZE".to_owned(), "0.0.0".to_owned()),
        ("CODEX_HOME".to_owned(), "/s/codex_home".to_owned()),
    ]);
    assert_eq!(
        wrapping(
            &["OPENAI_API_KEY".into(), "ANTHROPIC_API_KEY".into()],
            &said
        ),
        [
            "env",
            "-u",
            "ANTHROPIC_API_KEY",
            "-u",
            "OPENAI_API_KEY",
            "CODEX_HOME=/s/codex_home",
            "HUMANIZE=0.0.0"
        ]
    );
}

#[test]
fn a_short_command_that_never_answers_is_killed_and_given_up_on() {
    let fake = Fake::new(|_, _| Reply::default());
    let argv = sh(SWEEP, &["/tmp/tmp.S"]);
    let said = exchanged(&fake, &argv, "/w", b"", Duration::from_millis(50)).unwrap_err();
    assert_eq!(
        said.to_string(),
        "the target did not answer '/bin/sh' in 0s"
    );
    assert_eq!(fake.asked()[0].signals, [libc::SIGKILL]);
}

#[test]
fn a_short_command_is_fed_a_frame_at_a_time() {
    let fake = Fake::new(|_, _| exits(0));
    let big = vec![7u8; crate::proto::CHUNK_SIZE * 2 + 1];
    exchanged(&fake, &sh(SWEEP, &["x"]), "/w", &big, SETTLING).unwrap();
    assert_eq!(fake.asked()[0].stdin, big);
    assert_eq!(
        fake.asked()[0].request,
        request(&sh(SWEEP, &["x"]), "/w", Meta::new(), None)
    );
}

// ---------------------------------------------------------------- credentials

fn creds(dir: &Path, said: &str) -> PathBuf {
    let held = dir.join("creds");
    fs::create_dir_all(&held).unwrap();
    fs::write(held.join("auth.json"), said).unwrap();
    fs::set_permissions(held.join("auth.json"), fs::Permissions::from_mode(0o600)).unwrap();
    held
}

const SIGNED_IN: &str = "{\"tokens\": {\"access_token\": \"a1\", \"refresh_token\": \"r1\"}}\n";
const REFRESHED: &str = "{\"tokens\": {\"access_token\": \"a2\", \"refresh_token\": \"r2\"}}\n";

/// A target whose copy of the sign-in reads back as `now`.
fn reads_back(now: &'static str, status: i64) -> Fake {
    Fake::new(move |asked, _| {
        let argv = asked.argv();
        if argv[0] == "env" {
            return exits(0);
        }
        match argv[2].as_str() {
            FIND_PROGRAM => says(0, b"/usr/bin/codex\n"),
            MAKE_SESSION => says(0, b"/tmp/tmp.S"),
            READ_BACK => says(status, now.as_bytes()),
            _ => exits(0),
        }
    })
}

fn projecting(dir: &Path, said: &str) -> (AnchorConfig, PathBuf) {
    let held = creds(dir, said);
    let mut config = config("/w");
    config.projects = vec![("CODEX_HOME".into(), held.to_str().unwrap().into())];
    (config, held)
}

#[test]
fn a_projected_credential_crosses_on_stdin_into_the_turns_own_directory_and_is_swept() {
    let dir = tempfile::tempdir().unwrap();
    let (mut config, _) = projecting(dir.path(), "sk-the-actual-secret\n");
    config.tell = dir.path().join("tell").to_str().unwrap().into();
    fs::create_dir(dir.path().join("tell")).unwrap();
    let fake = reads_back("", 0);
    let turn = turned(&fake, &config, &["codex"], Meta::new(), b"");
    assert_eq!(turn.said.unwrap(), 0);
    let asked = fake.asked();
    let scripts: Vec<String> = asked.iter().map(Asked::script).collect();
    assert_eq!(scripts[1], MAKE_SESSION);
    assert_eq!(scripts[2], WRITE_PRIVATELY);
    assert_eq!(asked[2].argv()[4], "/tmp/tmp.S/codex_home/auth.json");
    assert_eq!(asked[2].stdin, b"sk-the-actual-secret\n");
    let cli = &asked[3];
    assert!(
        cli.argv()
            .contains(&"CODEX_HOME=/tmp/tmp.S/codex_home".to_owned())
    );
    for one in &asked {
        assert!(
            !one.argv()
                .iter()
                .any(|word| word.contains("sk-the-actual-secret"))
        );
    }
    // No sign-in that refreshes itself, so nothing read back; swept last.
    assert_eq!(asked.last().unwrap().argv()[2], SWEEP);
    assert_eq!(asked.last().unwrap().argv()[4], "/tmp/tmp.S");
    assert_eq!(asked.len(), 5);
    // The file telling where the variables landed is gone with the turn.
    assert_eq!(fs::read_dir(dir.path().join("tell")).unwrap().count(), 0);
}

#[test]
fn a_credential_that_could_not_be_put_there_fails_the_turn_and_is_swept() {
    let dir = tempfile::tempdir().unwrap();
    let (config, _) = projecting(dir.path(), "key\n");
    let fake = Fake::new(|asked, _| match asked.script().as_str() {
        FIND_PROGRAM => says(0, b"/usr/bin/codex\n"),
        MAKE_SESSION => says(0, b"/tmp/tmp.S"),
        WRITE_PRIVATELY => says(1, b"read-only file system"),
        _ => exits(0),
    });
    let turn = turned(&fake, &config, &["codex"], Meta::new(), b"");
    assert_eq!(
        turn.said.unwrap_err().to_string(),
        "[Errno 13] could not put CODEX_HOME on the target: read-only file system: \
         '/tmp/tmp.S/codex_home/auth.json'"
    );
    let asked = fake.asked();
    assert!(
        !asked.iter().any(|one| one.argv()[0] == "env"),
        "the CLI never ran"
    );
    assert_eq!(asked.last().unwrap().script(), SWEEP);
}

#[test]
fn a_private_directory_the_target_would_not_make_fails_the_turn() {
    let dir = tempfile::tempdir().unwrap();
    let (config, _) = projecting(dir.path(), "key\n");
    let fake = Fake::new(|asked, _| match asked.script().as_str() {
        FIND_PROGRAM => says(0, b"/usr/bin/codex\n"),
        _ => says(1, b""),
    });
    let turn = turned(&fake, &config, &["codex"], Meta::new(), b"");
    assert_eq!(
        turn.said.unwrap_err().to_string(),
        "[Errno 13] could not make a private directory on the target"
    );
    assert_eq!(fake.asked().len(), 2, "nothing to sweep");
}

#[test]
fn a_sign_in_refreshed_on_the_target_is_written_back() {
    let dir = tempfile::tempdir().unwrap();
    let (config, held) = projecting(dir.path(), SIGNED_IN);
    let fake = reads_back(REFRESHED, 0);
    assert_eq!(
        turned(&fake, &config, &["codex"], Meta::new(), b"")
            .said
            .unwrap(),
        0
    );
    assert_eq!(
        fs::read_to_string(held.join("auth.json")).unwrap(),
        REFRESHED
    );
    let mode = fs::metadata(held.join("auth.json"))
        .unwrap()
        .permissions()
        .mode();
    assert_eq!(mode & 0o777, 0o600);
    assert_eq!(fs::read_dir(&held).unwrap().count(), 1);
    let scripts: Vec<String> = fake.asked().iter().map(Asked::script).collect();
    let at = |script: &str| scripts.iter().position(|one| one == script).unwrap();
    assert!(at(READ_BACK) < at(SWEEP), "read back before it is swept");
}

#[test]
fn what_is_no_whole_sign_in_is_not_written_back() {
    for (now, status) in [
        ("{\"OPENAI_API_KEY\": \"sk-b\"}\n", 0),
        ("{\"tokens\": {\"refresh_token\": \"r2\"", 0),
        (REFRESHED, 1),
    ] {
        let dir = tempfile::tempdir().unwrap();
        let (config, held) = projecting(dir.path(), SIGNED_IN);
        let fake = reads_back(now, status);
        turned(&fake, &config, &["codex"], Meta::new(), b"")
            .said
            .unwrap();
        assert_eq!(
            fs::read_to_string(held.join("auth.json")).unwrap(),
            SIGNED_IN,
            "{now}"
        );
    }
}

#[test]
fn a_sign_in_refreshed_here_too_is_left_as_it_is() {
    let dir = tempfile::tempdir().unwrap();
    let held = creds(dir.path(), SIGNED_IN);
    let lent = [Lent {
        here: held.join("auth.json"),
        there: "/tmp/tmp.S/codex_home/auth.json".into(),
        sent: SIGNED_IN.as_bytes().to_vec(),
    }];
    fs::write(held.join("auth.json"), "{\"refresh_token\": \"here\"}").unwrap();
    brought_back(&reads_back(REFRESHED, 0), &lent, "/w");
    assert_eq!(
        fs::read_to_string(held.join("auth.json")).unwrap(),
        "{\"refresh_token\": \"here\"}"
    );
}

// ---------------------------------------------------------------- fences

fn fence(online: bool, write: &[&str]) -> Fence {
    Fence {
        write: write.iter().map(|one| (*one).to_owned()).collect(),
        online,
        hosts: vec!["api.anthropic.com".into()],
        tmp: "/tmp/fence".into(),
        drawn: vec![
            ("/".into(), "read".into()),
            ("~".into(), "none".into()),
            (".".into(), "write".into()),
        ],
        listen: vec![8080],
        ..Fence::default()
    }
}

#[test]
fn a_fence_the_target_cannot_hold_refuses_the_turn() {
    let fake = target(&["claude"], exits(0));
    let held = fence(false, &[]);
    let said = fenced(&fake, Some(&held), "/home/me").unwrap_err();
    assert_eq!(
        said.to_string(),
        "[Errno 1] the target cannot fence the CLI: it needs Landlock ABI 4 and seccomp"
    );
    let said = fenced(&fake, Some(&fence(true, &[])), "/home/me").unwrap_err();
    assert!(said.to_string().ends_with("it needs Landlock"));
    // Fencing nothing at all is no fence; carving something out of everything is one.
    assert!(
        fenced(&fake, Some(&fence(true, &["/"])), "/home/me")
            .unwrap()
            .is_none()
    );
    let carved = Fence {
        deny: vec!["/home/me/.ssh".into()],
        ..fence(true, &["/"])
    };
    assert!(fenced(&fake, Some(&carved), "/home/me").is_err());
    assert!(fenced(&fake, None, "/home/me").unwrap().is_none());
}

#[test]
fn a_fenced_turn_is_told_its_rules_and_may_write_its_own_directory() {
    let dir = tempfile::tempdir().unwrap();
    let (mut config, _) = projecting(dir.path(), "key\n");
    config.fence = Some(fence(
        false,
        &["/home/me/.codex", "/home/me/a/../.cache", "/elsewhere"],
    ));
    let mut fake = reads_back("", 0);
    fake.info = meta(json!({"version": 1, "fence": {"fs": true, "net": true}}));
    turned(&fake, &config, &["codex"], Meta::new(), b"")
        .said
        .unwrap();
    let asked = fake.asked();
    let cli = asked.iter().find(|one| one.argv()[0] == "env").unwrap();
    assert_eq!(
        serde_json::to_string(&cli.request["fence"]).unwrap(),
        serde_json::to_string(&json!({
            "rules": [["/", "read"], ["~", "none"], [".", "write"]], "online": false,
            "hosts": ["api.anthropic.com"], "write": ["~/.codex", "~/.cache", "/tmp/tmp.S"],
            "programs": true, "listen": [8080],
        }))
        .unwrap()
    );
    // The short commands are held to nothing.
    assert!(
        asked
            .iter()
            .filter(|one| one.argv()[0] != "env")
            .all(|one| one.request["fence"].is_null())
    );
}

#[test]
fn a_fence_drawn_path_by_path_cannot_be_drawn_again() {
    let mut held = fence(false, &[]);
    held.drawn.clear();
    assert!(
        told(&held, "/home/me")
            .unwrap_err()
            .to_string()
            .contains("path by path")
    );
}

// ---------------------------------------------------------------- the virtual home

fn skill(dir: &Path) -> PathBuf {
    let held = dir.join("review");
    fs::create_dir_all(&held).unwrap();
    fs::write(held.join("SKILL.md"), "---\nname: review\n---\n").unwrap();
    fs::set_permissions(held.join("SKILL.md"), fs::Permissions::from_mode(0o644)).unwrap();
    fs::write(held.join("run.sh"), "#!/bin/sh\n").unwrap();
    fs::set_permissions(held.join("run.sh"), fs::Permissions::from_mode(0o755)).unwrap();
    held
}

fn virtual_home(skill: &Path, secures: &str) -> Virtual {
    Virtual::loads(
        &json!({
            "variable": "CLAUDE_CONFIG_DIR", "default": ".claude", "rewrites": ["settings.json"],
            "outside": [["settings.json", ".claude.json"]], "lodges": "skills", "secures": secures,
            "private": ["projects"], "made": [], "kept": [], "skills": [["review", skill]],
            "flag": "", "merges": [], "records": [["db/*.sqlite", "t", "c"]], "keeps": "",
        })
        .to_string(),
    )
    .unwrap()
}

#[test]
fn a_virtual_home_is_built_its_skills_carried_and_written_back() {
    let dir = tempfile::tempdir().unwrap();
    let mut config = config("/w");
    config.home = Some(virtual_home(&skill(dir.path()), "CLAUDE_SECURE"));
    let fake = Fake::new(|asked, _| match asked.argv()[0].as_str() {
        "env" => exits(0),
        _ => match asked.script().as_str() {
            FIND_PROGRAM => says(0, b"/usr/bin/claude\n"),
            MAKE_SESSION => says(0, b"/tmp/tmp.S"),
            SCRIPT => says(0, b"/home/me/.moved\n"),
            _ => exits(0),
        },
    });
    turned(&fake, &config, &["claude"], Meta::new(), b"")
        .said
        .unwrap();
    let asked = fake.asked();
    let built = &asked[2];
    assert_eq!(
        built.argv()[4..],
        [
            "/tmp/tmp.S/claude_config_dir",
            "CLAUDE_CONFIG_DIR",
            ".claude",
            "skills",
            "copy=settings.json=.claude.json",
            "keep=projects",
            "skill=review",
            "record=db/*.sqlite=t=c"
        ]
    );
    assert_eq!(
        asked[3].argv()[4..],
        ["/tmp/tmp.S/claude_config_dir/skills/review/SKILL.md", "600"]
    );
    assert_eq!(asked[3].stdin, b"---\nname: review\n---\n");
    assert_eq!(
        asked[4].argv()[4..],
        ["/tmp/tmp.S/claude_config_dir/skills/review/run.sh", "700"]
    );
    let cli = &asked[5];
    assert!(
        cli.argv()
            .contains(&"CLAUDE_CONFIG_DIR=/tmp/tmp.S/claude_config_dir".to_owned())
    );
    // Nothing projected for the variable: the sign-in stays where the user's home has it.
    assert!(
        cli.argv()
            .contains(&"CLAUDE_SECURE=/home/me/.moved".to_owned())
    );
    assert_eq!(asked[6].script(), BACK);
    assert_eq!(
        asked[6].argv()[4..],
        built.argv()[4..5]
            .iter()
            .cloned()
            .chain(built.argv()[8..].iter().cloned())
            .collect::<Vec<_>>()
    );
    assert_eq!(asked[7].script(), SWEEP);
}

#[test]
fn a_skill_that_could_not_be_carried_is_left_out_whole() {
    let dir = tempfile::tempdir().unwrap();
    let mut config = config("/w");
    config.home = Some(virtual_home(&skill(dir.path()), ""));
    let fake = Fake::new(|asked, _| match asked.argv()[0].as_str() {
        "env" => exits(0),
        _ => match asked.script().as_str() {
            FIND_PROGRAM => says(0, b"/usr/bin/claude\n"),
            MAKE_SESSION => says(0, b"/tmp/tmp.S"),
            WRITE_WHOLE => says(1, b"no space"),
            _ => exits(0),
        },
    });
    assert_eq!(
        turned(&fake, &config, &["claude"], Meta::new(), b"")
            .said
            .unwrap(),
        0
    );
    let scripts: Vec<String> = fake.asked().iter().map(Asked::script).collect();
    // One file tried, then the skill swept rather than half there, and the turn goes on.
    assert_eq!(scripts[3], WRITE_WHOLE);
    assert_eq!(scripts[4], SWEEP);
    assert_eq!(
        fake.asked()[4].argv()[4],
        "/tmp/tmp.S/claude_config_dir/skills/review"
    );
    assert_eq!(fake.asked()[5].argv()[0], "env");
}

// ---------------------------------------------------------------- the turn Python took

/// The fixture `unit13_capture.py` wrote.
fn fixture() -> Value {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/tests/fixtures/unit13_drive.json"
    );
    serde_json::from_str(&fs::read_to_string(path).unwrap()).unwrap()
}

fn unhexed(said: &Value) -> Vec<u8> {
    hex::decode(said.as_str().unwrap()).unwrap()
}

#[test]
fn a_native_turn_asks_the_target_what_pythons_asked_in_the_same_order() {
    let fixture = fixture();
    let dir = tempfile::tempdir().unwrap();
    let root = dir.path();
    // The files the turn carried, made again here.
    for (name, said) in fixture["files"].as_object().unwrap() {
        let at = root.join(name);
        fs::create_dir_all(at.parent().unwrap()).unwrap();
        fs::write(&at, said.as_str().unwrap()).unwrap();
        let mode = if name.ends_with(".sh") || name.ends_with("auth.json") {
            if name.ends_with(".sh") { 0o755 } else { 0o600 }
        } else {
            0o644
        };
        fs::set_permissions(&at, fs::Permissions::from_mode(mode)).unwrap();
    }
    fs::create_dir(root.join("tell")).unwrap();
    let here = |name: &str| root.join(name).to_str().unwrap().to_owned();
    let mut home = fixture["home"].clone();
    home["skills"][0][1] = Value::from(here("skills/review"));
    let mut config = config(fixture["workspace"].as_str().unwrap());
    config.hushes = serde_json::from_value(fixture["hushes"].clone()).unwrap();
    config.projects = vec![("CODEX_HOME".into(), here("creds"))];
    config.home = Some(Virtual::loads(&home.to_string()).unwrap());
    config.brings = vec![("CODEX_HOME/sessions".into(), here("brought"))];
    config.tell = here("tell");

    let exchanges = fixture["exchanges"].as_array().unwrap().clone();
    let replayed = exchanges.clone();
    let fake = Fake::new(move |_, index| {
        let one = &replayed[index];
        Reply {
            stdout: unhexed(&one["stdout"]),
            stderr: unhexed(&one["stderr"]),
            done: Some(Ok(meta(one["result"].clone()))),
            echo: false,
        }
    });
    let command: Vec<&str> = fixture["command"]
        .as_array()
        .unwrap()
        .iter()
        .map(|one| one.as_str().unwrap())
        .collect();
    let environ = meta(fixture["environ"].clone());
    let refreshing: BTreeSet<PathBuf> =
        local::refreshing(config.projects.iter().map(|(_, whence)| whence.as_str()));
    let (read, write) = nix::unistd::pipe().unwrap();
    nix::unistd::write(&write, b"from stdin\n").unwrap();
    drop(write);
    let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
    let mut io = Io {
        stdin: read.as_raw_fd(),
        stdout: &mut stdout,
        stderr: &mut stderr,
    };
    let command = words(&command);
    let said = driven(
        &fake,
        &config,
        &command,
        &config.workspace,
        fixture["target"].as_str().unwrap(),
        &refreshing,
        environ,
        "/home/me",
        &mut io,
    )
    .unwrap();

    assert_eq!(i64::from(said), fixture["status"].as_i64().unwrap());
    let asked = fake.asked();
    assert_eq!(asked.len(), exchanges.len());
    for (index, (one, expected)) in asked.iter().zip(&exchanges).enumerate() {
        // Key for key, in the same order.
        assert_eq!(
            serde_json::to_string(&one.request).unwrap(),
            // Python was asked on `main`, where the version is 0.0.0; a release says its own.
            serde_json::to_string(&expected["request"])
                .unwrap()
                .replace(
                    "HUMANIZE=0.0.0",
                    concat!("HUMANIZE=", env!("CARGO_PKG_VERSION"))
                ),
            "request {index}"
        );
        assert_eq!(
            one.stdin,
            unhexed(&expected["stdin"]),
            "stdin of request {index}"
        );
        assert!(one.ended, "request {index} was told its input ended");
    }
    assert_eq!(
        fs::read_to_string(root.join("creds/auth.json")).unwrap(),
        fixture["written_back"].as_str().unwrap()
    );
    let mut brought: Vec<String> = Vec::new();
    let mut pending = vec![root.join("brought")];
    while let Some(at) = pending.pop() {
        for entry in fs::read_dir(&at).unwrap().flatten() {
            let path = entry.path();
            brought.push(
                path.strip_prefix(root.join("brought"))
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .into(),
            );
            if path.is_dir() {
                pending.push(path);
            }
        }
    }
    brought.sort();
    assert_eq!(Value::from(brought), fixture["brought"]);
    assert_eq!(fs::read_dir(root.join("tell")).unwrap().count(), 0);
}

// ---------------------------------------------------------------- given up on

#[test]
fn a_turn_given_up_on_from_the_keyboard_is_tidied_and_exits_130() {
    let dir = tempfile::tempdir().unwrap();
    let (config, _) = projecting(dir.path(), "key\n");
    // A CLI that never ends.
    let fake = Fake::new(|asked, _| match asked.argv()[0].as_str() {
        "env" => Reply::default(),
        _ => match asked.script().as_str() {
            FIND_PROGRAM => says(0, b"/usr/bin/codex\n"),
            MAKE_SESSION => says(0, b"/tmp/tmp.S"),
            _ => exits(0),
        },
    });
    let signals = Signals::quiet();
    let watched = Watched {
        remote: &fake,
        signals: &signals,
    };
    let said = std::thread::scope(|scope| {
        scope.spawn(|| {
            while !fake.asked().iter().any(|one| one.argv()[0] == "env") {
                std::thread::sleep(Duration::from_millis(10));
            }
            signals.interrupt();
        });
        let (read, _write) = nix::unistd::pipe().unwrap();
        let (mut stdout, mut stderr) = (Vec::new(), Vec::new());
        let mut io = Io {
            stdin: read.as_raw_fd(),
            stdout: &mut stdout,
            stderr: &mut stderr,
        };
        let command = words(&["codex"]);
        driven(
            &watched,
            &config,
            &command,
            "/w",
            "ssh://box",
            &BTreeSet::new(),
            Meta::new(),
            "/home/me",
            &mut io,
        )
    });
    assert_eq!(said.unwrap(), crate::exit::INTERRUPTED);
    let asked = fake.asked();
    assert_eq!(
        asked.last().unwrap().script(),
        SWEEP,
        "the credential is taken away"
    );
}

#[test]
fn a_short_command_given_up_on_is_given_up_on_at_once() {
    let fake = Fake::new(|_, _| Reply::default());
    let signals = Signals::quiet();
    let watched = Watched {
        remote: &fake,
        signals: &signals,
    };
    let said = std::thread::scope(|scope| {
        scope.spawn(|| {
            std::thread::sleep(Duration::from_millis(50));
            signals.interrupt();
        });
        exchanged(&watched, &sh(SWEEP, &["x"]), "/w", b"", SETTLING)
    });
    assert!(said.unwrap_err().is::<Interrupted>());
}

#[test]
fn a_turn_that_failed_half_way_through_its_credentials_brings_nothing_home() {
    let dir = tempfile::tempdir().unwrap();
    let (mut config, held) = projecting(dir.path(), "key\n");
    let other = dir.path().join("other");
    fs::create_dir(&other).unwrap();
    fs::write(other.join("token"), "t").unwrap();
    config
        .projects
        .push(("OTHER_HOME".into(), other.to_str().unwrap().into()));
    config.brings = vec![("CODEX_HOME/sessions".into(), held.to_str().unwrap().into())];
    let fake = Fake::new(|asked, _| match asked.script().as_str() {
        FIND_PROGRAM => says(0, b"/usr/bin/codex\n"),
        MAKE_SESSION => says(0, b"/tmp/tmp.S"),
        WRITE_PRIVATELY if asked.argv()[4].contains("other_home") => says(1, b"full"),
        _ => exits(0),
    });
    assert!(
        turned(&fake, &config, &["codex"], Meta::new(), b"")
            .said
            .is_err()
    );
    assert!(!fake.asked().iter().any(|one| one.script() == PACK));
}
