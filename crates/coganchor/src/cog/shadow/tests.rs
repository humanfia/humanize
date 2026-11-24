//! The mirror kept against a target held in a map: `tests/unit/coganchor/test_shadow.py`,
//! case for case, and the ledger shared with Python's `_Ledger` (ignored by default: it needs
//! `uv` and the repository's Python; run with `cargo test -- --ignored`).

use std::collections::BTreeMap;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use serde_json::{Value, json};

use super::*;

/// A file, directory or link on the fake target.
#[derive(Clone, Debug)]
struct Entry {
    kind: &'static str,
    body: Vec<u8>,
    mode: u32,
    mtime_ns: i64,
    target: String,
}

impl Entry {
    fn file(body: &[u8]) -> Entry {
        Entry {
            kind: "file",
            body: body.to_vec(),
            mode: 0o100644,
            mtime_ns: 1_000_000_000,
            target: String::new(),
        }
    }

    fn dir() -> Entry {
        Entry {
            kind: "dir",
            mode: 0o40755,
            ..Entry::file(b"")
        }
    }

    fn link(target: &str) -> Entry {
        Entry {
            kind: "link",
            mode: 0o120777,
            target: target.into(),
            ..Entry::file(b"")
        }
    }
}

type ListHook = Box<dyn Fn(&str) -> Option<Result<Meta, RemoteError>> + Send + Sync>;
type WriteHook = Box<dyn Fn(&str) + Send + Sync>;

/// A target held in a map of virtual paths, answering as `RemoteClient` does.
#[derive(Default)]
struct Target {
    tree: Mutex<BTreeMap<String, Entry>>,
    listed: Mutex<Vec<String>>,
    read: Mutex<Vec<String>>,
    written: Mutex<BTreeMap<String, Vec<u8>>>,
    /// Called before a listing; an answer it gives is the listing's.
    on_list: Mutex<Option<ListHook>>,
    /// Called after a write is taken.
    on_write: Mutex<Option<WriteHook>>,
    /// What a read fails with, if anything.
    read_fails: Mutex<Option<RemoteError>>,
}

impl Target {
    fn put(&self, path: &str, entry: Entry) {
        self.tree.lock().unwrap().insert(path.into(), entry);
    }

    fn listed(&self) -> Vec<String> {
        self.listed.lock().unwrap().clone()
    }

    fn read(&self) -> Vec<String> {
        self.read.lock().unwrap().clone()
    }

    fn written(&self) -> BTreeMap<String, Vec<u8>> {
        self.written.lock().unwrap().clone()
    }
}

impl Remote for Target {
    fn listdir(&self, path: &str) -> Result<Meta, RemoteError> {
        self.listed.lock().unwrap().push(path.into());
        if let Some(hook) = &*self.on_list.lock().unwrap()
            && let Some(answer) = hook(path)
        {
            return answer;
        }
        let tree = self.tree.lock().unwrap();
        match tree.get(path) {
            None => return Err(RemoteError::new(libc::ENOENT, "gone")),
            Some(held) if held.kind != "dir" => {
                return Err(RemoteError::new(libc::ENOTDIR, "not a directory"));
            }
            Some(_) => {}
        }
        let entries: Vec<Value> = tree
            .iter()
            .filter_map(|(name, entry)| {
                let (parent, base) = name.rsplit_once('/')?;
                (parent == path && name != path).then(|| {
                    let mut said = json!({
                        "name": base,
                        "kind": entry.kind,
                        "mode": entry.mode,
                        "size": entry.body.len(),
                        "mtime_ns": entry.mtime_ns,
                    });
                    if entry.kind == "link" {
                        said["target"] = json!(entry.target);
                    }
                    said
                })
            })
            .collect();
        Ok(json!({ "entries": entries }).as_object().unwrap().clone())
    }

