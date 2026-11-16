//! Unpacking what a turn brings back: `tarfile.open(...).extractall(into, filter="data")`, for
//! the archives a target's `tar cf -` writes (ustar, GNU long names, pax).
//!
//! Python's `data` filter, member by member: a leading `/` is taken off; nothing may land
//! outside `into`, through a link already there or one in the archive; a link may not be
//! absolute; a device or a pipe stops the unpacking; a file's mode loses its high bits and its
//! group's and others' write, keeps its execute bits only where its owner has one, and is at
//! least `0600`; a directory's and a link's mode, and every owner, are ignored. The first
//! member refused, or that cannot be written, stops the unpacking with what came before it
//! left in place, as `extractall` at its default `errorlevel` does.

use std::fs;
use std::io::{self, Read, Write};
use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
use std::path::Path;

use super::local::{resolved, within};

const BLOCK: usize = 512;

fn refused(why: impl Into<String>) -> io::Error {
    io::Error::other(why.into())
}

/// The records of a pax extended header, as `(key, value)`.
fn pax(data: &[u8]) -> Vec<(String, String)> {
    let mut records = Vec::new();
    let mut rest = data;
    while let Some(space) = rest.iter().position(|b| *b == b' ') {
        let Some(length) = std::str::from_utf8(&rest[..space])
            .ok()
            .and_then(|n| n.parse::<usize>().ok())
        else {
            break;
        };
        if length <= space || length > rest.len() {
            break;
        }
        let record = &rest[space + 1..length];
        let record = record.strip_suffix(b"\n").unwrap_or(record);
        if let Some(equals) = record.iter().position(|b| *b == b'=') {
            records.push((
                String::from_utf8_lossy(&record[..equals]).into_owned(),
                String::from_utf8_lossy(&record[equals + 1..]).into_owned(),
            ));
        }
        rest = &rest[length..];
    }
    records
}

/// What a member is, by its type flag.
#[derive(Clone, Copy, PartialEq)]
enum Kind {
    File,
    Hard,
    Symbolic,
    Directory,
    Special,
}

impl Kind {
    fn of(flag: u8) -> Kind {
        match flag {
            b'1' => Kind::Hard,
            b'2' => Kind::Symbolic,
            b'5' => Kind::Directory,
            b'3' | b'4' | b'6' => Kind::Special,
            // `0`, NUL, `7`, and what tarfile does not know, which it reads as a file.
            _ => Kind::File,
        }
    }
}

/// Sets a path's access and modification times to `mtime` seconds.
fn utime(path: &Path, mtime: f64) -> io::Result<()> {
    let seconds = mtime.floor();
    let micros = ((mtime - seconds) * 1e6) as i64;
    let when = nix::sys::time::TimeVal::new(seconds as _, micros as _);
    nix::sys::stat::utimes(path, &when, &when).map_err(io::Error::from)
}

