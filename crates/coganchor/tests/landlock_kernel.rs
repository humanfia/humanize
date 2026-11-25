//! Landlock behaviour on a kernel chosen by CI rather than the runner's own kernel.
//!
//! The harness runs no test unless `HMZ_LANDLOCK_MATRIX_ABI` names the ABI the kernel must
//! provide. The QEMU matrix sets it, and every prerequisite is then required rather than
//! skipped: the kernel, its LSM list and seccomp user notifications are the subject here.

#[cfg(not(target_os = "linux"))]
fn main() {}

#[cfg(target_os = "linux")]
fn main() {
    linux::run();
}

#[cfg(target_os = "linux")]
mod linux {

    use std::env;
    use std::fs;
    use std::io::{self, Read, Write};
    use std::net::{TcpListener, TcpStream, UdpSocket};
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
    use std::path::Path;
    use std::process::{Child, Command, Stdio};
    use std::thread;
    use std::time::{Duration, Instant};

    use coganchor::fence::landlock;
    use serde_json::json;

    const CHILD: &str = "HMZ_LANDLOCK_MATRIX_CHILD";
    const EXPECTED: &str = "HMZ_LANDLOCK_MATRIX_ABI";
    const PATIENCE: Duration = Duration::from_secs(20);

    pub fn run() {
        if env::var_os(CHILD).is_some() {
            std::process::exit(child());
        }
        let Ok(expected) = env::var(EXPECTED) else {
            println!("landlock kernel matrix: skipped; {EXPECTED} names an ABI in CI");
            return;
        };
        let expected = expected.parse::<u32>().expect("a numeric ABI");
        let actual = landlock::abi();
        assert_eq!(
            actual, expected,
            "the running kernel must speak Landlock ABI {expected}"
        );
        println!("landlock kernel matrix: ABI {actual}");

        paths();
        if actual < 4 {
            landlock_network_is_refused();
        } else {
            assert!(
                landlock::able().net,
                "ABI {actual} must hold the network with seccomp user notifications"
            );
            network();
        }
        scopes(actual);
        println!("LANDLOCK-MATRIX PASS ABI {actual}");
    }

    fn paths() {
        let root = tempfile::tempdir().expect("a temporary directory");
        let inside = root.path().join("inside");
        let outside = root.path().join("outside");
        fs::create_dir(&inside).expect("an inside directory");
        fs::create_dir(&outside).expect("an outside directory");
        fs::write(inside.join("readable"), b"inside").expect("a readable file inside");
        fs::write(outside.join("kept"), b"outside").expect("a file outside");
        let policy = policy_with_deny(&inside, true, &[], &[&outside]);
        let done = fenced(&policy)
            .args(["path"])
            .arg(&inside)
            .arg(&outside)
            .output()
            .expect("the path check runs");
        passed("path", &done);
    }

    fn landlock_network_is_refused() {
        let root = tempfile::tempdir().expect("a temporary directory");
        let done = fenced(&policy(root.path(), false, &[]))
            .args(["true"])
            .output()
            .expect("the network refusal runs");
        assert_eq!(done.status.code(), Some(126), "{done:?}");
        let stderr = String::from_utf8_lossy(&done.stderr);
        assert!(
            stderr.contains("Landlock ABI 4 and seccomp"),
            "network refusal said: {stderr}"
        );
        println!("landlock kernel matrix: network is refused before ABI 4");
    }

    fn network() {
        let root = tempfile::tempdir().expect("a temporary directory");
        let port = free_port();
        let ready = root.path().join("ready");
        let mut process = fenced(&policy(root.path(), false, &[port]))
            .args(["network", &port.to_string()])
            .arg(&ready)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("the network check starts");
        wait_for(&mut process, &ready);
        let mut stream = connect(port);
        stream
            .write_all(b"ping")
            .expect("the fence passes a connection");
        let mut said = [0; 4];
        stream
            .read_exact(&mut said)
            .expect("the fence passes a reply");
        assert_eq!(&said, b"pong");
        drop(stream);
        wait(&mut process, "network");
        println!("landlock kernel matrix: TCP connect and loopback listen held");
    }

