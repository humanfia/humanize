//! How a command is run on a target. Port of `Road` in `hmz.coganchor.transport`. [Unit 7]
//!
//! `ssh` (with connection reuse under a private control directory), `docker exec -i` (with the
//! endpoint, user, variables and wrapper words the target names), `container exec -i`, and an
//! `srun` step sharing a Slurm job's allocation; `local` has no prefix.

use std::collections::HashSet;
use std::ffi::{OsStr, OsString};
use std::fs;
use std::io::{self, Write};
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use sha2::{Digest, Sha256};

use crate::transport::Target;
use crate::transport::target::{APPLE, Endpoint, SLURM, ssh_flags};

/// Where coganchor is cached on a target reached over ssh or srun: `humanize` in that user's
/// XDG cache directory, `$XDG_CACHE_HOME` and `$HOME` expanded by the far side's shell, rather
/// than `~`. `transport.REMOTE_CACHE`.
pub const REMOTE_CACHE: &str = "${XDG_CACHE_HOME:-$HOME/.cache}/humanize";

/// Where a harness put on such a machine keeps its mirrors, beside the cache rather than in
/// it (see `transport.REMOTE_MIRRORS` for why). `transport.REMOTE_MIRRORS`.
pub const REMOTE_MIRRORS: &str = "${XDG_CACHE_HOME:-$HOME/.cache}/humanize-mirrors";

/// And in a container. `transport.CONTAINER_CACHE`.
pub const CONTAINER_CACHE: &str = "/tmp/humanize";

/// `transport.CONTAINER_MIRRORS`.
pub const CONTAINER_MIRRORS: &str = "/tmp/humanize-mirrors";

/// What every `ssh` carries: `-T`, the far side being a pipe, and a keepalive.
/// `transport._SSH_OPTIONS`.
const SSH_OPTIONS: [&str; 5] = ["-T", "-o", "BatchMode=no", "-o", "ServerAliveInterval=30"];

/// What lets the second `ssh` to a host ride the first one's connection.
/// `transport._SSH_REUSE`.
const SSH_REUSE: [&str; 4] = ["-o", "ControlMaster=auto", "-o", "ControlPersist=120"];

/// What a control socket's path spends after its directory: `%C`'s 40 digits, the `-<8>` of a
/// target's options and the `.<16>` ssh binds it under first. `transport._CONTROL`.
const CONTROL: usize = 40 + 9 + 17;

/// The longest path a Unix socket can be bound at, the macOS limit. `unix.LONGEST`.
const LONGEST: usize = 103;

/// What a `docker` sent to any daemon but this machine's default runs without.
/// `transport._DOCKER_AMBIENT`.
const DOCKER_AMBIENT: [&str; 5] = [
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
];

/// The road to one target.
#[derive(Clone, Debug)]
pub struct Road {
    pub target: Target,
}

impl Road {
    /// The road to `target`.
    pub fn to(target: &Target) -> Road {
        Road {
            target: target.clone(),
        }
    }

    /// The full command line that runs `argv` on the target.
    ///
    /// # Panics
    ///
    /// For a `tcp://` or `peer://` target, on whose far side nothing is started, and where a
    /// docker endpoint's `ssh` shim cannot be written. [`Road::try_line`] says so instead.
    pub fn line(&self, argv: &[OsString]) -> Vec<OsString> {
        self.try_line(argv)
            .unwrap_or_else(|error| panic!("{error}"))
    }

    /// The full command line that runs `argv` on the target. Port of `Road.line`: argv
    /// through as it is, or for ssh one string, `exec` and every word shell-quoted, which
    /// the login shell there reads back into the same words.
    pub fn try_line(&self, argv: &[OsString]) -> io::Result<Vec<OsString>> {
        let mut line = self.prefix()?;
        if self.target.scheme != "ssh" {
            line.extend(argv.iter().cloned());
            return Ok(line);
        }
        let mut joined = b"exec".to_vec();
        for word in argv {
            joined.push(b' ');
            joined.extend_from_slice(&shell_quote(word.as_bytes()));
        }
        line.push(OsString::from_vec(joined));
        Ok(line)
    }