    fn read_file(&self, path: &str) -> Result<(Vec<u8>, Meta), RemoteError> {
        self.read.lock().unwrap().push(path.into());
        if let Some(why) = self.read_fails.lock().unwrap().clone() {
            return Err(why);
        }
        let entry = self.tree.lock().unwrap()[path].clone();
        let meta = json!({"size": entry.body.len(), "mtime_ns": entry.mtime_ns});
        Ok((entry.body, meta.as_object().unwrap().clone()))
    }

    fn write_file(&self, path: &str, data: &[u8], mode: Option<u32>) -> Result<Meta, RemoteError> {
        self.written
            .lock()
            .unwrap()
            .insert(path.into(), data.to_vec());
        self.put(
            path,
            Entry {
                mode: mode.unwrap_or(0o100644),
                mtime_ns: 2_000_000_000,
                ..Entry::file(data)
            },
        );
        if let Some(hook) = &*self.on_write.lock().unwrap() {
            hook(path);
        }
        let meta = json!({"size": data.len(), "mtime_ns": 2_000_000_000i64});
        Ok(meta.as_object().unwrap().clone())
    }
}

/// Routes everything under one local directory to the target, and nothing else.
struct Layout {
    local: String,
    virtual_root: String,
}

impl Mapping for Layout {
    fn virtual_path(&self, local: &str) -> Option<String> {
        let rest = local.strip_prefix(&self.local)?;
        (rest.is_empty() || rest.starts_with('/')).then(|| format!("{}{rest}", self.virtual_root))
    }
}

/// A shadow tree at `<tmp>/mirror`, of a workspace the target calls `/w`.
struct Mirror {
    _dir: tempfile::TempDir,
    tmp: PathBuf,
    root: PathBuf,
    target: Arc<Target>,
    tree: ShadowTree,
}

impl Mirror {
    fn new() -> Mirror {
        let dir = tempfile::tempdir().unwrap();
        let tmp = dir.path().canonicalize().unwrap();
        let root = tmp.join("mirror");
        let target = Arc::new(Target::default());
        target.put("/w", Entry::dir());
        target.put(
            "/w/a.txt",
            Entry {
                mode: 0o100640,
                mtime_ns: 5_000_000_000,
                ..Entry::file(b"hello")
            },
        );
        target.put("/w/empty", Entry::file(b""));
        target.put("/w/sub", Entry::dir());
        target.put("/w/sub/deep.txt", Entry::file(b"deep"));
        target.put("/w/link", Entry::link("a.txt"));
        let mut mirror = Mirror {
            _dir: dir,
            tmp,
            root,
            target,
            tree: ShadowTree::build(Arc::new(Target::default()), Arc::new(nothing()), None),
        };
        mirror.tree = mirror.turn(false);
        mirror
    }

    /// Another tree on this mirror; `shared`, joining the ledger the registry keeps for it.
    fn turn(&self, shared: bool) -> ShadowTree {
        let mapping = Arc::new(Layout {
            local: self.root.to_str().unwrap().into(),
            virtual_root: "/w".into(),
        });
        let entry = registry::registry_entry(&self.tmp.join("shadows"), &self.root);
        ShadowTree::build(
            self.target.clone(),
            mapping,
            shared.then_some((entry.as_path(), self.root.as_path())),
        )
    }

    fn path(&self, name: &str) -> PathBuf {
        if name.is_empty() {
            self.root.clone()
        } else {
            self.root.join(name)
        }
    }
}

fn nothing() -> Layout {
    Layout {
        local: "/nowhere-at-all".into(),
        virtual_root: "/".into(),
    }
}

fn names(dir: &Path) -> Vec<String> {
    let mut found: Vec<String> = fs::read_dir(dir)
        .unwrap()
        .map(|one| one.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    found.sort();
    found
}

fn listed(paths: &[&str]) -> Vec<String> {
    paths.iter().map(|one| one.to_string()).collect()
}

fn written(pairs: &[(&str, &[u8])]) -> BTreeMap<String, Vec<u8>> {
    pairs
        .iter()
        .map(|(path, body)| (path.to_string(), body.to_vec()))
        .collect()
}

#[test]
fn a_directory_is_mirrored_as_placeholders() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert_eq!(names(&m.root), ["a.txt", "empty", "link", "sub"]);
    let placeholder = fs::symlink_metadata(m.path("a.txt")).unwrap();
    assert_eq!(placeholder.size(), 5);
    assert_eq!(placeholder.permissions().mode() & 0o7777, 0o640);
    assert_eq!(mtime_ns(&placeholder), 5_000_000_000);
    assert_eq!(placeholder.atime(), 5);
    assert!(m.path("sub").is_dir());
    assert_eq!(fs::read_link(m.path("link")).unwrap(), Path::new("a.txt"));
    assert_eq!(m.target.listed(), listed(&["/w"]));
}

