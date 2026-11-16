//! Target spellings. Port of `Target`, `Endpoint` and `describe` in
//! `hmz.coganchor.transport` (protocol/core.md 6.9). [Unit 7]
//!
//! What is read here is spelled back by [`Target::describe`] exactly as Python's
//! `Target.describe` spells it, so a target logged by either half can be typed into the other.
//! The options after a `?` are read as `urllib.parse.parse_qsl(..., strict_parsing=True)`
//! reads them and written as `urlencode(..., quote_via=quote, safe=...)` writes them.

use std::fmt;

/// A target, as one of the spellings of protocol/core.md 6.9.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Target {
    /// `local`, `ssh`, `docker`, `apple-container`, `slurm`, `tcp` or `peer`.
    pub scheme: String,
    /// For an `ssh://` target, what comes before the last `@` of its host, where it has one.
    pub user: Option<String>,
    /// The host, the container, or for a `slurm://` target the job's id.
    pub host: String,
    /// The port of an `ssh://`, `tcp://` or `peer://` target, where one is written.
    pub port: Option<u16>,
    /// `local:DIR`'s directory, a docker target's endpoint (none for the default), a
    /// `slurm://` target's `?python=PATH`, or a `peer://` target's ticket.
    pub path: Option<String>,
    /// The `?KEY=VALUE&...` options, in the order written.
    pub options: Vec<(String, String)>,
}

/// What an Apple container's target is spelled with.
pub const APPLE: &str = "apple-container";

/// What a Slurm job's target is spelled with.
pub const SLURM: &str = "slurm";

/// What a docker target may say after its `?`: `transport._DOCKER_OPTIONS`.
const DOCKER_OPTIONS: [&str; 3] = ["user", "env", "exec"];

impl Target {
    fn new(scheme: &str) -> Target {
        Target {
            scheme: scheme.to_owned(),
            user: None,
            host: String::new(),
            port: None,
            path: None,
            options: Vec::new(),
        }
    }

    /// Reads a target; any other spelling is an error naming every accepted one.
    /// Port of `Target.parse`.
    pub fn parse(said: &str) -> Result<Target, String> {
        if said == "local" || said.starts_with("local:") {
            let path = said.split_once(':').map_or("", |(_, path)| path);
            let mut target = Target::new("local");
            target.path = some(path);
            return Ok(target);
        }
        if let Some(rest) = said.strip_prefix("ssh://") {
            let (authority, query) = rest.split_once('?').unwrap_or((rest, ""));
            let options = ssh_options(query, said)?;
            let mut target = Target::new("ssh");
            let (mut host, port) = match authority.rsplit_once(':') {
                Some((host, port)) if !host.is_empty() && is_digits(port) => {
                    (host, Some(parse_port(port, said)?))
                }
                _ => (authority, None),
            };
            if let Some((user, rest)) = host.rsplit_once('@') {
                target.user = Some(user.to_owned());
                host = rest;
            }
            target.host = host.to_owned();
            // Port 0 is no port, as Python's 0 is: neither is written back or passed to ssh.
            target.port = port.filter(|port| *port != 0);
            target.options = options;
            return Ok(target);
        }
        if let Some(rest) = said.strip_prefix("docker://") {
            // At the first `@`: a container's name cannot hold one, its options are quoted so
            // as not to, and an endpoint's can.
            let (container, at, endpoint) = match rest.split_once('@') {
                Some((container, endpoint)) => (container, true, endpoint),
                None => (rest, false, ""),
            };
            let (container, query) = container.split_once('?').unwrap_or((container, ""));
            if !container.is_empty() && (!endpoint.is_empty() || !at) {
                let options = docker_options(query, said)?;
                let endpoint = Endpoint::parse(endpoint)?;
                let mut target = Target::new("docker");
                target.host = container.to_owned();
                // Kept as its own spelling, and none for the default -- so a target naming
                // its daemon `local` is the same target as one naming none.
                if endpoint != Endpoint::default() {
                    target.path = Some(endpoint.to_string());
                }
                target.options = options;
                return Ok(target);
            }
        }
        if let Some(container) = said.strip_prefix("apple-container://")
            && !container.is_empty()
            && !container.contains(['@', '/', '?', '#'])
        {
            let mut target = Target::new(APPLE);
            target.host = container.to_owned();
            return Ok(target);
        }
        if let Some(rest) = said.strip_prefix("slurm://") {
            let (job, query) = rest.split_once('?').unwrap_or((rest, ""));
            let python = python_option(query, said)?;
            if is_digits(job) {
                let mut target = Target::new(SLURM);
                target.host = job.to_owned();
                target.path = some(&python);
                return Ok(target);
            }
        }
        if let Some(rest) = said.strip_prefix("tcp://") {
            return match rest.rsplit_once(':') {
                Some((host, port)) if !host.is_empty() && is_digits(port) => {
                    let mut target = Target::new("tcp");
                    target.host = host.to_owned();
                    target.port = Some(parse_port(port, said)?);
                    Ok(target)
                }
                _ => Err(format!(
                    "malformed target {}; expected tcp://HOST:PORT",
                    py_repr(said)
                )),
            };
        }
        if let Some(rest) = said.strip_prefix("peer://") {
            // `Meeting.parse`: the ticket up to the first `@`, the port after the last `:`.
            let malformed = || {
                format!(
                    "malformed meeting {}; expected TICKET@HOST:PORT",
                    py_repr(rest)
                )
            };
            let (ticket, authority) = rest.split_once('@').ok_or_else(malformed)?;
            let (host, port) = authority.rsplit_once(':').ok_or_else(malformed)?;
            if ticket.is_empty() || host.is_empty() || !is_digits(port) {
                return Err(malformed());
            }
            let mut target = Target::new("peer");
            target.host = host.trim_matches(['[', ']']).to_owned();
            target.port = Some(port.parse().map_err(|_| malformed())?);
            target.path = Some(ticket.to_owned());
            return Ok(target);
        }
        Err(format!(
            "unsupported target {}; expected ssh://HOST, docker://CONTAINER[@ENDPOINT], \
             {APPLE}://CONTAINER, {SLURM}://JOBID[?python=PATH], tcp://HOST:PORT, \
             peer://TICKET@HOST:PORT or local[:PATH]",
            py_repr(said)
        ))
    }

