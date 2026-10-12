/// The app's commands, each granted by a capability: `notify` to `hmz web`'s page, the rest to
/// the app's own.
const COMMANDS: &[&str] = &["status", "retry", "keep", "update_now", "notify"];

fn main() {
    let manifest = tauri_build::AppManifest::new().commands(COMMANDS);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(manifest))
        .expect("failed to run the Tauri build script");
}
