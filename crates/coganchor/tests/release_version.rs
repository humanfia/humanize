//! The crate's version is hmz's: `--version`, HELLO and an agent's `HUMANIZE` all say it. On
//! `main` it is 0.0.0, and the release pull request sets it, in the manifest and in the lock
//! `cargo build --locked` holds it to, so release-please has to be told of both.

use std::fs;
use std::path::Path;

use serde_json::Value;

#[test]
fn a_release_sets_the_crates_version_in_its_manifest_and_its_lock() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let config = fs::read_to_string(root.join("release-please-config.json")).unwrap();
    let config: Value = serde_json::from_str(&config).unwrap();
    let bumped = config["packages"]["."]["extra-files"].as_array().unwrap();
    for (path, jsonpath) in [
        ("crates/coganchor/Cargo.toml", "$.package.version"),
        (
            "crates/coganchor/Cargo.lock",
            "$.package[?(@.name.value=='coganchor')].version",
        ),
    ] {
        assert!(root.join(path).is_file(), "{path} is not in the repository");
        assert!(
            bumped.iter().any(|file| file["type"] == "toml"
                && file["path"] == path
                && file["jsonpath"] == jsonpath),
            "release-please-config.json does not bump {path}"
        );
    }
}
