//! A CLI's virtual home: copies of what it rewrites, links to the rest, the flow's skills
//! beside. Port of `tests/unit/coganchor/test_homes.py` (the cases of what this crate builds:
//! `virtual`, `merged` and `Home.spelled` stay Python's) and of the mergers' own.

use std::collections::HashMap;
use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::{Path, PathBuf};
use std::time::{Duration, UNIX_EPOCH};

use coganchor::cog::homes::{Home, Options, Virtual, build_with, words};
use coganchor::cog::mergers;
use serde_json::{Value, json};

fn s(one: &str) -> String {
    one.to_owned()
}

fn claude() -> Virtual {
    Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        rewrites: vec![s(".claude.json"), s("settings.json")],
        outside: vec![(s(".claude.json"), s(".claude.json"))],
        lodges: s("skills"),
        secures: s("CLAUDE_SECURESTORAGE_CONFIG_DIR"),
        made: vec![s("projects"), s("history.jsonl")],
        ..Virtual::default()
    }
}

fn write(at: &Path, said: &str) {
    fs::create_dir_all(at.parent().expect("a parent")).expect("made");
    fs::write(at, said).expect("written");
}

fn read(at: &Path) -> String {
    fs::read_to_string(at).expect("read")
}

fn timed(at: &Path, seconds: u64) {
    let when = UNIX_EPOCH + Duration::from_secs(seconds);
    fs::File::options()
        .write(true)
        .open(at)
        .and_then(|file| file.set_times(fs::FileTimes::new().set_accessed(when).set_modified(when)))
        .expect("timed");
}

fn is_link(at: &Path) -> bool {
    fs::symlink_metadata(at).is_ok_and(|one| one.file_type().is_symlink())
}

struct Tmp {
    _held: tempfile::TempDir,
    path: PathBuf,
}

fn tmp() -> Tmp {
    let held = tempfile::tempdir().expect("a directory");
    let path = fs::canonicalize(held.path()).expect("its name");
    Tmp { _held: held, path }
}

/// A user's own home with a Claude in it: settings, a sign-in, a skill, a conversation.
fn user(tmp: &Path) -> PathBuf {
    let home = tmp.join("user");
    let real = home.join(".claude");
    write(&real.join("skills/mine/SKILL.md"), "theirs\n");
    write(&real.join("skills/review/SKILL.md"), "their review\n");
    write(&real.join("settings.json"), "{\"theirs\": true}\n");
    write(&real.join(".credentials.json"), "token\n");
    write(&real.join(".claude.json"), "{\"inside\": true}\n");
    write(&home.join(".claude.json"), "{\"outside\": true}\n");
    home
}

fn env(home: &Path) -> HashMap<String, String> {
    HashMap::from([(s("HOME"), home.to_string_lossy().into_owned())])
}

fn under(tmp: &Path) -> Options {
    Options {
        under: Some(tmp.to_path_buf()),
        ..Options::default()
    }
}

fn built(spec: &Virtual, environ: &HashMap<String, String>, tmp: &Path) -> Home {
    build_with(spec, environ, under(tmp)).expect("built")
}