    /// What goes in front of a command to send it there. The prefixes of `Road.to`.
    pub fn prefix(&self) -> io::Result<Vec<OsString>> {
        let target = &self.target;
        let words: Vec<String> = match target.scheme.as_str() {
            "local" => Vec::new(),
            "ssh" => {
                // The target's own options first: ssh keeps the first value it is given for
                // a setting, so what somebody wrote for this host wins over what hmz assumes.
                let mut words = vec!["ssh".to_owned()];
                words.extend(ssh_flags(&target.options));
                words.extend(SSH_OPTIONS.map(str::to_owned));
                words.extend(ssh_reuse(&target.options));
                if let Some(port) = target.port.filter(|port| *port != 0) {
                    words.extend(["-p".to_owned(), port.to_string()]);
                }
                words.push(target.login());
                words
            }
            "docker" => {
                let mut flags = vec!["exec".to_owned(), "-i".to_owned()];
                let mut wrapper = Vec::new();
                for (key, value) in &target.options {
                    match key.as_str() {
                        "user" => flags.extend(["-u".to_owned(), value.clone()]),
                        "env" => flags.extend(["-e".to_owned(), value.clone()]),
                        _ => wrapper.push(value.clone()),
                    }
                }
                flags.push(target.host.clone());
                let endpoint = target.endpoint().map_err(io::Error::other)?;
                let mut words = docker(&endpoint, &flags)?;
                words.extend(wrapper);
                words
            }
            APPLE => ["container", "exec", "-i", &target.host]
                .map(str::to_owned)
                .to_vec(),
            // A step of the job's own, sharing its allocation, on its one node: argv straight
            // through, nothing of this environment but whose it is, and none of its directory.
            SLURM => vec![
                "srun".to_owned(),
                format!("--jobid={}", target.host),
                "--overlap".to_owned(),
                "--nodes=1".to_owned(),
                "--ntasks=1".to_owned(),
                "--unbuffered".to_owned(),
                "--quiet".to_owned(),
                "--export=HOME,USER".to_owned(),
                "--chdir=/".to_owned(),
            ],
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!("nothing is started on the far side of {target}"),
                ));
            }
        };
        Ok(words.into_iter().map(OsString::from).collect())
    }

    /// The directory coganchor keeps its binaries in on the target (protocol/files.md 9.2.3).
    pub fn cache(&self) -> String {
        match self.target.scheme.as_str() {
            "ssh" | SLURM => REMOTE_CACHE.to_owned(),
            "docker" => CONTAINER_CACHE.to_owned() + &self.own(),
            APPLE => CONTAINER_CACHE.to_owned(),
            _ => String::new(),
        }
    }

    /// The directory mirrors are kept in on the target (protocol/files.md 9.2.4).
    pub fn mirrors(&self) -> String {
        match self.target.scheme.as_str() {
            "ssh" | SLURM => REMOTE_MIRRORS.to_owned(),
            "docker" => CONTAINER_MIRRORS.to_owned() + &self.own(),
            APPLE => CONTAINER_MIRRORS.to_owned(),
            _ => String::new(),
        }
    }

    /// Whether [`Road::cache`] and [`Road::mirrors`] have to be checked to be the far side's
    /// user's alone before anything goes in them: a docker target naming a `user`
    /// (protocol/core.md 6.9.1.8). `Road.owned`.
    pub fn owned(&self) -> bool {
        self.target.scheme == "docker" && !self.user().is_empty()
    }

    /// The uid a docker target's `user` names, or "".
    fn user(&self) -> String {
        self.target
            .options
            .iter()
            .filter(|(key, _)| key == "user")
            .map(|(_, value)| value.split(':').next().unwrap_or("").to_owned())
            .next_back()
            .unwrap_or_default()
    }

    /// `-UID` for a docker target naming a user, a container's `/tmp` being all of its users'.
    fn own(&self) -> String {
        match self.user() {
            user if user.is_empty() => user,
            user => format!("-{user}"),
        }
    }

    /// Runs one short command over there, feeding it `input`, and waits for it with both of
    /// its streams captured. Port of `Road.run`.
    pub fn run(
        &self,
        argv: &[OsString],
        input: &[u8],
        timeout: Option<Duration>,
    ) -> io::Result<Output> {
        let line = self.try_line(argv)?;
        let (program, args) = line
            .split_first()
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "nothing to run"))?;
        let mut child = Command::new(program)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        let mut stdin = child.stdin.take().expect("piped");
        let input = input.to_vec();
        // Fed from a thread of its own, so a command that answers without reading all of
        // its input (an install that finds its file already there) is not waited on for it.
        // `SIGPIPE` is blocked on that thread, so a write to a command that has gone is an
        // `EPIPE` there rather than the end of this process, whatever its disposition is.
        let feeder = std::thread::spawn(move || {
            use nix::sys::signal::{SigSet, SigmaskHow, Signal, pthread_sigmask};
            let mut pipe = SigSet::empty();
            pipe.add(Signal::SIGPIPE);
            let _ = pthread_sigmask(SigmaskHow::SIG_BLOCK, Some(&pipe), None);
            let _ = stdin.write_all(&input);
        });
        let output = match timeout {
            None => child.wait_with_output()?,
            Some(limit) => wait_within(child, limit)?,
        };
        let _ = feeder.join();
        Ok(output)
    }
}

