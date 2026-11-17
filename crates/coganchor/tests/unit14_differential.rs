//! The Rust virtual homes against Python's: each case of `fixtures/unit14_homes/cases.json`
//! built, changed by a session and dropped here, compared with what `gen.py` recorded of
//! `hmz.coganchor.homes` doing the same (`expected.json`). The same tree must come out: the
//! same files with the same bytes, modes and times, the same links, the same database rows,
//! the same variables and arguments -- and the same refusals.
//!
//! Regenerate the expectation after changing a case with
//! `uv run python crates/coganchor/tests/fixtures/unit14_homes/gen.py`.

use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::{Path, PathBuf};

use coganchor::cog::homes::{Options, Virtual, build_with};
use rusqlite::{Connection, OpenFlags, types::ValueRef};
use serde_json::{Map, Value, json};

const BEFORE: i64 = 1_600_000_000;
const AFTER: i64 = 1_700_000_000;

fn fixtures() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/unit14_homes")
}

fn placed(said: &str, root: &Path, at: Option<&Path>) -> String {
    let said = said.replace("{root}", &root.to_string_lossy());
    match at {
        Some(at) => said.replace("{at}", &at.to_string_lossy()),
        None => said,
    }
}

fn unplaced(said: &str, root: &Path, at: &Path) -> String {
    let said = said
        .replace(&*at.to_string_lossy(), "{at}")
        .replace(&*root.to_string_lossy(), "{root}");
    let name = at
        .file_name()
        .map(|one| one.to_string_lossy().into_owned())
        .unwrap_or_default();
    said.replace(&name, "{home}")
}

fn timed(path: &Path, seconds: i64) {
    let when = std::time::UNIX_EPOCH + std::time::Duration::from_secs(seconds as u64);
    let times = fs::FileTimes::new().set_accessed(when).set_modified(when);
    fs::File::options()
        .write(true)
        .open(path)
        .and_then(|file| file.set_times(times))
        .expect("timed");
}

fn sql(path: &Path, statements: &[Value], root: &Path, at: Option<&Path>) {
    let connection = Connection::open(path).expect("a database");
    for statement in statements {
        connection
            .execute(&placed(statement.as_str().expect("sql"), root, at), [])
            .expect("executed");
    }
}

fn lay(root: &Path, entries: &[Value]) {
    for one in entries {
        let path = root.join(one["path"].as_str().expect("a path"));
        fs::create_dir_all(path.parent().expect("a parent")).expect("made");
        if let Some(link) = one.get("link") {
            std::os::unix::fs::symlink(placed(link.as_str().expect("a link"), root, None), &path)
                .expect("linked");
        } else if let Some(statements) = one.get("sql") {
            sql(&path, statements.as_array().expect("sql"), root, None);
        } else {
            fs::write(&path, one["text"].as_str().expect("text")).expect("written");
            let mode = one.get("mode").and_then(Value::as_u64).unwrap_or(0o644) as u32;
            fs::set_permissions(&path, fs::Permissions::from_mode(mode)).expect("moded");
            timed(
                &path,
                one.get("mtime").and_then(Value::as_i64).unwrap_or(BEFORE),
            );
        }
    }
}