/// What an agent fenced to `roots` may reach, every link followed.
fn inside(roots: &[&Path]) -> Box<dyn Fn(&str) -> bool + Send + Sync> {
    let held: Vec<String> = roots
        .iter()
        .map(|one| {
            coganchor::cog::homes::realpath(one)
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    Box::new(move |path| {
        let path = coganchor::cog::homes::realpath(Path::new(path))
            .to_string_lossy()
            .into_owned();
        held.iter()
            .any(|root| path == *root || path.starts_with(&format!("{root}/")))
    })
}

/// What a CLI saving a file atomically does: writes another beside it, renames it over.
fn renamed(at: &Path, said: &str, mtime: Option<u64>) {
    let name = at.file_name().expect("a name").to_string_lossy();
    let beside = at.with_file_name(format!(".{name}.tmp"));
    fs::write(&beside, said).expect("written");
    if let Some(mtime) = mtime {
        timed(&beside, mtime);
    }
    fs::rename(&beside, at).expect("renamed");
}

#[test]
fn a_home_copies_what_the_cli_rewrites_and_links_the_rest() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let home = built(&claude(), &env(&user), &tmp.path);
    let real = user.join(".claude");

    assert_eq!(home.real(), real);
    assert_eq!(home.dir().parent(), Some(tmp.path.as_path()));
    let settings = home.dir().join("settings.json");
    assert!(!is_link(&settings));
    fs::write(&settings, "rewritten\n").expect("written");
    assert_eq!(read(&real.join("settings.json")), "{\"theirs\": true}\n");
    // Kept outside the home while the variable is unset, and copied from there.
    assert_eq!(
        read(&home.dir().join(".claude.json")),
        "{\"outside\": true}\n"
    );
    assert!(is_link(&home.dir().join(".credentials.json")));
    assert_eq!(
        fs::canonicalize(home.dir().join(".credentials.json")).expect("there"),
        real.join(".credentials.json")
    );
    // Where conversations go is made in the user's home, so what is written there stays.
    assert!(real.join("projects").is_dir());
    assert!(is_link(&home.dir().join("history.jsonl")));
    fs::write(home.dir().join("history.jsonl"), "said\n").expect("written");
    assert_eq!(read(&real.join("history.jsonl")), "said\n");
    let mode = fs::metadata(home.dir())
        .expect("there")
        .permissions()
        .mode();
    assert_eq!(mode & 0o777, 0o700);
}

#[test]
fn the_flows_skills_go_beside_the_users_own() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let skill = tmp.path.join("flow/review");
    write(&skill.join("SKILL.md"), "the flow's review\n");
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        lodges: s("skills"),
        skills: vec![(s("review"), skill.to_string_lossy().into_owned())],
        ..Virtual::default()
    };

    let home = built(&spec, &env(&user), &tmp.path);

    let skills = home.dir().join("skills");
    let mut names: Vec<String> = fs::read_dir(&skills)
        .expect("listed")
        .map(|one| {
            one.expect("an entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    names.sort();
    assert_eq!(names, ["mine", "review"]);
    assert_eq!(read(&skills.join("mine/SKILL.md")), "theirs\n");
    assert_eq!(read(&skills.join("review/SKILL.md")), "the flow's review\n");
    assert_eq!(
        read(&user.join(".claude/skills/review/SKILL.md")),
        "their review\n"
    );
}

#[test]
fn a_home_variable_the_user_set_is_the_home_and_keeps_the_sign_in() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let real = user.join(".claude");
    let mut said = env(&user);
    said.insert(s("CLAUDE_CONFIG_DIR"), real.to_string_lossy().into_owned());

    let home = built(&claude(), &said, &tmp.path);

    assert_eq!(
        read(&home.dir().join(".claude.json")),
        "{\"inside\": true}\n"
    );
    let sets: HashMap<String, String> = home
        .environ()
        .into_iter()
        .map(|(key, value)| {
            (
                key.to_string_lossy().into_owned(),
                value.to_string_lossy().into_owned(),
            )
        })
        .collect();
    assert_eq!(sets["CLAUDE_CONFIG_DIR"], home.dir().to_string_lossy());
    assert_eq!(
        sets["CLAUDE_SECURESTORAGE_CONFIG_DIR"],
        real.to_string_lossy()
    );
    let unset = built(&claude(), &env(&user), &tmp.path);
    assert!(
        unset
            .environ()
            .contains(&("CLAUDE_SECURESTORAGE_CONFIG_DIR".into(), "".into()))
    );
}

#[test]
fn a_sign_in_place_the_user_named_is_left_as_they_named_it() {
    let tmp = tmp();
    let mut said = env(&user(&tmp.path));
    said.insert(s("CLAUDE_SECURESTORAGE_CONFIG_DIR"), s("/x"));

    let home = built(&claude(), &said, &tmp.path);

    assert!(
        home.environ()
            .iter()
            .all(|(key, _)| key != "CLAUDE_SECURESTORAGE_CONFIG_DIR")
    );
}

#[test]
fn a_copy_is_made_of_what_a_provider_answers_the_path_with() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let account = tmp.path.join("account.json");
    write(&account, "{\"account\": true}\n");
    let outside = user.join(".claude.json").to_string_lossy().into_owned();
    let answer = account.to_string_lossy().into_owned();

    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            answered: Box::new(move |path| (path == outside).then(|| answer.clone())),
            ..under(&tmp.path)
        },
    )
    .expect("built");

    assert_eq!(
        read(&home.dir().join(".claude.json")),
        "{\"account\": true}\n"
    );
}

