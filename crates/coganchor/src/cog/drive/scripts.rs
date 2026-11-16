//! The POSIX shell a native turn settles itself with on the target, byte for byte the
//! Python's: the `_FIND_PROGRAM` .. `_PACK` of `hmz.coganchor.anchor`, and `SCRIPT`, `BACK` and
//! `words` of `hmz.coganchor.homes`.
//!
//! Each is run as `/bin/sh -c SCRIPT humanize ARG...`, so no argument is ever spliced into the
//! script's text. `SCRIPT` and `BACK` are `homes`' own, re-exported here.

use serde::Deserialize;

use crate::cog::homes::Virtual;

/// The command line running `script` with `args` on the target.
pub(super) fn sh(script: &str, args: &[&str]) -> Vec<String> {
    let mut argv = vec![
        "/bin/sh".to_owned(),
        "-c".to_owned(),
        script.to_owned(),
        "humanize".to_owned(),
    ];
    argv.extend(args.iter().map(|one| (*one).to_owned()));
    argv
}

/// What a virtual home is made of, read from the JSON `Virtual.dumps` writes. Only what a
/// native turn reads of it; `loads` (unit 14) has checked it already.
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub(super) struct Spec {
    pub variable: String,
    pub default: String,
    pub rewrites: Vec<String>,
    pub outside: Vec<(String, String)>,
    pub lodges: String,
    pub secures: String,
    pub private: Vec<String>,
    pub made: Vec<String>,
    pub skills: Vec<(String, String)>,
    pub records: Vec<(String, String, String)>,
}

impl Spec {
    /// The spec a virtual home's JSON says.
    pub fn of(home: &Virtual) -> anyhow::Result<Spec> {
        let raw: serde_json::Value = serde_json::from_str(&home.dumps())
            .map_err(|why| anyhow::anyhow!("not a virtual home: {why}"))?;
        Spec::deserialize(&raw).map_err(|why| anyhow::anyhow!("not a virtual home: {why}"))
    }

    /// What [`SCRIPT`] is told after its first four arguments, and [`BACK`] after its first.
    /// Port of `homes.words`.
    pub fn words(&self) -> Vec<String> {
        let outside = |one: &str| {
            self.outside
                .iter()
                .rev()
                .find(|(under, _)| under == one)
                .map_or("", |(_, there)| there.as_str())
        };
        let mut words = Vec::new();
        words.extend(
            self.rewrites
                .iter()
                .map(|one| format!("copy={one}={}", outside(one))),
        );
        words.extend(self.private.iter().map(|one| format!("keep={one}")));
        words.extend(self.made.iter().map(|one| format!("make={one}")));
        words.extend(self.skills.iter().map(|(name, _)| format!("skill={name}")));
        words.extend(
            self.records
                .iter()
                .map(|(one, table, column)| format!("record={one}={table}={column}")),
        );
        words
    }
}

/// Finding the CLI on the target, in POSIX sh (`_FIND_PROGRAM`). `command -v` rather than
/// `which`; a path is answered with itself where it is executable.
/// `homes.SCRIPT` and `homes.BACK`, which build and write back a virtual home on the target.
pub(super) use crate::cog::homes::{BACK, SCRIPT};

pub(super) const FIND_PROGRAM: &str = r##"command -v -- "$1" 2>/dev/null || exit 127"##;

/// Making the directory a session's credentials live in on the target (`_MAKE_SESSION`):
/// `mktemp -d`, made only its owner's again by the `umask` and the `chmod`; BSD's and GNU's
/// spellings both.
pub(super) const MAKE_SESSION: &str = r##"umask 077; d=$(mktemp -d 2>/dev/null || mktemp -d -t humanize) || exit 1; chmod 700 "$d" || exit 1; printf %s "$d""##;

/// Writing one credential from what arrives on stdin (`_WRITE_PRIVATELY`): whatever was at the
/// name goes first, and the file is `0600` before anything is in it.
pub(super) const WRITE_PRIVATELY: &str = r##"umask 077; mkdir -p "$(dirname -- "$1")" || exit 1; rm -f -- "$1" || exit 1; : > "$1" || exit 1; chmod 600 "$1" || exit 1; cat > "$1""##;

/// Writing one file of a skill from stdin with the mode in `$2` (`_WRITE_WHOLE`): beside it and
/// moved over it, so it is never half written.
pub(super) const WRITE_WHOLE: &str = r##"umask 077; mkdir -p "$(dirname -- "$1")" || exit 1; t="$1.hmz-new"; rm -f -- "$t"; if cat > "$t" && chmod "$2" "$t" && mv -f -- "$t" "$1"; then exit 0; fi; rm -f -- "$t"; exit 1"##;

/// Taking one of them away again, whatever it turned out to be (`_SWEEP`).
pub(super) const SWEEP: &str = r##"rm -rf -- "$1""##;

/// Reading one of them back once the CLI is done with it (`_READ_BACK`).
pub(super) const READ_BACK: &str = r##"cat -- "$1""##;

/// Everything at the paths after `$1` inside it, each a glob of one name per part, as one
/// `tar` on stdout, or nothing where none is there (`_PACK`).
pub(super) const PACK: &str = r##"
cd "$1" 2>/dev/null || exit 0
shift
n=$#
for p in "$@"; do for f in $p; do [ -e "$f" ] && set -- "$@" "$f"; done; done
shift "$n"
[ $# -gt 0 ] || exit 0
tar cf - "$@" 2>/dev/null
exit 0
"##;
