//! A CLI's virtual home: a directory standing in for its own home for one process of it, built
//! as it starts and dropped when it stops. Port of `hmz.coganchor.homes` (`Virtual`, `build`,
//! `Home.drop`, `_respelled`, `SCRIPT`, `BACK`, `words`) and the `atomic.writes` dropping
//! uses; the mergers it names are [`crate::cog::mergers`]. [Unit 14]
//!
//! - what the CLI rewrites (`Virtual::rewrites`) is a *copy* of the user's own, so what it
//!   writes lands in the copy and goes with it;
//! - everything else of the user's home is *linked*, so credentials, caches and conversations
//!   are the ones it always reads and writes; a link the CLI replaced by renaming a file over
//!   it is written back as the home is dropped ([`Home::drop_home`]), unless what is there is
//!   newer;
//! - the skills directory (`Virtual::lodges`) is a directory of links to each of the user's
//!   skills, with the flow's beside them.

mod paths;
mod records;
mod scripts;

use std::collections::HashMap;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Read, Write};
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use crate::cog::mergers::{self, pyjson};

pub(crate) use paths::copytree;
pub use paths::realpath;
pub use scripts::{BACK, SCRIPT, words};

/// What one CLI's virtual home is made of, wherever it is built: `hmz.coganchor.homes.Virtual`,
/// field for field (its docstring says what each is).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Virtual {
    /// The variable that moves the CLI's home, set to the virtual one; "" for a CLI only a
    /// flag moves.
    pub variable: String,
    /// Where that home is under the user's own where the variable is unset.
    pub default: String,
    /// What under that home is copied rather than linked, relative to it.
    pub rewrites: Vec<String>,
    /// Of those, the ones kept outside the home while the variable is unset, as `(path under
    /// the home, path under ~)`.
    pub outside: Vec<(String, String)>,
    /// The user-level skills directory under the home, or "".
    pub lodges: String,
    /// A variable keeping where the CLI looks for its sign-in where the user's home puts it.
    pub secures: String,
    /// Globs of names directly under the home that are neither linked nor made.
    pub private: Vec<String>,
    /// Names directly under the home whose directory is made in the user's where missing.
    pub made: Vec<String>,
    /// Globs of names the CLI may make that are moved into the user's home as it is dropped.
    pub kept: Vec<String>,
    /// The flow's own skills, as `(name, the directory holding its SKILL.md)`.
    pub skills: Vec<(String, String)>,
    /// The flag that moves the home where no variable does, or "".
    pub flag: String,
    /// What a driver merges in once it is built, as `(merger, its argument as JSON)`.
    pub merges: Vec<(String, String)>,
    /// Where the CLI writes down paths of its home, as `(database glob, table, column)`.
    pub records: Vec<(String, String, String)>,
    /// The absolute directory its conversations are kept in instead of the user's home, or "".
    pub keeps: String,
}