/// `child.wait_with_output()`, killing it once `limit` has passed.
fn wait_within(mut child: std::process::Child, limit: Duration) -> io::Result<Output> {
    use std::io::Read;
    let mut out = child.stdout.take().expect("piped");
    let mut err = child.stderr.take().expect("piped");
    let reading = std::thread::spawn(move || {
        let mut said = Vec::new();
        let _ = out.read_to_end(&mut said);
        said
    });
    let erring = std::thread::spawn(move || {
        let mut said = Vec::new();
        let _ = err.read_to_end(&mut said);
        said
    });
    let started = Instant::now();
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        if started.elapsed() >= limit {
            let _ = child.kill();
            let _ = child.wait();
            return Err(io::Error::new(
                io::ErrorKind::TimedOut,
                format!("no answer within {}s", limit.as_secs_f64()),
            ));
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    Ok(Output {
        status,
        stdout: reading.join().unwrap_or_default(),
        stderr: erring.join().unwrap_or_default(),
    })
}

/// The `docker` command that runs `argv` against `endpoint` and no other. Port of
/// `Endpoint.docker`: docker's default finds itself; any other is named on the command line,
/// with the variables that would redirect it taken off, and an `ssh://` one with options is
/// dialled through an `ssh` told them, first on the `PATH` it runs with.
pub fn docker(endpoint: &Endpoint, argv: &[String]) -> io::Result<Vec<String>> {
    if endpoint.host.is_empty() && endpoint.context.is_empty() {
        return Ok(["docker".to_owned()]
            .into_iter()
            .chain(argv.iter().cloned())
            .collect());
    }
    let mut said = if endpoint.context.is_empty() {
        vec!["--host".to_owned(), endpoint.host.clone()]
    } else {
        vec!["--context".to_owned(), endpoint.context.clone()]
    };
    if !endpoint.certs.is_empty() {
        said.push("--tlsverify".to_owned());
        for (flag, pem) in [
            ("--tlscacert", "ca"),
            ("--tlscert", "cert"),
            ("--tlskey", "key"),
        ] {
            said.push(flag.to_owned());
            said.push(
                Path::new(&endpoint.certs)
                    .join(format!("{pem}.pem"))
                    .to_string_lossy()
                    .into_owned(),
            );
        }
    }
    let mut line = vec!["env".to_owned()];
    for name in DOCKER_AMBIENT {
        line.extend(["-u".to_owned(), name.to_owned()]);
    }
    if !endpoint.options.is_empty() {
        let shim = ssh_shim(&endpoint.options).map_err(|error| {
            io::Error::new(
                error.kind(),
                format!(
                    "could not write the ssh docker dials {} through: {error}",
                    endpoint.host
                ),
            )
        })?;
        let path = std::env::var("PATH").unwrap_or_else(|_| "/bin:/usr/bin".to_owned());
        line.push(format!("PATH={}:{path}", shim.display()));
    }
    line.push("docker".to_owned());
    line.extend(said);
    line.extend(argv.iter().cloned());
    Ok(line)
}

/// The `ssh` shims this process has written or found whole. `transport._SHIMS`.
static SHIMS: Mutex<Option<HashSet<PathBuf>>> = Mutex::new(None);

/// The directory holding an `ssh` that tells the real one these options first, for docker's
/// own ssh transport to find on `PATH`. Port of `transport._ssh_shim`: one per set of
/// options, at `$TMPDIR/humanize-<uid>/docker-ssh/<sha16>/ssh`, written once and whole,
/// touched each time it is used and written again if it has gone.
pub fn ssh_shim(options: &[(String, String)]) -> io::Result<PathBuf> {
    let flags = ssh_flags(options)
        .iter()
        .map(|flag| String::from_utf8_lossy(&shell_quote(flag.as_bytes())).into_owned())
        .collect::<Vec<_>>()
        .join(" ");
    let at = machine()?
        .join("docker-ssh")
        .join(&hex::encode(Sha256::digest(flags.as_bytes()))[..16]);
    let ssh = at.join("ssh");
    let mut shims = SHIMS.lock().unwrap();
    let shims = shims.get_or_insert_with(HashSet::new);
    if shims.contains(&at) && touched(&ssh) {
        return Ok(at);
    }
    let prefix = format!("{}:", at.display());
    let script = format!(
        "#!/bin/sh\n\
         # The ssh docker dials its daemon's host through, told what the endpoint says.\n\
         PATH=${{PATH#{}}}\n\
         exec ssh {flags} \"$@\"\n",
        String::from_utf8_lossy(&shell_quote(prefix.as_bytes()))
    );
    if fs::read_to_string(&ssh).is_ok_and(|there| there.trim() == script.trim()) {
        shims.insert(at.clone());
        return Ok(at);
    }
    fs::DirBuilder::new()
        .recursive(true)
        .mode(0o700)
        .create(&at)?;
    let staged = at.join(format!(".ssh.{}.new", std::process::id()));
    let written = (|| {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o700)
            .open(&staged)?;
        file.write_all(script.as_bytes())?;
        fs::set_permissions(&staged, fs::Permissions::from_mode(0o700))?;
        fs::rename(&staged, &ssh)
    })();
    if let Err(error) = written {
        let _ = fs::remove_file(&staged);
        return Err(error);
    }
    shims.insert(at.clone());
    Ok(at)
}