#[test]
fn a_directory_is_listed_once_per_generation() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert_eq!(m.target.listed(), listed(&["/w"]));
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert_eq!(m.target.listed(), listed(&["/w", "/w"]));
}

#[test]
fn a_path_mirrors_the_directory_holding_it() {
    let m = Mirror::new();
    m.tree.ensure_path(&m.path("sub/deep.txt")).unwrap();
    assert_eq!(m.target.listed(), listed(&["/w/sub"]));
    assert_eq!(fs::metadata(m.path("sub/deep.txt")).unwrap().len(), 4);
}

#[test]
fn a_path_outside_the_workspace_is_left_alone() {
    let m = Mirror::new();
    let elsewhere = m.tmp.join("elsewhere");
    m.tree.ensure_directory(&elsewhere).unwrap();
    m.tree.ensure_content(&elsewhere.join("f")).unwrap();
    m.tree.note_write(&elsewhere.join("f"));
    assert!(m.target.listed().is_empty());
    assert_eq!(m.tree.flush_counted().unwrap(), 0);
}

#[test]
fn what_vanished_on_the_target_vanishes_here() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.target.tree.lock().unwrap().remove("/w/a.txt");
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert!(!m.path("a.txt").exists());
}

#[test]
fn a_kind_changed_on_the_target_is_changed_here() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.target.put("/w/a.txt", Entry::dir());
    m.target.put("/w/sub", Entry::file(b"now a file"));
    m.target.put("/w/link", Entry::link("empty"));
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert!(m.path("a.txt").is_dir());
    assert!(m.path("sub").is_file());
    assert_eq!(fs::read_link(m.path("link")).unwrap(), Path::new("empty"));
}

#[test]
fn a_link_that_became_a_file_does_not_truncate_what_it_led_to() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("a.txt")).unwrap();
    m.target.put("/w/link", Entry::file(b"own"));
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert!(!fs::symlink_metadata(m.path("link")).unwrap().is_symlink());
    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
}

#[test]
fn a_directory_gone_on_the_target_is_dropped_here() {
    for missing in [libc::ENOENT, libc::ENOTDIR, libc::EACCES] {
        let m = Mirror::new();
        m.tree.ensure_directory(&m.path("sub")).unwrap();
        assert!(m.path("sub").is_dir());
        *m.target.on_list.lock().unwrap() = Some(Box::new(move |_| {
            Some(Err(RemoteError::new(missing, "gone")))
        }));
        m.tree.invalidate();
        m.tree.ensure_directory(&m.path("sub")).unwrap();
        assert!(!m.path("sub").exists(), "errno {missing}");
    }
}

#[test]
fn any_other_failure_to_list_is_raised() {
    let m = Mirror::new();
    *m.target.on_list.lock().unwrap() =
        Some(Box::new(|_| Some(Err(RemoteError::new(libc::EIO, "disk")))));
    let why = m.tree.ensure_directory(&m.path("")).unwrap_err();
    assert_eq!((why.errno, why.strerror.as_str()), (libc::EIO, "disk"));
}

#[test]
fn content_is_fetched_once() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("a.txt")).unwrap();
    m.tree.ensure_content(&m.path("a.txt")).unwrap();
    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
    assert_eq!(m.target.read(), listed(&["/w/a.txt"]));
    let fetched = fs::metadata(m.path("a.txt")).unwrap();
    assert_eq!(mtime_ns(&fetched), 5_000_000_000);
    assert_eq!(fetched.permissions().mode() & 0o7777, 0o640);
    assert!(
        !names(&m.root)
            .iter()
            .any(|name| name.ends_with(FETCH_SUFFIX))
    );
}

