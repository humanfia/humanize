//! The virtual home as POSIX shell, for a target where nothing of Humanize runs: what a native
//! turn's driver sends there. Port of `hmz.coganchor.homes.SCRIPT`, `BACK` and `words`, the
//! scripts byte for byte.

use super::Virtual;

/// The same as [`super::build`], as a POSIX shell script for a target where nothing of
/// Humanize runs (`homes.SCRIPT`). Run as `sh -c SCRIPT Humanize AT VARIABLE DEFAULT LODGES
/// [WORD...]`, after anything projected into `AT` has landed there, which this leaves as it
/// is. Each word is one of `copy=PATH=OUTSIDE` (a rewrite, and where it is under `~` while the
/// variable is unset, or nothing), `keep=GLOB` (private), `make=NAME` (made) and `skill=NAME`
/// (a flow's own skill, which the caller writes into `AT/LODGES/NAME` afterwards). It prints
/// the user's own value of the variable, which is what `secures` is set to. What it links
/// directly in `AT` it lists, a target per line, in `AT.links` beside it, for [`BACK`].
pub const SCRIPT: &str = r#"
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
"#;

/// [`super::Home::drop_home`]'s writing back, for a home [`SCRIPT`] built (`homes.BACK`): run
/// as `sh -c BACK Humanize AT [WORD...]` once the CLI is done, before `AT` is taken away. Each
/// link listed in `AT.links` that the CLI replaced is written back to the file it pointed at
/// -- a directory a file at a time -- by a copy renamed over it, with the mode the one there
/// had, and never over one that is as new or newer.
pub const BACK: &str = r#"
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
"#;

/// What [`SCRIPT`] is told after its first four arguments, for one virtual home
/// (`homes.words`). And [`BACK`] after its first: the paths its databases hold of the home
/// (`Virtual::records`), said again with the home's links followed where the target has
/// `sqlite3` to say them with, which `SCRIPT` passes over.
pub fn words(spec: &Virtual) -> Vec<String> {
    let outside = |one: &str| {
        // `dict(spec.outside)`: the last pair of a name is the one said.
        spec.outside
            .iter()
            .rev()
            .find(|(name, _)| name == one)
            .map_or("", |(_, there)| there.as_str())
    };
    let mut said = Vec::new();
    said.extend(
        spec.rewrites
            .iter()
            .map(|one| format!("copy={one}={}", outside(one))),
    );
    said.extend(spec.private.iter().map(|one| format!("keep={one}")));
    said.extend(spec.made.iter().map(|one| format!("make={one}")));
    said.extend(spec.skills.iter().map(|(name, _)| format!("skill={name}")));
    said.extend(
        spec.records
            .iter()
            .map(|(one, table, column)| format!("record={one}={table}={column}")),
    );
    said
}