/// Unpacks `archive` into `into` under the `data` filter. Reading the archive (ustar, GNU long
/// names, pax) is the `tar` crate's; what may land where, and with which mode, is the filter's.
pub(super) fn extract(archive: &[u8], into: &Path) -> io::Result<()> {
    if archive.len() < BLOCK {
        return Err(refused("empty file"));
    }
    let into = std::path::absolute(into)?;
    let dest = resolved(&into);
    // A pax global header's records, which hold for every member after it.
    let mut global: Vec<(String, String)> = Vec::new();
    let mut directories: Vec<(String, f64)> = Vec::new();
    let mut reader = tar::Archive::new(archive);
    for entry in reader.entries()? {
        let mut entry = entry?;
        // The type flag as written: the crate reads a pre-POSIX NUL as `0`, which loses the
        // old way of saying a directory (a NUL flag and a name ending in `/`).
        let flag = entry.header().as_bytes()[156];
        let mut data = Vec::new();
        if flag == b'g' {
            entry.read_to_end(&mut data)?;
            global.extend(pax(&data));
            continue;
        }
        let own: Vec<(String, String)> = match entry.pax_extensions()? {
            Some(records) => records
                .filter_map(Result::ok)
                .filter_map(|one| Some((one.key().ok()?.to_owned(), one.value().ok()?.to_owned())))
                .collect(),
            None => Vec::new(),
        };
        let said = |key: &str| {
            own.iter()
                .rev()
                .chain(global.iter().rev())
                .find(|(k, _)| k == key)
                .map(|(_, v)| v.clone())
        };
        let mut name = said("path")
            .unwrap_or_else(|| String::from_utf8_lossy(&entry.path_bytes()).into_owned());
        let link = said("linkpath").unwrap_or_else(|| {
            entry
                .link_name_bytes()
                .map(|link| String::from_utf8_lossy(&link).into_owned())
                .unwrap_or_default()
        });
        let mtime = match said("mtime").and_then(|n| n.parse::<f64>().ok()) {
            Some(mtime) => mtime,
            None => entry.header().mtime()? as f64,
        };
        let mode = entry.header().mode()?;
        // A pre-POSIX member named with a trailing slash is a directory, as tarfile reads it.
        let kind = match Kind::of(flag) {
            Kind::File if flag == 0 && name.ends_with('/') => Kind::Directory,
            kind => kind,
        };
        if kind == Kind::File {
            entry.read_to_end(&mut data)?;
        }
        if kind == Kind::Directory {
            name = name.trim_end_matches('/').to_owned();
        }
        let name = filtered(&name, &link, kind, &dest)?;
        let target = into.join(&name);
        if let Some(upper) = target.parent()
            && !upper.exists()
        {
            fs::create_dir_all(upper)?;
        }
        // Its owner's read and write, and execute only where its owner has it.
        let mut mode = mode & 0o755;
        if mode & 0o100 == 0 {
            mode &= !0o111;
        }
        mode |= 0o600;
        match kind {
            Kind::Directory => {
                if let Err(why) = fs::DirBuilder::new().mode(0o700).create(&target)
                    && !target.is_dir()
                {
                    return Err(why);
                }
                directories.push((name, mtime));
                continue;
            }
            Kind::File => {
                let mut file = fs::File::create(&target)?;
                file.write_all(&data)?;
            }
            Kind::Symbolic => {
                if fs::symlink_metadata(&target).is_ok() {
                    fs::remove_file(&target)?;
                }
                std::os::unix::fs::symlink(&link, &target)?;
                continue;
            }
            Kind::Hard => {
                // Where what it links to was not unpacked, tarfile unpacks the member it names
                // again; nothing here packs a hard link, so that is refused instead.
                let source = into.join(&link);
                if !source.exists() {
                    return Err(refused(format!(
                        "{name:?} links to {link:?}, which is not there"
                    )));
                }
                if fs::symlink_metadata(&target).is_ok() {
                    fs::remove_file(&target)?;
                }
                fs::hard_link(source, &target)?;
            }
            Kind::Special => unreachable!("refused by the filter"),
        }
        fs::set_permissions(&target, fs::Permissions::from_mode(mode))?;
        utime(&target, mtime)?;
    }
    directories.sort_by(|one, other| other.0.cmp(&one.0));
    for (name, mtime) in directories {
        utime(&into.join(name), mtime)?;
    }
    Ok(())
}