impl Virtual {
    /// Reads `--home JSON`: what `Virtual.dumps` wrote, and refuses what `Virtual` refuses.
    pub fn loads(said: &str) -> Result<Virtual, String> {
        let wrong = || format!("not a virtual home: {said:?}");
        let held: Value =
            serde_json::from_str(said).map_err(|error| format!("{}: {error}", wrong()))?;
        let held = held.as_object().ok_or_else(wrong)?;
        let text = |key: &str, required: bool| -> Result<String, String> {
            match held.get(key) {
                Some(Value::String(one)) => Ok(one.clone()),
                None if !required => Ok(String::new()),
                _ => Err(wrong()),
            }
        };
        let tuples =
            |key: &str, width: usize, required: bool| -> Result<Vec<Vec<String>>, String> {
                let items = match held.get(key) {
                    Some(Value::Array(items)) => items,
                    None if !required => return Ok(Vec::new()),
                    _ => return Err(wrong()),
                };
                items
                    .iter()
                    .map(|item| {
                        let strings = |all: &Vec<Value>| -> Option<Vec<String>> {
                            all.iter()
                                .map(|one| one.as_str().map(str::to_owned))
                                .collect()
                        };
                        match (width, item) {
                            (0, Value::String(one)) => Some(vec![one.clone()]),
                            (0, _) => None,
                            (_, Value::Array(all)) if all.len() == width => strings(all),
                            _ => None,
                        }
                        .ok_or_else(wrong)
                    })
                    .collect()
            };
        let names = |key: &str| -> Result<Vec<String>, String> {
            Ok(tuples(key, 0, true)?.into_iter().flatten().collect())
        };
        let pairs = |key: &str, required: bool| -> Result<Vec<(String, String)>, String> {
            Ok(tuples(key, 2, required)?
                .into_iter()
                .map(|mut one| {
                    let second = one.pop().unwrap_or_default();
                    (one.pop().unwrap_or_default(), second)
                })
                .collect())
        };
        let spec = Virtual {
            variable: text("variable", true)?,
            default: text("default", true)?,
            rewrites: names("rewrites")?,
            outside: pairs("outside", true)?,
            lodges: text("lodges", true)?,
            secures: text("secures", true)?,
            private: names("private")?,
            made: names("made")?,
            kept: names("kept")?,
            skills: pairs("skills", true)?,
            flag: text("flag", false)?,
            merges: pairs("merges", false)?,
            records: tuples("records", 3, false)?
                .into_iter()
                .map(|one| (one[0].clone(), one[1].clone(), one[2].clone()))
                .collect(),
            keeps: text("keeps", false)?,
        };
        spec.checked()?;
        Ok(spec)
    }

    /// It, as the one JSON line `Virtual.dumps` writes: the same bytes.
    pub fn dumps(&self) -> String {
        let strings =
            |all: &[String]| Value::Array(all.iter().cloned().map(Value::String).collect());
        let pairs = |all: &[(String, String)]| {
            Value::Array(
                all.iter()
                    .map(|(one, other)| {
                        Value::Array(vec![one.clone().into(), other.clone().into()])
                    })
                    .collect(),
            )
        };
        let mut held = Map::new();
        held.insert("variable".into(), self.variable.clone().into());
        held.insert("default".into(), self.default.clone().into());
        held.insert("rewrites".into(), strings(&self.rewrites));
        held.insert("outside".into(), pairs(&self.outside));
        held.insert("lodges".into(), self.lodges.clone().into());
        held.insert("secures".into(), self.secures.clone().into());
        held.insert("private".into(), strings(&self.private));
        held.insert("made".into(), strings(&self.made));
        held.insert("kept".into(), strings(&self.kept));
        held.insert("skills".into(), pairs(&self.skills));
        held.insert("flag".into(), self.flag.clone().into());
        held.insert("merges".into(), pairs(&self.merges));
        held.insert(
            "records".into(),
            Value::Array(
                self.records
                    .iter()
                    .map(|(one, table, column)| {
                        Value::Array(vec![
                            one.clone().into(),
                            table.clone().into(),
                            column.clone().into(),
                        ])
                    })
                    .collect(),
            ),
        );
        held.insert("keeps".into(), self.keeps.clone().into());
        pyjson::dumps(&Value::Object(held), pyjson::Layout::Compact)
    }

    /// `Virtual.__post_init__`: refuses a virtual home that would name something outside
    /// itself.
    pub fn checked(&self) -> Result<(), String> {
        for name in [&self.variable, &self.secures] {
            if !name.is_empty() && !name.chars().all(|one| one == '_' || one.is_alphanumeric()) {
                return Err(format!("unsupported variable {name:?}"));
            }
        }
        if self.variable.is_empty() && !self.flag.starts_with("--") {
            return Err("a virtual home needs the variable or the flag that moves it".into());
        }
        let named = std::iter::once(&self.default)
            .chain(&self.rewrites)
            .chain(self.outside.iter().map(|(_, there)| there))
            .chain(std::iter::once(&self.lodges))
            .chain(&self.made)
            .chain(self.skills.iter().map(|(name, _)| name));
        for one in named {
            if one.starts_with('/') || one.split('/').any(|part| part == "..") {
                return Err(format!("unsupported path {one:?} in a virtual home"));
            }
        }
        if !self.keeps.is_empty() && !self.keeps.starts_with('/') {
            return Err(format!(
                "unsupported directory {:?} to keep sessions in",
                self.keeps
            ));
        }
        Ok(())
    }