/// Marks a file as just used, and says whether it was there to mark.
fn touched(path: &Path) -> bool {
    fs::File::options()
        .append(true)
        .open(path)
        .and_then(|file| file.set_modified(std::time::SystemTime::now()))
        .is_ok()
}

/// The ssh options that let every command to a host ride one connection, worked out once per
/// process. Port of `transport._reuse`.
pub fn ssh_reuse(options: &[(String, String)]) -> Vec<String> {
    static HELD: OnceLock<Vec<String>> = OnceLock::new();
    let base = HELD.get_or_init(|| {
        reuse_flags(
            std::env::var("HUMANIZE_SSH_REUSE").ok().as_deref(),
            &std::env::var("XDG_RUNTIME_DIR").unwrap_or_default(),
        )
    });
    with_options(base, options)
}

/// The reuse options for a `HUMANIZE_SSH_REUSE` and `XDG_RUNTIME_DIR`: none where the first
/// says `off`, `0`, `no` or `false` (trimmed, in any case) or is set and empty, and none where
/// the control directory, `humanize-ssh-<uid>`, is not a directory of this user's alone.
pub fn reuse_flags(said: Option<&str>, runtime: &str) -> Vec<String> {
    let said = said.unwrap_or("on").trim().to_lowercase();
    if ["off", "0", "no", "false", ""].contains(&said.as_str()) {
        return Vec::new();
    }
    let uid = nix::unistd::getuid().as_raw();
    let name = format!("humanize-ssh-{uid}");
    let under = sockets(format!("/{name}/").len() + CONTROL, runtime);
    let control = under.join(&name);
    let _ = fs::DirBuilder::new().mode(0o700).create(&control);
    match fs::symlink_metadata(&control) {
        // Under `/tmp` a directory of this name may be anybody's, made first, and a socket
        // in it one they could take this user's connections over.
        Ok(found) if found.is_dir() && found.uid() == uid && found.mode() & 0o077 == 0 => {
            let mut flags: Vec<String> = SSH_REUSE.map(str::to_owned).to_vec();
            flags.push("-o".to_owned());
            flags.push(format!("ControlPath={}/%C", control.display()));
            flags
        }
        _ => Vec::new(),
    }
}

