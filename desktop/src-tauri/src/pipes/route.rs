//! Routes, as the page names a carrier to a daemon: the grammar of Section 3.3 of [WIRE], read
//! into what opens each.

/// An ssh route's host and what `ssh` is told to reach it with, percent-decoded.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Ssh {
    pub user: Option<String>,
    pub host: String,
    pub port: Option<u16>,
    pub identity: Option<String>,
    pub jump: Option<String>,
    /// Each `<Keyword>=<value>`, in the order given.
    pub options: Vec<String>,
}

/// One route, read.
#[derive(Clone, Debug, PartialEq)]
pub enum Route {
    Unix(Option<String>),
    Local,
    Ssh(Ssh),
    Wsl(Option<String>),
    /// The host, an IPv6 one without its brackets, and the port.
    Tcp(String, u16),
    /// The WebSocket's URL, as written.
    Ws(String),
    Easytier(String),
    /// The relay's WebSocket URL.
    Relay(String),
    Webrtc(String),
}

impl Route {
    /// Reads a route, or says that it is none.
    pub fn parse(route: &str) -> Result<Route, String> {
        read(route).ok_or_else(|| format!("{route} is not a route."))
    }

    /// Whether reaching its end already proves the client is the daemon's user (Section 3.5
    /// of [WIRE]).
    pub fn trusted(&self) -> bool {
        matches!(
            self,
            Route::Unix(_) | Route::Local | Route::Ssh(_) | Route::Wsl(_)
        )
    }

    /// Whether the app opens it here (Section 3.12.2 of [DESKTOP]): `stdio:local` on macOS,
    /// `stdio:wsl` on Windows, and the rest but `unix` and `webrtc`, which the web view opens
    /// itself, on both -- a `stdio:ssh` one only where `ssh` reads its destination as one
    /// destination (Section 3.3.5 of [WIRE]).
    pub fn offered(&self) -> bool {
        match self {
            Route::Local => cfg!(not(windows)),
            Route::Wsl(_) => cfg!(windows),
            Route::Unix(_) | Route::Webrtc(_) => false,
            Route::Ssh(ssh) => {
                let first = ssh.user.as_ref().unwrap_or(&ssh.host);
                let said = |part: &str| !part.contains([' ', '\t', '\r', '\n', '\0']);
                !first.starts_with('-') && said(first) && said(&ssh.host)
            }
            _ => true,
        }
    }
}

fn read(route: &str) -> Option<Route> {
    if route == "stdio:local" {
        return Some(Route::Local);
    }
    if let Some(path) = route.strip_prefix("unix:") {
        let ok =
            path.is_empty() || path.starts_with('/') && chars(path, |c| unreserved(c) || c == b'/');
        return ok.then(|| Route::Unix((!path.is_empty()).then(|| path.to_owned())));
    }
    if let Some(rest) = route.strip_prefix("stdio:ssh://") {
        return ssh(rest).map(Route::Ssh);
    }
    if let Some(rest) = route.strip_prefix("stdio:wsl") {
        return match rest.strip_prefix(':') {
            None if rest.is_empty() => Some(Route::Wsl(None)),
            Some(distro) if !distro.is_empty() && chars(distro, unreserved) => {
                Some(Route::Wsl(Some(decoded(distro)?)))
            }
            _ => None,
        };
    }
    if let Some(rest) = route.strip_prefix("tcp://") {
        let (host, port) = authority(rest)?;
        return Some(Route::Tcp(host, port?));
    }
    if let Some(name) = route.strip_prefix("easytier:") {
        return self::name(name).then(|| Route::Easytier(name.to_owned()));
    }
    if let Some(url) = route.strip_prefix("relay:") {
        return ws(url).then(|| Route::Relay(url.to_owned()));
    }
    if let Some(url) = route.strip_prefix("webrtc:") {
        return ws(url).then(|| Route::Webrtc(url.to_owned()));
    }
    ws(route).then(|| Route::Ws(route.to_owned()))
}

/// `name` of the grammar: a letter or digit, then letters, digits, `.`, `_` and `-`.
pub fn name(name: &str) -> bool {
    name.starts_with(|c: char| c.is_ascii_alphanumeric())
        && name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
}

/// `ws-url`: `ws://` or `wss://`, a host, an optional port and `path-abempty`.
fn ws(url: &str) -> bool {
    let Some(rest) = url
        .strip_prefix("ws://")
        .or_else(|| url.strip_prefix("wss://"))
    else {
        return false;
    };
    let end = rest.find('/').unwrap_or(rest.len());
    let (hostport, path) = rest.split_at(end);
    authority(hostport).is_some() && chars(path, |c| pchar(c) || c == b'/')
}