#[test]
fn an_empty_file_needs_nothing_fetched() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("empty")).unwrap();
    assert!(m.target.read().is_empty());
}

#[test]
fn a_link_is_followed_to_the_file_it_names() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("link")).unwrap();
    assert_eq!(m.target.read(), listed(&["/w/a.txt"]));
    assert_eq!(fs::read(m.path("link")).unwrap(), b"hello");
}

#[test]
fn a_failed_fetch_leaves_the_placeholder_and_no_scratch() {
    let m = Mirror::new();
    *m.target.read_fails.lock().unwrap() = Some(RemoteError::new(libc::EIO, "torn"));
    let why = m.tree.ensure_content(&m.path("a.txt")).unwrap_err();
    assert_eq!(why.strerror, "torn");
    assert_eq!(names(&m.root), ["a.txt", "empty", "link", "sub"]);
    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"\0\0\0\0\0");
}

#[test]
fn a_local_write_is_pushed_on_flush() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("a.txt")).unwrap();
    m.tree.note_write(&m.path("a.txt"));
    assert_eq!(m.tree.flush_counted().unwrap(), 0); // nothing changed yet
    fs::write(m.path("a.txt"), b"changed").unwrap();
    assert_eq!(m.tree.flush_counted().unwrap(), 1);
    assert_eq!(m.target.written(), written(&[("/w/a.txt", b"changed")]));
    assert_eq!(m.tree.flush_counted().unwrap(), 0);
}

#[test]
fn a_new_file_is_pushed_and_a_removed_one_is_not() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    fs::write(m.path("new.txt"), b"fresh").unwrap();
    m.tree.note_write(&m.path("new.txt"));
    m.tree.note_write(&m.path("never-made"));
    m.tree.note_write(&m.path("sub"));
    assert_eq!(m.tree.flush_counted().unwrap(), 1);
    assert_eq!(m.target.written(), written(&[("/w/new.txt", b"fresh")]));
}

#[test]
fn a_forgotten_path_is_not_pushed() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    fs::write(m.path("new.txt"), b"x").unwrap();
    m.tree.note_write(&m.path("new.txt"));
    m.tree.note_removed(&m.path("new.txt"));
    assert_eq!(m.tree.flush_counted().unwrap(), 0);
}

#[test]
fn a_renamed_placeholder_is_fetched_under_its_new_name() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    fs::rename(m.path("a.txt"), m.path("b.txt")).unwrap();
    m.tree.note_renamed(&m.path("a.txt"), &m.path("b.txt"));
    let moved = m.target.tree.lock().unwrap()["/w/a.txt"].clone();
    m.target.put("/w/b.txt", moved);
    m.tree.ensure_content(&m.path("b.txt")).unwrap();
    assert_eq!(fs::read(m.path("b.txt")).unwrap(), b"hello");
    assert_eq!(m.target.read(), listed(&["/w/b.txt"]));
}

#[test]
fn a_duplicated_placeholder_is_fetched_through_the_new_name() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    fs::hard_link(m.path("a.txt"), m.path("hard.txt")).unwrap();
    m.tree
        .note_linked(&m.path("a.txt"), &m.path("hard.txt"))
        .unwrap();
    m.tree
        .note_linked(&m.path("unknown"), &m.path("nothing"))
        .unwrap();
    let same = m.target.tree.lock().unwrap()["/w/a.txt"].clone();
    m.target.put("/w/hard.txt", same);
    m.tree.ensure_content(&m.path("hard.txt")).unwrap();
    assert_eq!(m.target.read(), listed(&["/w/hard.txt"]));
}