    /// The user's own home for this CLI, as a process with that environment finds it.
    pub fn real(&self, environ: &HashMap<String, String>) -> PathBuf {
        if let Some(moved) = environ
            .get(&self.variable)
            .filter(|one| !self.variable.is_empty() && !one.is_empty())
        {
            return paths::pure(moved);
        }
        paths::pure(&format!("{}/{}", user_home(environ), self.default))
    }
}

/// `environ.get("HOME") or Path.home()`.
fn user_home(environ: &HashMap<String, String>) -> String {
    if let Some(home) = environ.get("HOME").filter(|one| !one.is_empty()) {
        return home.clone();
    }
    if let Some(home) = std::env::var("HOME").ok().filter(|one| !one.is_empty()) {
        return home;
    }
    nix::unistd::User::from_uid(nix::unistd::getuid())
        .ok()
        .flatten()
        .map(|user| user.dir.to_string_lossy().into_owned())
        .unwrap_or_else(|| "/".to_owned())
}

/// What a supervisor answers a path of the user's home with, or `None` for one it leaves.
pub type Answered = Box<dyn Fn(&str) -> Option<String> + Send + Sync>;

/// Whether the agent a home is for may reach a path, every link in it followed.
pub type Reaches = Box<dyn Fn(&str) -> bool + Send + Sync>;

/// What [`build_with`] takes beside the virtual home: `build`'s keyword arguments.
pub struct Options {
    /// The directory to make the home in, or `None` for the system's temporary one.
    pub under: Option<PathBuf>,
    /// What a supervisor answers a path of the user's home with: a provider's own copy of a
    /// credential, which is copied in its place and written back to.
    pub answered: Answered,
    /// Whether the agent may read a path: a file it may not is never copied in.
    pub readable: Reaches,
    /// Whether it may write one: where the home is written back to as it is dropped.
    pub writable: Reaches,
}

impl Default for Options {
    fn default() -> Options {
        Options {
            under: None,
            answered: Box::new(|_| None),
            readable: Box::new(|_| true),
            writable: Box::new(|_| true),
        }
    }
}

/// A virtual home built on this machine: `hmz.coganchor.homes.Home`.
pub struct Home {
    /// Where it is, every link in its path followed: the spelling a CLI is told.
    dir: PathBuf,
    /// The user's own home it stands for.
    real: PathBuf,
    /// The variables a process started in it is started with.
    sets: Vec<(String, String)>,
    /// Globs of what of it is moved into the user's home as it is dropped.
    kept: Vec<String>,
    /// What the CLI is told after its own name: the flag naming it, for one no variable moves.
    argv: Vec<String>,
    /// The names directly in it that were links when it was built, written back if replaced.
    linked: Vec<OsString>,
    /// Where the CLI writes down paths of this home.
    records: Vec<(String, String, String)>,
    /// Where its conversations are kept instead of `real`, if anywhere.
    keeps: Option<PathBuf>,
    /// The names of `linked` that were links into `keeps`.
    held: Vec<OsString>,
    options: Options,
}

/// Builds `virtual_home` under this machine's temporary directory, for a process started with
/// this process's environment.
pub fn build(virtual_home: &Virtual) -> io::Result<Home> {
    build_with(virtual_home, &environment(), Options::default())
}

