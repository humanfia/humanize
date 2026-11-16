#!/bin/sh
# Runs coganchor's checks on Linux from any machine with Docker: fmt, clippy and the crate's
# tests, then the given pytest arguments against the binary just built, with
# HUMANIZE_COGANCHOR naming it. With no pytest arguments only the crate is checked.
#
#   crates/coganchor/dev/linux-test.sh tests/integration/test_anchor_transport.py -x
#
# Caches (cargo registry, target directory, the virtualenv) persist in Docker volumes named
# for this checkout, so a second run builds only what changed.
set -eu

here=$(cd "$(dirname "$0")/../../.." && pwd)
key=$(printf '%s' "$here" | shasum | cut -c1-12)
image=hmz-coganchor-dev

docker image inspect "$image" >/dev/null 2>&1 \
  || docker build -t "$image" "$here/crates/coganchor/dev"

exec docker run --rm ${COGANCHOR_TTY:+-it} \
  --cap-add SYS_PTRACE --security-opt seccomp=unconfined --security-opt apparmor=unconfined \
  -v "$here:/src" \
  -v "coganchor-target-$key:/target" \
  -v "coganchor-venv-$key:/venv" \
  -v "coganchor-registry:/usr/local/cargo/registry" \
  -e HUMANIZE_COGANCHOR=/target/debug/coganchor \
  "$image" sh -euc '
    cd /src/crates/coganchor
    cargo fmt --check
    cargo clippy --all-targets -- -D warnings
    cargo test
    cargo build
    cd /src
    if [ "$#" -gt 0 ]; then
      uv sync --frozen --all-extras --quiet
      uv run --frozen pytest "$@"
    fi
  ' linux-test "$@"
