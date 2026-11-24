//! `tests/unit/coganchor/test_statepaths.py`, ported. Each case sets `HOME` and `PATH`,
//! which are the process's, so the cases take turns.

use std::ffi::OsString;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};

use coganchor::cog::statepaths::{
    AgentProfile, COMMON_STATE_PATHS, PROFILES, Resolved, XDG_HOMES, profile_for, resolve,
};

static ENV: Mutex<()> = Mutex::new(());

/// A resolved scratch root with its own `HOME` and an empty `PATH`, held for the case.
struct Root {
    _dir: tempfile::TempDir,
    at: PathBuf,
    _turn: MutexGuard<'static, ()>,
}

impl Root {
    fn new() -> Root {
        let turn = ENV.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
        let dir = tempfile::tempdir().unwrap();
        let at = fs::canonicalize(dir.path()).unwrap();
        fs::create_dir(at.join("home")).unwrap();
        set("HOME", &at.join("home"));
        set("PATH", &at.join("empty"));
        for one in XDG_HOMES {
            // SAFETY: as in `set`.
            unsafe { std::env::remove_var(one) };
        }
        Root {
            _dir: dir,
            at,
            _turn: turn,
        }
    }

    fn path(&self, below: &str) -> PathBuf {
        self.at.join(below)
    }

    fn s(&self, below: &str) -> String {
        self.path(below).to_str().unwrap().to_owned()
    }
}

fn set(name: &str, value: &Path) {
    // SAFETY: every case that reads or writes the environment holds `ENV`.
    unsafe { std::env::set_var(name, value) };
}

fn set_path(directories: &[PathBuf]) {
    let joined = std::env::join_paths(directories).unwrap();
    set("PATH", Path::new(&joined));
}

fn program(at: &Path, first: &str) -> PathBuf {
    fs::create_dir_all(at.parent().unwrap()).unwrap();
    fs::write(at, format!("{first}exit 0\n")).unwrap();
    fs::set_permissions(at, fs::Permissions::from_mode(0o755)).unwrap();
    at.to_owned()
}

fn argv(all: &[&str]) -> Vec<OsString> {
    all.iter().map(OsString::from).collect()
}

fn has(found: &Resolved, path: &Path) -> bool {
    found.programs.iter().any(|one| Path::new(one) == path)
}

#[test]
fn every_profile_is_named_once_with_state_under_the_home() {
    let mut names: Vec<_> = PROFILES.iter().map(|one| &*one.name).collect();
    names.sort_unstable();
    let all = names.len();
    names.dedup();
    assert_eq!(names.len(), all);
    assert_eq!(
        names,
        [
            "agy",
            "claude",
            "codex",
            "cursor-agent",
            "dsh",
            "grok",
            "kimi",
            "litellm",
            "mcode",
            "mimo",
            "omp",
            "opencode",
            "pi",
            "qwen"
        ]
    );
    for one in PROFILES {
        assert!(!one.state_paths.is_empty());
        assert!(one.state_paths.iter().all(|path| path.starts_with("~/")));
    }
}

#[test]
fn profile_for_a_known_agent_and_a_generic_one() {
    for (name, expected) in [
        ("claude", "claude"),
        ("/usr/local/bin/codex", "codex"),
        ("cursor-agent", "cursor-agent"),
        ("dsh-jsonrpc-agent-darwin-arm64", "dsh"),
        ("/opt/x/dsh-jsonrpc-agent-linux", "dsh"),
    ] {
        let found = profile_for(name);
        assert_eq!(found.name, expected);
        assert!(!found.state_paths.is_empty());
    }
    assert_eq!(
        profile_for("/somewhere/my-agent"),
        AgentProfile {
            name: "my-agent".into(),
            state_paths: &[]
        }
    );
}

#[test]
fn resolve_refuses_no_command_and_an_agent_that_is_not_there() {
    let root = Root::new();
    let none = resolve(&[]).unwrap_err();
    assert_eq!(none.kind(), std::io::ErrorKind::InvalidInput);
    assert!(none.to_string().contains("no agent command"));
    for command in ["claude", "/nowhere/claude"] {
        let error = resolve(&argv(&[command])).unwrap_err();
        assert_eq!(error.kind(), std::io::ErrorKind::NotFound);
        assert_eq!(error.to_string(), format!("{command}: not found on PATH"));
    }
    drop(root);
}

#[test]
fn resolve_keeps_the_agents_own_state_and_humanizes_here() {
    let root = Root::new();
    let program = program(&root.path("bin/claude"), "#!/bin/sh\n");
    set_path(&[root.path("bin")]);

    let found = resolve(&argv(&["claude", "-p", "hi"])).unwrap();

    assert_eq!(found.profile.name, "claude");
    assert_eq!(found.program, program);
    assert_eq!(found.argv, argv(&[program.to_str().unwrap(), "-p", "hi"]));
    let mut sorted = found.state.clone();
    sorted.sort();
    assert_eq!(found.state, sorted);
    for kept in [
        ".claude",
        ".claude.json",
        ".hmz",
        ".humanize",
        ".cache/humanize",
        ".config/humanize",
        ".local/share/humanize",
        ".local/state/humanize",
    ] {
        assert!(
            found.state.contains(&root.s(&format!("home/{kept}"))),
            "{kept}"
        );
    }
    assert_eq!(
        found.state.len(),
        4 + COMMON_STATE_PATHS.len(),
        "{:?}",
        found.state
    );
    assert!(has(&found, &program));
    assert!(has(&found, &root.path("home/.claude")));
    assert!(has(&found, Path::new("/bin/sh"))); // the interpreter it names outright
}

