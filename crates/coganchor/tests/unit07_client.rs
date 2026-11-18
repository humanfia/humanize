//! The cog's client, against a fake anchor speaking frames over a socket pair.

use std::os::unix::net::UnixStream;
use std::sync::Arc;
use std::sync::mpsc::Receiver;
use std::thread::JoinHandle;
use std::time::Duration;

use coganchor::client::{Event, Exchange, RemoteClient};
use coganchor::meta;
use coganchor::proto::{Channel, Frame, Kind, Meta, Op, RemoteError, Stream};
use serde_json::{Value, json};

/// A fake anchor: answers each request as `answer` says, from a thread of its own, and hands
/// back every frame it was sent.
fn fake(
    answer: impl Fn(&Channel, &Frame) -> bool + Send + 'static,
) -> (RemoteClient, JoinHandle<Vec<Frame>>) {
    let (ours, theirs) = UnixStream::pair().unwrap();
    let server = Channel::from_unix(theirs).unwrap();
    let serving = std::thread::spawn(move || {
        let mut seen = Vec::new();
        while let Ok(Some(frame)) = server.recv() {
            seen.push(frame.clone());
            if !answer(&server, &frame) {
                server.close();
                break;
            }
        }
        seen
    });
    let client = RemoteClient::with_timeout(
        Arc::new(Channel::from_unix(ours).unwrap()),
        Duration::from_secs(5),
    );
    (client, serving)
}

/// Answers a `HELLO` as protocol 1 does; anything else is left to `rest`.
fn hello_then(
    rest: impl Fn(&Channel, &Frame) -> bool + Send + 'static,
) -> impl Fn(&Channel, &Frame) -> bool + Send + 'static {
    move |server, frame| {
        if frame.op() == Some(Op::Hello) {
            let reply = meta! {"version" => 1, "platform" => "linux"};
            server
                .send(&Frame::reply(frame.id, reply, Vec::new()))
                .unwrap();
            return true;
        }
        rest(server, frame)
    }
}

fn events(exchange: &Exchange) -> Vec<Event> {
    collect(&exchange.events)
}

fn collect(events: &Receiver<Event>) -> Vec<Event> {
    let mut seen = Vec::new();
    loop {
        let event = events.recv_timeout(Duration::from_secs(5)).unwrap();
        let done = matches!(event, Event::Done(_));
        seen.push(event);
        if done {
            return seen;
        }
    }
}

#[test]
fn shakes_hands_with_its_token_or_null() {
    for token in [Some("s3cret"), None] {
        let (client, serving) = fake(hello_then(|_, _| true));
        let info = client.start(token).unwrap();
        assert_eq!(info["platform"], "linux");
        assert_eq!(client.info(), info);
        client.close();
        let seen = serving.join().unwrap();
        let hello = &seen[0];
        assert_eq!(hello.kind, Kind::Req);
        assert_eq!(hello.meta["version"], 1);
        // The key is always there, null where there is no token.
        assert_eq!(
            hello.meta.get("token"),
            Some(&token.map_or(Value::Null, Value::from))
        );
    }
}

#[test]
fn another_version_is_refused() {
    let (client, _serving) = fake(|server, frame| {
        server
            .send(&Frame::reply(frame.id, meta! {"version" => 2}, Vec::new()))
            .unwrap();
        true
    });
    let error = client.start(None).unwrap_err();
    assert_eq!(error.errno, libc::EPROTO);
    assert!(error.strerror.contains("protocol 2"));
}