#[test]
fn dropping_a_home_leaves_the_users_own_whole() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let home = built(&claude(), &env(&user), &tmp.path);
    let at = home.dir().to_path_buf();

    home.drop_home().expect("dropped");

    assert!(!at.exists());
    assert_eq!(read(&user.join(".claude/.credentials.json")), "token\n");
    assert!(user.join(".claude/skills/mine/SKILL.md").exists());
}

#[test]
fn private_names_are_neither_linked_nor_made() {
    let tmp = tmp();
    let user = user(&tmp.path);
    fs::create_dir(user.join(".claude/sessions")).expect("made");
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        private: vec![s("sess*")],
        ..Virtual::default()
    };

    let home = built(&spec, &env(&user), &tmp.path);

    assert!(!home.dir().join("sessions").exists());
    assert!(is_link(&home.dir().join("settings.json")));
}

#[test]
fn a_virtual_home_reads_back_as_itself() {
    let spec = Virtual {
        variable: s("CODEX_HOME"),
        default: s(".codex"),
        rewrites: vec![s("config.toml")],
        outside: vec![(s("config.toml"), s(".codex.toml"))],
        lodges: s("skills"),
        private: vec![s("state_*.sqlite*")],
        made: vec![s("sessions")],
        skills: vec![(s("review"), s("/flow/review"))],
        merges: vec![(
            s("hmz.coganchor.agents.qwen:_merged"),
            s("{\"effort\": \"high\"}"),
        )],
        records: vec![(s("state_*.sqlite"), s("threads"), s("rollout_path"))],
        keeps: s("/epic/sessions/codex"),
        ..Virtual::default()
    };

    assert_eq!(Virtual::loads(&spec.dumps()), Ok(spec.clone()));
    assert_eq!(
        words(&spec),
        [
            "copy=config.toml=.codex.toml",
            "keep=state_*.sqlite*",
            "make=sessions",
            "skill=review",
            "record=state_*.sqlite=threads=rollout_path",
        ]
    );
    // What an older `hmz` said, before `flag`, `merges`, `records` and `keeps` were.
    let older = r#"{"variable":"X","default":".x","rewrites":[],"outside":[],"lodges":"","secures":"","private":[],"made":[],"kept":[],"skills":[]}"#;
    assert_eq!(Virtual::loads(older).map(|one| one.variable), Ok(s("X")));
}

#[test]
fn a_virtual_home_naming_outside_itself_is_refused() {
    for (variable, rewrites, skills) in [
        ("", vec![], vec![]),
        ("A-B", vec![], vec![]),
        ("X", vec![s("../out")], vec![]),
        ("X", vec![], vec![(s("/abs"), s("/flow"))]),
    ] {
        let spec = Virtual {
            variable: s(variable),
            default: s(".x"),
            rewrites,
            skills,
            ..Virtual::default()
        };
        let said = spec.checked().expect_err("refused");
        assert!(
            said.contains("unsupported") || said.contains("needs"),
            "{said}"
        );
        assert!(Virtual::loads(&spec.dumps()).is_err());
    }
    assert!(
        Virtual::loads("{}")
            .expect_err("refused")
            .contains("not a virtual home")
    );
    let relative = Virtual {
        variable: s("CODEX_HOME"),
        default: s(".codex"),
        keeps: s("epic/codex"),
        ..Virtual::default()
    };
    assert!(
        relative
            .checked()
            .expect_err("refused")
            .contains("to keep sessions in")
    );
}

#[test]
fn a_home_that_cannot_be_built_leaves_nothing() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let settings = user.join(".claude/settings.json");
    fs::set_permissions(&settings, fs::Permissions::from_mode(0o000)).expect("moded");
    if fs::File::open(&settings).is_ok() {
        return; // this user reads everything
    }
    let homes = tmp.path.join("homes");
    fs::create_dir(&homes).expect("made");

    let error = build_with(&claude(), &env(&user), under(&homes))
        .err()
        .expect("refused");

    assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
    assert_eq!(fs::read_dir(&homes).expect("listed").count(), 0);
}