/// The reuse options for a target's own options: a digest of them joins the socket's name,
/// so two targets at one host told different things do not share a connection
/// (protocol/core.md 6.9.1.4). The digest is of Python's `repr(tuple(options))`, so both
/// halves name one target's socket alike.
fn with_options(base: &[String], options: &[(String, String)]) -> Vec<String> {
    let mut flags = base.to_vec();
    if options.is_empty() || flags.is_empty() {
        return flags;
    }
    let pairs: Vec<String> = options
        .iter()
        .map(|(key, value)| {
            use crate::transport::target::py_repr;
            format!("({}, {})", py_repr(key), py_repr(value))
        })
        .collect();
    let repr = if pairs.len() == 1 {
        format!("({},)", pairs[0])
    } else {
        format!("({})", pairs.join(", "))
    };
    let told = &hex::encode(Sha256::digest(repr.as_bytes()))[..8];
    if let Some(last) = flags.last_mut() {
        last.push('-');
        last.push_str(told);
    }
    flags
}

/// Where a directory holding a Unix socket goes so the socket's path fits in `room` more
/// bytes: `under` or the temporary directory where it fits, `/tmp` otherwise (unless `/tmp`
/// is not this user's to write in either). Port of `unix.sockets`.
fn sockets(room: usize, under: &str) -> PathBuf {
    let at = if under.is_empty() {
        temporary()
    } else {
        PathBuf::from(under)
    };
    let writable = nix::unistd::access(
        "/tmp",
        nix::unistd::AccessFlags::W_OK | nix::unistd::AccessFlags::X_OK,
    )
    .is_ok();
    if at.as_os_str().len() + room <= LONGEST || !writable {
        at
    } else {
        PathBuf::from("/tmp")
    }
}

/// The temporary directory, as Python's `tempfile.gettempdir` finds it: the first of
/// `TMPDIR`, `TEMP` and `TMP`, then `/tmp`, `/var/tmp` and `/usr/tmp`, that is a directory
/// this user can write in, spelled without a trailing `/`.
pub fn temporary() -> PathBuf {
    let named = ["TMPDIR", "TEMP", "TMP"]
        .into_iter()
        .filter_map(std::env::var_os)
        .filter(|said| !said.is_empty());
    let fixed = ["/tmp", "/var/tmp", "/usr/tmp"].map(OsString::from);
    for candidate in named.chain(fixed) {
        let bytes = candidate.as_bytes();
        let trimmed = match bytes.iter().rposition(|byte| *byte != b'/') {
            Some(last) => &bytes[..=last],
            None => &b"/"[..],
        };
        let path = PathBuf::from(OsStr::from_bytes(trimmed));
        if path.is_dir()
            && nix::unistd::access(
                &path,
                nix::unistd::AccessFlags::W_OK | nix::unistd::AccessFlags::X_OK,
            )
            .is_ok()
        {
            return path;
        }
    }
    PathBuf::from("/tmp")
}

/// This machine's own directory for this user, `<tmp>/humanize-<uid>`, made `0700` and
/// refused where it is not a directory of this user's that nobody else can write. Port of
/// `hmz.machine`.
pub fn machine() -> io::Result<PathBuf> {
    let uid = nix::unistd::getuid().as_raw();
    let mine = temporary().join(format!("humanize-{uid}"));
    match fs::DirBuilder::new().mode(0o700).create(&mine) {
        Err(error) if error.kind() != io::ErrorKind::AlreadyExists => return Err(error),
        _ => {}
    }
    let found = fs::symlink_metadata(&mine)?;
    if !found.is_dir() || found.uid() != uid || found.mode() & 0o022 != 0 {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            format!(
                "{} is not a directory of this user's that nobody else can write",
                mine.display()
            ),
        ));
    }
    Ok(mine)
}

