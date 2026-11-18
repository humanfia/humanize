//! agy's merger: Humanize's agents in the virtual home's `agents/`. Port of
//! `hmz.coganchor.agents.agy._agents` and the `_DEFINED` it writes.

use std::fs;
use std::io;
use std::path::Path;

use super::owned;

/// Each agent of Humanize's, by name, as the file agy reads it out of (`agy._DEFINED`, in its
/// order).
pub const DEFINED: [(&str, &str); 3] = [
    (
        "hmz-read-only",
        "---
name: hmz-read-only
description: Reads, and runs commands that change nothing.
tools: [view_file, grep_search, find_by_name, list_dir, run_command]
excludeDefaultComponents: true
subagent: false
---
# Reader

You may read files, search them, and run commands. You may not change anything: no tool here
writes a file, and any command that tries to write is refused. When asked to change something,
say that you cannot.
",
    ),
    (
        "hmz-read-only-web",
        "---
name: hmz-read-only-web
description: Reads, the web included, and runs commands that change nothing.
tools: [view_file, grep_search, find_by_name, list_dir, run_command, read_url_content, search_web]
excludeDefaultComponents: true
subagent: false
---
# Reader

You may read files, search them, run commands, and read and search the web. You may not change
anything: no tool here writes a file, and any command that tries to write is refused. When
asked to change something, say that you cannot.
",
    ),
    (
        "hmz-offline",
        "---
name: hmz-offline
description: Works on this machine, without the web.
tools: [view_file, grep_search, find_by_name, list_dir, run_command, write_to_file, replace_file_content, manage_task, generate_image, ask_question]
subagent: false
---
# Offline

You have no tool that reaches the web, and the commands you run cannot reach it either.
",
    ),
];

/// `_agents(home, None)`: the home's `agents/` made its own, linking each of the user's
/// agents and holding Humanize's beside them.
pub fn agents(home: &Path) -> io::Result<()> {
    let into = home.join("agents");
    let ours: Vec<String> = DEFINED
        .iter()
        .map(|(name, _)| format!("{name}.md"))
        .collect();
    owned(&into, &ours)?;
    for (name, text) in DEFINED {
        fs::write(into.join(format!("{name}.md")), text)?;
    }
    Ok(())
}