#[test]
fn calls_return_replies_and_errors_with_rising_ids() {
    let (client, serving) = fake(hello_then(|server, frame| {
        let path = frame.meta["path"].as_str().unwrap_or("");
        let reply = if path == "/w/missing" {
            Frame::error(
                frame.id,
                &RemoteError::errno(libc::ENOENT).with_filename(path),
            )
        } else {
            Frame::reply(frame.id, meta! {"size" => 3}, Vec::new())
        };
        server.send(&reply).unwrap();
        true
    }));
    client.start(None).unwrap();
    assert_eq!(
        client.call(Op::Stat, meta! {"path" => "/w/f"}).unwrap()["size"],
        3
    );
    let error = client
        .call(Op::Stat, meta! {"path" => "/w/missing"})
        .unwrap_err();
    assert_eq!(error.errno, libc::ENOENT);
    assert_eq!(error.filename.as_deref(), Some("/w/missing"));
    client.close();
    let ids: Vec<u64> = serving
        .join()
        .unwrap()
        .iter()
        .map(|frame| frame.id)
        .collect();
    assert_eq!(ids, [1, 2, 3]);
}

#[test]
fn files_cross_in_chunks() {
    let (client, serving) = fake(hello_then(|server, frame| {
        match (frame.kind, frame.op()) {
            (Kind::Req, Some(Op::Read)) => {
                for piece in [&b"abc"[..], b"def", b"g"] {
                    server
                        .send(&Frame::chunk(frame.id, Stream::Data, piece.to_vec()))
                        .unwrap();
                }
                let reply = meta! {"size" => 7, "mode" => 0o100644, "mtime_ns" => 1};
                server
                    .send(&Frame::reply(frame.id, reply, Vec::new()))
                    .unwrap();
            }
            (Kind::End, _) => {
                let reply = meta! {"size" => 300_000};
                server
                    .send(&Frame::reply(frame.id, reply, Vec::new()))
                    .unwrap();
            }
            _ => {}
        }
        true
    }));
    client.start(None).unwrap();
    let (data, meta) = client.read_file("/w/f").unwrap();
    assert_eq!(data, b"abcdefg");
    assert_eq!(meta["size"], 7);
    let blob = vec![7u8; 300_000];
    assert_eq!(
        client.write_file("/w/g", &blob, Some(0o600)).unwrap()["size"],
        300_000
    );
    client.close();
    let seen = serving.join().unwrap();
    let write = seen
        .iter()
        .find(|frame| frame.op() == Some(Op::Write))
        .unwrap();
    assert_eq!(write.meta["path"], "/w/g");
    assert_eq!(write.meta["mode"], 0o600);
    let chunks: Vec<&Frame> = seen
        .iter()
        .filter(|frame| frame.id == write.id && frame.kind == Kind::Chunk)
        .collect();
    assert!(chunks.iter().all(|frame| frame.stream() == Stream::Data));
    assert_eq!(
        chunks.iter().map(|frame| frame.body.len()).sum::<usize>(),
        300_000
    );
    let end = seen.last().unwrap();
    assert_eq!(
        (end.kind, end.id, end.stream()),
        (Kind::End, write.id, Stream::Data)
    );
}

#[test]
fn commands_stream_events_and_take_signals() {
    let (client, serving) = fake(hello_then(|server, frame| {
        match (frame.kind, frame.op()) {
            (Kind::Req, Some(Op::Exec)) => {
                let id = frame.id;
                server
                    .send(&Frame::chunk(id, Stream::Stdout, b"out".to_vec()))
                    .unwrap();
                server
                    .send(&Frame::chunk(id, Stream::Stderr, b"err".to_vec()))
                    .unwrap();
                server.send(&Frame::end(id, Stream::Stdout)).unwrap();
            }
            (Kind::Req, Some(Op::Signal)) => {
                server
                    .send(&Frame::reply(frame.id, Meta::new(), Vec::new()))
                    .unwrap();
            }
            (Kind::Chunk, _) => {
                let echo = Frame::chunk(frame.id, Stream::Stdout, frame.body.clone());
                server.send(&echo).unwrap();
            }
            (Kind::End, _) => {
                let reply = meta! {"exit_code" => 3};
                server
                    .send(&Frame::reply(frame.id, reply, Vec::new()))
                    .unwrap();
            }
            _ => {}
        }
        true
    }));
    client.start(None).unwrap();
    let request = meta! {"argv" => json!(["sh"]), "cwd" => "/w", "env" => json!({})};
    let exchange = client.start_exec(request).unwrap();
    exchange.signal(libc::SIGINT).unwrap();
    exchange.send(Stream::Stdin, b"back").unwrap();
    exchange.end(Stream::Stdin).unwrap();
    let seen = events(&exchange);
    let mut stdout = Vec::new();
    let mut stderr = Vec::new();
    for event in &seen {
        match event {
            Event::Chunk(Stream::Stdout, body) => stdout.extend_from_slice(body),
            Event::Chunk(Stream::Stderr, body) => stderr.extend_from_slice(body),
            _ => {}
        }
    }
    assert_eq!(stdout, b"outback");
    assert_eq!(stderr, b"err");
    assert!(
        seen.iter()
            .any(|event| matches!(event, Event::End(Stream::Stdout)))
    );
    match seen.last().unwrap() {
        Event::Done(Ok(meta)) => assert_eq!(meta["exit_code"], 3),
        other => panic!("ended with {other:?}"),
    }
    client.close();
    let frames = serving.join().unwrap();
    let signal = frames
        .iter()
        .find(|frame| frame.op() == Some(Op::Signal))
        .unwrap();
    assert_eq!(signal.meta["target"], exchange.id);
    assert_eq!(signal.meta["sig"], libc::SIGINT);
}

