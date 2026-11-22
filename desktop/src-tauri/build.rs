/// The app's commands, each granted to its window by capabilities/default.json: the splash's,
/// and the page's (Section 3.7.11 and Section 3.12 of [DESKTOP]).
const COMMANDS: &[&str] = &[
    "status",
    "retry",
    "keep",
    "update_now",
    "notify",
    "file_read",
    "pipe_open",
    "pipe_send",
    "pipe_close",
    "pipe_answer",
    "easytier_list",
    "easytier_set",
    "easytier_remove",
];

/// What tauri.conf.json's `frontendDist` builds into the app: the page, and the splash beside it.
const CARRIED: &[&str] = &["../../src/hmz/web/static", "../ui"];

fn main() {
    // Built in again once the page or the splash changes.
    for dir in CARRIED {
        println!("cargo:rerun-if-changed={dir}");
    }
    let manifest = tauri_build::AppManifest::new().commands(COMMANDS);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to run the Tauri build script");
}
