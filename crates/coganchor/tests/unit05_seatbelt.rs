//! Unit 5: the Seatbelt profile and its command line, built on any platform.

use std::ffi::OsString;

use coganchor::fence::Fence;
use coganchor::fence::seatbelt::{SANDBOX_EXEC, command, profile, realpath, rules, security};

fn strings(list: &[&str]) -> Vec<String> {
    list.iter().map(|s| (*s).to_owned()).collect()
}

#[test]
fn profile_text_matches_the_python() {
    let dir = tempfile::tempdir().unwrap();
    let base = realpath(dir.path().to_str().unwrap());
    let real = format!("{base}/real");
    std::fs::create_dir(&real).unwrap();
    let link = format!("{base}/link");
    std::os::unix::fs::symlink(&real, &link).unwrap();

    let (text, params) = rules(
        &strings(&[&link, "/nonexistent//a/./x/..", &format!("{link}/")]),
        &strings(&["/w/one", "/w/one/", "/w/two"]),
        &[],
        &[],
        Some(4321),
    );
    assert_eq!(
        text,
        "(version 1)\n\
         (allow default)\n\
         (deny file-read* file-write* process-exec)\n\
         (allow file-read-metadata)\n\
         (allow file-read-data (literal \"/\"))\n\
         (allow file-read* process-exec (subpath (param \"R0\")) (subpath (param \"R1\")) \
         (subpath (param \"R2\")))\n\
         (allow file-read* file-write* process-exec (subpath (param \"W0\")) \
         (subpath (param \"W1\")))\n\
         (deny file-write-create (require-all (vnode-type SYMLINK) \
         (require-any (literal (param \"W0\")) (literal (param \"W1\")))))\n\
         (deny file-write-unlink (require-all (vnode-type DIRECTORY) \
         (require-any (literal (param \"W0\")) (literal (param \"W1\")))))\n\
         (allow file-read* file-write* (regex #\"^/dev/ttys[0-9]+$\"))\n\
         (deny network*)\n\
         (allow network-outbound (remote tcp \"localhost:4321\"))\n\
         (allow network-inbound (local tcp \"localhost:*\"))\n\
         (allow network* (local unix-socket) (remote unix-socket))\n\
         (deny network-outbound (remote unix-socket (path-literal \
         \"/private/var/run/mDNSResponder\")))"
    );
    let want = vec![
        ("R0".to_owned(), link.clone()),
        ("R1".to_owned(), real.clone()),
        ("R2".to_owned(), "/nonexistent/a".to_owned()),
        ("W0".to_owned(), "/w/one".to_owned()),
        ("W1".to_owned(), "/w/two".to_owned()),
    ];
    assert_eq!(params, want);
}

#[test]
fn online_and_empty_profile() {
    let (text, params) = rules(&[], &[], &[], &[], None);
    assert!(params.is_empty());
    assert_eq!(
        text,
        "(version 1)\n(allow default)\n(deny file-read* file-write* process-exec)\n\
         (allow file-read-metadata)\n(allow file-read-data (literal \"/\"))\n\
         (allow file-read* file-write* (regex #\"^/dev/ttys[0-9]+$\"))"
    );
}

#[test]
fn realpath_keeps_what_is_missing() {
    let dir = tempfile::tempdir().unwrap();
    let base = realpath(dir.path().to_str().unwrap());
    let link = dir.path().join("l");
    std::os::unix::fs::symlink("gone/deeper", &link).unwrap();
    assert_eq!(
        realpath(&format!("{}/missing/../x", dir.path().display())),
        format!("{base}/x")
    );
    assert_eq!(
        realpath(link.join("y").to_str().unwrap()),
        format!("{base}/gone/deeper/y")
    );
    // A loop is kept as the link's own path, the rest resolved on from there.
    std::os::unix::fs::symlink("b", format!("{base}/a")).unwrap();
    std::os::unix::fs::symlink("a", format!("{base}/b")).unwrap();
    assert_eq!(realpath(&format!("{base}/a/z")), format!("{base}/a/z"));
}

#[test]
fn command_line() {
    let fence = Fence {
        read: strings(&["/r"]),
        write: strings(&["/w"]),
        tmp: "/t".into(),
        ..Fence::default()
    };
    let argv: Vec<OsString> = vec!["sh".into(), "-c".into(), "true".into()];
    let line = command(&fence, Some(9), &argv);
    let (text, params) = profile(&fence, Some(9));
    let mut want: Vec<OsString> = vec![SANDBOX_EXEC.into()];
    want.extend(
        params
            .iter()
            .map(|(k, v)| OsString::from(format!("-D{k}={v}"))),
    );
    want.extend(["-p".into(), text.into(), "--".into()]);
    want.extend(argv);
    assert_eq!(line, want);
    let names: Vec<&str> = params.iter().map(|(k, _)| k.as_str()).collect();
    let mut expected = vec!["R0", "W0", "W1"];
    if security().is_some() {
        expected.push("W2");
    }
    assert_eq!(names, expected);
    assert_eq!(params[1].1, "/w");
    assert_eq!(params[2].1, "/t");
}