#[test]
fn tunnels_carry_data() {
    let (client, _serving) = fake(hello_then(|server, frame| {
        match frame.kind {
            Kind::Req => assert_eq!(
                (frame.meta["host"].as_str(), frame.meta["port"].as_u64()),
                (Some("127.0.0.1"), Some(8080))
            ),
            Kind::Chunk => {
                let echo = Frame::chunk(frame.id, Stream::Data, frame.body.clone());
                server.send(&echo).unwrap();
            }
            Kind::End => {
                server.send(&Frame::end(frame.id, Stream::Data)).unwrap();
                server
                    .send(&Frame::reply(frame.id, Meta::new(), Vec::new()))
                    .unwrap();
            }
            _ => {}
        }
        true
    }));
    client.start(None).unwrap();
    let tunnel = client.open_tunnel("127.0.0.1", 8080).unwrap();
    tunnel.send(Stream::Data, b"ping").unwrap();
    tunnel.end(Stream::Data).unwrap();
    let seen = events(&tunnel);
    assert!(matches!(&seen[0], Event::Chunk(Stream::Data, body) if body == b"ping"));
    assert!(matches!(seen[1], Event::End(Stream::Data)));
    assert!(matches!(seen[2], Event::Done(Ok(_))));
}

#[test]
fn a_lost_connection_fails_everything_in_flight() {
    // The fake goes away at the first request after the handshake.
    let (client, _serving) = fake(hello_then(|_, frame| frame.op() != Some(Op::Rmdir)));
    client.start(None).unwrap();
    let exchange = client
        .start_exec(meta! {"argv" => json!(["sleep"])})
        .unwrap();
    let error = client
        .call(Op::Rmdir, meta! {"path" => "/w/d"})
        .unwrap_err();
    assert_eq!(error.errno, libc::EPIPE);
    match events(&exchange).pop().unwrap() {
        Event::Done(Err(error)) => assert_eq!(error.errno, libc::EPIPE),
        other => panic!("ended with {other:?}"),
    }
    // And anything after.
    assert_eq!(
        client
            .call(Op::Stat, meta! {"path" => "/w"})
            .unwrap_err()
            .errno,
        libc::EPIPE
    );
}

#[test]
fn closing_fails_what_is_open() {
    let (client, _serving) = fake(hello_then(|_, _| true));
    client.start(None).unwrap();
    let exchange = client
        .start_exec(meta! {"argv" => json!(["sleep"])})
        .unwrap();
    client.close();
    assert!(matches!(events(&exchange).pop(), Some(Event::Done(Err(_)))));
    assert!(client.start_exec(Meta::new()).is_err());
}

