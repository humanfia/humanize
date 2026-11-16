//! A fence drawn again on the target, around a command a fenced agent runs there. Port of
//! `hmz.coganchor.fence.abroad` and `hmz.coganchor.serve.fencing`. [Unit 4]
//!
//! What crosses to the target is not a fence but what it was drawn from (`abroad.told`): its
//! rules, whether the network is cut, and for a CLI that runs there itself the hosts
//! its model is at and the state it keeps under its home. This end draws the same fence again
//! around its own workdirs, its own home and its own minimum ([`drawn`]), and runs the
//! command under `coganchor internal fence` ([`fenced`]).

use std::ffi::OsString;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};

use serde_json::{Map, Value};

use crate::anchor::ExportTable;
use crate::fence::policy::{normpath, rules, truthy};
use crate::fence::{Fence, wrap};
use crate::proto::RemoteError;

/// How a path under the home is said to the target: relative to whatever home it has.
pub const HOME: &str = "~/";

/// The command line running `argv` (or `program`, where it is on this machine) inside the
/// fence the `EXEC` request's `fence` rules draw around this machine's own paths: the
/// exports, this user's home, this machine's minimum. `EPERM` where this machine cannot hold
/// it; `EIO` where the rules are malformed.
///
/// A program named by `programs` is looked up on this process's own `PATH`: the request's
/// environment is not handed down here.
pub fn fenced(
    argv: &[OsString],
    program: Option<&OsString>,
    said: &Value,
    exports: &ExportTable,
) -> Result<Vec<OsString>, RemoteError> {
    let empty = Map::new();
    let said = said.as_object().unwrap_or(&empty);
    let net = said.get("online") == Some(&Value::Bool(false));
    if let Some(why) = wrap::unable(net, "command") {
        let refused = RemoteError::new(libc::EPERM, why);
        return Err(match argv.first() {
            Some(first) => refused.with_filename(first.to_string_lossy()),
            None => refused,
        });
    }
    let mut run = argv.first().cloned().unwrap_or_default();
    if let Some(program) = program.filter(|one| !one.is_empty()) {
        run = if Path::new(program).exists() {
            program.clone()
        } else {
            Path::new(program)
                .file_name()
                .map(OsString::from)
                .unwrap_or_default()
        };
    }
    let home = wrap::home();
    let workdirs: Vec<String> = exports
        .exports()
        .iter()
        .map(|one| one.real.to_string_lossy().into_owned())
        .collect();
    let mut line: Vec<OsString> = vec![run.clone()];
    line.extend(argv.iter().skip(1).cloned());
    let read = if truthy(said, "programs") {
        let path = std::env::var("PATH").ok();
        installed(&named(&line).to_string_lossy(), path.as_deref())
    } else {
        Vec::new()
    };
    let mut held = drawn(said, &workdirs, &home, &read, &[])
        .map_err(|why| RemoteError::new(libc::EIO, why))?;
    if truthy(said, "write") {
        ready(&held, &home);
    }
    if !held.tmp.is_empty() && !scratch(&held) {
        held.tmp = String::new();
    }
    Ok(wrap::command(&held, &line))
}

/// A list of strings out of what was said, or a refusal of one that is not.
fn strings(said: &Map<String, Value>, name: &str) -> Result<Vec<String>, String> {
    match said.get(name) {
        None => Ok(Vec::new()),
        Some(Value::Array(listed)) => listed
            .iter()
            .map(|one| one.as_str().map(str::to_owned))
            .collect::<Option<_>>()
            .ok_or_else(|| format!("a fence's {name} is a list of strings")),
        Some(_) => Err(format!("a fence's {name} is a list of strings")),
    }
}