fn ssh(rest: &str) -> Option<Ssh> {
    let (authority, query) = match rest.split_once('?') {
        Some((authority, query)) => (authority, Some(query)),
        None => (rest, None),
    };
    let (user, hostport) = match authority.rsplit_once('@') {
        Some((user, hostport)) => {
            let ok = chars(user, |c| unreserved(c) || sub_delim(c) || c == b':');
            (Some(decoded(user).filter(|_| ok)?), hostport)
        }
        None => (None, authority),
    };
    let (host, port) = self::authority(hostport)?;
    let mut ssh = Ssh {
        user,
        host,
        port,
        ..Ssh::default()
    };
    for param in query.map(|query| query.split('&')).into_iter().flatten() {
        let (key, value) = param.split_once('=')?;
        if value.is_empty() || !chars(value, |c| unreserved(c) || c == b'=') {
            return None;
        }
        let value = decoded(value)?;
        match key {
            "identity" => ssh.identity = Some(value),
            "jump" => ssh.jump = Some(value),
            "option" => ssh.options.push(value),
            _ => return None,
        }
    }
    Some(ssh)
}

/// `host [":" port]`: the host, an IPv6 one without its brackets, and the port where one is
/// given.
fn authority(hostport: &str) -> Option<(String, Option<u16>)> {
    let (host, port) = if let Some(literal) = hostport.strip_prefix('[') {
        let (inside, after) = literal.split_once(']')?;
        if inside.is_empty() || !chars(inside, |c| unreserved(c) || sub_delim(c) || c == b':') {
            return None;
        }
        let port = match after {
            "" => None,
            _ => Some(after.strip_prefix(':')?),
        };
        (inside, port)
    } else {
        let (host, port) = match hostport.rsplit_once(':') {
            Some((host, port)) => (host, Some(port)),
            None => (hostport, None),
        };
        if host.is_empty() || !chars(host, |c| unreserved(c) || sub_delim(c)) {
            return None;
        }
        (host, port)
    };
    let port = match port {
        Some(port) if port.bytes().all(|c| c.is_ascii_digit()) => {
            Some(port.parse().ok().filter(|&port| port != 0)?)
        }
        Some(_) => return None,
        None => None,
    };
    Some((decoded(host)?, port))
}

/// Whether every byte of `text` is allowed, a `%` only where two hex digits follow it.
fn chars(text: &str, allowed: impl Fn(u8) -> bool) -> bool {
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            if !bytes
                .get(i + 1..i + 3)
                .is_some_and(|hex| hex.iter().all(u8::is_ascii_hexdigit))
            {
                return false;
            }
            i += 3;
        } else if allowed(bytes[i]) {
            i += 1;
        } else {
            return false;
        }
    }
    true
}

/// Percent-decoded, where it is UTF-8 then.
fn decoded(text: &str) -> Option<String> {
    let mut out = Vec::with_capacity(text.len());
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' {
            let hex = std::str::from_utf8(bytes.get(i + 1..i + 3)?).ok()?;
            out.push(u8::from_str_radix(hex, 16).ok()?);
            i += 3;
        } else {
            out.push(bytes[i]);
            i += 1;
        }
    }
    String::from_utf8(out).ok()
}

fn unreserved(c: u8) -> bool {
    c.is_ascii_alphanumeric() || b"-._~".contains(&c)
}

fn sub_delim(c: u8) -> bool {
    b"!$&'()*+,;=".contains(&c)
}