#[test]
fn a_record_matches_the_target_by_kind_size_and_time() {
    let record = FileRecord::new("file", 0o100644, 5, 9);
    for (kind, size, mtime_ns, matches) in [
        ("file", 5, 9, true),
        ("file", 6, 9, false),
        ("file", 5, 8, false),
        ("link", 5, 9, false),
    ] {
        let entry = Listed {
            name: "x".into(),
            kind: kind.into(),
            mode: 0,
            size,
            mtime_ns,
            target: String::new(),
        };
        assert_eq!(record.matches_remote(&entry), matches);
    }
}

#[test]
fn a_file_written_while_its_directory_is_listed_waits_for_the_next_flush() {
    let m = Mirror::new();
    m.tree.ensure_content(&m.path("a.txt")).unwrap();
    m.tree.note_write(&m.path("a.txt"));
    m.tree.note_write(&m.path("late.txt"));
    let (a, late) = (m.path("a.txt"), m.path("late.txt"));
    // Another turn's writes, landing between the flush and the listing it was for.
    *m.target.on_list.lock().unwrap() = Some(Box::new(move |_| {
        fs::write(&a, b"edited").unwrap();
        fs::write(&late, b"late").unwrap();
        None
    }));
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();

    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"edited");
    assert_eq!(fs::read(m.path("late.txt")).unwrap(), b"late");
    assert_eq!(m.tree.flush_counted().unwrap(), 2);
    assert_eq!(
        m.target.written(),
        written(&[("/w/a.txt", b"edited"), ("/w/late.txt", b"late")])
    );
}

#[test]
fn a_placeholder_written_over_is_not_fetched_over() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.tree.note_write(&m.path("a.txt"));
    fs::write(m.path("a.txt"), b"new").unwrap(); // opened to truncate, so not fetched

    m.tree.ensure_content(&m.path("a.txt")).unwrap();

    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"new");
    assert!(m.target.read().is_empty());
}

#[test]
fn a_write_landing_while_its_file_is_pushed_is_pushed_too() {
    let m = Mirror::new();
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.tree.note_write(&m.path("new.txt"));
    fs::write(m.path("new.txt"), b"half").unwrap();
    let racing = Mutex::new(vec![b"half and the rest".to_vec()]);
    let new = m.path("new.txt");
    *m.target.on_write.lock().unwrap() = Some(Box::new(move |_| {
        if let Some(rest) = racing.lock().unwrap().pop() {
            // A different size, so seen whatever the clock's resolution.
            fs::write(&new, rest).unwrap();
        }
    }));
    assert_eq!(m.tree.flush_counted().unwrap(), 1);
    assert_eq!(m.tree.flush_counted().unwrap(), 1);
    assert_eq!(
        m.target.written(),
        written(&[("/w/new.txt", b"half and the rest")])
    );
}

// ---------------------------------------------------------- turns sharing one mirror

fn turns(m: &Mirror) -> (ShadowTree, ShadowTree) {
    (m.turn(true), m.turn(true))
}

#[test]
fn a_file_another_turn_has_not_pushed_yet_is_pushed_not_swept() {
    let m = Mirror::new();
    let (one, other) = turns(&m);
    one.ensure_directory(&m.path("")).unwrap();
    one.note_write(&m.path("made.txt"));
    fs::write(m.path("made.txt"), b"MARK").unwrap();

    other.ensure_directory(&m.path("")).unwrap();

    assert_eq!(fs::read(m.path("made.txt")).unwrap(), b"MARK");
    assert_eq!(m.target.written(), written(&[("/w/made.txt", b"MARK")]));
    assert_eq!(one.flush_counted().unwrap(), 0);
}

#[test]
fn a_file_another_turn_pushed_is_not_made_a_placeholder_again() {
    let m = Mirror::new();
    let (one, other) = turns(&m);
    one.ensure_directory(&m.path("")).unwrap();
    one.note_write(&m.path("made.txt"));
    fs::write(m.path("made.txt"), b"MARK").unwrap();
    assert_eq!(one.flush_counted().unwrap(), 1);

    other.ensure_directory(&m.path("")).unwrap();

    assert_eq!(fs::read(m.path("made.txt")).unwrap(), b"MARK");
    assert_eq!(
        (one.flush_counted().unwrap(), other.flush_counted().unwrap()),
        (0, 0)
    );
    assert_eq!(m.target.tree.lock().unwrap()["/w/made.txt"].body, b"MARK");
}

