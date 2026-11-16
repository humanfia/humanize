//! EasyTier (Section 3.8.5 of [DAEMON], Section 3.12.6 of [DESKTOP]): the entries the app keeps
//! in `easytier.json`, the `easytier-core` it downloads and checks into `easytier/<version>/`,
//! and the joining side it runs, which puts the daemon's port on a port of this machine's
//! loopback without root or a TUN device.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use super::identity::random_suffix;

/// The release of EasyTier downloaded: the one `hmz` pins.
pub const VERSION: &str = "2.6.4";

/// The port the daemon's EasyTier listener takes on its loopback, which `hmz` fixes.
pub const PORT: u16 = 41817;

/// The address the daemon's side has in the network; the joining side takes one by DHCP.
const SERVER: &str = "10.144.144.1";

/// The SHA-256 of the release's zip for each system the app runs on.
const SHA256: [(&str, &str); 3] = [
    (
        "macos-aarch64",
        "4be1882d1aa36d31c1d6ba0596f2cf8a097e371f8da124212324b2e0f8df7e4b",
    ),
    (
        "macos-x86_64",
        "89fc28a6e6995259d76ce3f11775220e8a21c760e94df91a6a9db30a69b6982e",
    ),
    (
        "windows-x86_64",
        "27af91e270e554709b048bd32327fefd2dfce5062ae1e8701af7550c6f525f84",
    ),
];

/// The most a release may be.
const LIMIT: u64 = 128 << 20;

/// The fewest bytes a secret may be.
const FEWEST: usize = 16;

/// The protocols a shared node is reached over.
const PROTOCOLS: [&str; 6] = ["tcp", "udp", "ws", "wss", "quic", "wg"];

/// Held while `easytier.json` is read to be written, so that no write loses another's.
static WRITING: Mutex<()> = Mutex::new(());

/// One entry of `easytier.json`.
#[derive(Clone, Debug, Default, PartialEq, Serialize, Deserialize)]
pub struct Entry {
    pub secret: String,
    pub nodes: Vec<String>,
}

/// An entry as the page is shown it: never its secret, but whether one is written.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Shown {
    pub name: String,
    pub nodes: Vec<String>,
    pub secret: bool,
}

/// The entries in `file`; none where there is none.
pub fn entries(file: &Path) -> io::Result<BTreeMap<String, Entry>> {
    match fs::read(file) {
        Ok(bytes) => serde_json::from_slice(&bytes).map_err(io::Error::other),
        Err(why) if why.kind() == io::ErrorKind::NotFound => Ok(BTreeMap::new()),
        Err(why) => Err(why),
    }
}

/// Every entry, as the page is shown them.
pub fn list(file: &Path) -> Result<Vec<Shown>, String> {
    Ok(entries(file)
        .map_err(|why| why.to_string())?
        .into_iter()
        .map(|(name, entry)| Shown {
            name,
            nodes: entry.nodes,
            secret: !entry.secret.is_empty(),
        })
        .collect())
}

/// Writes the entry `name`, keeping the secret written where none is given.
pub fn set(
    file: &Path,
    name: &str,
    secret: Option<&str>,
    nodes: Vec<String>,
) -> Result<(), String> {
    if !super::route::name(name) {
        return Err(format!("{name} is not a name."));
    }
    if nodes.is_empty() {
        return Err("An EasyTier daemon needs at least one node.".into());
    }
    for url in &nodes {
        node(url)?;
    }
    let _writing = crate::lock(&WRITING);
    let mut all = entries(file).map_err(|why| why.to_string())?;
    let secret = match secret {
        Some(secret) => secret.to_owned(),
        None => all
            .get(name)
            .map(|entry| entry.secret.clone())
            .unwrap_or_default(),
    };
    if secret.len() < FEWEST {
        return Err("A secret must be at least 16 bytes.".into());
    }
    all.insert(name.to_owned(), Entry { secret, nodes });
    write(file, &all).map_err(|why| why.to_string())
}

/// Removes the entry `name`, where there is one.
pub fn remove(file: &Path, name: &str) -> Result<(), String> {
    let _writing = crate::lock(&WRITING);
    let mut all = entries(file).map_err(|why| why.to_string())?;
    if all.remove(name).is_some() {
        write(file, &all).map_err(|why| why.to_string())?;
    }
    Ok(())
}

