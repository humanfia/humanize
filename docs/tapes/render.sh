#!/bin/sh
# Records the documentation's terminal demos.
#
#   docs/tapes/render.sh                     every tape
#   docs/tapes/render.sh tui.tape            one of them
#
# Needs Apple's `container` (or `docker`, if CONTAINER=docker) and nothing else. Each tape is
# played inside a container built from the Dockerfile beside this script -- a scratch home, a
# throwaway project, and a stand-in for the coding agent CLIs -- so a recording cannot pick up
# an account, a path or a hostname.
#
# A tape becomes docs/public/demo/<name>.cast, text the page plays in the reader's browser.
# The casts are committed. Nothing in CI runs this.

set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
out="$root/docs/public/demo"
image=humanize-tapes
run=${CONTAINER:-container}

# A cast is text and is served compressed, but it is still fetched before it plays.
limit=460800

# The build is handed only what the Dockerfile copies, so it neither reads the whole tree nor
# leans on an ignore file every builder reads its own way.
context=$(mktemp -d)
trap 'rm -rf "$context"' EXIT
cp -R "$root/pyproject.toml" "$root/README.md" "$root/LICENSE" "$root/src" \
    "$here/stage.py" "$here/standin" "$context/"
find "$context/src" -name __pycache__ -prune -exec rm -rf {} +

echo "==> building $image"
"$run" build --quiet -t "$image" -f "$here/Dockerfile" "$context" >/dev/null

mkdir -p "$out"

if [ "$#" -gt 0 ]; then
    tapes=$*
else
    tapes=$(cd "$here" && echo ./*.tape)
fi

failed=0
for tape in $tapes; do
    name=$(basename "$tape" .tape)
    echo "==> $name"
    "$run" run --rm \
        -v "$here:/tapes" \
        -v "$out:/out" \
        --entrypoint /opt/cast/bin/python \
        "$image" /tapes/cast.py "/tapes/$name.tape" "/out/$name.cast"
    size=$(wc -c < "$out/$name.cast")
    printf '    %s KB\n' "$((size / 1024))"
    if [ "$size" -gt "$limit" ]; then
        echo "    too large: shorten the tape" >&2
        failed=1
    fi
done

echo
echo "Play what you recorded before committing it (pnpm dev, then the page it is on). A demo"
echo "must show Humanize and nothing about the machine it was recorded on."

exit "$failed"