/// `shlex.quote` on bytes: the word itself where it is only `[A-Za-z0-9_@%+=:,./-]`, `''` for
/// an empty one, and otherwise the word in single quotes with each `'` written `'"'"'`.
pub fn shell_quote(word: &[u8]) -> Vec<u8> {
    if word.is_empty() {
        return b"''".to_vec();
    }
    if word
        .iter()
        .all(|byte| byte.is_ascii_alphanumeric() || b"_@%+=:,./-".contains(byte))
    {
        return word.to_vec();
    }
    let mut out = vec![b'\''];
    for byte in word {
        if *byte == b'\'' {
            out.extend_from_slice(b"'\"'\"'");
        } else {
            out.push(*byte);
        }
    }
    out.push(b'\'');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(target: &str, argv: &[&str]) -> Vec<String> {
        let argv: Vec<OsString> = argv.iter().map(OsString::from).collect();
        Road::to(&Target::parse(target).unwrap())
            .try_line(&argv)
            .unwrap()
            .into_iter()
            .map(|word| word.into_string().unwrap())
            .collect()
    }

    #[test]
    fn quotes_as_shlex_does() {
        assert_eq!(shell_quote(b""), b"''");
        assert_eq!(shell_quote(b"/a/b-c.d"), b"/a/b-c.d");
        assert_eq!(shell_quote(b"it's"), b"'it'\"'\"'s'");
        assert_eq!(shell_quote(b"a b"), b"'a b'");
    }

    #[test]
    fn containers_take_argv_through() {
        assert_eq!(
            line(
                "docker://box?user=1000:1000&env=A=b c&exec=tini&exec=--",
                &["ls", "a b"]
            ),
            [
                "docker",
                "exec",
                "-i",
                "-u",
                "1000:1000",
                "-e",
                "A=b c",
                "box",
                "tini",
                "--",
                "ls",
                "a b"
            ]
        );
        assert_eq!(
            line("apple-container://c1", &["x"]),
            ["container", "exec", "-i", "c1", "x"]
        );
        assert_eq!(line("slurm://42", &["x"])[..2], ["srun", "--jobid=42"]);
    }

    #[test]
    fn other_daemons_are_named() {
        let said = line("docker://box@tcp://h:2376?tls=/certs", &["x"]);
        assert_eq!(said[0], "env");
        assert_eq!(said[1..3], ["-u", "DOCKER_HOST"]);
        let docker = said.iter().position(|word| word == "docker").unwrap();
        assert_eq!(
            said[docker..],
            [
                "docker",
                "--host",
                "tcp://h:2376",
                "--tlsverify",
                "--tlscacert",
                "/certs/ca.pem",
                "--tlscert",
                "/certs/cert.pem",
                "--tlskey",
                "/certs/key.pem",
                "exec",
                "-i",
                "box",
                "x"
            ]
        );
    }

    #[test]
    fn caches_are_named_for_the_user() {
        let road = Road::to(&Target::parse("docker://box?user=7:8").unwrap());
        assert_eq!(road.cache(), "/tmp/humanize-7");
        assert_eq!(road.mirrors(), "/tmp/humanize-mirrors-7");
        assert!(road.owned());
        let road = Road::to(&Target::parse("ssh://h").unwrap());
        assert_eq!(road.cache(), "${XDG_CACHE_HOME:-$HOME/.cache}/humanize");
        assert!(!road.owned());
    }

    #[test]
    fn reuse_is_off_when_said_so() {
        for said in ["off", " NO ", "0", "false", ""] {
            assert!(reuse_flags(Some(said), "").is_empty());
        }
        // Short enough for a socket path, as an XDG_RUNTIME_DIR is.
        let dir = tempfile::tempdir_in("/tmp").unwrap();
        let flags = reuse_flags(None, dir.path().to_str().unwrap());
        let uid = nix::unistd::getuid().as_raw();
        assert_eq!(
            flags.last().unwrap(),
            &format!("ControlPath={}/humanize-ssh-{uid}/%C", dir.path().display())
        );
        // A digest of the options joins the name, as Python's `repr` of them spells them.
        let told = with_options(&flags, &[("F".into(), "/c".into())]);
        let expected = &hex::encode(Sha256::digest(b"(('F', '/c'),)"))[..8];
        assert!(told.last().unwrap().ends_with(&format!("%C-{expected}")));
    }

    #[test]
    fn a_daemon_over_ssh_is_dialled_through_a_shim() {
        let said = line("docker://box@ssh://me@daemon?IdentityFile=/k%20ey", &["x"]);
        let path = said.iter().find(|word| word.starts_with("PATH=")).unwrap();
        let shim = PathBuf::from(path["PATH=".len()..].split(':').next().unwrap());
        let flags = "-o 'IdentityFile=\"/k ey\"'";
        let digest = &hex::encode(Sha256::digest(flags.as_bytes()))[..16];
        assert_eq!(shim, machine().unwrap().join("docker-ssh").join(digest));
        let script = fs::read_to_string(shim.join("ssh")).unwrap();
        assert!(
            script.ends_with(&format!("exec ssh {flags} \"$@\"\n")),
            "{script}"
        );
        assert_eq!(
            fs::metadata(shim.join("ssh")).unwrap().mode() & 0o777,
            0o700
        );
        let docker = said.iter().position(|word| word == "docker").unwrap();
        assert_eq!(said[docker + 1..docker + 3], ["--host", "ssh://me@daemon"]);
    }
}