/// A shared node's URL, where it is one: `<protocol>://<host>:<port>`.
fn node(url: &str) -> Result<(), String> {
    let refused = || format!("{url:?} is not an EasyTier node, as tcp://host:port.");
    let parsed = url::Url::parse(url).map_err(|_| refused())?;
    let whole = PROTOCOLS.contains(&parsed.scheme())
        && parsed.host_str().is_some_and(|host| !host.is_empty())
        && url.rsplit(':').next().is_some_and(|port| {
            !port.is_empty()
                && port.bytes().all(|c| c.is_ascii_digit())
                && port.parse::<u16>().is_ok()
        })
        && url.trim() == url;
    whole.then_some(()).ok_or_else(refused)
}

/// Writes every entry, readable by this user alone, by atomic replacement.
fn write(file: &Path, all: &BTreeMap<String, Entry>) -> io::Result<()> {
    let dir = file.parent().unwrap_or(Path::new("."));
    fs::create_dir_all(dir)?;
    let beside = dir.join(format!(".easytier.json.{}.new", random_suffix()));
    let mut options = fs::OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    std::os::unix::fs::OpenOptionsExt::mode(&mut options, 0o600);
    let written = options.open(&beside).and_then(|mut opened| {
        opened.write_all(&serde_json::to_vec_pretty(all).map_err(io::Error::other)?)?;
        opened.sync_all()
    });
    let moved = written.and_then(|()| fs::rename(&beside, file));
    if moved.is_err() {
        let _ = fs::remove_file(&beside);
    }
    moved
}

/// The name and the secret of the network a secret stands for: each a SHA-256 of it under a
/// label of its own, in hex, as `hmz` derives them.
pub fn network(secret: &str) -> (String, String) {
    let derived = |label: &str| {
        let digest = Sha256::digest(format!("{label}\0{secret}").as_bytes());
        data_encoding::HEXLOWER.encode(&digest)
    };
    (derived("hmz-easytier-name"), derived("hmz-easytier-secret"))
}

/// This machine's release asset, where EasyTier has one the app pins.
fn asset() -> Option<(&'static str, &'static str)> {
    let os = match std::env::consts::OS {
        "macos" => "macos",
        "windows" => "windows",
        _ => return None,
    };
    let wanted = format!("{os}-{}", std::env::consts::ARCH);
    SHA256.into_iter().find(|(asset, _)| *asset == wanted)
}

/// The binary's name.
fn core() -> &'static str {
    if cfg!(windows) {
        "easytier-core.exe"
    } else {
        "easytier-core"
    }
}

/// The `easytier-core` kept in `data`, downloaded and checked first where it is not there;
/// `say` is told that it is downloading.
pub fn binary(data: &Path, say: &dyn Fn(&str)) -> Result<PathBuf, String> {
    let kept = data.join("easytier").join(VERSION);
    let core = kept.join(core());
    if core.is_file() {
        return Ok(core);
    }
    let (asset, sum) = asset().ok_or_else(|| {
        format!(
            "EasyTier has no release for {} {}",
            std::env::consts::OS,
            std::env::consts::ARCH
        )
    })?;
    say(&format!("Downloading EasyTier {VERSION}"));
    let url = format!(
        "https://github.com/EasyTier/EasyTier/releases/download/v{VERSION}/easytier-{asset}-v{VERSION}.zip"
    );
    log::info!("downloading {url}");
    let failed = |why: &dyn std::fmt::Display| {
        format!("EasyTier {VERSION} could not be downloaded from {url}: {why}")
    };
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_connect(Some(Duration::from_secs(30)))
        .timeout_global(Some(Duration::from_secs(30 * 60)))
        .tls_config(
            ureq::tls::TlsConfig::builder()
                .root_certs(ureq::tls::RootCerts::PlatformVerifier)
                .build(),
        )
        .build()
        .into();
    let mut got = agent.get(&url).call().map_err(|why| failed(&why))?;
    let mut archive = Vec::new();
    got.body_mut()
        .with_config()
        .limit(LIMIT)
        .reader()
        .read_to_end(&mut archive)
        .map_err(|why| failed(&why))?;
    unpack(&archive, sum, &kept)
}