#[cfg(target_os = "macos")]
#[test]
fn security_is_the_cache_mds() {
    let mds = security().expect("a Mac has a per-user cache");
    assert!(mds.starts_with("/private/var/folders/"), "{mds}");
    assert!(mds.ends_with("/C/mds"), "{mds}");
}

/// Runs `sh -c script` inside `fence` under `sandbox-exec`, returning its status and stderr.
#[cfg(target_os = "macos")]
fn sandboxed(fence: &Fence, port: Option<u16>, script: &str) -> (bool, String) {
    let argv: Vec<OsString> = vec!["/bin/sh".into(), "-c".into(), script.into()];
    let line = command(fence, port, &argv);
    let out = std::process::Command::new(&line[0])
        .args(&line[1..])
        .output()
        .unwrap();
    (
        out.status.success(),
        String::from_utf8_lossy(&out.stderr).into_owned(),
    )
}

#[cfg(target_os = "macos")]
#[test]
fn sandbox_holds_writes_to_the_fence() {
    if !coganchor::fence::seatbelt::available() {
        eprintln!("sandbox-exec cannot run here; skipped");
        return;
    }
    let granted = tempfile::tempdir().unwrap();
    let other = tempfile::tempdir().unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let w = realpath(granted.path().to_str().unwrap());
    let fence = Fence {
        read: strings(&["/"]),
        write: vec![w.clone()],
        tmp: realpath(tmp.path().to_str().unwrap()),
        ..Fence::default()
    };
    let (ok, why) = sandboxed(&fence, None, &format!("touch '{w}/ok'"));
    assert!(ok, "{why}");
    assert!(granted.path().join("ok").exists());
    let no = other.path().join("no");
    let (ok, _) = sandboxed(&fence, None, &format!("touch '{}'", no.display()));
    assert!(!ok);
    assert!(!no.exists());
    // A directory written may not be removed, nor a link made in its place.
    std::fs::remove_file(granted.path().join("ok")).unwrap();
    let (ok, _) = sandboxed(&fence, None, &format!("rmdir '{w}'"));
    assert!(!ok);
    assert!(granted.path().is_dir());
}

#[cfg(target_os = "macos")]
#[test]
fn offline_sandbox_reaches_only_the_proxy() {
    use coganchor::fence::proxy::{PORTS, Proxy, Upstream};
    use std::io::{Read, Write};
    use std::net::TcpListener;

    if !coganchor::fence::seatbelt::available() {
        eprintln!("sandbox-exec cannot run here; skipped");
        return;
    }
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let origin = listener.local_addr().unwrap().port();
    std::thread::spawn(move || {
        for sock in listener.incoming() {
            let Ok(mut sock) = sock else { return };
            let mut buf = [0u8; 4096];
            let _ = sock.read(&mut buf);
            let _ = sock.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nhello\n");
        }
    });
    let allowed = vec![format!("127.0.0.1:{origin}")];
    let proxy = Proxy::start_upstream(&allowed, &PORTS, 256, Upstream::default()).unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let fence = Fence {
        read: strings(&["/"]),
        tmp: realpath(tmp.path().to_str().unwrap()),
        ..Fence::default()
    };
    let url = format!("http://127.0.0.1:{origin}/");
    let curl = "/usr/bin/curl -sS --max-time 10";
    let (ok, _) = sandboxed(
        &fence,
        Some(proxy.port),
        &format!("{curl} --noproxy '*' {url}"),
    );
    assert!(!ok, "a direct connection got out");
    let (ok, why) = sandboxed(
        &fence,
        Some(proxy.port),
        &format!("{curl} --proxy http://127.0.0.1:{} {url}", proxy.port),
    );
    assert!(ok, "{why}");
    proxy.stop();
}

/// The profile's lines with every parameter put back as the path it names (`_said`).
fn said(profile: &str, params: &[(String, String)]) -> Vec<String> {
    let mut named: Vec<&(String, String)> = params.iter().collect();
    named.sort_by_key(|(name, _)| std::cmp::Reverse(name.len()));
    let mut text = profile.to_owned();
    for (name, path) in named {
        text = text.replace(&format!("(param \"{name}\")"), path);
    }
    text.lines().map(str::to_owned).collect()
}

fn at(lines: &[String], line: &str) -> usize {
    lines
        .iter()
        .position(|one| one == line)
        .unwrap_or_else(|| panic!("{line} is not in {lines:#?}"))
}

