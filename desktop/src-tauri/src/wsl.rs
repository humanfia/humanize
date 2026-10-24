//! On Windows hmz lives in WSL: everything of hmz's, uv's or the login shell's is started
//! through `wsl.exe`, in the default distribution, from its user's home.

use std::collections::HashMap;
use std::ffi::{OsStr, OsString};
use std::os::windows::process::CommandExt;
use std::process::Command;

/// No console window for `wsl.exe`.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// `program`, a path or a name in WSL, run there; with `env`, in that environment alone.
pub fn command(program: impl AsRef<OsStr>, env: Option<&HashMap<OsString, OsString>>) -> Command {
    let mut command = Command::new("wsl.exe");
    command
        .args(["--cd", "~", "--exec"])
        .creation_flags(CREATE_NO_WINDOW);
    if let Some(env) = env {
        command.args(["/usr/bin/env", "-i"]);
        for (key, value) in env {
            let mut pair = key.clone();
            pair.push("=");
            pair.push(value);
            command.arg(pair);
        }
    }
    command.arg(program);
    command
}