/// The binary of a release, and on Windows the libraries it loads, written into `kept` once
/// the release's SHA-256 is `sum`: each whole, the binary last, so that a binary found there
/// is one whose libraries are there too.
pub fn unpack(archive: &[u8], sum: &str, kept: &Path) -> Result<PathBuf, String> {
    let digest = data_encoding::HEXLOWER.encode(&Sha256::digest(archive));
    if digest != sum {
        return Err(format!(
            "EasyTier {VERSION} is not the one pinned: its SHA-256 is {digest}"
        ));
    }
    let broken =
        |why: &dyn std::fmt::Display| format!("EasyTier {VERSION} could not be unpacked: {why}");
    let mut zip = zip::ZipArchive::new(io::Cursor::new(archive)).map_err(|why| broken(&why))?;
    let name_of = |path: &str| {
        path.rsplit(['/', '\\'])
            .next()
            .unwrap_or_default()
            .to_owned()
    };
    let mut wanted: Vec<(usize, String)> = (0..zip.len())
        .filter_map(|at| {
            let name = name_of(&zip.name_for_index(at)?.ok()?);
            let library = cfg!(windows) && name.to_ascii_lowercase().ends_with(".dll");
            (name == core() || library).then_some((at, name))
        })
        .collect();
    if !wanted.iter().any(|(_, name)| name == core()) {
        return Err(broken(&format!("it has no {}", core())));
    }
    wanted.sort_by_key(|(_, name)| name == core());
    fs::create_dir_all(kept).map_err(|why| broken(&why))?;
    for (at, name) in wanted {
        let beside = kept.join(format!(".{name}.{}.new", random_suffix()));
        let written = (|| -> io::Result<()> {
            let mut entry = zip.by_index(at).map_err(io::Error::other)?;
            let mut out = fs::File::create(&beside)?;
            io::copy(&mut entry, &mut out)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                out.set_permissions(fs::Permissions::from_mode(0o755))?;
            }
            out.sync_all()?;
            fs::rename(&beside, kept.join(&name))
        })();
        if let Err(why) = written {
            let _ = fs::remove_file(&beside);
            // One already there and running, as Windows will not replace.
            if !kept.join(&name).is_file() {
                return Err(broken(&why));
            }
        }
    }
    Ok(kept.join(core()))
}

/// The `easytier-core` that joins the entry's network and forwards `local` on this machine's
/// loopback to the daemon's port: no TUN device, nothing of this machine let through to the
/// network, and the network's secret in its environment alone.
pub fn joining(core: &Path, entry: &Entry, local: u16) -> Command {
    let (name, secret) = network(&entry.secret);
    let mut command = Command::new(core);
    #[cfg(windows)]
    std::os::windows::process::CommandExt::creation_flags(
        &mut command,
        crate::wsl::CREATE_NO_WINDOW,
    );
    command
        .args([
            "--network-name",
            &name,
            "--no-tun",
            "true",
            "--private-mode",
            "true",
        ])
        .args(["--listeners", "tcp://0.0.0.0:0", "udp://0.0.0.0:0"])
        .args([
            "--dhcp",
            "true",
            "--tcp-whitelist",
            "0",
            "--udp-whitelist",
            "0",
        ])
        .arg("--port-forward")
        .arg(format!("tcp://127.0.0.1:{local}/{SERVER}:{PORT}"))
        .arg("--peers")
        .args(&entry.nodes);
    // EasyTier reads every flag from an `ET_` variable too: none of this process's is passed.
    for (key, _) in std::env::vars_os() {
        if key.to_string_lossy().starts_with("ET_") {
            command.env_remove(key);
        }
    }
    command
        .env("ET_NETWORK_SECRET", secret)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command
}

#[cfg(test)]
mod tests {
    use super::*;

    const SECRET: &str = "a secret of more than 16 bytes";