#[test]
fn what_the_cli_made_for_the_user_to_keep_is_moved_home_as_it_goes() {
    let tmp = tmp();
    let user = user(&tmp.path);
    write(&user.join(".claude/state_1.sqlite"), "theirs\n");
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        kept: vec![s("state_*.sqlite*")],
        ..Virtual::default()
    };
    let home = built(&spec, &env(&user), &tmp.path);
    write(&home.dir().join("state_2.sqlite"), "new\n");
    write(&home.dir().join("scratch.txt"), "the CLI's own\n");

    home.drop_home().expect("dropped");

    assert_eq!(read(&user.join(".claude/state_2.sqlite")), "new\n");
    assert_eq!(read(&user.join(".claude/state_1.sqlite")), "theirs\n");
    assert!(!user.join(".claude/scratch.txt").exists());
}

#[test]
fn a_directory_the_cli_rewrites_starts_empty() {
    let tmp = tmp();
    let user = user(&tmp.path);
    write(&user.join(".claude/backups/old.json"), "theirs\n");
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        rewrites: vec![s("backups")],
        ..Virtual::default()
    };

    let home = built(&spec, &env(&user), &tmp.path);

    let backups = home.dir().join("backups");
    assert!(backups.is_dir() && !is_link(&backups));
    assert_eq!(fs::read_dir(&backups).expect("listed").count(), 0);
}

#[test]
fn a_home_only_a_flag_moves_is_named_on_the_command_line() {
    let tmp = tmp();
    let user = tmp.path.join("user");
    let real = user.join(".gemini/antigravity-cli");
    fs::create_dir_all(real.join("conversations")).expect("made");
    let spec = Virtual {
        variable: s(""),
        default: s(".gemini/antigravity-cli"),
        flag: s("--app_data_dir"),
        ..Virtual::default()
    };

    let home = built(&spec, &env(&user), &tmp.path);

    assert_eq!(home.real(), real);
    assert!(home.environ().is_empty());
    let argv = home.argv();
    assert_eq!(argv.len(), 1);
    let said = argv[0].to_string_lossy().into_owned();
    let (flag, where_) = said.split_once('=').expect("a flag");
    assert_eq!(flag, "--app_data_dir");
    // Relative to `~/.gemini`, the one way agy takes it, and naming the home from there.
    assert!(!where_.starts_with('/'));
    assert_eq!(
        fs::canonicalize(user.join(".gemini").join(where_)).expect("there"),
        home.dir()
    );
    assert_eq!(
        fs::canonicalize(home.dir().join("conversations")).expect("there"),
        real.join("conversations")
    );
    let bare = Virtual {
        variable: s(""),
        default: s(".x"),
        ..Virtual::default()
    };
    assert!(bare.checked().expect_err("refused").contains("needs"));
}

#[test]
fn a_credential_the_cli_replaced_by_rename_is_written_back() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let real = user.join(".claude/.credentials.json");
    fs::set_permissions(&real, fs::Permissions::from_mode(0o600)).expect("moded");
    timed(&real, 1_000_000);
    let home = built(&claude(), &env(&user), &tmp.path);
    let at = home.dir().to_path_buf();

    renamed(&at.join(".credentials.json"), "refreshed\n", None);
    assert!(!is_link(&at.join(".credentials.json")));
    home.drop_home().expect("dropped");

    assert_eq!(read(&real), "refreshed\n");
    assert_eq!(
        fs::metadata(&real).expect("there").permissions().mode() & 0o777,
        0o600
    );
    assert!(!at.exists());
    // Nothing of the writing is left beside it.
    let beside: Vec<_> = fs::read_dir(user.join(".claude"))
        .expect("listed")
        .filter(|one| {
            one.as_ref()
                .is_ok_and(|one| one.file_name().to_string_lossy().ends_with(".new"))
        })
        .collect();
    assert!(beside.is_empty());
}

#[test]
fn an_older_replacement_does_not_clobber_a_newer_real_file() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let real = user.join(".claude/.credentials.json");
    let home = built(&claude(), &env(&user), &tmp.path);

    renamed(
        &home.dir().join(".credentials.json"),
        "stale\n",
        Some(1_000_000),
    );
    fs::write(&real, "another process's newer token\n").expect("written");
    home.drop_home().expect("dropped");

    assert_eq!(read(&real), "another process's newer token\n");
}

