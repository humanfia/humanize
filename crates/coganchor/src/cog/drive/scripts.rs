//! The POSIX shell a native turn settles itself with on the target, byte for byte the
//! Python's: the `_FIND_PROGRAM` .. `_PACK` of `hmz.coganchor.anchor`, and `SCRIPT`, `BACK` and
//! `words` of `hmz.coganchor.homes`.
//!
//! Each is run as `/bin/sh -c SCRIPT humanize ARG...`, so no argument is ever spliced into the
//! script's text. Unit 14 owns `homes` and declares none of `SCRIPT`, `BACK` or `words` yet;
//! they live here, privately, until it does.

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
        Spec::deserialize(&home.raw).map_err(|why| anyhow::anyhow!("not a virtual home: {why}"))
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

/// `homes.build` as POSIX sh for a target where nothing of Humanize runs (`homes.SCRIPT`): run as
/// `sh -c SCRIPT humanize AT VARIABLE DEFAULT LODGES [WORD...]` after anything projected into
/// `AT` has landed. Prints the user's own value of the variable; lists what it linked in
/// `AT.links` for [`BACK`].
pub(super) const SCRIPT: &str = r##"
set -e
at=$1 var=$2 default=$3 lodges=$4
shift 4
eval "moved=\${$var:-}"
real=${moved:-$HOME/$default}
umask 077
mkdir -p "$at"
: > "$at.links"
nl='
'
link() {
  if [ -e "$at/$1" ] || [ -h "$at/$1" ]; then return 0; fi
  ln -s -- "$real/$1" "$at/$1"
  case $real/$1 in *"$nl"*) ;; *) printf '%s\n' "$real/$1" >> "$at.links" ;; esac
}
skipped() {
  for word in "$@"; do
    case $word in
    copy=*) spec=${word#copy=}; rel=${spec%%=*}; [ "$name" = "${rel%%/*}" ] && return 0 ;;
    keep=*) case $name in ${word#keep=}) return 0 ;; esac ;;
    esac
  done
  [ "$name" = "$lodges" ]
}
for word in "$@"; do
  case $word in
  copy=*)
    spec=${word#copy=}; rel=${spec%%=*}; alt=${spec#*=}; src=$real/$rel
    if [ -z "$moved" ] && [ -n "$alt" ]; then src=$HOME/$alt; fi
    if [ -d "$src" ]; then mkdir -p "$at/$rel"
    elif [ ! -e "$at/$rel" ] && [ -e "$src" ]; then
      mkdir -p "$(dirname -- "$at/$rel")"; cp -p -- "$src" "$at/$rel"
    fi ;;
  esac
done
for word in "$@"; do
  case $word in
  make=*)
    name=${word#make=}
    skipped "$@" && continue
    case $name in *.*) mkdir -p "$real" ;; *) mkdir -p "$real/$name" ;; esac
    link "$name" ;;
  esac
done
for f in "$real"/* "$real"/.[!.]* "$real"/..?*; do
  [ -e "$f" ] || [ -h "$f" ] || continue
  name=${f##*/}
  skipped "$@" && continue
  link "$name"
done
if [ -n "$lodges" ]; then
  mkdir -p "$at/$lodges"
  for f in "$real/$lodges"/* "$real/$lodges"/.[!.]* "$real/$lodges"/..?*; do
    [ -e "$f" ] || [ -h "$f" ] || continue
    name=${f##*/}
    ours=
    for word in "$@"; do [ "$word" = "skill=$name" ] && ours=1; done
    [ -n "$ours" ] || [ -e "$at/$lodges/$name" ] || ln -s -- "$f" "$at/$lodges/$name"
  done
fi
printf '%s\n' "$moved"
"##;

/// `Home.drop`'s writing back, for a home [`SCRIPT`] built (`homes.BACK`): run as
/// `sh -c BACK humanize AT [WORD...]` once the CLI is done, before `AT` is taken away.
pub(super) const BACK: &str = r##"
at=$1
shift
[ -f "$at.links" ] || exit 0
put='
src=$1 dst=$2
shift 2
for g in "$@"; do
  [ -f "$g" ] && [ ! -h "$g" ] || continue
  t=$dst${g#"$src"} n=0
  while [ -h "$t" ] && [ $n -lt 8 ]; do
    l=$(readlink -- "$t") || break
    case $l in /*) t=$l ;; *) t=$(dirname -- "$t")/$l ;; esac
    n=$((n + 1))
  done
  if [ -e "$t" ]; then
    [ -f "$t" ] || continue
    # Where times are only to the second, the same second and other bytes is newer.
    [ "$g" -nt "$t" ] || { ! [ "$t" -nt "$g" ] && ! cmp -s -- "$g" "$t"; } || continue
  fi
  d=$(dirname -- "$t")
  mkdir -p -- "$d" 2>/dev/null || continue
  tmp=$d/.hmz-back.$$
  rm -f -- "$tmp"
  if [ -e "$t" ] && cp -p -- "$t" "$tmp" 2>/dev/null && cat -- "$g" > "$tmp" 2>/dev/null &&
    touch -r "$g" "$tmp"; then :
  else rm -f -- "$tmp"; cp -p -- "$g" "$tmp" || { rm -f -- "$tmp"; continue; }
  fi
  mv -f -- "$tmp" "$t" || rm -f -- "$tmp"
done
'
while IFS= read -r f; do
  p=$at/${f##*/}
  if [ -h "$p" ]; then continue; fi
  if [ -d "$p" ]; then find "$p" -type f -exec sh -c "$put" sh "$p" "$f" {} +
  elif [ -f "$p" ]; then sh -c "$put" sh "$p" "$f" "$p"
  fi
done < "$at.links"
command -v sqlite3 >/dev/null 2>&1 || exit 0
q() { printf '%s' "$1" | sed "s/'/''/g"; }
for word in "$@"; do
  case $word in record=*) ;; *) continue ;; esac
  spec=${word#record=}; glob=${spec%%=*}; rest=${spec#*=}
  table=${rest%%=*}; column=${rest#*=}
  for db in "$at"/$glob; do
    [ -h "$db" ] || continue
    while IFS= read -r f; do
      from=$(q "$at/${f##*/}/"); to=$(q "$f/")
      sqlite3 -cmd '.timeout 10000' "$db" "UPDATE \"$table\" SET \"$column\" = '$to' ||
        substr(\"$column\", length('$from') + 1)
        WHERE substr(\"$column\", 1, length('$from')) = '$from';" 2>/dev/null || :
    done < "$at.links"
  done
done
exit 0
"##;