    #[test]
    fn keeps_entries_and_never_shows_a_secret() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("easytier.json");
        assert_eq!(list(&file).unwrap(), []);
        let nodes = vec!["tcp://public.example:11010".to_owned()];
        set(&file, "home", Some(SECRET), nodes.clone()).unwrap();
        // The secret kept where none is given.
        let more = vec![
            "udp://1.2.3.4:11010".to_owned(),
            "wss://n.example:443".to_owned(),
        ];
        set(&file, "home", None, more.clone()).unwrap();
        assert_eq!(
            list(&file).unwrap(),
            [Shown {
                name: "home".into(),
                nodes: more.clone(),
                secret: true
            }]
        );
        assert_eq!(entries(&file).unwrap()["home"].secret, SECRET);
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&file).unwrap().permissions().mode() & 0o777,
                0o600
            );
        }
        let refused = |name, secret, nodes| set(&file, name, secret, nodes).unwrap_err();
        assert_eq!(
            refused("other", None, nodes.clone()),
            "A secret must be at least 16 bytes."
        );
        assert_eq!(
            refused("other", Some("short"), nodes.clone()),
            "A secret must be at least 16 bytes."
        );
        assert_eq!(
            refused("other", Some(SECRET), vec![]),
            "An EasyTier daemon needs at least one node."
        );
        assert_eq!(
            refused("other", Some(SECRET), vec!["http://h:1".into()]),
            "\"http://h:1\" is not an EasyTier node, as tcp://host:port."
        );
        assert!(refused("other", Some(SECRET), vec!["tcp://h".into()]).contains("not an"));
        assert_eq!(
            refused("-x", Some(SECRET), nodes.clone()),
            "-x is not a name."
        );
        remove(&file, "home").unwrap();
        remove(&file, "home").unwrap();
        assert_eq!(list(&file).unwrap(), []);
    }

    #[test]
    fn derives_the_network_as_hmz_does() {
        // hashlib.sha256(b"hmz-easytier-name\0" + secret) in hmz.coganchor.easytier.
        let (name, secret) = network("0123456789abcdef");
        assert_eq!(
            name,
            data_encoding::HEXLOWER
                .encode(&Sha256::digest(b"hmz-easytier-name\x000123456789abcdef"))
        );
        assert_eq!(secret.len(), 64);
        assert_ne!(name, secret);
    }

    #[test]
    fn joins_with_the_secret_in_its_environment_alone() {
        let entry = Entry {
            secret: SECRET.into(),
            nodes: vec!["tcp://n.example:11010".into()],
        };
        let command = joining(Path::new("/et/easytier-core"), &entry, 5555);
        let args: Vec<_> = command
            .get_args()
            .map(|a| a.to_string_lossy().into_owned())
            .collect();
        let (name, secret) = network(SECRET);
        assert!(
            args.windows(2)
                .any(|w| w == ["--network-name", name.as_str()])
        );
        assert!(args.windows(2).any(|w| w == ["--no-tun", "true"]));
        assert!(
            args.windows(2)
                .any(|w| w == ["--port-forward", "tcp://127.0.0.1:5555/10.144.144.1:41817"])
        );
        assert_eq!(args[args.len() - 2..], ["--peers", "tcp://n.example:11010"]);
        assert!(
            !args
                .iter()
                .any(|arg| arg.contains(SECRET) || arg.contains(&secret))
        );
        let env: Vec<_> = command.get_envs().collect();
        assert!(env.contains(&(
            std::ffi::OsStr::new("ET_NETWORK_SECRET"),
            Some(std::ffi::OsStr::new(&secret))
        )));
    }

    #[test]
    fn unpacks_a_release_only_once_it_is_the_one_pinned() {
        let mut zipped = io::Cursor::new(Vec::new());
        {
            let mut zip = zip::ZipWriter::new(&mut zipped);
            let options = zip::write::SimpleFileOptions::default();
            zip.start_file(format!("easytier-x/{}", core()), options)
                .unwrap();
            zip.write_all(b"core").unwrap();
            zip.start_file("easytier-x/easytier-cli", options).unwrap();
            zip.write_all(b"cli").unwrap();
            zip.finish().unwrap();
        }
        let archive = zipped.into_inner();
        let sum = data_encoding::HEXLOWER.encode(&Sha256::digest(&archive));
        let dir = tempfile::tempdir().unwrap();
        let kept = dir.path().join("easytier").join(VERSION);
        assert!(
            unpack(&archive, &"0".repeat(64), &kept)
                .unwrap_err()
                .contains("not the one pinned")
        );
        assert!(!kept.exists());
        let core = unpack(&archive, &sum, &kept).unwrap();
        assert_eq!(fs::read(&core).unwrap(), b"core");
        let names: Vec<_> = fs::read_dir(&kept)
            .unwrap()
            .map(|e| e.unwrap().file_name())
            .collect();
        assert_eq!(names, [core.file_name().unwrap()]);
        // Found there from now on.
        assert_eq!(binary(dir.path(), &|_| panic!("downloaded")).unwrap(), core);
    }
}