#[test]
fn what_a_cli_rewrites_is_still_discarded() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let home = built(&claude(), &env(&user), &tmp.path);

    renamed(
        &home.dir().join("settings.json"),
        "{\"rewritten\": true}\n",
        None,
    );
    renamed(
        &home.dir().join(".claude.json"),
        "{\"rewritten\": true}\n",
        None,
    );
    home.drop_home().expect("dropped");

    assert_eq!(
        read(&user.join(".claude/settings.json")),
        "{\"theirs\": true}\n"
    );
    assert_eq!(read(&user.join(".claude.json")), "{\"outside\": true}\n");
}

#[test]
fn a_replaced_directory_is_merged_back_a_new_or_changed_file_at_a_time() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let sessions = user.join(".claude/projects");
    write(&sessions.join("old.jsonl"), "theirs\n");
    timed(&sessions.join("old.jsonl"), 1_000_000);
    write(&sessions.join("newer.jsonl"), "newer\n");
    let home = built(&claude(), &env(&user), &tmp.path);
    let replaced = home.dir().join("projects.tmp");
    write(&replaced.join("old.jsonl"), "changed\n");
    write(&replaced.join("made.jsonl"), "made\n");
    write(&replaced.join("newer.jsonl"), "stale\n");
    timed(&replaced.join("newer.jsonl"), 1_000_000);
    fs::remove_file(home.dir().join("projects")).expect("unlinked");
    fs::rename(&replaced, home.dir().join("projects")).expect("renamed");

    home.drop_home().expect("dropped");

    assert_eq!(read(&sessions.join("old.jsonl")), "changed\n");
    assert_eq!(read(&sessions.join("made.jsonl")), "made\n");
    assert_eq!(read(&sessions.join("newer.jsonl")), "newer\n");
}

#[test]
fn a_replaced_credential_goes_back_to_the_account_a_provider_answers_with() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let account = tmp.path.join("account/.credentials.json");
    write(&account, "the account's\n");
    timed(&account, 1_000_000);
    let named = user
        .join(".claude/.credentials.json")
        .to_string_lossy()
        .into_owned();
    let answer = account.to_string_lossy().into_owned();
    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            answered: Box::new(move |path| (path == named).then(|| answer.clone())),
            ..under(&tmp.path)
        },
    )
    .expect("built");

    renamed(&home.dir().join(".credentials.json"), "refreshed\n", None);
    home.drop_home().expect("dropped");

    assert_eq!(read(&account), "refreshed\n");
    assert_eq!(read(&user.join(".claude/.credentials.json")), "token\n");
}