fn act(root: &Path, at: &Path, ops: &[Value]) {
    for op in ops {
        let path = PathBuf::from(placed(op["path"].as_str().expect("a path"), root, Some(at)));
        let mtime = op.get("mtime").and_then(Value::as_i64).unwrap_or(AFTER);
        let name = path
            .file_name()
            .expect("a name")
            .to_string_lossy()
            .into_owned();
        match op["op"].as_str().expect("an op") {
            "write" => {
                fs::create_dir_all(path.parent().expect("a parent")).expect("made");
                fs::write(&path, op["text"].as_str().expect("text")).expect("written");
                timed(&path, mtime);
            }
            "rename_over" => {
                let beside = path.with_file_name(format!(".{name}.tmp"));
                fs::write(&beside, op["text"].as_str().expect("text")).expect("written");
                timed(&beside, mtime);
                fs::rename(&beside, &path).expect("renamed");
            }
            "replace_dir" => {
                let beside = path.with_file_name(format!("{name}.tmp"));
                for (file, said) in op["files"].as_object().expect("files") {
                    let into = beside.join(file);
                    fs::create_dir_all(into.parent().expect("a parent")).expect("made");
                    fs::write(&into, said["text"].as_str().expect("text")).expect("written");
                    timed(
                        &into,
                        said.get("mtime").and_then(Value::as_i64).unwrap_or(AFTER),
                    );
                }
                fs::remove_file(&path).expect("unlinked");
                fs::rename(&beside, &path).expect("renamed");
            }
            "sql" => sql(&path, op["sql"].as_array().expect("sql"), root, Some(at)),
            other => panic!("no op {other}"),
        }
    }
}

fn listed(top: &Path, root: &Path, at: &Path, times: bool) -> Value {
    let mut out = BTreeMap::new();
    walk(top, top, root, at, times, &mut out);
    Value::Object(out.into_iter().collect::<Map<_, _>>())
}

fn walk(
    top: &Path,
    dir: &Path,
    root: &Path,
    at: &Path,
    times: bool,
    out: &mut BTreeMap<String, Value>,
) {
    for entry in fs::read_dir(dir).expect("listed") {
        let path = entry.expect("an entry").path();
        let rel = path
            .strip_prefix(top)
            .expect("under")
            .to_string_lossy()
            .into_owned();
        let name = path
            .file_name()
            .expect("a name")
            .to_string_lossy()
            .into_owned();
        let meta = fs::symlink_metadata(&path).expect("there");
        if meta.file_type().is_symlink() {
            let target = fs::read_link(&path).expect("a link");
            out.insert(
                rel,
                json!({"link": unplaced(&target.to_string_lossy(), root, at)}),
            );
        } else if meta.is_dir() {
            out.insert(rel, json!({"dir": true}));
            walk(top, &path, root, at, times, out);
        } else {
            let data = fs::read(&path).expect("read");
            if name.ends_with(".sqlite") && data.starts_with(b"SQLite") {
                out.insert(rel, json!({"sqlite": dumped(&path, root, at)}));
                continue;
            }
            if name.contains(".sqlite-") {
                continue;
            }
            let mut one = Map::new();
            one.insert("mode".into(), json!(meta.permissions().mode() & 0o7777));
            match String::from_utf8(data) {
                Ok(text) => one.insert("text".into(), json!(unplaced(&text, root, at))),
                Err(error) => one.insert("hex".into(), json!(hex::encode(error.into_bytes()))),
            };
            if times && !name.contains(".sqlite") {
                let ns = meta.mtime() as i128 * 1_000_000_000 + meta.mtime_nsec() as i128;
                one.insert("mtime".into(), json!(ns as i64));
            }
            out.insert(rel, Value::Object(one));
        }
    }
}

fn dumped(path: &Path, root: &Path, at: &Path) -> Value {
    let connection =
        Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY).expect("a database");
    let mut tables = connection
        .prepare("select name from sqlite_master where type = 'table' order by name")
        .expect("prepared");
    let names: Vec<String> = tables
        .query_map([], |row| row.get(0))
        .expect("queried")
        .collect::<Result<_, _>>()
        .expect("names");
    let mut out = Map::new();
    for table in names {
        let mut rows = connection
            .prepare(&format!("select * from \"{table}\" order by rowid"))
            .expect("prepared");
        let width = rows.column_count();
        let said: Vec<Value> = rows
            .query_map([], |row| {
                Ok(Value::Array(
                    (0..width)
                        .map(|index| match row.get_ref(index).expect("a value") {
                            ValueRef::Null => Value::Null,
                            ValueRef::Integer(n) => json!(n),
                            ValueRef::Real(n) => json!(n),
                            ValueRef::Text(text) => {
                                json!(unplaced(&String::from_utf8_lossy(text), root, at))
                            }
                            ValueRef::Blob(blob) => json!(hex::encode(blob)),
                        })
                        .collect(),
                ))
            })
            .expect("queried")
            .collect::<Result<_, _>>()
            .expect("rows");
        out.insert(table, Value::Array(said));
    }
    Value::Object(out)
}