/// This process's environment, as Python's `os.environ` holds it (what is not UTF-8 left out).
fn environment() -> HashMap<String, String> {
    std::env::vars_os()
        .filter_map(|(key, value)| Some((key.into_string().ok()?, value.into_string().ok()?)))
        .collect()
}

/// Builds one virtual home on this machine, for one process of the CLI about to start in
/// `environ`: `homes.build`.
///
/// # Errors
///
/// Whatever stopped it being built -- a turn that must not run, since a CLI pointed at half a
/// home is one that has lost its settings -- with nothing of it left; `InvalidInput` for a
/// merge no merger has, and whatever a merger refused.
pub fn build_with(
    spec: &Virtual,
    environ: &HashMap<String, String>,
    options: Options,
) -> io::Result<Home> {
    let real = spec.real(environ);
    let dir = realpath(&mkdtemp(options.under.as_deref())?);
    let built = built(spec, environ, &real, &dir, &options).and_then(|linked| {
        for (name, argument) in &spec.merges {
            let said: Value = serde_json::from_str(argument)
                .map_err(|error| io::Error::new(io::ErrorKind::InvalidInput, error))?;
            mergers::merge(name, &dir, &said)?;
        }
        Ok(linked)
    });
    let (linked, held) = match built {
        Ok(one) => one,
        Err(error) => {
            let _ = fs::remove_dir_all(&dir);
            return Err(error);
        }
    };
    // What a merge made the home's own in place of a link is the driver's, never written back.
    let linked: Vec<OsString> = linked
        .into_iter()
        .filter(|one| is_link(&dir.join(one)))
        .collect();
    let held: Vec<OsString> = held
        .into_iter()
        .filter(|one| linked.contains(one))
        .collect();
    let mut sets = Vec::new();
    if !spec.variable.is_empty() {
        sets.push((spec.variable.clone(), dir.to_string_lossy().into_owned()));
    }
    let mut argv = Vec::new();
    if !spec.flag.is_empty() {
        // Relative to where the default home is, the only way such a flag takes one.
        let whence = paths::pure(&format!("{}/{}", user_home(environ), spec.default));
        let parent = whence.parent().unwrap_or(Path::new("/"));
        argv.push(format!("{}={}", spec.flag, paths::relpath(&dir, parent)));
    }
    if !spec.secures.is_empty() && !environ.contains_key(&spec.secures) {
        // The user's own value of the home variable, or nothing: Claude Code names its
        // keychain item and finds `.credentials.json` by this.
        let theirs = environ.get(&spec.variable).cloned().unwrap_or_default();
        sets.push((spec.secures.clone(), theirs));
    }
    Ok(Home {
        dir,
        real,
        sets,
        kept: spec.kept.clone(),
        argv,
        linked,
        records: spec.records.clone(),
        keeps: (!spec.keeps.is_empty()).then(|| paths::pure(&spec.keeps)),
        held,
        options,
    })
}