#[test]
fn what_a_driver_manages_is_merged_into_the_copies() {
    let tmp = tmp();
    let user = tmp.path.join("user");
    write(&user.join(".qwen/settings.json"), "{\"theirs\": true}\n");
    let spec = Virtual {
        variable: s("QWEN_HOME"),
        default: s(".qwen"),
        rewrites: vec![s("settings.json")],
        merges: vec![(
            s("hmz.coganchor.agents.qwen:_merged"),
            s(r#"{"managed": {"effort": "high"}, "headless": false}"#),
        )],
        ..Virtual::default()
    };

    let home = built(
        &Virtual::loads(&spec.dumps()).expect("read back"),
        &env(&user),
        &tmp.path,
    );

    let merged: Value =
        serde_json::from_str(&read(&home.dir().join("settings.json"))).expect("JSON");
    assert_eq!(merged, json!({"theirs": true, "effort": "high"}));
    assert_eq!(
        read(&user.join(".qwen/settings.json")),
        "{\"theirs\": true}\n"
    );
}

#[test]
fn what_a_merge_made_its_own_is_never_written_back() {
    let tmp = tmp();
    let user = tmp.path.join("user");
    write(
        &user.join(".gemini/antigravity-cli/agents/mine.md"),
        "the user's own\n",
    );
    let spec = Virtual {
        variable: s(""),
        default: s(".gemini/antigravity-cli"),
        flag: s("--app_data_dir"),
        merges: vec![(s("hmz.coganchor.agents.agy:_agents"), s("null"))],
        ..Virtual::default()
    };

    let home = built(&spec, &env(&user), &tmp.path);
    let mut names: Vec<String> = fs::read_dir(home.dir().join("agents"))
        .expect("listed")
        .map(|one| {
            one.expect("an entry")
                .file_name()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    names.sort();
    assert_eq!(
        names,
        [
            "hmz-offline.md",
            "hmz-read-only-web.md",
            "hmz-read-only.md",
            "mine.md"
        ]
    );
    assert!(!home.linked().iter().any(|one| one == "agents"));
    home.drop_home().expect("dropped");

    let theirs: Vec<_> = fs::read_dir(user.join(".gemini/antigravity-cli/agents"))
        .expect("listed")
        .map(|one| one.expect("an entry").file_name())
        .collect();
    assert_eq!(theirs, ["mine.md"]);
}

#[test]
fn a_merge_humanize_has_no_merger_for_leaves_no_home() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        merges: vec![
            (s("hmz.nowhere:_merge"), s("null")),
            (s("os:system"), s("\"true\"")),
        ],
        ..Virtual::default()
    };

    let error = build_with(&spec, &env(&user), under(&tmp.path))
        .err()
        .expect("refused");

    assert!(error.to_string().contains("no merger"));
    let left: Vec<_> = fs::read_dir(&tmp.path)
        .expect("listed")
        .map(|one| one.expect("an entry").file_name())
        .collect();
    assert_eq!(left, ["user"]);
}

fn threads(at: &Path) -> rusqlite::Connection {
    rusqlite::Connection::open(at).expect("a database")
}

fn rows(at: &Path) -> HashMap<String, String> {
    let connection = threads(at);
    let mut said = connection
        .prepare("select id, rollout_path from threads")
        .expect("prepared");
    said.query_map([], |row| Ok((row.get(0)?, row.get(1)?)))
        .expect("queried")
        .collect::<Result<_, _>>()
        .expect("rows")
}

#[test]
fn a_path_of_the_home_the_cli_wrote_down_is_followed_as_it_goes() {
    let tmp = tmp();
    let real = tmp.path.join("user/.codex");
    fs::create_dir_all(real.join("sessions")).expect("made");
    let state = real.join("state_5.sqlite");
    threads(&state)
        .execute("create table threads (id text, rollout_path text)", [])
        .expect("made");
    let spec = Virtual {
        variable: s("CODEX_HOME"),
        default: s(".codex"),
        rewrites: vec![s("config.toml")],
        made: vec![s("sessions")],
        records: vec![(s("state_*.sqlite"), s("threads"), s("rollout_path"))],
        ..Virtual::default()
    };
    let home = built(&spec, &env(&tmp.path.join("user")), &tmp.path);
    let at = home.dir().display().to_string();
    write(&home.dir().join("sessions/a.jsonl"), "{}\n");
    let gone = format!("{at}/sessions/b.jsonl");
    let other = format!("{}/sessions/c.jsonl", real.display());
    let connection = threads(&home.dir().join("state_5.sqlite"));
    for (id, path) in [
        ("kept", format!("{at}/sessions/a.jsonl")),
        ("gone", gone.clone()),
        ("other", other.clone()),
    ] {
        connection
            .execute("insert into threads values (?, ?)", [id, &path])
            .expect("inserted");
    }
    drop(connection);

    home.drop_home().expect("dropped");

    assert_eq!(
        rows(&state),
        HashMap::from([
            (
                s("kept"),
                real.join("sessions/a.jsonl").to_string_lossy().into_owned()
            ),
            (s("gone"), gone),
            (s("other"), other),
        ])
    );
}

fn keeping(tmp: &Path) -> Virtual {
    Virtual {
        variable: s("CODEX_HOME"),
        default: s(".codex"),
        rewrites: vec![s("config.toml")],
        made: vec![s("sessions"), s("session_index.jsonl")],
        kept: vec![s("state_*.sqlite*")],
        records: vec![(s("state_*.sqlite"), s("threads"), s("rollout_path"))],
        keeps: tmp.join("epic/codex").to_string_lossy().into_owned(),
        ..Virtual::default()
    }
}

#[test]
fn a_home_keeping_conversations_elsewhere_links_them_there() {
    let tmp = tmp();
    let real = tmp.path.join("user/.codex");
    fs::create_dir_all(real.join("sessions")).expect("made");
    write(&real.join("state_5.sqlite"), "theirs\n");
    write(&real.join("auth.json"), "token\n");
    let keeps = tmp.path.join("epic/codex");
    write(&keeps.join("state_6.sqlite"), "the run's\n");

    let home = built(&keeping(&tmp.path), &env(&tmp.path.join("user")), &tmp.path);
    write(&home.dir().join("sessions/a.jsonl"), "{}\n");
    fs::write(home.dir().join("session_index.jsonl"), "a\n").expect("written");
    fs::write(home.dir().join("state_5.sqlite"), "the run's own\n").expect("written");

    assert_eq!(
        fs::canonicalize(home.dir().join("auth.json")).expect("there"),
        real.join("auth.json")
    );
    assert!(keeps.join("sessions/a.jsonl").is_file());
    assert_eq!(read(&keeps.join("session_index.jsonl")), "a\n");
    assert_eq!(read(&keeps.join("state_5.sqlite")), "the run's own\n");
    assert_eq!(read(&home.dir().join("state_6.sqlite")), "the run's\n");
    home.drop_home().expect("dropped");
    assert_eq!(
        fs::read_dir(real.join("sessions")).expect("listed").count(),
        0
    );
    assert!(!real.join("session_index.jsonl").exists());
    assert_eq!(read(&real.join("state_5.sqlite")), "theirs\n");
    assert!(!real.join("state_6.sqlite").exists());
}

#[test]
fn a_database_made_in_a_home_keeping_elsewhere_is_moved_there_followed() {
    let tmp = tmp();
    let real = tmp.path.join("user/.codex");
    fs::create_dir_all(&real).expect("made");
    let home = built(&keeping(&tmp.path), &env(&tmp.path.join("user")), &tmp.path);
    write(&home.dir().join("sessions/a.jsonl"), "{}\n");
    let connection = threads(&home.dir().join("state_5.sqlite"));
    connection
        .execute("create table threads (id text, rollout_path text)", [])
        .expect("made");
    let named = format!("{}/sessions/a.jsonl", home.dir().display());
    connection
        .execute("insert into threads values (?, ?)", ["a", &named])
        .expect("inserted");
    drop(connection);

    home.drop_home().expect("dropped");

    let keeps = tmp.path.join("epic/codex");
    assert_eq!(
        rows(&keeps.join("state_5.sqlite")),
        HashMap::from([(
            s("a"),
            keeps
                .join("sessions/a.jsonl")
                .to_string_lossy()
                .into_owned()
        )])
    );
    assert!(!real.join("state_5.sqlite").exists());
}

#[test]
fn a_replaced_link_into_a_kept_directory_is_written_back_there() {
    let tmp = tmp();
    let real = tmp.path.join("user/.codex");
    fs::create_dir_all(&real).expect("made");
    let home = built(&keeping(&tmp.path), &env(&tmp.path.join("user")), &tmp.path);
    fs::remove_file(home.dir().join("session_index.jsonl")).expect("unlinked");
    fs::write(home.dir().join("session_index.jsonl"), "renamed over\n").expect("written");

    home.drop_home().expect("dropped");

    assert_eq!(
        read(&tmp.path.join("epic/codex/session_index.jsonl")),
        "renamed over\n"
    );
    assert!(!real.join("session_index.jsonl").exists());
}

#[test]
fn a_link_planted_in_the_users_home_is_not_written_through() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let outside = tmp.path.join("bashrc");
    write(&outside, "theirs\n");
    timed(&outside, 1_000_000);
    let planted = user.join(".claude/.credentials.json");
    fs::remove_file(&planted).expect("unlinked");
    symlink(&outside, &planted).expect("linked");
    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            writable: inside(&[&user.join(".claude")]),
            ..under(&tmp.path)
        },
    )
    .expect("built");

    renamed(&home.dir().join(".credentials.json"), "payload\n", None);
    home.drop_home().expect("dropped");

    assert_eq!(read(&outside), "theirs\n");
}