/// The fence a target holds a command to, drawn around its own paths (`abroad.drawn`).
///
/// `workdirs` are the directories this machine exports, the first of them the workdir;
/// `home` is the home of the user commands run as, which is no home where it is `/` or not a
/// directory, and `~` is then the first workdir. The workdirs after the first are each drawn as
/// the workdir is ([`Fence::beside`]). Refuses rules that are not a fence's, a scratch that is not an absolute path of
/// its own, a path to write that is neither under `~/` nor absolute (or that has `..` in it),
/// and a port that is not one.
pub fn drawn(
    said: &Map<String, Value>,
    workdirs: &[String],
    home: &str,
    read: &[String],
    write: &[String],
) -> Result<Fence, String> {
    let Some((first, rest)) = workdirs.split_first() else {
        return Err("a fence is drawn around a workdir, and there is none".into());
    };
    let drawn = said
        .get("rules")
        .and_then(rules)
        .ok_or("a fence's rules are a list of [path, access]")?;
    let online = match said.get("online") {
        None => true,
        Some(Value::Bool(online)) => *online,
        Some(_) => return Err("a fence's online is true or false".into()),
    };
    let hosts = strings(said, "hosts")?;
    let tmp = match said.get("tmp") {
        None => String::new(),
        Some(Value::String(tmp)) => tmp.clone(),
        Some(_) => return Err("a fence's tmp is an absolute path".into()),
    };
    if !tmp.is_empty()
        && (!tmp.starts_with('/') || tmp.split('/').any(|one| one == "..") || normpath(&tmp) == "/")
    {
        return Err("a fence's tmp is an absolute path".into());
    }
    let kept = strings(said, "write")?;
    if kept.iter().any(|one| {
        !(one.starts_with(HOME) || one.starts_with('/')) || one.split('/').any(|part| part == "..")
    }) {
        return Err(format!(
            "a fence's own paths are said under {HOME}, or as the target's own"
        ));
    }
    let homed = !home.is_empty() && normpath(home) != "/" && Path::new(home).is_dir();
    let listen: Vec<u16> = match said.get("listen") {
        None => Vec::new(),
        Some(Value::Array(ports)) => ports
            .iter()
            .map(|one| {
                one.as_u64()
                    .filter(|port| (1..65536).contains(port))
                    .map(|port| port as u16)
            })
            .collect::<Option<_>>()
            .ok_or("a fence's listen is a list of ports")?,
        Some(_) => return Err("a fence's listen is a list of ports".into()),
    };
    let mut writing = write.to_vec();
    writing.extend(kept.iter().filter(|one| one.starts_with('/')).cloned());
    if homed {
        writing.extend(
            kept.iter()
                .filter_map(|one| one.strip_prefix(HOME))
                .map(|rest| Path::new(home).join(rest).to_string_lossy().into_owned()),
        );
    }
    let home = if homed { home } else { first.as_str() };
    let mut fence = Fence::of(&drawn, online, first, home, "", &hosts, read, &writing)?.granting(
        &[],
        &[],
        &[],
        &listen,
    );
    for one in rest {
        fence = fence.beside(one, home);
    }
    Ok(if tmp.is_empty() {
        fence
    } else {
        Fence {
            tmp: normpath(&tmp),
            ..fence
        }
    })
}

/// Makes the directories a fence lets be written under the home, where they are not yet
/// (`abroad.ready`): only directories, read off the name (`~/.cli` is one, `~/.cli.json` a
/// file), and made as the fence reaches them, through no link a fenced program could have
/// made.
pub fn ready(fence: &Fence, home: &str) {
    // A home that is `/` is no home (`drawn`): nothing is kept under it. The Python made every
    // missing directory the fence writes, `/dev/kfd` among them; that is not followed here.
    if normpath(home) == "/" {
        return;
    }
    let root = format!("{}/", normpath(home).trim_end_matches('/'));
    for one in &fence.write {
        let name = Path::new(one)
            .file_name()
            .map(|name| name.to_string_lossy().trim_start_matches('.').to_owned())
            .unwrap_or_default();
        if one.starts_with(&root) && !name.contains('.') && std::fs::symlink_metadata(one).is_err()
        {
            let _ = fence.reach(one, true);
        }
    }
}

/// Makes the scratch a supervised agent names in its commands, at the path it names
/// (`fencing._scratch`): used only where it is a directory of this user's own, reached
/// through no link a fenced command could have made. Whether it is there to be used.
fn scratch(fence: &Fence) -> bool {
    let missing = std::fs::symlink_metadata(&fence.tmp).is_err();
    // Nothing made at the far end of a link that is there already.
    if fence.reach(&fence.tmp, missing).is_err() {
        return false;
    }
    match std::fs::symlink_metadata(&fence.tmp) {
        Ok(seen) => seen.is_dir() && seen.uid() == nix::unistd::geteuid().as_raw(),
        Err(_) => false,
    }
}

/// The program a command line runs, past the `env` a native CLI is started behind
/// (`fencing._named`).
fn named(argv: &[OsString]) -> OsString {
    if Path::new(&argv[0])
        .file_name()
        .is_none_or(|name| name != "env")
    {
        return argv[0].clone();
    }
    let mut words = argv[1..].iter();
    while let Some(word) = words.next() {
        let text = word.to_string_lossy();
        if text == "-u" {
            words.next();
        } else if !text.contains('=') && !text.starts_with('-') {
            return word.clone();
        }
    }
    argv[0].clone()
}