#[test]
fn a_silent_target_times_out() {
    let (ours, _theirs) = UnixStream::pair().unwrap();
    let client = RemoteClient::with_timeout(
        Arc::new(Channel::from_unix(ours).unwrap()),
        Duration::from_millis(100),
    );
    assert_eq!(client.start(None).unwrap_err().errno, libc::ETIMEDOUT);
}

/// A cog holding `ours` and a real anchor holding `theirs`, over TLS on loopback as a
/// `tcp://` target is reached; `serve` answers in place of the anchor where given.
fn sealed(
    ours: Option<&str>,
    theirs: Option<&str>,
    serve: Option<fn(Channel)>,
) -> (RemoteClient, JoinHandle<()>) {
    use coganchor::anchor::ExportTable;
    use coganchor::anchor::server::Server;
    use coganchor::tls;

    let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let theirs = theirs.map(|key| key.as_bytes().to_vec());
    let serving = std::thread::spawn(move || {
        let (tcp, _) = listener.accept().unwrap();
        let identity = tls::Identity::fresh().unwrap();
        let channel = identity.answer(tcp, theirs, String::new()).unwrap();
        match serve {
            Some(serve) => serve(channel),
            None => {
                let exports = ExportTable::parse(&["/w:/".to_owned()]).unwrap();
                Server::new(Arc::new(channel), Arc::new(exports), None).run();
            }
        }
    });
    let tcp = std::net::TcpStream::connect(("127.0.0.1", port)).unwrap();
    let key = ours.map(|key| key.as_bytes().to_vec());
    let channel = tls::dial(tcp, key, format!("tcp://127.0.0.1:{port}")).unwrap();
    (
        RemoteClient::with_timeout(Arc::new(channel), Duration::from_secs(5)),
        serving,
    )
}

#[test]
fn over_tls_the_token_is_proved_both_ways() {
    let (client, serving) = sealed(Some("s3cret"), Some("s3cret"), None);
    let info = client.start(Some("ignored")).unwrap();
    assert!(info["proof"].is_string());
    assert_eq!(
        client.call(Op::Stat, meta! {"path" => "/w"}).unwrap()["kind"],
        "dir"
    );
    client.close();
    serving.join().unwrap();

    // Nobody holding a key, as a loopback listener without a token: null both ways.
    let (client, serving) = sealed(None, None, None);
    assert_eq!(client.start(None).unwrap()["proof"], Value::Null);
    client.close();
    serving.join().unwrap();
}

#[test]
fn over_tls_a_wrong_or_missing_token_is_refused() {
    for ours in [Some("wrong"), None] {
        let (client, serving) = sealed(ours, Some("s3cret"), None);
        let error = client.start(Some("s3cret")).unwrap_err();
        assert_eq!(
            (error.errno, error.strerror.as_str()),
            (libc::EACCES, "invalid token")
        );
        // And the connection is closed, so no other proof can be tried on it.
        let closed = client.call(Op::Stat, meta! {"path" => "/w"}).unwrap_err();
        assert_ne!(closed.strerror, "not authenticated");
        serving.join().unwrap();
        client.close();
    }
}

#[test]
fn over_tls_an_anchor_that_cannot_prove_the_token_is_refused() {
    // One that answers without a proof, and one without the token at all.
    fn impostor(channel: Channel) {
        while let Ok(Some(frame)) = channel.recv() {
            let reply = meta! {"version" => 1, "proof" => "00".repeat(32)};
            let _ = channel.send(&Frame::reply(frame.id, reply, Vec::new()));
        }
    }
    for (theirs, serve) in [
        (None, Some(impostor as fn(Channel))),
        (Some("other"), Some(impostor as fn(Channel))),
        (None, None),
    ] {
        let (client, serving) = sealed(Some("s3cret"), theirs, serve);
        let error = client.start(None).unwrap_err();
        assert_eq!(error.errno, libc::ECONNREFUSED);
        assert!(
            error
                .strerror
                .starts_with("the serving half at tcp://127.0.0.1:"),
            "{error}"
        );
        assert!(error.strerror.ends_with(" did not prove the token"));
        client.close();
        serving.join().unwrap();
    }
}