#[test]
fn a_directory_planted_as_a_link_is_not_written_through() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let outside = tmp.path.join("elsewhere");
    fs::create_dir(&outside).expect("made");
    symlink(&outside, user.join(".claude/d")).expect("linked");
    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            writable: inside(&[&user.join(".claude")]),
            ..under(&tmp.path)
        },
    )
    .expect("built");
    fs::remove_file(home.dir().join("d")).expect("unlinked");
    write(&home.dir().join("d/.bashrc"), "payload\n");

    home.drop_home().expect("dropped");

    assert!(!outside.join(".bashrc").exists());
}

#[test]
fn a_replacement_the_agent_may_write_is_still_written_back() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let real = user.join(".claude/.credentials.json");
    timed(&real, 1_000_000);
    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            readable: inside(&[&user.join(".claude"), &tmp.path]),
            writable: inside(&[&user.join(".claude")]),
            ..under(&tmp.path)
        },
    )
    .expect("built");

    renamed(&home.dir().join(".credentials.json"), "refreshed\n", None);
    home.drop_home().expect("dropped");

    assert_eq!(read(&real), "refreshed\n");
}

#[test]
fn a_copy_is_never_made_of_what_the_agent_may_not_read() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let secret = tmp.path.join("id_ed25519");
    write(&secret, "key\n");
    let settings = user.join(".claude/settings.json");
    fs::remove_file(&settings).expect("unlinked");
    symlink(&secret, &settings).expect("linked");

    let home = build_with(
        &claude(),
        &env(&user),
        Options {
            readable: inside(&[&user.join(".claude"), &user.join(".claude.json")]),
            ..under(&tmp.path)
        },
    )
    .expect("built");

    assert!(!home.dir().join("settings.json").exists());
    assert_eq!(
        read(&home.dir().join(".claude.json")),
        "{\"outside\": true}\n"
    );
    home.drop_home().expect("dropped");
}