#[test]
fn resolve_keeps_humanizes_own_wherever_xdg_moves_it() {
    let root = Root::new();
    program(&root.path("bin/claude"), "#!/bin/sh\n");
    set_path(&[root.path("bin")]);
    for (one, under) in XDG_HOMES.iter().zip(["conf", "data", "state", "cache"]) {
        set(one, &root.path(under));
    }
    // A relative one is no XDG directory at all.
    set("XDG_STATE_HOME", Path::new("relative/state"));

    let found = resolve(&argv(&["claude"])).unwrap();

    for under in ["conf", "data", "cache"] {
        assert!(
            found.state.contains(&root.s(&format!("{under}/humanize"))),
            "{under}"
        );
    }
    assert!(!found.state.iter().any(|one| one.contains("relative")));
    // And the defaults still, where an earlier process may have left something.
    assert!(found.state.contains(&root.s("home/.local/state/humanize")));
    for one in XDG_HOMES {
        // SAFETY: as in `set`.
        unsafe { std::env::remove_var(one) };
    }
}

#[test]
fn resolve_follows_a_link_to_the_real_program() {
    let root = Root::new();
    let real = program(&root.path("real/grok"), "#!/bin/sh\n");
    fs::create_dir(root.path("bin")).unwrap();
    symlink(&real, root.path("bin/grok")).unwrap();
    set_path(&[root.path("bin")]);

    let found = resolve(&argv(&["grok"])).unwrap();

    assert_eq!(found.program, real);
    assert_eq!(found.argv, argv(&[&root.s("bin/grok")]));
    assert!(has(&found, &real));
    assert!(has(&found, &root.path("bin/grok")));
}

#[test]
fn resolve_takes_a_path_as_it_is_written() {
    let root = Root::new();
    let program = program(&root.path("elsewhere/kimi"), "#!/bin/sh\n");
    let found = resolve(&argv(&[program.to_str().unwrap(), "--yolo"])).unwrap();
    assert_eq!(found.profile.name, "kimi");
    assert_eq!(found.argv, argv(&[program.to_str().unwrap(), "--yolo"]));
}

#[test]
fn an_env_shebang_claims_every_place_the_interpreter_could_be() {
    let root = Root::new();
    program(&root.path("bin/qwen"), "#!/usr/bin/env node\n");
    let node = program(&root.path("tools/node"), "#!/bin/sh\n");
    set_path(&[root.path("bin"), root.path("tools")]);

    let found = resolve(&argv(&["qwen"])).unwrap();

    assert!(has(&found, Path::new("/usr/bin/env")));
    assert!(has(&found, &root.path("bin/node"))); // a miss, kept here too
    assert!(has(&found, &node));
}

#[test]
fn an_env_shebang_reads_past_flags_and_variables() {
    for shebang in [
        "#!/usr/bin/env -S node --flag\n",
        "#!/usr/bin/env FOO=1 node\n",
    ] {
        let root = Root::new();
        program(&root.path("bin/pi"), shebang);
        set_path(&[root.path("bin")]);
        assert!(has(
            &resolve(&argv(&["pi"])).unwrap(),
            &root.path("bin/node")
        ));
    }
}

#[test]
fn an_env_shebang_naming_a_path_keeps_that_path() {
    let root = Root::new();
    program(
        &root.path("bin/pi"),
        &format!("#!/usr/bin/env {}/opt/node\n", root.at.display()),
    );
    set_path(&[root.path("bin")]);
    assert!(has(
        &resolve(&argv(&["pi"])).unwrap(),
        &root.path("opt/node")
    ));
}

#[test]
fn an_npm_package_keeps_the_programs_beside_its_own() {
    let root = Root::new();
    let package = root.path("lib/node_modules/@x/mimo/bin");
    let launcher = program(&package.join("mimo"), "#!/bin/sh\n");
    let native = program(&package.join(".mimocode"), "#!/bin/sh\n");
    fs::write(package.join("README"), "not a program").unwrap();
    let shims = root.path("lib/node_modules/.bin");
    fs::create_dir(&shims).unwrap();
    symlink(&launcher, shims.join("mimo")).unwrap();
    set_path(std::slice::from_ref(&shims));

    let found = resolve(&argv(&["mimo"])).unwrap();

    assert!(has(&found, &launcher));
    assert!(has(&found, &native));
    assert!(!has(&found, &package.join("README")));
}

#[test]
fn a_program_outside_a_package_keeps_no_neighbours() {
    let root = Root::new();
    program(&root.path("bin/pi"), "#!/bin/sh\n");
    let neighbour = program(&root.path("bin/other"), "#!/bin/sh\n");
    set_path(&[root.path("bin")]);
    assert!(!has(&resolve(&argv(&["pi"])).unwrap(), &neighbour));
}

#[test]
fn codex_keeps_its_native_runtime_here() {
    let root = Root::new();
    let package = root.path("codex");
    program(&package.join("bin/codex"), "#!/usr/bin/env node\n");
    let vendor = package.join("vendor/x86_64-unknown-linux-musl/bin");
    let native = program(&vendor.join("codex"), "#!/bin/sh\n");
    let host = program(&vendor.join("codex-code-mode-host"), "#!/bin/sh\n");
    let node = program(&root.path("tools/node"), "#!/bin/sh\n");
    set_path(&[package.join("bin"), root.path("tools")]);

    let found = resolve(&argv(&["codex"])).unwrap();

    assert!(has(&found, &native));
    assert!(has(&found, &host));
    assert!(has(&found, &node));
    let mut sorted = found.programs.clone();
    sorted.sort();
    sorted.dedup();
    assert_eq!(found.programs, sorted);
}
