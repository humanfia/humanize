//! The Rust client against the Python anchor, `hmz internal anchor serve --stdio`.
//!
//! Needs `uv` and this checkout's Python environment, so it is ignored by default; run it with
//! `cargo test --test unit07_interop -- --ignored`.

use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::Arc;
use std::time::Duration;

use coganchor::client::{Event, Exchange, RemoteClient};
use coganchor::meta;
use coganchor::proto::{Channel, Meta, Op, Stream};
use serde_json::{Value, json};

/// The Python anchor serving `/w` from `real`, and a started client of it.
fn python_anchor(real: &Path, token: Option<&str>) -> (RemoteClient, Child) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut command = Command::new("uv");
    command
        .current_dir(&root)
        .args([
            "run", "--quiet", "python", "-m", "hmz", "internal", "anchor", "serve",
        ])
        .args(["--stdio", "--export"])
        .arg(format!("/w:{}", real.display()))
        .env_remove("HUMANIZE_COGANCHOR")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    if let Some(token) = token {
        command.env("HUMANIZE_TOKEN", token);
    }
    let mut child = command.spawn().expect("uv");
    let channel = Channel::new(
        Box::new(child.stdout.take().unwrap()),
        Box::new(child.stdin.take().unwrap()),
    );
    let client = RemoteClient::new(Arc::new(channel));
    (client, child)
}

/// Everything an exchange said: stdout, stderr, and how it ended.
fn drain(exchange: &Exchange) -> (Vec<u8>, Vec<u8>, Meta) {
    let mut out = Vec::new();
    let mut err = Vec::new();
    loop {
        match exchange
            .events
            .recv_timeout(Duration::from_secs(60))
            .unwrap()
        {
            Event::Chunk(Stream::Stderr, body) => err.extend(body),
            Event::Chunk(_, body) => out.extend(body),
            Event::End(_) => {}
            Event::Done(done) => return (out, err, done.expect("the exchange")),
        }
    }
}

fn exec(argv: &[&str]) -> Meta {
    meta! {
        "argv" => json!(argv),
        "program" => Value::Null,
        "cwd" => "/w",
        "env" => json!({"PATH": "/usr/bin:/bin"}),
        "tty" => false,
        "winsize" => Value::Null,
        "fence" => Value::Null,
    }
}

#[test]
#[ignore = "needs uv and the Python anchor"]
fn speaks_to_the_python_anchor() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("hello.txt"), b"hi there").unwrap();
    let (client, mut child) = python_anchor(dir.path(), Some("tok"));

    let info = client.start(Some("tok")).unwrap();
    assert_eq!(info["version"], 1);
    assert_eq!(info["platform"], coganchor::proto::this_platform());

    let stat = client
        .call(Op::Stat, meta! {"path" => "/w/hello.txt"})
        .unwrap();
    assert_eq!(stat["size"], 8);
    let missing = client
        .call(Op::Stat, meta! {"path" => "/w/nope"})
        .unwrap_err();
    assert_eq!(missing.errno, libc::ENOENT);

    let listed = client.call(Op::Listdir, meta! {"path" => "/w"}).unwrap();
    let names: Vec<&str> = listed["entries"]
        .as_array()
        .unwrap()
        .iter()
        .map(|entry| entry["name"].as_str().unwrap())
        .collect();
    assert_eq!(names, ["hello.txt"]);

    let (data, meta) = client.read_file("/w/hello.txt").unwrap();
    assert_eq!(data, b"hi there");
    assert_eq!(meta["size"], 8);

    let blob: Vec<u8> = (0..300_000u32).map(|n| (n % 251) as u8).collect();
    client.write_file("/w/big.bin", &blob, Some(0o600)).unwrap();
    assert_eq!(std::fs::read(dir.path().join("big.bin")).unwrap(), blob);
    assert_eq!(client.read_file("/w/big.bin").unwrap().0, blob);

    let command = client
        .start_exec(exec(&["sh", "-c", "echo out; echo err >&2; exit 3"]))
        .unwrap();
    let (out, err, done) = drain(&command);
    assert_eq!(
        (out.as_slice(), err.as_slice()),
        (&b"out\n"[..], &b"err\n"[..])
    );
    assert_eq!(done["exit_code"], 3);

    let cat = client.start_exec(exec(&["cat"])).unwrap();
    cat.send(Stream::Stdin, b"round trip").unwrap();
    cat.end(Stream::Stdin).unwrap();
    let (out, _, done) = drain(&cat);
    assert_eq!(out, b"round trip");
    assert_eq!(done["exit_code"], 0);

    let sleeper = client.start_exec(exec(&["sleep", "30"])).unwrap();
    std::thread::sleep(Duration::from_millis(500));
    sleeper.signal(libc::SIGTERM).unwrap();
    let (_, _, done) = drain(&sleeper);
    assert_eq!(done["signal"], libc::SIGTERM);

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let echo = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut said = Vec::new();
        stream.read_to_end(&mut said).unwrap();
        stream.write_all(&said).unwrap();
    });
    let tunnel = client.open_tunnel("127.0.0.1", port).unwrap();
    tunnel.send(Stream::Data, b"echo me").unwrap();
    tunnel.end(Stream::Data).unwrap();
    let (out, _, _) = drain(&tunnel);
    assert_eq!(out, b"echo me");
    echo.join().unwrap();

    client.close();
    let _ = child.wait();
}

#[test]
#[ignore = "needs uv and the Python anchor"]
fn a_wrong_token_is_refused() {
    let dir = tempfile::tempdir().unwrap();
    let (client, mut child) = python_anchor(dir.path(), Some("right"));
    assert_eq!(client.start(Some("wrong")).unwrap_err().errno, libc::EACCES);
    client.close();
    let _ = child.kill();
    let _ = child.wait();
}