    /// The target spelled back, options included, as `Target.describe` spells it.
    pub fn describe(&self) -> String {
        let path = self.path.as_deref().unwrap_or("");
        match self.scheme.as_str() {
            "ssh" => {
                let mut said = format!("ssh://{}", self.login());
                if let Some(port) = self.port.filter(|port| *port != 0) {
                    said += &format!(":{port}");
                }
                if !self.options.is_empty() {
                    said += "?";
                    said += &urlencode(&self.options, "/~:@,");
                }
                said
            }
            "docker" => {
                let mut said = format!("docker://{}", self.host);
                if !self.options.is_empty() {
                    // An `@` quoted, so that the container's part still ends at the first one.
                    said += "?";
                    said += &urlencode(&self.options, "/~:,=");
                }
                if !path.is_empty() {
                    said += "@";
                    said += path;
                }
                said
            }
            APPLE => format!("{APPLE}://{}", self.host),
            SLURM => {
                let mut said = format!("{SLURM}://{}", self.host);
                if !path.is_empty() {
                    said += "?python=";
                    said += &quote(path, "/~:@,");
                }
                said
            }
            "tcp" => format!("tcp://{}:{}", self.host, self.port.unwrap_or(0)),
            "peer" => format!("peer://{path}@{}:{}", self.host, self.port.unwrap_or(0)),
            _ if path.is_empty() => "local".to_owned(),
            _ => format!("local:{path}"),
        }
    }

    /// `[USER@]HOST`, what `ssh` is handed as its destination.
    pub fn login(&self) -> String {
        match &self.user {
            Some(user) => format!("{user}@{}", self.host),
            None => self.host.clone(),
        }
    }

    /// The daemon a `docker://` target's container is held by. Port of `Target.endpoint`.
    pub fn endpoint(&self) -> Result<Endpoint, String> {
        if self.scheme != "docker" {
            return Err(format!("{} is not a container", self.describe()));
        }
        Endpoint::parse(self.path.as_deref().unwrap_or(""))
    }
}

impl fmt::Display for Target {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.describe())
    }
}

/// Which docker daemon a container is reached through. Port of `transport.Endpoint`.
///
/// `local` for docker's default here, `unix:///PATH`, `tcp://HOST:PORT` with `?tls=DIR` for a
/// verified one, `ssh://[USER@]HOST[:PORT]` with `?KEYWORD=VALUE&...` for what its `ssh` is
/// told besides, or `context:NAME`.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Endpoint {
    /// docker's `--host` for it, or "" for a context or for the default.
    pub host: String,
    /// The docker context it is reached by, or "".
    pub context: String,
    /// For a `tcp://` host, the directory holding its `ca.pem`, `cert.pem` and `key.pem`.
    pub certs: String,
    /// For an `ssh://` host, what its `ssh` is told besides the login, port and host.
    pub options: Vec<(String, String)>,
}

