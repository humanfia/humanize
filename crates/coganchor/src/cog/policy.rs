//! What a redirect answers a path with, shared by the cog and the cred tracer. Port of
//! `answered`, `head` and `parents` in `hmz.coganchor.policy`. [Unit 8]

use std::io;

/// The path `redirects` answer `path` with (`*` patterns allowed), if any.
pub fn answered(redirects: &[(String, String)], path: &str) -> Option<String> {
    todo!("unit 8")
}

/// The directory a redirect target lives in (the part before any `*`).
pub fn head(target: &str) -> String {
    todo!("unit 8")
}

/// Makes the parent directories of a redirect target that is about to be created.
pub fn parents(path: &str) -> io::Result<()> {
    todo!("unit 8")
}