/// `shutil.which`: a name looked up on `path` (this process's `PATH` where none), or a path
/// with a `/` in it taken as it is.
fn which(program: &str, path: Option<&str>) -> Option<String> {
    use nix::unistd::{AccessFlags, access};
    let runs =
        |candidate: &Path| candidate.is_file() && access(candidate, AccessFlags::X_OK).is_ok();
    if program.contains('/') {
        return runs(Path::new(program)).then(|| program.to_owned());
    }
    let searched = match path {
        Some(path) => path.to_owned(),
        None => std::env::var("PATH").unwrap_or_else(|_| "/bin:/usr/bin".into()),
    };
    searched
        .split(':')
        .filter(|dir| !dir.is_empty())
        .map(|dir| Path::new(dir).join(program))
        .find(|candidate| runs(candidate))
        .map(|found| found.to_string_lossy().into_owned())
}

/// What a program needs to be read for it to run: itself, and the tree it was installed as
/// part of, and the same for the interpreter its first line names (`abroad.installed`).
pub fn installed(program: &str, path: Option<&str>) -> Vec<String> {
    let found = if program.contains('/') {
        Some(program.to_owned())
    } else {
        which(program, path)
    };
    let Some(found) = found.filter(|one| Path::new(one).exists()) else {
        return Vec::new();
    };
    let mut held = vec![found.clone()];
    let real = resolve(Path::new(&found));
    held.extend(tree(&real));
    let Ok(file) = std::fs::File::open(&real) else {
        return held;
    };
    let mut first = Vec::new();
    {
        use std::io::{BufRead, Read};
        let _ = std::io::BufReader::new(file.take(256)).read_until(b'\n', &mut first);
    }
    if let Some(line) = first.strip_prefix(b"#!") {
        let text = String::from_utf8_lossy(line);
        let mut words: Vec<&str> = text.split_whitespace().collect();
        if words.len() > 1
            && Path::new(words[0])
                .file_name()
                .is_some_and(|name| name == "env")
        {
            words.remove(0);
        }
        if let Some(interpreter) = words.first().and_then(|word| which(word, path)) {
            let real = resolve(Path::new(&interpreter));
            held.push(interpreter);
            held.extend(tree(&real));
        }
    }
    held
}

/// `Path.resolve()`, which does not fail.
fn resolve(path: &Path) -> PathBuf {
    std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf())
}