    fn scopes(abi: u32) {
        let root = tempfile::tempdir().expect("a temporary directory");
        let outside = abstract_listener("outside").expect("an outside abstract socket");
        let other = std::process::id() as i32;

        let signals = fenced(&policy(root.path(), true, &[]))
            .args(["signal", &other.to_string(), &abi.to_string()])
            .output()
            .expect("the signal check runs");
        passed("signal", &signals);

        let sockets = fenced(&policy(root.path(), true, &[]))
            .args(["abstract", &abi.to_string()])
            .output()
            .expect("the abstract socket check runs");
        passed("abstract Unix socket", &sockets);
        drop(outside);
    }

    fn child() -> i32 {
        let args: Vec<String> = env::args().skip(1).collect();
        let mode = args.first().map(String::as_str).unwrap_or("");
        let done = match mode {
            "true" => Ok(()),
            "path" => child_path(&args[1], &args[2]),
            "network" => child_network(args[1].parse().expect("a port"), &args[2]),
            "signal" => child_signal(
                args[1].parse().expect("the parent pid"),
                args[2].parse().expect("the ABI"),
            ),
            "abstract" => child_abstract(args[1].parse().expect("the ABI")),
            "sleep" => {
                thread::sleep(Duration::from_secs(30));
                Ok(())
            }
            _ => Err(format!("unknown child mode {mode:?}")),
        };
        match done {
            Ok(()) => 0,
            Err(why) => {
                eprintln!("{mode}: {why}");
                1
            }
        }
    }

    fn child_path(inside: &str, outside: &str) -> Result<(), String> {
        let inside = Path::new(inside);
        let outside = Path::new(outside);
        match fs::read(inside.join("readable")) {
            Ok(said) if said.as_slice() == b"inside" => {}
            Ok(said) => return Err(format!("the inside file held {said:?}")),
            Err(why) => return Err(format!("read inside: {why}")),
        }
        fs::write(inside.join("written"), b"inside")
            .map_err(|why| format!("write inside: {why}"))?;
        match fs::read(outside.join("kept")) {
            Err(why) if why.kind() == io::ErrorKind::PermissionDenied => {}
            Err(why) => return Err(format!("read outside failed with {why}")),
            Ok(_) => return Err("the fence allowed a read outside".into()),
        }
        match fs::write(outside.join("written"), b"outside") {
            Err(why) if why.kind() == io::ErrorKind::PermissionDenied => Ok(()),
            Err(why) => Err(format!(
                "write outside failed with {why}, not permission denied"
            )),
            Ok(()) => Err("the fence allowed a write outside".into()),
        }
    }

    fn child_network(port: u16, ready: &str) -> Result<(), String> {
        let proxy = env::var("HTTPS_PROXY").map_err(|_| "HTTPS_PROXY was not set")?;
        let proxy = proxy
            .rsplit_once(':')
            .ok_or("HTTPS_PROXY had no port")?
            .1
            .parse::<u16>()
            .map_err(|why| format!("HTTPS_PROXY port: {why}"))?;
        TcpStream::connect(("127.0.0.1", proxy))
            .map_err(|why| format!("connect to the proxy: {why}"))?;

        let unallowed = free_port();
        match TcpStream::connect(("127.0.0.1", unallowed)) {
            Err(why) if why.kind() == io::ErrorKind::PermissionDenied => {}
            Err(why) => return Err(format!("unallowed TCP failed with {why}")),
            Ok(_) => return Err("the fence allowed an unlisted TCP port".into()),
        }
        match UdpSocket::bind(("127.0.0.1", 0)) {
            Err(why) if why.kind() == io::ErrorKind::PermissionDenied => {}
            Err(why) => return Err(format!("UDP failed with {why}")),
            Ok(_) => return Err("the fence allowed UDP".into()),
        }
        match TcpListener::bind(("0.0.0.0", 0)) {
            Err(why) if why.kind() == io::ErrorKind::PermissionDenied => {}
            Err(why) => return Err(format!("a non-loopback bind failed with {why}")),
            Ok(_) => return Err("the fence allowed a non-loopback bind".into()),
        }

        let listener = TcpListener::bind(("127.0.0.1", port))
            .map_err(|why| format!("bind the allowed port: {why}"))?;
        fs::write(ready, b"ready").map_err(|why| format!("write ready marker: {why}"))?;
        let (mut stream, _) = listener
            .accept()
            .map_err(|why| format!("accept through the relay: {why}"))?;
        let mut said = [0; 4];
        stream
            .read_exact(&mut said)
            .map_err(|why| format!("read the relayed request: {why}"))?;
        if &said != b"ping" {
            return Err(format!("the relayed request was {said:?}"));
        }
        stream
            .write_all(b"pong")
            .map_err(|why| format!("write the relayed reply: {why}"))
    }

