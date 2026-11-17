//! `tests/unit/coganchor/test_policy.py`'s `Layout` and `Router` cases, ported.

use coganchor::cog::router::{Layout, Place, Router, RouterConfig};

fn s(all: &[&str]) -> Vec<String> {
    all.iter().map(|one| (*one).to_owned()).collect()
}

fn p(all: &[(&str, &str)]) -> Vec<(String, String)> {
    all.iter()
        .map(|(a, b)| ((*a).to_owned(), (*b).to_owned()))
        .collect()
}

fn router(config: RouterConfig, platform: &str) -> Router {
    let router = Router::new(config);
    router.learn_platform(platform);
    router
}

/// A router over one mirror at `/srv/mirror`, answering for a target on `platform`.
fn on(platform: &str) -> Router {
    router(
        RouterConfig {
            layouts: vec![Layout::create("/srv/mirror", Some("/work"))],
            ..Default::default()
        },
        platform,
    )
}

fn layouts(all: &[(&str, Option<&str>)]) -> Vec<Layout> {
    all.iter()
        .map(|(local, remote)| Layout::create(local, *remote))
        .collect()
}

#[test]
fn a_layout_with_no_target_path_is_the_mirror_itself() {
    let layout = Layout::create("/srv/mirror/", None);
    assert_eq!(layout.local_root(), "/srv/mirror");
    assert_eq!(layout.virtual_root(), "/srv/mirror");
    assert_eq!(
        layout.to_virtual("/srv/mirror/a").as_deref(),
        Some("/srv/mirror/a")
    );
}

#[test]
fn a_layout_names_a_path_as_the_target_does() {
    let layout = Layout::create("/srv/mirror", Some("/work"));
    assert_eq!(layout.to_virtual("/srv/mirror").as_deref(), Some("/work"));
    assert_eq!(
        layout.to_virtual("/srv/mirror/src/x.py").as_deref(),
        Some("/work/src/x.py")
    );
    assert_eq!(
        layout.to_virtual("/SRV/Mirror/src").as_deref(),
        Some("/work/src")
    );
    assert_eq!(layout.to_virtual("/etc/passwd"), None);
}

#[test]
fn a_layout_holds_what_lies_under_its_root_comparing_case_only_when_asked() {
    let layout = Layout::create("/srv/mirror", Some("/work"));
    for (path, inside) in [
        ("/srv/mirror", true),
        ("/srv/mirror/a", true),
        ("/srv/mirrored", false),
        ("/srv", false),
    ] {
        assert_eq!(layout.contains(path, false), inside, "{path}");
    }
    assert!(!layout.contains("/SRV/MIRROR/a", false));
    assert!(layout.contains("/SRV/MIRROR/a", true));
    assert_eq!(layout.below("/SRV/MIRROR/a", true).as_deref(), Some("a"));
}

#[test]
fn paths_in_the_mirror_are_the_targets_and_the_rest_are_local() {
    let router = on("linux");
    assert!(router.is_remote_path("/srv/mirror/a"));
    assert!(!router.is_remote_path("/home/me/.ssh"));
    assert_eq!(
        router.to_virtual("/srv/mirror/a").as_deref(),
        Some("/work/a")
    );
    assert_eq!(router.to_virtual("/home/me"), None);
    assert_eq!(
        router.place("/srv/mirror/a"),
        Place::Mirror {
            local: "/srv/mirror/a".into(),
            virtual_path: "/work/a".into()
        }
    );
    assert_eq!(router.place("/home/me"), Place::Local);
    assert_eq!(router.virtual_cwd("/srv/mirror/sub"), "/work/sub");
    assert_eq!(router.virtual_cwd("/home/me"), "/home/me");
}

#[test]
fn nested_layouts_prefer_the_longest_root() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/m", Some("/w")), ("/m/inner", Some("/elsewhere"))]),
            ..Default::default()
        },
        "",
    );
    assert_eq!(
        router.to_virtual("/m/inner/a").as_deref(),
        Some("/elsewhere/a")
    );
    assert_eq!(router.to_virtual("/m/other").as_deref(), Some("/w/other"));
}

#[test]
fn local_paths_carve_holes_in_the_mirror_in_whatever_case_the_target_ignores() {
    let config = RouterConfig {
        layouts: layouts(&[("/m", Some("/w"))]),
        local_paths: s(&["/m/.state"]),
        ..Default::default()
    };
    let linux = router(config.clone(), "");
    assert!(linux.layout_for("/m/.state/x").is_none());
    assert!(linux.layout_for("/m/src").is_some());
    assert!(router(config, "darwin").layout_for("/m/.STATE/x").is_none());
}

#[test]
fn a_mirror_inside_a_local_path_is_still_the_targets() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/home/me/.hmz/mirror", Some("/w"))]),
            local_paths: s(&["/home/me/.hmz"]),
            ..Default::default()
        },
        "",
    );
    assert!(router.is_remote_path("/home/me/.hmz/mirror/a"));
    assert!(!router.is_remote_path("/home/me/.hmz/other"));
}

#[test]
fn programs_run_on_the_target_unless_kept_here() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/m", Some("/w"))]),
            local_programs: s(&["/opt/agent"]),
            ..Default::default()
        },
        "",
    );
    assert!(router.runs_locally("/opt/agent/bin/node"));
    assert!(!router.runs_locally("/usr/bin/git"));
    assert!(!router.runs_locally("/opt/agentx"));
}

