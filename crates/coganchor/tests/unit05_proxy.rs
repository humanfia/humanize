//! Unit 5: the fence's proxy, against HTTP servers and proxies on loopback.

use std::io::{Read, Write};
use std::net::{Shutdown, TcpListener, TcpStream};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use coganchor::fence::proxy::{PORTS, Proxy, Upstream, permits};

fn hosts(list: &[&str]) -> Vec<String> {
    list.iter().map(|s| (*s).to_owned()).collect()
}

fn start(allowed: &[&str], upstream: Upstream) -> Proxy {
    Proxy::start_upstream(&hosts(allowed), &PORTS, 256, upstream).unwrap()
}

fn dial(proxy: &Proxy) -> TcpStream {
    let sock = TcpStream::connect(("127.0.0.1", proxy.port)).unwrap();
    sock.set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap();
    sock
}

fn read_all(sock: &mut TcpStream) -> String {
    let mut out = Vec::new();
    let _ = sock.read_to_end(&mut out);
    String::from_utf8_lossy(&out).into_owned()
}

fn read_head(sock: &mut TcpStream) -> String {
    let mut out = Vec::new();
    let mut byte = [0u8; 1];
    while !out.ends_with(b"\r\n\r\n") {
        if sock.read(&mut byte).unwrap() == 0 {
            break;
        }
        out.push(byte[0]);
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// A server echoing every byte back until its client half-closes.
fn echo() -> u16 {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    thread::spawn(move || {
        for sock in listener.incoming() {
            let Ok(mut sock) = sock else { return };
            thread::spawn(move || {
                let mut buf = [0u8; 4096];
                while let Ok(n) = sock.read(&mut buf) {
                    if n == 0 || sock.write_all(&buf[..n]).is_err() {
                        break;
                    }
                }
                let _ = sock.shutdown(Shutdown::Write);
            });
        }
    });
    port
}

/// An HTTP server answering each request with the head it was sent; the head goes to `heads`.
fn origin() -> (u16, mpsc::Receiver<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let (send, heads) = mpsc::channel();
    thread::spawn(move || {
        for sock in listener.incoming() {
            let Ok(mut sock) = sock else { return };
            let head = read_head(&mut sock);
            let body = format!("saw {}", head.len());
            let _ = write!(
                sock,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n{body}",
                body.len()
            );
            let _ = send.send(head);
        }
    });
    (port, heads)
}

/// A proxy that answers a `CONNECT` with `status` and, on success, echoes; each head it was
/// sent goes to `heads`.
fn fake_upstream(status: &'static str) -> (u16, mpsc::Receiver<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let (send, heads) = mpsc::channel();
    thread::spawn(move || {
        for sock in listener.incoming() {
            let Ok(mut sock) = sock else { return };
            let head = read_head(&mut sock);
            let _ = send.send(head);
            let _ = write!(sock, "HTTP/1.1 {status}\r\n\r\n");
            if !status.starts_with('2') {
                continue;
            }
            let mut buf = [0u8; 4096];
            while let Ok(n) = sock.read(&mut buf) {
                if n == 0 || sock.write_all(&buf[..n]).is_err() {
                    break;
                }
            }
            let _ = sock.shutdown(Shutdown::Write);
        }
    });
    (port, heads)
}

fn refused(host: &str, port: u16) -> String {
    let body = format!("hmz: {host}:{port} is not a host this run may reach\n");
    format!(
        "HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain; charset=utf-8\r\n\
         Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

#[test]
fn connect_allowed_tunnels() {
    let target = echo();
    let proxy = start(&[&format!("127.0.0.1:{target}")], Upstream::default());
    let mut sock = dial(&proxy);
    write!(
        sock,
        "CONNECT 127.0.0.1:{target} HTTP/1.1\r\nHost: x\r\n\r\nearly"
    )
    .unwrap();
    assert_eq!(
        read_head(&mut sock),
        "HTTP/1.1 200 Connection Established\r\n\r\n"
    );
    sock.write_all(b" and late").unwrap();
    sock.shutdown(Shutdown::Write).unwrap();
    assert_eq!(read_all(&mut sock), "early and late");
    proxy.stop();
}

#[test]
fn connect_by_name_resolves_here() {
    let target = echo();
    let proxy = start(&[&format!("LOCALHOST.:{target}")], Upstream::default());
    let mut sock = dial(&proxy);
    write!(sock, "CONNECT localhost:{target} HTTP/1.1\r\n\r\n").unwrap();
    assert_eq!(
        read_head(&mut sock),
        "HTTP/1.1 200 Connection Established\r\n\r\n"
    );
}

#[test]
fn connect_refused_names_the_host() {
    let proxy = start(&["api.example.com"], Upstream::default());
    let mut sock = dial(&proxy);
    sock.write_all(b"CONNECT evil.example:443 HTTP/1.1\r\n\r\n")
        .unwrap();
    assert_eq!(read_all(&mut sock), refused("evil.example", 443));

    // A listed host on a port it was not listed for.
    let mut sock = dial(&proxy);
    sock.write_all(b"CONNECT api.example.com:22 HTTP/1.1\r\n\r\n")
        .unwrap();
    assert_eq!(read_all(&mut sock), refused("api.example.com", 22));
}

#[test]
fn absolute_get_is_forwarded_in_origin_form() {
    let (port, heads) = origin();
    let proxy = start(&[&format!("127.0.0.1:{port}")], Upstream::default());
    let mut sock = dial(&proxy);
    write!(
        sock,
        "get http://127.0.0.1:{port}/a/b?q=1#frag HTTP/1.1\r\nHost: 127.0.0.1\r\n\
         Proxy-Connection: keep-alive\r\nConnection: keep-alive\r\nKeep-Alive: 5\r\n\
         Proxy-Authorization: Basic eA==\r\nX-Kept: yes\r\n\r\n"
    )
    .unwrap();
    let answer = read_all(&mut sock);
    assert!(answer.starts_with("HTTP/1.1 200 OK\r\n"), "{answer}");
    let head = heads.recv_timeout(Duration::from_secs(5)).unwrap();
    assert_eq!(
        head,
        "GET /a/b?q=1 HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Kept: yes\r\nConnection: close\r\n\r\n"
    );
}

#[test]
fn absolute_get_with_no_path_asks_for_root() {
    let (port, heads) = origin();
    let proxy = start(&[&format!("127.0.0.1:{port}")], Upstream::default());
    let mut sock = dial(&proxy);
    write!(sock, "GET http://127.0.0.1:{port} HTTP/1.0\r\n\r\n").unwrap();
    read_all(&mut sock);
    let head = heads.recv_timeout(Duration::from_secs(5)).unwrap();
    assert_eq!(head, "GET / HTTP/1.0\r\nConnection: close\r\n\r\n");
}

#[test]
fn absolute_get_on_port_zero_is_port_80() {
    // `split.port or 80`: checked, and refused, as port 80.
    let proxy = start(&["api.example.com:8080"], Upstream::default());
    let mut sock = dial(&proxy);
    sock.write_all(b"GET http://api.example.com:0/ HTTP/1.1\r\n\r\n")
        .unwrap();
    assert_eq!(read_all(&mut sock), refused("api.example.com", 80));
}

#[test]
fn absolute_get_refused() {
    let proxy = start(&["api.example.com"], Upstream::default());
    let mut sock = dial(&proxy);
    sock.write_all(b"GET http://other.example/ HTTP/1.1\r\n\r\n")
        .unwrap();
    assert_eq!(read_all(&mut sock), refused("other.example", 80));
}

#[test]
fn bad_requests_get_400() {
    let proxy = start(&["api.example.com"], Upstream::default());
    for (said, body) in [
        (
            "GET /path HTTP/1.1",
            "only absolute http:// requests and CONNECT are proxied\n",
        ),
        (
            "GET https://api.example.com/ HTTP/1.1",
            "only absolute http:// requests and CONNECT are proxied\n",
        ),
        (
            "CONNECT api.example.com HTTP/1.1",
            "CONNECT needs host:port\n",
        ),
        ("NONSENSE", "malformed request line\n"),
        ("GET http://x/ FTP/1", "malformed request line\n"),
        (
            "CONNECT [::1]:99999 HTTP/1.1",
            "Port out of range 0-65535\n",
        ),
        (
            "CONNECT a:b HTTP/1.1",
            "Port could not be cast to integer value as 'b'\n",
        ),
        (
            "CONNECT [api.example.com]:443 HTTP/1.1",
            "'api.example.com' does not appear to be an IPv4 or IPv6 address\n",
        ),
        (
            "CONNECT [1.2.3.4]:443 HTTP/1.1",
            "An IPv4 address cannot be in brackets\n",
        ),
        ("GET http://[x/ HTTP/1.1", "Invalid IPv6 URL\n"),
    ] {
        let mut sock = dial(&proxy);
        write!(sock, "{said}\r\n\r\n").unwrap();
        let answer = read_all(&mut sock);
        assert!(
            answer.starts_with("HTTP/1.1 400 Bad Request\r\n"),
            "{said}: {answer}"
        );
        assert!(
            answer.ends_with(&format!("\r\n\r\n{body}")),
            "{said}: {answer}"
        );
    }
}

#[test]
fn unreachable_host_gets_502() {
    let closed = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = closed.local_addr().unwrap().port();
    drop(closed);
    let proxy = start(&[&format!("127.0.0.1:{port}")], Upstream::default());
    let mut sock = dial(&proxy);
    write!(sock, "CONNECT 127.0.0.1:{port} HTTP/1.1\r\n\r\n").unwrap();
    let answer = read_all(&mut sock);
    assert!(
        answer.starts_with("HTTP/1.1 502 Bad Gateway\r\n"),
        "{answer}"
    );
    assert!(
        answer.contains(&format!("\r\n\r\nhmz: could not reach 127.0.0.1:{port}: ")),
        "{answer}"
    );
}

#[test]
fn chains_through_the_upstream_proxy() {
    let (up, heads) = fake_upstream("200 Connection established");
    let upstream = Upstream {
        https: Some(format!("http://us%65r:p%40ss@127.0.0.1:{up}")),
        ..Upstream::default()
    };
    // Resolved by the upstream, not here: `.invalid` never resolves.
    let proxy = start(&["api.example.invalid"], upstream);
    let mut sock = dial(&proxy);
    sock.write_all(b"CONNECT API.example.invalid:443 HTTP/1.1\r\n\r\nhello")
        .unwrap();
    assert_eq!(
        read_head(&mut sock),
        "HTTP/1.1 200 Connection Established\r\n\r\n"
    );
    sock.shutdown(Shutdown::Write).unwrap();
    assert_eq!(read_all(&mut sock), "hello");
    assert_eq!(
        heads.recv_timeout(Duration::from_secs(5)).unwrap(),
        "CONNECT api.example.invalid:443 HTTP/1.1\r\nHost: api.example.invalid:443\r\n\
         Proxy-Authorization: Basic dXNlcjpwQHNz\r\n\r\n"
    );
}

#[test]
fn plain_http_is_tunnelled_through_the_upstream_too() {
    let (up, heads) = fake_upstream("200 OK");
    let upstream = Upstream {
        all: Some(format!("127.0.0.1:{up}")),
        ..Upstream::default()
    };
    let proxy = start(&["site.invalid"], upstream);
    let mut sock = dial(&proxy);
    sock.write_all(b"GET http://site.invalid/x HTTP/1.1\r\nHost: site.invalid\r\n\r\n")
        .unwrap();
    sock.shutdown(Shutdown::Write).unwrap();
    // The fake upstream echoes what came through the tunnel: the request in origin form.
    assert_eq!(
        read_all(&mut sock),
        "GET /x HTTP/1.1\r\nHost: site.invalid\r\nConnection: close\r\n\r\n"
    );
    assert_eq!(
        heads.recv_timeout(Duration::from_secs(5)).unwrap(),
        "CONNECT site.invalid:80 HTTP/1.1\r\nHost: site.invalid:80\r\n\r\n"
    );
}

#[test]
fn upstream_refusal_gets_502() {
    let (up, _heads) = fake_upstream("407 Proxy Authentication Required");
    let upstream = Upstream {
        https: Some(format!("http://127.0.0.1:{up}")),
        ..Upstream::default()
    };
    let proxy = start(&["api.example.invalid"], upstream);
    let mut sock = dial(&proxy);
    sock.write_all(b"CONNECT api.example.invalid:443 HTTP/1.1\r\n\r\n")
        .unwrap();
    let answer = read_all(&mut sock);
    let body = "hmz: the proxy upstream refused api.example.invalid:443: \
                HTTP/1.1 407 Proxy Authentication Required\n";
    assert!(
        answer.starts_with("HTTP/1.1 502 Bad Gateway\r\n"),
        "{answer}"
    );
    assert!(answer.ends_with(&format!("\r\n\r\n{body}")), "{answer}");
}

#[test]
fn no_proxy_goes_direct() {
    let target = echo();
    let upstream = Upstream {
        https: Some("http://127.0.0.1:1".into()),
        no: Some(" other.example , .0.0.1".into()),
        ..Upstream::default()
    };
    let proxy = start(&[&format!("127.0.0.1:{target}")], upstream);
    let mut sock = dial(&proxy);
    write!(sock, "CONNECT 127.0.0.1:{target} HTTP/1.1\r\n\r\n").unwrap();
    assert_eq!(
        read_head(&mut sock),
        "HTTP/1.1 200 Connection Established\r\n\r\n"
    );
}

#[test]
fn turns_away_past_the_limit_and_stop_cuts_what_it_holds() {
    let proxy = Proxy::start_upstream(&hosts(&["x"]), &PORTS, 1, Upstream::default()).unwrap();
    let mut first = dial(&proxy);
    first.write_all(b"CONNECT x").unwrap();
    thread::sleep(Duration::from_millis(300));
    let mut second = dial(&proxy);
    second
        .write_all(b"CONNECT x:443 HTTP/1.1\r\n\r\n")
        .unwrap_or(());
    assert_eq!(read_all(&mut second), "");
    proxy.stop();
    assert_eq!(read_all(&mut first), "");
}

#[test]
fn host_rules() {
    let allowed = hosts(&[
        "api.example.com",
        "*.googleapis.com",
        "gateway.internal:8443",
        "10.0.0.1",
        "[::1]:9000",
        "2001:db8::1",
    ]);
    let yes = |host: &str, port: u16| Proxy::permits(&allowed, host, port);
    assert!(yes("api.example.com", 443));
    assert!(yes("API.Example.com.", 80));
    assert!(!yes("api.example.com", 8080));
    assert!(!yes("sub.api.example.com", 443));
    assert!(yes("oauth2.googleapis.com", 443));
    assert!(yes("a.b.googleapis.com", 443));
    assert!(!yes("googleapis.com", 443));
    assert!(!yes("evilgoogleapis.com", 443));
    assert!(yes("gateway.internal", 8443));
    assert!(!yes("gateway.internal", 443));
    assert!(yes("10.0.0.1", 443));
    assert!(!yes("10.0.0.2", 443));
    assert!(yes("[::1]", 9000));
    assert!(yes("::1", 9000));
    assert!(!yes("::1", 443));
    assert!(yes("[2001:db8::1]", 443));
    assert!(!yes("", 443));
    // Only `*.` is a wildcard; any other entry is a name, matched as one.
    assert!(permits(&hosts(&["*foo"]), "*foo", 443, &PORTS));
    assert!(!permits(&hosts(&["*foo"]), "afoo", 443, &PORTS));
    // An address matches no name, even one a wildcard would.
    assert!(!permits(&hosts(&["*.0.0.1"]), "127.0.0.1", 443, &PORTS));
    assert!(permits(&hosts(&["a.b"]), "a.b", 22, &[22]));
}

#[test]
fn reads_the_environment_as_urllib_does() {
    let vars = |list: &[(&str, &str)]| {
        Upstream::from_vars(
            list.iter()
                .map(|(n, v)| ((*n).to_owned(), (*v).to_owned()))
                .collect::<Vec<_>>(),
        )
    };
    let got = vars(&[
        ("HTTPS_PROXY", "http://upper:1"),
        ("https_proxy", "http://lower:2"),
        ("ALL_PROXY", "all:3"),
        ("NO_PROXY", "x"),
    ]);
    assert_eq!(got.https.as_deref(), Some("http://lower:2"));
    assert_eq!(got.all.as_deref(), Some("all:3"));
    assert_eq!(got.no.as_deref(), Some("x"));
    let got = vars(&[("HTTP_PROXY", "h:1"), ("REQUEST_METHOD", "GET")]);
    assert_eq!(got.http, None);
    let got = vars(&[("HTTPS_PROXY", "h:1"), ("https_proxy", "")]);
    assert_eq!(got.https, None);
}