#[test]
fn what_one_turn_fetched_another_reads_as_it_is() {
    let m = Mirror::new();
    let (one, other) = turns(&m);
    one.ensure_content(&m.path("a.txt")).unwrap();

    other.ensure_directory(&m.path("")).unwrap();
    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
    other.ensure_content(&m.path("a.txt")).unwrap();

    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
    assert_eq!(m.target.read(), listed(&["/w/a.txt"]));
}

#[test]
fn a_rename_one_turn_makes_is_known_to_the_others() {
    let m = Mirror::new();
    let (one, other) = turns(&m);
    one.ensure_directory(&m.path("")).unwrap();
    other.ensure_directory(&m.path("")).unwrap();
    let moved = m.target.tree.lock().unwrap().remove("/w/a.txt").unwrap();
    m.target.put("/w/b.txt", moved);
    fs::rename(m.path("a.txt"), m.path("b.txt")).unwrap();
    one.note_renamed(&m.path("a.txt"), &m.path("b.txt"));

    other.ensure_content(&m.path("b.txt")).unwrap();

    assert_eq!(fs::read(m.path("b.txt")).unwrap(), b"hello");
}

#[test]
fn a_turn_alone_in_a_mirror_knows_nothing_of_turns_gone() {
    let m = Mirror::new();
    let (one, other) = turns(&m);
    one.ensure_content(&m.path("a.txt")).unwrap();
    one.close();
    other.close();
    // Changed while nobody worked in it, keeping the size and time it had.
    fs::write(m.path("a.txt"), b"\0\0\0\0\0").unwrap();
    set_mtime(m.path("a.txt").to_str().unwrap(), 5_000_000_000).unwrap();

    m.turn(true).ensure_content(&m.path("a.txt")).unwrap();

    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
}

#[test]
fn a_mirror_that_cannot_be_shared_is_kept_alone() {
    let m = Mirror::new();
    fs::write(m.tmp.join("blocked"), b"not a directory").unwrap();
    let entry = registry::registry_entry(&m.tmp.join("blocked"), &m.root);
    let tree = ShadowTree::build(
        m.target.clone(),
        Arc::new(Layout {
            local: m.root.to_str().unwrap().into(),
            virtual_root: "/w".into(),
        }),
        Some((&entry, &m.root)),
    );
    assert!(tree.lock().ledger.is_none());
    tree.ensure_content(&m.path("a.txt")).unwrap();
    assert_eq!(fs::read(m.path("a.txt")).unwrap(), b"hello");
    tree.close();
}

#[test]
fn a_journal_entry_is_replayed_as_python_reads_it() {
    let m = Mirror::new();
    let mut s = m.tree.lock();
    replay(&mut s, json!(["file", "/m/a", "file", 33188, 5, 9]));
    replay(&mut s, json!(["dirty", "/m/a"]));
    replay(&mut s, json!(["dirty", "/m/d/x"]));
    replay(&mut s, json!(["rename", "/m/d", "/m/e"]));
    replay(&mut s, json!(["rename", "/m/d"]));
    replay(&mut s, json!(["file", "/m/bad", "file"]));
    replay(&mut s, json!(7));
    assert_eq!(s.files["/m/a"], FileRecord::new("file", 33188, 5, 9));
    assert!(!s.files.contains_key("/m/bad"));
    assert_eq!(
        s.dirty.iter().cloned().collect::<Vec<_>>(),
        ["/m/a", "/m/e/x"]
    );
    replay(&mut s, json!(["forget", "/m"]));
    assert!(s.files.is_empty() && s.dirty.is_empty());
}