impl Endpoint {
    /// Reads an endpoint spelling, "" being `local`. Port of `Endpoint.parse`.
    pub fn parse(said: &str) -> Result<Endpoint, String> {
        if said.is_empty() || said == "local" {
            return Ok(Endpoint::default());
        }
        if let Some(context) = said.strip_prefix("context:")
            && !context.is_empty()
        {
            return Ok(Endpoint {
                context: context.to_owned(),
                ..Endpoint::default()
            });
        }
        if said.starts_with("unix:///") {
            return Ok(Endpoint {
                host: said.to_owned(),
                ..Endpoint::default()
            });
        }
        if let Some(rest) = said.strip_prefix("ssh://") {
            let (authority, query) = rest.split_once('?').unwrap_or((rest, ""));
            let host = authority
                .rsplit_once('@')
                .map_or(authority, |(_, host)| host);
            if !host.is_empty()
                && !authority.contains(['/', '#'])
                && let Ok(options) = ssh_options(query, said)
            {
                return Ok(Endpoint {
                    host: format!("ssh://{authority}"),
                    options,
                    ..Endpoint::default()
                });
            }
        }
        if let Some(rest) = said.strip_prefix("tcp://") {
            let (address, asks, certs) = match rest.split_once("?tls=") {
                Some((address, certs)) => (address, true, certs),
                None => (rest, false, ""),
            };
            if let Some((host, port)) = address.rsplit_once(':')
                && !host.is_empty()
                && is_digits(port)
                && (!asks || certs.starts_with('/'))
            {
                return Ok(Endpoint {
                    host: format!("tcp://{address}"),
                    certs: certs.to_owned(),
                    ..Endpoint::default()
                });
            }
        }
        Err(format!(
            "unsupported docker endpoint {}; expected local, unix:///PATH, \
             tcp://HOST:PORT[?tls=DIR], ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...] or \
             context:NAME",
            py_repr(said)
        ))
    }

    /// Whether the daemon is this machine's. Port of `Endpoint.here` (protocol 6.9.2.2).
    pub fn here(&self) -> bool {
        if !self.context.is_empty() {
            return false;
        }
        let host = if self.host.is_empty() {
            std::env::var("DOCKER_HOST").unwrap_or_default()
        } else {
            self.host.clone()
        };
        host.is_empty() || host.starts_with("unix://")
    }
}

impl fmt::Display for Endpoint {
    /// Its own spelling back, which [`Endpoint::parse`] reads as this endpoint again.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if !self.context.is_empty() {
            return write!(f, "context:{}", self.context);
        }
        if !self.certs.is_empty() {
            return write!(f, "{}?tls={}", self.host, self.certs);
        }
        if !self.options.is_empty() {
            return write!(f, "{}?{}", self.host, urlencode(&self.options, "/~:@,"));
        }
        if self.host.is_empty() {
            f.write_str("local")
        } else {
            f.write_str(&self.host)
        }
    }
}

/// What `ssh` is told for a target's options, in the order written: `-F FILE` for `F`, and
/// `-o KEYWORD=VALUE` for the rest, a value holding whitespace in double quotes. Port of
/// `transport.ssh_flags`.
pub fn ssh_flags(options: &[(String, String)]) -> Vec<String> {
    let mut flags = Vec::new();
    for (key, value) in options {
        if key == "F" {
            flags.push("-F".to_owned());
            flags.push(value.clone());
        } else {
            let said = if value.chars().any(is_space) {
                format!("\"{value}\"")
            } else {
                value.clone()
            };
            flags.push("-o".to_owned());
            flags.push(format!("{key}={said}"));
        }
    }
    flags
}

/// What Python's `str.isspace` answers yes to: Unicode's white space, and the four
/// separators `\x1c`-`\x1f` that Rust's `char::is_whitespace` leaves out.
fn is_space(one: char) -> bool {
    one.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&one)
}

/// `Some(said)`, or `None` for "".
fn some(said: &str) -> Option<String> {
    (!said.is_empty()).then(|| said.to_owned())
}

/// Whether `said` is a non-empty run of ASCII digits, as `str.isdigit` answers for them.
fn is_digits(said: &str) -> bool {
    !said.is_empty() && said.bytes().all(|byte| byte.is_ascii_digit())
}