#[test]
fn rewriting() {
    let same = router(
        RouterConfig {
            layouts: layouts(&[("/m", None)]),
            ..Default::default()
        },
        "",
    );
    assert_eq!(same.rewrite("grep -r x /m/src"), "grep -r x /m/src");
    assert_eq!(
        on("linux").rewrite("grep -r x /srv/mirror/src"),
        "grep -r x /work/src"
    );
    assert_eq!(
        on("linux").rewrite("echo hello/srv/mirror"),
        "echo hello/srv/mirror"
    );
    assert_eq!(
        on("linux").rewrite("cat /SRV/MIRROR/a"),
        "cat /SRV/MIRROR/a"
    );
    assert_eq!(on("darwin").rewrite("cat /SRV/MIRROR/a"), "cat /work/a");
    let private = router(
        RouterConfig {
            layouts: layouts(&[("/tmp/m", Some("/w"))]),
            ..Default::default()
        },
        "",
    );
    assert_eq!(private.rewrite("ls /private/tmp/m/x"), "ls /w/x");
    let aliased = router(
        RouterConfig {
            layouts: layouts(&[("/srv/mirror", Some("/work"))]),
            aliases: p(&[("/home/me/proj", "/srv/mirror")]),
            ..Default::default()
        },
        "",
    );
    assert_eq!(aliased.rewrite("cat /home/me/proj/a"), "cat /work/a");
}

#[test]
fn a_redirect_answers_by_the_entry_that_says_most() {
    let router = router(
        RouterConfig {
            redirects: p(&[("/h/.c", "/p/all"), ("/h/.c/creds.json", "/p/creds.json")]),
            ..Default::default()
        },
        "",
    );
    assert_eq!(
        router.swap("/h/.c/creds.json").as_deref(),
        Some("/p/creds.json")
    );
    assert_eq!(router.swap("/h/.c/other").as_deref(), Some("/p/all/other"));
    assert_eq!(router.swap("/h/elsewhere"), None);
}

#[test]
fn a_target_not_yet_reached_is_no_mac() {
    let router = Router::new(RouterConfig {
        layouts: layouts(&[("/m", Some("/w"))]),
        ..Default::default()
    });
    assert!(!router.insensitive());
    assert!(!router.settles());
    assert!(on("darwin").insensitive());
    assert!(!on("linux").insensitive());
}

#[test]
fn a_session_with_one_spelling_for_everything_has_nothing_to_settle() {
    let router = on("linux");
    assert!(!router.settles());
    assert_eq!(router.canonical("/SRV/MIRROR/a"), "/SRV/MIRROR/a");
}

#[test]
fn what_settles_is_asked_again_until_the_target_answers() {
    let router = Router::new(RouterConfig {
        layouts: layouts(&[("/m", Some("/w"))]),
        ..Default::default()
    });
    assert!(!router.settles());
    assert_eq!(router.canonical("/M/a"), "/M/a");
    router.learn_platform("");
    assert!(!router.settles());
    router.learn_platform("darwin");
    assert!(router.settles());
    assert_eq!(router.canonical("/M/a"), "/m/a");
    // A machine does not become another one mid-session.
    router.learn_platform("linux");
    assert!(router.settles());
    assert_eq!(router.platform(), "darwin");
}

#[test]
fn a_mac_settles_a_path_onto_the_mirrors_own_spelling() {
    for (path, settled) in [
        ("/SRV/Mirror/a/B", "/srv/mirror/a/B"),
        ("/srv/mirror", "/srv/mirror"),
        ("/SRV/MIRROR", "/srv/mirror"),
        ("/Elsewhere/X", "/Elsewhere/X"),
    ] {
        assert_eq!(on("darwin").canonical(path), settled);
    }
}

#[test]
fn a_path_named_through_private_is_settled_onto_the_mirror() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/tmp/m", Some("/w"))]),
            ..Default::default()
        },
        "linux",
    );
    assert!(router.settles());
    assert_eq!(router.canonical("/private/tmp/m/a"), "/tmp/m/a");
    assert_eq!(router.canonical("/private/var/x"), "/private/var/x");
}

#[test]
fn a_fold_that_changes_length_is_a_refusal_not_a_match() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/strasse/m", Some("/w"))]),
            ..Default::default()
        },
        "darwin",
    );
    assert_eq!(router.canonical("/STRASSE/m/x"), "/strasse/m/x");
    assert_eq!(router.canonical("/straße/m/x"), "/straße/m/x");
}

#[test]
fn the_workspace_named_by_its_own_path_is_settled_onto_the_mirror() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/srv/mirror", Some("/work"))]),
            aliases: p(&[("/work", "/srv/mirror")]),
            ..Default::default()
        },
        "linux",
    );
    assert_eq!(router.canonical("/work/a"), "/srv/mirror/a");
    assert_eq!(router.canonical("/work"), "/srv/mirror");
    assert_eq!(router.canonical("/workshop"), "/workshop");
}

#[test]
fn an_alias_keeps_the_holes_and_programs_named_under_it() {
    let router = router(
        RouterConfig {
            layouts: layouts(&[("/srv/mirror", Some("/work"))]),
            local_paths: s(&["/work/.state"]),
            local_programs: s(&["/work/bin/agent"]),
            aliases: p(&[("/work", "/srv/mirror")]),
            ..Default::default()
        },
        "",
    );
    assert!(router.layout_for("/srv/mirror/.state/x").is_none());
    assert!(router.runs_locally("/srv/mirror/bin/agent"));
}