#[test]
fn paths_are_spelled_as_pythons_os_path() {
    assert_eq!(normpath("/a//b/./c/../d/"), "/a/b/d");
    assert_eq!(normpath("/../a"), "/a");
    assert_eq!(normpath("a/../../b"), "../b");
    assert_eq!(normpath("//a"), "//a");
    assert_eq!(normpath("///a"), "/a");
    assert_eq!(dirname("/a/b"), "/a");
    assert_eq!(dirname("/a"), "/");
    assert_eq!(dirname("a"), "");
    assert_eq!(dirname("/a//b"), "/a");
    assert_eq!(join("/a", "b"), "/a/b");
    assert_eq!(join("/a/", "/b"), "/b");
    assert!(covers("/a", "/a") && covers("/a", "/a/b") && covers("/a/", "/a/b"));
    assert!(!covers("/a", "/ab"));
}

#[test]
fn a_rename_spelled_with_a_trailing_slash_keeps_the_separator() {
    let m = Mirror::new();
    let mut s = m.tree.lock();
    s.dirty.insert("/m/d/\u{e9}".into());
    s.dirty.insert("/m/d".into());
    relocate(&mut s, "/m/d//", "/m/e");
    assert_eq!(
        s.dirty.iter().cloned().collect::<Vec<_>>(),
        ["/m/e", "/m/e/\u{e9}"]
    );
}

#[test]
fn a_read_only_placeholder_is_made_again_when_the_target_changes_it() {
    let m = Mirror::new();
    m.target.put(
        "/w/ro",
        Entry {
            mode: 0o100444,
            ..Entry::file(b"one")
        },
    );
    m.tree.ensure_directory(&m.path("")).unwrap();
    m.target.put(
        "/w/ro",
        Entry {
            mode: 0o100444,
            ..Entry::file(b"three")
        },
    );
    m.tree.invalidate();
    m.tree.ensure_directory(&m.path("")).unwrap();
    assert_eq!(fs::metadata(m.path("ro")).unwrap().len(), 5);
}

// ------------------------------------------------------------------- the mirror's root

fn registry_in(tmp: &Path) -> PathBuf {
    tmp.join("shadows")
}

#[test]
fn the_registry_is_written_as_python_writes_it() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    registry::prepare_in(&registry_in(tmp), &tmp.join("m"), false, "ssh://ä").unwrap();
    let records: Vec<_> = fs::read_dir(registry_in(tmp)).unwrap().collect();
    assert_eq!(records.len(), 1);
    let blob = fs::read(records[0].as_ref().unwrap().path()).unwrap();
    assert_eq!(
        String::from_utf8(blob).unwrap(),
        format!(
            "{{\"shadow\": \"{}\", \"target\": \"ssh://\\u00e4\"}}",
            tmp.join("m").display()
        )
    );
}

#[test]
fn a_new_root_is_made() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    registry::prepare_in(&registry_in(tmp), &tmp.join("a/b"), false, "ssh://a").unwrap();
    assert!(tmp.join("a/b").is_dir());
}

#[test]
fn an_empty_directory_is_taken() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    fs::create_dir(tmp.join("m")).unwrap();
    registry::prepare_in(&registry_in(tmp), &tmp.join("m"), false, "ssh://a").unwrap();
}

#[test]
fn a_directory_of_somebody_elses_files_is_refused() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    fs::create_dir(tmp.join("m")).unwrap();
    fs::write(tmp.join("m/precious"), b"x").unwrap();
    let why =
        registry::prepare_in(&registry_in(tmp), &tmp.join("m"), false, "ssh://a").unwrap_err();
    assert_eq!(why.kind(), io::ErrorKind::AlreadyExists);
    assert!(why.to_string().contains("not a Humanize mirror"));
    registry::prepare_in(&registry_in(tmp), &tmp.join("m"), true, "ssh://a").unwrap();
}

#[test]
fn a_mirror_is_reused_for_its_own_target_only() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    let (registry, root) = (registry_in(tmp), tmp.join("m"));
    registry::prepare_in(&registry, &root, false, "ssh://a").unwrap();
    fs::write(root.join("f"), b"mirrored").unwrap();
    registry::prepare_in(&registry, &root, false, "ssh://a").unwrap();
    let why = registry::prepare_in(&registry, &root, false, "ssh://b").unwrap_err();
    assert_eq!(why.kind(), io::ErrorKind::AlreadyExists);
    assert!(why.to_string().contains("mirrors ssh://a, not ssh://b"));
    registry::prepare_in(&registry, &root, true, "ssh://b").unwrap();
    registry::prepare_in(&registry, &root, false, "ssh://b").unwrap();
}