#[test]
fn carve_outs_are_said_after_the_grants_deepest_last() {
    let (profile, params) = rules(
        &strings(&["/"]),
        &strings(&["/w", "/w/k/g"]),
        &strings(&["/w/k"]),
        &strings(&["/w/d", "/w/k/g/d"]),
        None,
    );
    let lines = said(&profile, &params);
    let granted = at(
        &lines,
        "(allow file-read* file-write* process-exec (subpath /w) (subpath /w/k/g))",
    );
    let order: Vec<usize> = [
        "(deny file-read* file-write* process-exec (subpath /w/d))",
        "(deny file-write* (subpath /w/k))",
        "(allow file-read* file-write* process-exec (subpath /w/k/g))",
        "(deny file-read* file-write* process-exec (subpath /w/k/g/d))",
    ]
    .iter()
    .map(|one| at(&lines, one))
    .collect();
    assert!(granted < order[0] && order[0] < order[1] && order[1] < order[2]);
    assert!(order[2] < order[3]);
    assert_eq!(lines[order[3] + 1], "(allow file-read-metadata)");
}

#[test]
fn a_carve_out_and_every_directory_above_it_are_held_at_their_names() {
    let (profile, params) = rules(
        &[],
        &strings(&["/w"]),
        &[],
        &strings(&["/w/a/secret"]),
        None,
    );
    let lines = said(&profile, &params);
    let held = "(literal /w) (literal /w/a) (literal /w/a/secret)";
    at(
        &lines,
        &format!("(deny file-write-unlink (require-any {held}))"),
    );
    at(
        &lines,
        &format!(
            "(deny file-write-create (require-all (vnode-type SYMLINK) (require-any {held})))"
        ),
    );
}

#[test]
fn a_root_written_again_beneath_a_carve_out_is_held_at_its_name() {
    let (profile, params) = rules(
        &[],
        &strings(&["/", "/h/.cli"]),
        &[],
        &strings(&["/h"]),
        None,
    );
    let lines = said(&profile, &params);
    assert!(
        at(
            &lines,
            "(deny file-read* file-write* process-exec (subpath /h))"
        ) < at(
            &lines,
            "(allow file-read* file-write* process-exec (subpath /h/.cli))"
        )
    );
    at(
        &lines,
        "(deny file-write-unlink (require-all (vnode-type DIRECTORY) (require-any (literal /h/.cli))))",
    );
}

#[test]
fn a_carve_out_is_named_as_given_and_as_resolved() {
    let dir = tempfile::tempdir().unwrap();
    let base = realpath(dir.path().to_str().unwrap());
    let real = format!("{base}/real");
    std::fs::create_dir(&real).unwrap();
    let link = format!("{base}/link");
    std::os::unix::fs::symlink(&real, &link).unwrap();
    let (_, params) = rules(
        &[],
        &strings(&["/"]),
        &[],
        std::slice::from_ref(&link),
        None,
    );
    let values: Vec<&str> = params.iter().map(|(_, path)| path.as_str()).collect();
    assert!(
        values.contains(&link.as_str()) && values.contains(&real.as_str()),
        "{values:?}"
    );
}

#[test]
fn nothing_carved_out_says_nothing_more() {
    let (profile, _) = rules(&strings(&["/r"]), &strings(&["/w"]), &[], &[], None);
    assert!(!profile.contains("(deny file-write* "));
    assert!(!profile.contains("file-write-unlink (require-any"));
}

#[cfg(target_os = "macos")]
#[test]
fn sandbox_holds_what_is_carved_out_of_a_grant() {
    if !coganchor::fence::seatbelt::available() {
        eprintln!("sandbox-exec cannot run here; skipped");
        return;
    }
    let granted = tempfile::tempdir().unwrap();
    let tmp = tempfile::tempdir().unwrap();
    let w = realpath(granted.path().to_str().unwrap());
    std::fs::create_dir_all(format!("{w}/secret")).unwrap();
    std::fs::write(format!("{w}/secret/key"), "key").unwrap();
    std::fs::create_dir_all(format!("{w}/ro")).unwrap();
    let fence = Fence {
        read: strings(&["/"]),
        write: vec![w.clone()],
        keep: vec![format!("{w}/ro")],
        deny: vec![format!("{w}/secret")],
        tmp: realpath(tmp.path().to_str().unwrap()),
        ..Fence::default()
    };
    let (ok, why) = sandboxed(&fence, None, &format!("touch '{w}/ok'"));
    assert!(ok, "{why}");
    assert!(!sandboxed(&fence, None, &format!("cat '{w}/secret/key'")).0);
    assert!(!sandboxed(&fence, None, &format!("touch '{w}/ro/x'")).0);
    assert!(sandboxed(&fence, None, &format!("ls '{w}/ro'")).0);
    assert!(!sandboxed(&fence, None, &format!("mv '{w}/secret' '{w}/moved'")).0);
    assert!(std::path::Path::new(&format!("{w}/secret/key")).exists());
}