fn run(case: &Value, expected: &Value) -> Value {
    let made = tempfile::tempdir().expect("a directory");
    let root = fs::canonicalize(made.path()).expect("its name");
    lay(&root, case["user"].as_array().expect("user"));
    let dumps = placed(expected["dumps"].as_str().expect("dumps"), &root, None);
    let spec = Virtual::loads(&dumps).expect("a virtual home");
    assert_eq!(spec.dumps(), dumps, "said again as Python says it");
    let environ: HashMap<String, String> = case["env"]
        .as_object()
        .expect("env")
        .iter()
        .map(|(key, value)| {
            (
                key.clone(),
                placed(value.as_str().expect("a value"), &root, None),
            )
        })
        .collect();
    let options = Options {
        under: Some(root.clone()),
        ..Options::default()
    };
    let home = match build_with(&spec, &environ, options) {
        Ok(home) => home,
        Err(_) => {
            let mut left: Vec<String> = fs::read_dir(&root)
                .expect("listed")
                .map(|one| {
                    one.expect("an entry")
                        .file_name()
                        .to_string_lossy()
                        .into_owned()
                })
                .filter(|one| one.starts_with("hmz-home-"))
                .collect();
            left.sort();
            return json!({"dumps": expected["dumps"], "error": expected["error"], "left": left});
        }
    };
    let at = home.dir().to_path_buf();
    let mut linked: Vec<String> = home
        .linked()
        .iter()
        .map(|one| one.to_string_lossy().into_owned())
        .collect();
    linked.sort();
    let sets: Vec<Value> = home
        .environ()
        .into_iter()
        .map(|(key, value)| {
            json!([
                key.to_string_lossy(),
                unplaced(&value.to_string_lossy(), &root, &at)
            ])
        })
        .collect();
    let argv: Vec<String> = home
        .argv()
        .into_iter()
        .map(|one| unplaced(&one.to_string_lossy(), &root, &at))
        .collect();
    let built = listed(&at, &root, &at, false);
    act(&root, &at, case["session"].as_array().expect("session"));
    home.drop_home().expect("dropped");
    json!({
        "dumps": unplaced(&dumps, &root, &at),
        "sets": sets,
        "argv": argv,
        "linked": linked,
        "built": built,
        "at_left": at.exists(),
        "dropped": listed(&root, &root, &at, true),
    })
}

#[test]
fn a_home_built_and_dropped_here_is_the_one_python_builds_and_drops() {
    nix::sys::stat::umask(nix::sys::stat::Mode::from_bits_truncate(0o022));
    let cases: Value =
        serde_json::from_str(&fs::read_to_string(fixtures().join("cases.json")).expect("cases"))
            .expect("JSON");
    let expected: Value = serde_json::from_str(
        &fs::read_to_string(fixtures().join("expected.json")).expect("expected"),
    )
    .expect("JSON");
    let mut failed = Vec::new();
    for case in cases.as_array().expect("cases") {
        let name = case["name"].as_str().expect("a name");
        let wanted = &expected[name];
        let got = run(case, wanted);
        if got != *wanted {
            eprintln!(
                "=== {name}\n--- python\n{}\n--- rust\n{}",
                serde_json::to_string_pretty(wanted).unwrap_or_default(),
                serde_json::to_string_pretty(&got).unwrap_or_default()
            );
            failed.push(name.to_owned());
        }
    }
    assert!(failed.is_empty(), "differs from Python: {failed:?}");
}