/// A port, which unlike Python's `int` has to fit in 16 bits.
fn parse_port(port: &str, spec: &str) -> Result<u16, String> {
    port.parse()
        .map_err(|_| format!("malformed target {}; {port} is not a port", py_repr(spec)))
}

/// The options after the `?` of an ssh target. Port of `transport._ssh_options`.
fn ssh_options(query: &str, spec: &str) -> Result<Vec<(String, String)>, String> {
    if query.is_empty() {
        return Ok(Vec::new());
    }
    let pairs = parse_qsl(query, true).map_err(|_| {
        format!(
            "malformed target {}; expected ssh://HOST?KEYWORD=VALUE&...",
            py_repr(spec)
        )
    })?;
    for (key, value) in &pairs {
        if !is_keyword(key) || value.is_empty() || value.contains(['\n', '\r', '\0', '"']) {
            return Err(format!(
                "malformed target {}; {key}={} is not an ssh option",
                py_repr(spec),
                py_repr(value)
            ));
        }
    }
    Ok(pairs)
}

/// `[A-Za-z][A-Za-z0-9]*`: an ssh_config keyword, or `F`.
fn is_keyword(said: &str) -> bool {
    let mut chars = said.chars();
    chars
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic())
        && chars.all(|one| one.is_ascii_alphanumeric())
}

/// `[A-Za-z_][A-Za-z0-9_]*`: a variable's name.
fn is_variable(said: &str) -> bool {
    let mut chars = said.chars();
    chars
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && chars.all(|one| one.is_ascii_alphanumeric() || one == '_')
}

/// `[0-9]+(?::[0-9]+)?`: the numeric `UID[:GID]` docker's `-u` takes.
fn is_docker_user(said: &str) -> bool {
    match said.split_once(':') {
        Some((uid, gid)) => is_digits(uid) && is_digits(gid),
        None => is_digits(said),
    }
}

/// The options after the `?` of a docker target. Port of `transport._docker_options`.
fn docker_options(query: &str, spec: &str) -> Result<Vec<(String, String)>, String> {
    if query.is_empty() {
        return Ok(Vec::new());
    }
    let pairs = parse_qsl(query, true).map_err(|_| {
        format!(
            "malformed target {}; expected \
             docker://CONTAINER?user=UID[:GID]&env=NAME=VALUE&exec=WORD&...",
            py_repr(spec)
        )
    })?;
    let mut users = 0;
    for (key, value) in &pairs {
        users += usize::from(key == "user");
        let env_ok = value
            .split_once('=')
            .is_some_and(|(name, _)| is_variable(name));
        if value.contains(['\n', '\r', '\0'])
            || (key == "user" && (users > 1 || !is_docker_user(value)))
            || (key == "env" && !env_ok)
            || (key == "exec" && value.is_empty())
            || !DOCKER_OPTIONS.contains(&key.as_str())
        {
            return Err(format!(
                "malformed target {}; {key}={} is not a docker exec option",
                py_repr(spec),
                py_repr(value)
            ));
        }
    }
    Ok(pairs)
}

/// The Python a `slurm://` target names after its `?`. Port of `transport._python_option`.
fn python_option(query: &str, spec: &str) -> Result<String, String> {
    if query.is_empty() {
        return Ok(String::new());
    }
    let pairs = parse_qsl(query, false).unwrap_or_default();
    match pairs.as_slice() {
        [(key, value)]
            if key == "python"
                && (value.starts_with('/') || value.starts_with("~/"))
                && !value.contains(['\n', '\r', '\0', '"']) =>
        {
            Ok(value.clone())
        }
        _ => Err(format!(
            "malformed target {}; expected {SLURM}://JOBID[?python=PATH]",
            py_repr(spec)
        )),
    }
}

/// `urllib.parse.parse_qsl(query, keep_blank_values=..., strict_parsing=True)`: `&`-separated
/// `NAME=VALUE` pairs, each unquoted with `+` read as a space; an empty field or one without
/// `=` is an error.
fn parse_qsl(query: &str, keep_blank: bool) -> Result<Vec<(String, String)>, String> {
    let mut pairs = Vec::new();
    for field in query.split('&') {
        let Some((name, value)) = field.split_once('=') else {
            return Err(format!("bad query field: {}", py_repr(field)));
        };
        if !value.is_empty() || keep_blank {
            pairs.push((unquote_plus(name), unquote_plus(value)));
        }
    }
    Ok(pairs)
}