/// `tempfile.mkdtemp(prefix="hmz-home-", dir=under)`: a directory of its own, `0700`.
fn mkdtemp(under: Option<&Path>) -> io::Result<PathBuf> {
    const CHARACTERS: &[u8] = b"abcdefghijklmnopqrstuvwxyz0123456789_";
    let under = match under {
        Some(one) => one.to_path_buf(),
        None => std::env::temp_dir(),
    };
    let under = if under.is_absolute() {
        under
    } else {
        std::env::current_dir()?.join(under)
    };
    loop {
        let name: String = (0..8)
            .map(|_| CHARACTERS[rand::random_range(0..CHARACTERS.len())] as char)
            .collect();
        let at = under.join(format!("hmz-home-{name}"));
        match fs::DirBuilder::new().mode(0o700).create(&at) {
            Ok(()) => return Ok(at),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
}

fn is_link(at: &Path) -> bool {
    fs::symlink_metadata(at).is_ok_and(|one| one.file_type().is_symlink())
}

/// Python's `fnmatch.fnmatchcase(name, one)` for any of `globs`.
fn globbed(name: &str, globs: &[String]) -> bool {
    globs.iter().any(|one| paths::fnmatch(name, one))
}

/// `at.symlink_to(to)`, leaving one already there as it is: whether it linked it.
fn link(at: &Path, to: &Path) -> io::Result<bool> {
    match std::os::unix::fs::symlink(to, at) {
        Ok(()) => Ok(true),
        Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Ok(false),
        Err(error) => Err(error),
    }
}

/// Fills a virtual home in (`homes._built`), returning the names directly in it that it linked
/// to the user's home or to where conversations are kept, and of those the latter.
fn built(
    spec: &Virtual,
    environ: &HashMap<String, String>,
    real: &Path,
    at: &Path,
    options: &Options,
) -> io::Result<(Vec<OsString>, Vec<OsString>)> {
    let mut linked = Vec::new();
    let mut held = Vec::new();
    let keeps = (!spec.keeps.is_empty()).then(|| paths::pure(&spec.keeps));
    let sessions = keeps.clone().unwrap_or_else(|| real.to_path_buf());
    let moved = environ
        .get(&spec.variable)
        .is_some_and(|one| !one.is_empty() && !spec.variable.is_empty());
    for one in &spec.rewrites {
        let mut whence = paths::pure(&format!("{}/{one}", real.display()));
        if !moved {
            for (name, there) in &spec.outside {
                if name == one {
                    whence = paths::pure(&format!("{}/{there}", user_home(environ)));
                }
            }
        }
        // `answered(...) or whence`: an empty answer is none.
        let answered = (options.answered)(&whence.to_string_lossy()).filter(|one| !one.is_empty());
        let source = answered.map_or(whence, |one| paths::pure(&one));
        let into = paths::pure(&format!("{}/{one}", at.display()));
        if let Some(parent) = into.parent() {
            fs::create_dir_all(parent)?;
        }
        if source.is_dir() {
            // A directory the CLI writes into starts empty: none of the user's is read back.
            match fs::create_dir(&into) {
                Err(error) if !(error.kind() == io::ErrorKind::AlreadyExists && into.is_dir()) => {
                    return Err(error);
                }
                _ => {}
            }
        } else if source.is_file() {
            if (options.readable)(&realpath(&source).to_string_lossy()) {
                paths::copy2(&source, &into)?;
            } else {
                tracing::warn!(
                    "not copying {}: the agent may not read it",
                    source.display()
                );
            }
        }
    }
    let copied: Vec<&str> = spec
        .rewrites
        .iter()
        .map(|one| one.split('/').next().unwrap_or(""))
        .collect();
    for name in &spec.made {
        if copied.contains(&name.as_str()) || *name == spec.lodges {
            continue;
        }
        if !name.contains('.') {
            fs::create_dir_all(sessions.join(name))?;
        } else if !sessions.is_dir() {
            fs::create_dir_all(&sessions)?;
        }
        if link(&at.join(name), &sessions.join(name))? {
            linked.push(OsString::from(name));
            held.push(OsString::from(name));
        }
    }
    if let Some(keeps) = keeps.as_ref().filter(|_| !spec.kept.is_empty()) {
        // A database named for its schema's version: whichever the user's home or the kept
        // directory has, linked to the kept one -- there or not yet.
        fs::create_dir_all(keeps)?;
        let mut names = std::collections::BTreeSet::new();
        for root in [real, keeps.as_path()] {
            if !root.is_dir() {
                continue;
            }
            for entry in fs::read_dir(root)? {
                // Matched as Python spells a name it cannot decode, linked by its own bytes.
                let name = entry?.file_name();
                if globbed(&name.to_string_lossy(), &spec.kept) {
                    names.insert(name);
                }
            }
        }
        for name in names {
            if link(&at.join(&name), &keeps.join(&name))? {
                linked.push(name.clone());
                held.push(name);
            }
        }
    }
    if real.is_dir() {
        for entry in fs::read_dir(real)? {
            let name = entry?.file_name();
            let said = name.to_string_lossy();
            if copied.contains(&&*said) || said == spec.lodges.as_str() {
                continue;
            }
            if globbed(&said, &spec.private) {
                continue;
            }
            if link(&at.join(&name), &real.join(&name))? {
                linked.push(name);
            }
        }
    }
    if !spec.lodges.is_empty() {
        let into = paths::pure(&format!("{}/{}", at.display(), spec.lodges));
        fs::create_dir_all(&into)?;
        let theirs = paths::pure(&format!("{}/{}", real.display(), spec.lodges));
        if theirs.is_dir() {
            for entry in fs::read_dir(&theirs)? {
                let name = entry?.file_name();
                if !spec.skills.iter().any(|(one, _)| *one.as_str() == *name) {
                    link(&into.join(&name), &theirs.join(&name))?;
                }
            }
        }
        for (name, whence) in &spec.skills {
            link(&into.join(name), &paths::pure(whence))?;
        }
    }
    Ok((linked, held))
}

impl Home {
    /// Its directory.
    pub fn dir(&self) -> &Path {
        &self.dir
    }

    /// The user's own home it stands for.
    pub fn real(&self) -> &Path {
        &self.real
    }

    /// The names directly in it that are links to the user's home (or to where conversations
    /// are kept), written back as it is dropped where the CLI replaced one.
    pub fn linked(&self) -> &[OsString] {
        &self.linked
    }

    /// The variables pointing the CLI at it, to set over the environment it would have had.
    pub fn environ(&self) -> Vec<(OsString, OsString)> {
        self.sets
            .iter()
            .map(|(key, value)| (key.into(), value.into()))
            .collect()
    }

    /// Arguments to put after the program's name.
    pub fn argv(&self) -> Vec<OsString> {
        self.argv.iter().map(OsString::from).collect()
    }

    /// Writes back what the session changed, respells its records, and removes the directory
    /// (`Home.drop`). Takes away the copies and the links, never what a link points at.
    ///
    /// A path of this home a database holds is said again with its links followed first,
    /// while they are there to follow. A link the CLI replaced is then written back to what it
    /// stood for (or what a supervisor answers that with): a file whole and atomically, a
    /// directory a file at a time; never over one that is newer, nor where the agent may not
    /// write, nor from a file it may not read. What the CLI made that is the user's to keep
    /// (`kept`) and that the user's home has none of yet is moved there. Never fails on what
    /// it could not write back, which is logged: only the removal's own failure is said.
    pub fn drop_home(self) -> io::Result<()> {
        let moved: &[String] = if self.keeps.is_some() {
            &self.kept
        } else {
            &[]
        };
        records::respelled(&self.dir, &self.records, moved, &*self.options.writable);
        for name in &self.linked {
            let whence = match &self.keeps {
                Some(keeps) if self.held.contains(name) => keeps.clone(),
                _ => self.real.clone(),
            };
            let entry = self.dir.join(name);
            if is_link(&entry) || !entry.exists() {
                continue;
            }
            if entry.is_dir() {
                let mut files = Vec::new();
                if let Err(why) = walk(&entry, &mut files) {
                    tracing::warn!("could not write {} back: {why}", entry.display());
                    continue;
                }
                files.sort();
                for one in files {
                    let under = one.strip_prefix(&entry).unwrap_or(&one);
                    self.back(&one, &whence.join(name).join(under));
                }
            } else {
                self.back(&entry, &whence.join(name));
            }
        }
        let into = self.keeps.clone().unwrap_or_else(|| self.real.clone());
        if !self.kept.is_empty() {
            // Any failure ends the moving, as Python's `contextlib.suppress(OSError)` does.
            let _ = (|| -> io::Result<()> {
                for entry in fs::read_dir(&self.dir)? {
                    let entry = entry?;
                    let name = entry.file_name();
                    let there = into.join(&name);
                    // Nor over a link, which a move across devices would write through.
                    if !entry.file_type()?.is_symlink()
                        && globbed(&name.to_string_lossy(), &self.kept)
                        && fs::symlink_metadata(&there).is_err()
                    {
                        paths::move_to(&entry.path(), &there)?;
                    }
                }
                Ok(())
            })();
        }
        // `shutil.rmtree(at, ignore_errors=True)`: what cannot be removed is left.
        if let Err(why) = fs::remove_dir_all(&self.dir) {
            tracing::warn!("could not remove {}: {why}", self.dir.display());
        }
        Ok(())
    }

    /// Writes one file the CLI saved in place of a link back to where the link pointed
    /// (`homes._back`). Never fails: this is the end of a turn.
    fn back(&self, entry: &Path, whence: &Path) {
        let answered =
            (self.options.answered)(&whence.to_string_lossy()).filter(|one| !one.is_empty());
        let there = realpath(&answered.map_or_else(|| whence.to_path_buf(), PathBuf::from));
        let wrote = (|| -> io::Result<()> {
            if !(self.options.readable)(&realpath(entry).to_string_lossy())
                || !(self.options.writable)(&there.to_string_lossy())
            {
                tracing::warn!(
                    "not writing {} back to {}: the agent may not reach it",
                    entry.display(),
                    there.display()
                );
                return Ok(());
            }
            let now = fs::metadata(entry)?;
            let was = match fs::metadata(&there) {
                Ok(one) => Some(one),
                Err(error) if error.kind() == io::ErrorKind::NotFound => None,
                Err(error) => return Err(error),
            };
            if let Some(was) = &was {
                let newer = (was.mtime(), was.mtime_nsec()) >= (now.mtime(), now.mtime_nsec());
                if !was.file_type().is_file() || newer {
                    return Ok(()); // saved there since, or not a file to write over
                }
            }
            if let Some(parent) = there.parent() {
                fs::create_dir_all(parent)?;
            }
            let mode = was.as_ref().unwrap_or(&now).permissions().mode() & 0o7777;
            writes(&there, &mut fs::File::open(entry)?, mode)?;
            paths::utime(&there, &now)
        })();
        if let Err(why) = wrote {
            tracing::warn!(
                "could not write {} back to {}: {why}",
                entry.display(),
                there.display()
            );
        }
    }
}

/// Every file under `at` that is not a link, links to directories not followed: what
/// `entry.rglob("*")` filtered by `is_file() and not is_symlink()` gives.
fn walk(at: &Path, files: &mut Vec<PathBuf>) -> io::Result<()> {
    for entry in fs::read_dir(at)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if kind.is_dir() {
            // What cannot be listed below is passed over, as `rglob` passes it over.
            let _ = walk(&entry.path(), files);
        } else if kind.is_file() {
            files.push(entry.path());
        }
    }
    Ok(())
}

/// `atomic.writes(at, reading, mode=mode)`: replaces a file with what is read, whole and on
/// disk before it is moved into place, written beside it under a name nothing else has with
/// `mode` set before anything is written.
fn writes(at: &Path, reading: &mut dyn Read, mode: u32) -> io::Result<()> {
    let name = at
        .file_name()
        .map(|one| one.to_string_lossy().into_owned())
        .unwrap_or_default();
    let (beside, mut file) = loop {
        let token = hex::encode(rand::random::<[u8; 8]>());
        let beside = at.with_file_name(format!(".{name}.{token}.new"));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&beside)
        {
            Ok(file) => break (beside, file),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    };
    let written = (|| -> io::Result<()> {
        // Exactly, which is more than the umask allows.
        file.set_permissions(fs::Permissions::from_mode(mode))?;
        io::copy(reading, &mut file)?;
        file.flush()?;
        file.sync_all()?;
        drop(file);
        fs::rename(&beside, at)
    })();
    if written.is_err() {
        let _ = fs::remove_file(&beside);
    }
    written
}