    fn child_signal(parent: i32, abi: u32) -> Result<(), String> {
        let mut inside = Command::new(env::current_exe().map_err(|why| why.to_string())?)
            .arg("sleep")
            .env(CHILD, "1")
            .spawn()
            .map_err(|why| format!("spawn inside the scope: {why}"))?;
        signal(inside.id() as i32, 0).map_err(|why| format!("signal inside: {why}"))?;
        signal(inside.id() as i32, 15).map_err(|why| format!("stop inside: {why}"))?;
        inside.wait().map_err(|why| format!("wait inside: {why}"))?;

        match signal(parent, 0) {
            Ok(()) if abi < 6 => Ok(()),
            Ok(()) => Err("ABI 6 let a signal reach outside the fence".into()),
            Err(why) if abi >= 6 && why.kind() == io::ErrorKind::PermissionDenied => Ok(()),
            Err(why) => Err(format!("signal outside the scope: {why}")),
        }
    }

    fn child_abstract(abi: u32) -> Result<(), String> {
        let inside = abstract_listener("inside")
            .map_err(|why| format!("inside abstract listener: {why}"))?;
        let client = raw_socket().map_err(|why| format!("inside abstract client: {why}"))?;
        connect_abstract(client.as_raw_fd(), "inside")
            .map_err(|why| format!("connect the inside abstract socket: {why}"))?;
        let outside = raw_socket().map_err(|why| format!("outside abstract client: {why}"))?;
        match connect_abstract(outside.as_raw_fd(), "outside") {
            Ok(()) if abi < 6 => {}
            Ok(()) => return Err("ABI 6 let an abstract socket reach outside the fence".into()),
            Err(why) if abi >= 6 && why.kind() == io::ErrorKind::PermissionDenied => {}
            Err(why) => return Err(format!("connect an outside abstract socket: {why}")),
        }
        drop(client);
        drop(inside);
        Ok(())
    }

    fn fenced(policy: &str) -> Command {
        let mut command = Command::new(env!("CARGO_BIN_EXE_coganchor"));
        command
            .args(["internal", "fence", &format!("--policy={policy}")])
            .args(["--sandbox=landlock", "--"])
            .arg(env::current_exe().expect("the harness path"))
            .env(CHILD, "1");
        command
    }

    fn policy(write: &std::path::Path, online: bool, listen: &[u16]) -> String {
        policy_with_deny(write, online, listen, &[])
    }

    fn policy_with_deny(write: &Path, online: bool, listen: &[u16], deny: &[&Path]) -> String {
        let deny = deny
            .iter()
            .map(|path| path.to_string_lossy().into_owned())
            .collect::<Vec<_>>();
        json!({
            "read": ["/"],
            "write": [write],
            "keep": [],
            "deny": deny,
            "online": online,
            "hosts": [],
            "tmp": "",
            "drawn": [],
            "listen": listen,
        })
        .to_string()
    }

    fn passed(what: &str, done: &std::process::Output) {
        assert!(
            done.status.success(),
            "{what} failed with {:?}\nstdout:\n{}\nstderr:\n{}",
            done.status.code(),
            String::from_utf8_lossy(&done.stdout),
            String::from_utf8_lossy(&done.stderr)
        );
        println!("landlock kernel matrix: {what} held");
    }