#[test]
fn a_record_python_wrote_is_read() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    let root = tmp.join("m");
    fs::create_dir(&root).unwrap();
    fs::write(root.join("f"), b"mirrored").unwrap();
    let entry = registry::registry_entry(&registry_in(tmp), &root);
    fs::create_dir_all(registry_in(tmp)).unwrap();
    fs::write(
        &entry,
        b"{\"shadow\": \"m\", \"target\": \"ssh://\\u00e4\"}",
    )
    .unwrap();
    registry::prepare_in(&registry_in(tmp), &root, false, "ssh://ä").unwrap();
}

#[test]
fn turns_starting_in_one_mirror_at_once_are_none_refused() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path().to_path_buf();
    let root = tmp.join("m");
    registry::prepare_in(&registry_in(&tmp), &root, false, "ssh://a").unwrap();
    fs::write(root.join("kept.txt"), b"what the target has").unwrap();
    let together = Arc::new(std::sync::Barrier::new(3));
    let workers: Vec<_> = (0..3)
        .map(|_| {
            let (tmp, root, together) = (tmp.clone(), root.clone(), together.clone());
            std::thread::spawn(move || {
                together.wait();
                (0..20)
                    .filter(|_| {
                        registry::prepare_in(&registry_in(&tmp), &root, false, "ssh://a").is_err()
                    })
                    .count()
            })
        })
        .collect();
    let refused: usize = workers.into_iter().map(|one| one.join().unwrap()).sum();
    assert_eq!(refused, 0);
    // The record alone: nothing written beside it is left there.
    assert_eq!(fs::read_dir(registry_in(&tmp)).unwrap().count(), 1);
}

#[test]
fn a_file_is_no_root() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    fs::write(tmp.join("f"), b"x").unwrap();
    let why = registry::prepare_in(&registry_in(tmp), &tmp.join("f"), false, "").unwrap_err();
    assert_eq!(why.kind(), io::ErrorKind::NotADirectory);
    assert!(why.to_string().starts_with(UNMIRRORED));
}

#[test]
fn a_registry_kept_before_is_moved_to_where_it_is_now() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    let was = tmp.join("cache/humanize/shadows");
    fs::create_dir_all(&was).unwrap();
    fs::write(was.join("0123456789abcdef.json"), b"{}").unwrap();
    let now = tmp.join("state/humanize/shadows");

    registry::settle(&was, &now);

    assert_eq!(names(&now), ["0123456789abcdef.json"]);
    assert!(!was.exists());
}

#[test]
fn a_registry_kept_before_is_never_merged_into_one_kept_since() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    let (was, now) = (tmp.join("was"), tmp.join("now"));
    fs::create_dir_all(&was).unwrap();
    fs::write(was.join("old.json"), b"{}").unwrap();
    fs::create_dir_all(&now).unwrap();
    fs::write(now.join("new.json"), b"{}").unwrap();

    registry::settle(&was, &now);
    registry::settle(&tmp.join("nothing"), &tmp.join("nowhere"));

    assert_eq!(names(&now), ["new.json"]);
    assert_eq!(names(&was), ["old.json"]);
    assert!(!tmp.join("nowhere").exists());
}

#[test]
fn a_root_that_cannot_be_made_is_said_so() {
    let dir = tempfile::tempdir().unwrap();
    let tmp = dir.path();
    fs::write(tmp.join("f"), b"x").unwrap();
    let why = registry::prepare_in(&registry_in(tmp), &tmp.join("f/m"), false, "").unwrap_err();
    assert!(
        why.to_string()
            .starts_with(&format!("{UNMIRRORED} {}: ", tmp.join("f/m").display())),
        "{why}"
    );
}