/// The file a program really is, and the tree it was installed as a part of (`_tree`).
fn tree(real: &Path) -> Vec<String> {
    let parts: Vec<Component> = real.components().collect();
    if let Some(last) = parts
        .iter()
        .rposition(|one| one.as_os_str() == "node_modules")
    {
        let at = last + 1;
        let width = if parts
            .get(at)
            .is_some_and(|one| one.as_os_str().to_string_lossy().starts_with('@'))
        {
            2
        } else {
            1
        };
        let package: PathBuf = parts.iter().take(at + width).collect();
        return vec![
            real.to_string_lossy().into_owned(),
            package.to_string_lossy().into_owned(),
        ];
    }
    let mut directory = real.parent().unwrap_or(Path::new("/")).to_path_buf();
    if directory.file_name().is_some_and(|name| name == "bin")
        && directory.parent().is_some_and(|up| up.join("lib").is_dir())
    {
        directory = directory.parent().expect("a parent").to_path_buf();
    }
    let mut held = vec![real.to_string_lossy().into_owned()];
    let home = PathBuf::from(wrap::home());
    if directory != Path::new("/") && directory != home {
        held.push(directory.to_string_lossy().into_owned());
    }
    held
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn said(value: Value) -> Map<String, Value> {
        value.as_object().unwrap().clone()
    }

    #[test]
    fn a_fence_is_drawn_around_the_workdirs_and_home() {
        let dir = tempfile::tempdir().unwrap();
        let home = std::fs::canonicalize(dir.path()).unwrap();
        let home = home.to_string_lossy().into_owned();
        let fence = drawn(
            &said(json!({
                "rules": [["/", "none"], ["~", "read"], [".", "write"]], "online": false,
                "write": ["~/.cli", "/opt/state"], "listen": [8080], "tmp": "/tmp/x/",
            })),
            &["/w1".into(), "/w2".into()],
            &home,
            &[],
            &[],
        )
        .unwrap();
        assert!(fence.allows("/w1/a", true));
        assert!(fence.allows("/w2/a", true));
        assert!(fence.allows("/opt/state/a", true));
        assert!(fence.allows(&format!("{home}/.cli/a"), true));
        assert!(fence.allows(&format!("{home}/.bashrc"), false));
        assert!(!fence.allows("/srv/elsewhere", false));
        assert!(!fence.online);
        assert_eq!(fence.listen, vec![8080]);
        assert_eq!(fence.tmp, "/tmp/x");
        assert_eq!(
            fence.drawn,
            vec![
                ("/".to_owned(), "none".to_owned()),
                ("~".to_owned(), "read".to_owned()),
                (".".to_owned(), "write".to_owned()),
            ]
        );
    }

    #[test]
    fn a_fence_carves_out_around_the_targets_own_paths() {
        let dir = tempfile::tempdir().unwrap();
        let home = std::fs::canonicalize(dir.path()).unwrap();
        let home = home.to_string_lossy().into_owned();
        let fence = drawn(
            &said(json!({"rules": [
                ["/", "read"], [".", "write"], ["./secret", "none"], ["~/.ssh", "none"],
            ]})),
            &["/srv/work".into(), "/srv/more".into()],
            &home,
            &[],
            &[],
        )
        .unwrap();
        assert!(fence.allows("/srv/work/a.py", true));
        assert!(!fence.allows("/srv/work/secret/key", false));
        assert!(fence.allows("/srv/more/a.py", true));
        assert!(!fence.allows("/srv/more/secret/key", false));
        assert!(!fence.allows(&format!("{home}/.ssh/id"), false));
        assert!(fence.allows(&format!("{home}/.bashrc"), false));
    }

    #[test]
    fn every_export_is_drawn_as_the_workdir() {
        for (local, written, read) in [
            ("write", true, true),
            ("read", false, true),
            ("none", false, false),
        ] {
            let fence = drawn(
                &said(json!({"rules": [[".", local]]})),
                &["/w".into(), "/x".into()],
                "/",
                &[],
                &[],
            )
            .unwrap();
            assert_eq!(fence.allows("/x/a", true), written, "{local}");
            assert_eq!(fence.allows("/x/a", false), read, "{local}");
        }
    }

    #[test]
    fn what_is_not_a_fence_is_refused() {
        let w = ["/w".to_owned()];
        let base = json!({"rules": [["/", "none"]]});
        let with = |key: &str, value: Value| {
            let mut one = said(base.clone());
            one.insert(key.into(), value);
            one
        };
        assert!(drawn(&said(base.clone()), &[], "/", &[], &[]).is_err());
        assert!(drawn(&said(json!({})), &w, "/", &[], &[]).is_err());
        for rules in [
            json!("/"),
            json!([["/"]]),
            json!([["/", 1]]),
            json!([["/", "all"]]),
            json!([["relative", "read"]]),
        ] {
            assert!(
                drawn(&with("rules", rules.clone()), &w, "/", &[], &[]).is_err(),
                "{rules}"
            );
        }
        assert!(drawn(&with("tmp", json!("relative")), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("tmp", json!("/a/../b")), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("write", json!(["rel"])), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("write", json!(["~/../x"])), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("listen", json!([0])), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("listen", json!([65536])), &w, "/", &[], &[]).is_err());
        assert!(drawn(&with("online", json!("no")), &w, "/", &[], &[]).is_err());
    }

    #[test]
    fn env_is_looked_past() {
        let line: Vec<OsString> = ["env", "-u", "X", "A=1", "claude", "-p"]
            .iter()
            .map(OsString::from)
            .collect();
        assert_eq!(named(&line), "claude");
        assert_eq!(named(&["git".into()]), "git");
    }

    #[test]
    fn an_install_tree_is_found() {
        let root = std::fs::canonicalize(tempfile::tempdir().unwrap().keep()).unwrap();
        let package = root.join("node_modules/@scope/cli/bin");
        std::fs::create_dir_all(&package).unwrap();
        assert_eq!(
            tree(&package.join("run.js")),
            vec![
                package.join("run.js").to_string_lossy().into_owned(),
                root.join("node_modules/@scope/cli")
                    .to_string_lossy()
                    .into_owned()
            ]
        );
        std::fs::create_dir_all(root.join("prefix/bin")).unwrap();
        std::fs::create_dir_all(root.join("prefix/lib")).unwrap();
        assert_eq!(
            tree(&root.join("prefix/bin/tool"))[1],
            root.join("prefix").to_string_lossy()
        );
        let script = root.join("prefix/bin/tool");
        std::fs::write(&script, "#!/usr/bin/env sh\necho\n").unwrap();
        let found = installed(&script.to_string_lossy(), None);
        assert_eq!(found[0], script.to_string_lossy());
        assert!(found.iter().any(|one| one.ends_with("/sh")), "{found:?}");
    }
}