#[test]
fn what_the_cli_made_is_not_moved_through_a_link_planted_for_it() {
    let tmp = tmp();
    let user = user(&tmp.path);
    let spec = Virtual {
        variable: s("CLAUDE_CONFIG_DIR"),
        default: s(".claude"),
        kept: vec![s("state_*.sqlite*")],
        ..Virtual::default()
    };
    let home = built(&spec, &env(&user), &tmp.path);
    write(&home.dir().join("state_2.sqlite"), "payload\n");
    let target = tmp.path.join("authorized_keys");
    symlink(&target, user.join(".claude/state_2.sqlite")).expect("linked");

    home.drop_home().expect("dropped");

    assert!(!target.exists());
}

// The mergers' own refusals and what they keep of the user's, each as its Python one.

#[test]
fn a_pi_models_file_that_is_not_plain_json_is_refused() {
    let tmp = tmp();
    write(&tmp.path.join("models.json"), "{ // theirs\n}\n");
    let said = json!({"named": "humanize-x", "declared": {"baseUrl": "http://gw"}});

    let error =
        mergers::merge("hmz.coganchor.agents.pi:_declare", &tmp.path, &said).expect_err("refused");

    assert!(
        error
            .to_string()
            .contains("the gateway http://gw cannot be added")
    );
    assert!(
        error
            .to_string()
            .contains(r#"{"humanize-x": {"baseUrl": "http://gw"}}"#)
    );
    write(&tmp.path.join("models.json"), "{\"providers\": []}");
    let error =
        mergers::merge("hmz.coganchor.agents.pi:_declare", &tmp.path, &said).expect_err("refused");
    assert!(error.to_string().contains("holds no providers by name"));
}

#[test]
fn a_qwen_settings_file_that_is_not_an_object_is_refused() {
    let tmp = tmp();
    let said = json!({"managed": {}, "headless": true});
    for (text, wanted) in [
        ("[]", "is not a JSON object"),
        ("{,}", "cannot be read as plain JSON"),
    ] {
        write(&tmp.path.join("settings.json"), text);
        let error = mergers::merge("hmz.coganchor.agents.qwen:_merged", &tmp.path, &said)
            .expect_err("refused");
        assert!(error.to_string().contains(wanted), "{error}");
    }
}

#[test]
fn codex_rules_link_the_users_own_and_write_humanizes_beside() {
    let tmp = tmp();
    let theirs = tmp.path.join("theirs");
    write(&theirs.join("default.rules"), "theirs\n");
    write(&theirs.join("hmz.rules"), "an old one\n");
    fs::create_dir_all(tmp.path.join("home")).expect("made");
    symlink(&theirs, tmp.path.join("home/rules")).expect("linked");

    mergers::merge(
        "hmz.coganchor.agents.codex:_ruled",
        &tmp.path.join("home"),
        &json!(["hmz-git"]),
    )
    .expect("merged");

    let rules = tmp.path.join("home/rules");
    assert!(!is_link(&rules));
    assert_eq!(
        read(&rules.join("hmz.rules")),
        "prefix_rule(pattern=[\"hmz-git\"], decision=\"allow\")\n"
    );
    assert_eq!(
        fs::read_link(rules.join("default.rules")).expect("a link"),
        theirs.join("default.rules")
    );
    assert_eq!(read(&theirs.join("hmz.rules")), "an old one\n");
}