/// `urllib.parse.unquote_plus`: `+` as a space, `%XX` as that byte, the bytes read as UTF-8
/// with anything else replaced.
fn unquote_plus(said: &str) -> String {
    let bytes = said.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut at = 0;
    while at < bytes.len() {
        match bytes[at] {
            b'+' => out.push(b' '),
            b'%' if at + 2 < bytes.len()
                && hex(bytes[at + 1]).is_some()
                && hex(bytes[at + 2]).is_some() =>
            {
                out.push(hex(bytes[at + 1]).unwrap() << 4 | hex(bytes[at + 2]).unwrap());
                at += 2;
            }
            byte => out.push(byte),
        }
        at += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex(digit: u8) -> Option<u8> {
    (digit as char).to_digit(16).map(|value| value as u8)
}

/// `urllib.parse.quote(said, safe)`: every byte but ASCII letters, digits, `_.-~` and `safe`
/// as `%XX`.
pub(crate) fn quote(said: &str, safe: &str) -> String {
    let mut out = String::with_capacity(said.len());
    for byte in said.bytes() {
        if byte.is_ascii_alphanumeric()
            || b"_.-~".contains(&byte)
            || safe.as_bytes().contains(&byte)
        {
            out.push(byte as char);
        } else {
            out += &format!("%{byte:02X}");
        }
    }
    out
}

/// `urlencode(pairs, quote_via=quote, safe=safe)`.
fn urlencode(pairs: &[(String, String)], safe: &str) -> String {
    pairs
        .iter()
        .map(|(key, value)| format!("{}={}", quote(key, safe), quote(value, safe)))
        .collect::<Vec<_>>()
        .join("&")
}

/// `repr(said)` for a `str`, as Python writes it, for messages that name what was said.
pub(crate) fn py_repr(said: &str) -> String {
    let mark = if said.contains('\'') && !said.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(said.len() + 2);
    out.push(mark);
    for one in said.chars() {
        match one {
            '\\' => out += "\\\\",
            '\n' => out += "\\n",
            '\r' => out += "\\r",
            '\t' => out += "\\t",
            _ if one == mark => {
                out.push('\\');
                out.push(one);
            }
            _ if (one as u32) < 0x20 || one as u32 == 0x7f => {
                out += &format!("\\x{:02x}", one as u32);
            }
            _ if (0x80..=0xa0).contains(&(one as u32)) || one == '\u{ad}' => {
                out += &format!("\\x{:02x}", one as u32);
            }
            // The rest of what `str.isprintable` refuses that is likely to be met: Unicode's
            // spaces, line and paragraph separators and invisible formatting.
            '\u{1680}'
            | '\u{2000}'..='\u{200f}'
            | '\u{2028}'..='\u{202f}'
            | '\u{205f}'
            | '\u{2060}'..='\u{2064}'
            | '\u{3000}'
            | '\u{feff}' => {
                out += &format!("\\u{:04x}", one as u32);
            }
            _ => out.push(one),
        }
    }
    out.push(mark);
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn options_read_as_parse_qsl_reads_them() {
        assert_eq!(
            parse_qsl("a=b%20c&d=e+f&g=%zz", true).unwrap(),
            vec![
                ("a".into(), "b c".into()),
                ("d".into(), "e f".into()),
                ("g".into(), "%zz".into()),
            ]
        );
        assert!(parse_qsl("a=b&&c=d", true).is_err());
        assert!(parse_qsl("a", true).is_err());
        assert_eq!(parse_qsl("a=", false).unwrap(), vec![]);
        assert_eq!(unquote_plus("%C3%A9%"), "é%");
        assert_eq!(unquote_plus("%C3"), "\u{fffd}");
    }

    #[test]
    fn reprs_as_python_does() {
        assert_eq!(py_repr("a'b"), "\"a'b\"");
        assert_eq!(py_repr("a'\"b"), "'a\\'\"b'");
        assert_eq!(py_repr("x\ny\0"), "'x\\ny\\x00'");
    }

    #[test]
    fn a_user_is_its_own_field() {
        let target = Target::parse("ssh://me@box:2201?F=/c").unwrap();
        assert_eq!(target.user.as_deref(), Some("me"));
        assert_eq!(target.host, "box");
        assert_eq!(target.port, Some(2201));
        assert_eq!(target.login(), "me@box");
        assert_eq!(target.describe(), "ssh://me@box:2201?F=/c");
    }
}