fn pchar(c: u8) -> bool {
    unreserved(c) || sub_delim(c) || c == b':' || c == b'@'
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(route: &str) -> Route {
        Route::parse(route).unwrap()
    }

    #[test]
    fn reads_every_kind_of_route() {
        assert_eq!(ok("unix:"), Route::Unix(None));
        assert_eq!(
            ok("unix:/tmp/d.sock"),
            Route::Unix(Some("/tmp/d.sock".into()))
        );
        assert_eq!(ok("stdio:local"), Route::Local);
        assert_eq!(ok("stdio:wsl"), Route::Wsl(None));
        assert_eq!(
            ok("stdio:wsl:Ubuntu-24.04"),
            Route::Wsl(Some("Ubuntu-24.04".into()))
        );
        assert_eq!(
            ok("tcp://10.0.0.2:4242"),
            Route::Tcp("10.0.0.2".into(), 4242)
        );
        assert_eq!(ok("tcp://[::1]:4242"), Route::Tcp("::1".into(), 4242));
        assert_eq!(ok("tcp://box.lan:1"), Route::Tcp("box.lan".into(), 1));
        assert_eq!(ok("ws://h:8/a/b"), Route::Ws("ws://h:8/a/b".into()));
        assert_eq!(
            ok("wss://relay.example"),
            Route::Ws("wss://relay.example".into())
        );
        assert_eq!(ok("easytier:home-1"), Route::Easytier("home-1".into()));
        assert_eq!(
            ok("relay:wss://relay.example/r"),
            Route::Relay("wss://relay.example/r".into())
        );
        assert_eq!(ok("webrtc:ws://r:1"), Route::Webrtc("ws://r:1".into()));
    }

    #[test]
    fn reads_an_ssh_route_decoded_and_in_order() {
        assert_eq!(
            ok("stdio:ssh://me@box"),
            Route::Ssh(Ssh {
                user: Some("me".into()),
                host: "box".into(),
                ..Ssh::default()
            })
        );
        assert_eq!(
            ok(
                "stdio:ssh://a%40b@[fe80::1]:2222?identity=~%2F.ssh%2Fid&jump=gw&option=ProxyCommand%3Dnc%20%25h%20%25p&option=Compression=yes"
            ),
            Route::Ssh(Ssh {
                user: Some("a@b".into()),
                host: "fe80::1".into(),
                port: Some(2222),
                identity: Some("~/.ssh/id".into()),
                jump: Some("gw".into()),
                options: vec!["ProxyCommand=nc %h %p".into(), "Compression=yes".into()],
            })
        );
    }

    #[test]
    fn refuses_what_is_not_a_route() {
        for bad in [
            "",
            "stdio:",
            "stdio:local:x",
            "stdio:wsl:",
            "stdio:wsl:a b",
            "stdio:ssh://",
            "stdio:ssh://h?user=x",
            "stdio:ssh://h?identity=",
            "stdio:ssh://h/path",
            "stdio:ssh://h:22x",
            "tcp://h",
            "tcp://:1",
            "tcp://h:99999",
            "tcp://h:0",
            "ws://h:0/x",
            "relay:wss://h:0",
            "stdio:ssh://h:0",
            "tcp://h:1/x",
            "tcp://[::1:1",
            "http://h",
            "ws://",
            "ws://h?q=1",
            "ws://h/a%zz",
            "easytier:",
            "easytier:-x",
            "easytier:a/b",
            "relay:tcp://h:1",
            "unix:relative",
        ] {
            assert_eq!(
                Route::parse(bad),
                Err(format!("{bad} is not a route.")),
                "{bad}"
            );
        }
    }

    #[test]
    fn trusts_the_stdio_and_unix_routes_alone() {
        for (route, trusted) in [
            ("unix:", true),
            ("stdio:local", true),
            ("stdio:ssh://h", true),
            ("stdio:wsl", true),
            ("tcp://h:1", false),
            ("ws://h", false),
            ("wss://h", false),
            ("easytier:n", false),
            ("relay:wss://h", false),
            ("webrtc:wss://h", false),
        ] {
            assert_eq!(ok(route).trusted(), trusted, "{route}");
        }
    }

    #[test]
    fn offers_the_routes_of_this_system() {
        assert!(!ok("unix:").offered());
        assert!(!ok("webrtc:wss://h").offered());
        assert_eq!(ok("stdio:local").offered(), cfg!(not(windows)));
        assert_eq!(ok("stdio:wsl").offered(), cfg!(windows));
        for route in [
            "stdio:ssh://h",
            "tcp://h:1",
            "ws://h",
            "easytier:n",
            "relay:ws://h",
        ] {
            assert!(ok(route).offered(), "{route}");
        }
    }

    #[test]
    fn offers_no_ssh_destination_ssh_would_misread() {
        for route in [
            "stdio:ssh://-oProxyCommand=x",
            "stdio:ssh://-l@box",
            "stdio:ssh://me%20x@box",
            "stdio:ssh://a%09b",
            "stdio:ssh://a%0Db",
            "stdio:ssh://a%0Ab",
            "stdio:ssh://me@a%00b",
        ] {
            assert!(!ok(route).offered(), "{route}");
        }
        assert!(ok("stdio:ssh://me@-box").offered());
    }
}