/// The name a member is unpacked at, or why the `data` filter refuses it.
fn filtered(name: &str, link: &str, kind: Kind, dest: &Path) -> io::Result<String> {
    let name = name.trim_start_matches('/').to_owned();
    if !within(&resolved(&dest.join(&name)), dest) {
        return Err(refused(format!(
            "{name:?} would be extracted outside the destination"
        )));
    }
    if kind == Kind::Special {
        return Err(refused(format!("{name:?} is a special file")));
    }
    if matches!(kind, Kind::Symbolic | Kind::Hard) {
        if link.starts_with('/') {
            return Err(refused(format!("{name:?} is a link to an absolute path")));
        }
        let to = if kind == Kind::Symbolic {
            let upper = Path::new(&name).parent().unwrap_or(Path::new(""));
            dest.join(upper).join(link)
        } else {
            dest.join(link)
        };
        if !within(&resolved(&to), dest) {
            return Err(refused(format!(
                "{name:?} would link outside the destination"
            )));
        }
    }
    Ok(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A ustar header block and its data, padded.
    fn member(name: &str, flag: u8, data: &[u8], link: &str, mode: u32) -> Vec<u8> {
        let mut header = [0u8; BLOCK];
        header[..name.len()].copy_from_slice(name.as_bytes());
        header[100..108].copy_from_slice(format!("{mode:07o}\0").as_bytes());
        header[124..136].copy_from_slice(format!("{:011o}\0", data.len()).as_bytes());
        header[136..148].copy_from_slice(format!("{:011o}\0", 1_700_000_000u64).as_bytes());
        header[156] = flag;
        header[157..157 + link.len()].copy_from_slice(link.as_bytes());
        header[257..263].copy_from_slice(b"ustar\0");
        header[263..265].copy_from_slice(b"00");
        header[148..156].copy_from_slice(b"        ");
        let sum: u32 = header.iter().map(|b| u32::from(*b)).sum();
        header[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        let mut out = header.to_vec();
        out.extend_from_slice(data);
        out.resize(out.len().div_ceil(BLOCK) * BLOCK, 0);
        out
    }

    fn archive(members: &[Vec<u8>]) -> Vec<u8> {
        let mut out: Vec<u8> = members.concat();
        out.extend_from_slice(&[0u8; BLOCK * 2]);
        out
    }

    #[test]
    fn files_directories_and_links_land_inside() {
        let dir = tempfile::tempdir().unwrap();
        let into = dir.path().join("into");
        let packed = archive(&[
            member("sessions/", b'5', b"", "", 0o755),
            member("sessions/one.jsonl", b'0', b"{}\n", "", 0o4777),
            member("/rooted", b'0', b"r", "", 0o640),
            member("sessions/latest", b'2', b"", "one.jsonl", 0o777),
        ]);
        extract(&packed, &into).unwrap();
        assert_eq!(fs::read(into.join("sessions/one.jsonl")).unwrap(), b"{}\n");
        let mode = fs::metadata(into.join("sessions/one.jsonl"))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o7777, 0o755);
        let mode = fs::metadata(into.join("rooted"))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o777, 0o640);
        assert_eq!(
            fs::read_link(into.join("sessions/latest")).unwrap(),
            Path::new("one.jsonl")
        );
    }

    #[test]
    fn what_would_land_outside_is_refused() {
        let dir = tempfile::tempdir().unwrap();
        let into = dir.path().join("into");
        for bad in [
            member("../out", b'0', b"x", "", 0o644),
            member("up", b'2', b"", "../../etc", 0o777),
            member("abs", b'2', b"", "/etc/passwd", 0o777),
            member("fifo", b'6', b"", "", 0o644),
        ] {
            assert!(extract(&archive(&[bad]), &into).is_err());
        }
        assert!(!dir.path().join("out").exists());
    }

    #[test]
    fn an_old_style_member_ending_in_a_slash_is_a_directory() {
        let dir = tempfile::tempdir().unwrap();
        let packed = archive(&[
            member("old/", 0, b"", "", 0o755),
            member("old/f", b'0', b"f", "", 0o644),
        ]);
        extract(&packed, dir.path()).unwrap();
        assert!(dir.path().join("old").is_dir());
        assert_eq!(fs::read(dir.path().join("old/f")).unwrap(), b"f");
    }

    #[test]
    fn global_pax_records_hold_for_every_member_after_them() {
        let dir = tempfile::tempdir().unwrap();
        let record = "18 mtime=1234567.5\n";
        let packed = archive(&[
            member("pax_global_header", b'g', record.as_bytes(), "", 0o644),
            member("a", b'0', b"a", "", 0o644),
        ]);
        extract(&packed, dir.path()).unwrap();
        let modified = fs::metadata(dir.path().join("a"))
            .unwrap()
            .modified()
            .unwrap();
        let seconds = modified
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        assert_eq!(seconds, 1234567.5);
    }

    #[test]
    fn long_names_are_read() {
        let dir = tempfile::tempdir().unwrap();
        let long = "d/".repeat(60) + "f";
        let packed = archive(&[
            member(
                "././@LongLink",
                b'L',
                format!("{long}\0").as_bytes(),
                "",
                0o644,
            ),
            member("truncated", b'0', b"long", "", 0o644),
        ]);
        extract(&packed, dir.path()).unwrap();
        assert_eq!(fs::read(dir.path().join(long)).unwrap(), b"long");
    }

    #[test]
    fn garbage_is_no_archive() {
        let dir = tempfile::tempdir().unwrap();
        assert!(extract(b"not a tar", dir.path()).is_err());
        assert!(extract(&[1u8; 1024], dir.path()).is_err());
    }
}