    fn wait_for(process: &mut Child, ready: &std::path::Path) {
        let until = Instant::now() + PATIENCE;
        while Instant::now() < until {
            if ready.exists() {
                return;
            }
            if let Some(status) = process.try_wait().expect("the network check is waitable") {
                panic!("the network check exited before it listened: {status}");
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = process.kill();
        panic!("the allowed listener did not become ready");
    }

    fn wait(process: &mut Child, what: &str) {
        let until = Instant::now() + PATIENCE;
        while Instant::now() < until {
            if let Some(status) = process.try_wait().expect("the child is waitable") {
                assert!(status.success(), "{what} exited with {status}");
                return;
            }
            thread::sleep(Duration::from_millis(50));
        }
        let _ = process.kill();
        panic!("{what} did not finish");
    }

    fn connect(port: u16) -> TcpStream {
        let until = Instant::now() + PATIENCE;
        loop {
            match TcpStream::connect(("127.0.0.1", port)) {
                Ok(stream) => return stream,
                Err(_) if Instant::now() < until => thread::sleep(Duration::from_millis(50)),
                Err(why) => panic!("the relayed listener on {port} refused: {why}"),
            }
        }
    }

    fn free_port() -> u16 {
        TcpListener::bind(("127.0.0.1", 0))
            .expect("a free TCP port")
            .local_addr()
            .expect("the free port")
            .port()
    }

    fn signal(pid: i32, number: i32) -> io::Result<()> {
        // SAFETY: kill takes integers only.
        if unsafe { libc::kill(pid, number) } == 0 {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }

    fn abstract_listener(name: &str) -> io::Result<OwnedFd> {
        let socket = raw_socket()?;
        bind_abstract(socket.as_raw_fd(), name)?;
        // SAFETY: listening changes the socket this process owns.
        if unsafe { libc::listen(socket.as_raw_fd(), 1) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(socket)
    }

    fn raw_socket() -> io::Result<OwnedFd> {
        // SAFETY: socket takes integers only.
        let fd = unsafe { libc::socket(libc::AF_UNIX, libc::SOCK_STREAM | libc::SOCK_CLOEXEC, 0) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: the kernel just returned this descriptor, which nothing else owns.
        Ok(unsafe { OwnedFd::from_raw_fd(fd) })
    }

    fn abstract_address(name: &str) -> (libc::sockaddr_un, libc::socklen_t) {
        // SAFETY: an all-zero sockaddr_un is valid to fill.
        let mut address: libc::sockaddr_un = unsafe { std::mem::zeroed() };
        address.sun_family = libc::AF_UNIX as libc::sa_family_t;
        let name = name.as_bytes();
        assert!(!name.is_empty() && name.len() + 1 < address.sun_path.len());
        address.sun_path[1..=name.len()]
            .iter_mut()
            .zip(name)
            .for_each(|(held, said)| *held = *said as libc::c_char);
        let length = std::mem::offset_of!(libc::sockaddr_un, sun_path) + 1 + name.len();
        (address, length as libc::socklen_t)
    }

    fn bind_abstract(fd: i32, name: &str) -> io::Result<()> {
        let (address, length) = abstract_address(name);
        // SAFETY: the address is alive for the call and its length was computed above.
        if unsafe {
            libc::bind(
                fd,
                &address as *const libc::sockaddr_un as *const libc::sockaddr,
                length,
            )
        } == 0
        {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }

    fn connect_abstract(fd: i32, name: &str) -> io::Result<()> {
        let (address, length) = abstract_address(name);
        // SAFETY: the address is alive for the call and its length was computed above.
        if unsafe {
            libc::connect(
                fd,
                &address as *const libc::sockaddr_un as *const libc::sockaddr,
                length,
            )
        } == 0
        {
            Ok(())
        } else {
            Err(io::Error::last_os_error())
        }
    }
}
