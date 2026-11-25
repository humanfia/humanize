#!/usr/bin/env bash
# Runs the Landlock integration tests inside one kernel under QEMU's software emulation.
#
#   crates/coganchor/ci/landlock-kernel-matrix.sh 5.15 1
#
# KVM is deliberately not needed: these tests check kernel behaviour, not speed. Kernels are
# downloaded from kernel.org, checked against fixed SHA-256 sums, built once under target/ with
# a tiny configuration, and booted with a minimal initramfs containing the static test binaries
# and host BusyBox.
set -euo pipefail

version=${1:?usage: landlock-kernel-matrix.sh KERNEL ABI}
abi=${2:?usage: landlock-kernel-matrix.sh KERNEL ABI}
here=$(cd "$(dirname "$0")/.." && pwd)
jobs=${JOBS:-$(getconf _NPROCESSORS_ONLN)}
qemu=${QEMU:-qemu-system-x86_64}
busybox=${BUSYBOX:-$(command -v busybox)}
cache=${HMZ_LANDLOCK_KERNEL_CACHE:-$here/target/landlock-kernels}
target=x86_64-unknown-linux-musl

case "$version" in
  5.15) digest=57b2cf6991910e3b67a1b3490022e8a0674b6965c74c12da1e99d138d1991ee8 ;;
  6.8) digest=c969dea4e8bb6be991bbf7c010ba0e0a5643a3a8d8fb0a2aaa053406f1e965f3 ;;
  6.10) digest=774698422ee54c5f1e704456f37c65c06b51b4e9a8b0866f34580d86fef8e226 ;;
  6.12) digest=b1a2562be56e42afb3f8489d4c2a7ac472ac23098f1ef1c1e40da601f54625eb ;;
  *) echo "no kernel $version" >&2; exit 2 ;;
esac
case "$abi" in
  1) [ "$version" = 5.15 ] || { echo "ABI 1 belongs to 5.15" >&2; exit 2; } ;;
  4) [ "$version" = 6.8 ] || { echo "ABI 4 belongs to 6.8" >&2; exit 2; } ;;
  5) [ "$version" = 6.10 ] || { echo "ABI 5 belongs to 6.10" >&2; exit 2; } ;;
  6) [ "$version" = 6.12 ] || { echo "ABI 6 belongs to 6.12" >&2; exit 2; } ;;
  *) echo "no ABI $abi" >&2; exit 2 ;;
esac

file "$busybox" | grep -q 'statically linked' \
  || { echo "$busybox is not static" >&2; exit 2; }
command -v "$qemu" >/dev/null
command -v cpio >/dev/null
command -v gzip >/dev/null
command -v jq >/dev/null
command -v sha256sum >/dev/null
command -v tar >/dev/null

config_sum=$(sha256sum "$here/ci/kernel.config" | cut -d' ' -f1)
kernel_cache=$cache/linux-$version-$config_sum
kernel=$kernel_cache/bzImage
mkdir -p "$kernel_cache"

if [ ! -f "$kernel" ]; then
  work=$(mktemp -d "${TMPDIR:-/tmp}/hmz-landlock-kernel.XXXXXX")
  trap 'rm -rf "$work"' EXIT
  archive=$work/linux-$version.tar.xz
  curl --fail --location --retry 3 --max-time 600 --proto '=https' --tlsv1.2 \
    --output "$archive" \
    "https://cdn.kernel.org/pub/linux/kernel/v${version%%.*}.x/linux-$version.tar.xz"
  echo "$digest  $archive" | sha256sum --check --status \
    || { echo "linux-$version.tar.xz failed its checksum" >&2; exit 1; }
  tar -C "$work" -xf "$archive"
  source=$work/linux-$version
  (
    cd "$source"
    make tinyconfig
    KCONFIG_CONFIG=.config scripts/kconfig/merge_config.sh -m .config "$here/ci/kernel.config"
    make olddefconfig
    # GCC 15 defaults to C23, whose bool/false keywords do not compile in the boot
    # wrappers of these kernel releases. Fix only that small pre-kernel C dialect.
    sed -i 's/^KBUILD_CFLAGS[[:space:]]*:=/KBUILD_CFLAGS := -std=gnu11 /' \
      arch/x86/boot/Makefile arch/x86/boot/compressed/Makefile
    for setting in SECURITY_LANDLOCK SECURITY_YAMA SECCOMP SECCOMP_FILTER CHECKPOINT_RESTORE; do
      grep -q "^CONFIG_$setting=y$" .config \
        || { echo "CONFIG_$setting is not enabled" >&2; exit 1; }
    done
    KBUILD_BUILD_USER=humanize KBUILD_BUILD_HOST=github-actions \
      make -j"$jobs" WERROR=0 KCFLAGS=-std=gnu11 bzImage
  )
  cp "$source/arch/x86/boot/bzImage" "$kernel.tmp"
  mv "$kernel.tmp" "$kernel"
  rm -rf "$work"
  trap - EXIT
fi

build_log=$(mktemp "${TMPDIR:-/tmp}/hmz-landlock-cargo.XXXXXX")
trap 'rm -f "$build_log"' EXIT
if ! (
  cd "$here"
  cargo test --locked --target "$target" --test landlock_kernel --no-run \
    --message-format=json-render-diagnostics
) >"$build_log"; then
  cat "$build_log" >&2
  exit 1
fi
test_binary=$(jq -r '
  select(.reason == "compiler-artifact" and
    .target.name == "landlock_kernel" and
    .executable != null) |
  .executable
' "$build_log" | tail -n 1)
rm -f "$build_log"
trap - EXIT
if [[ -n "$test_binary" && "$test_binary" != /* ]]; then
  test_binary=$here/$test_binary
fi
[ -n "$test_binary" ] && [ -x "$test_binary" ] \
  || { echo "the Landlock test executable is missing" >&2; exit 1; }
coganchor=$here/target/$target/debug/coganchor
[ -f "$coganchor" ] || { echo "the static coganchor is missing" >&2; exit 1; }

initramfs=$(mktemp -d "${TMPDIR:-/tmp}/hmz-landlock-initramfs.XXXXXX")
trap 'rm -rf "$initramfs" "$initramfs.cpio.gz" "${serial:-}"' EXIT
mkdir -p "$initramfs"/bin "$initramfs"/dev "$initramfs"/proc "$initramfs"/sys \
  "$initramfs"/tmp/home "$initramfs"/test "$initramfs"/etc "$initramfs$(dirname "$coganchor")"
for command in cat chown chmod echo ip mkdir mount reboot sh su; do
  ln -s busybox "$initramfs/bin/$command"
done
cp "$busybox" "$initramfs/bin/busybox"
chmod 755 "$initramfs/bin/busybox"
printf 'root:x:0:0:root:/root:/bin/sh\nmatrix:x:1000:1000:matrix:/tmp/home:/bin/sh\n' \
  >"$initramfs/etc/passwd"
printf 'root:x:0:\nmatrix:x:1000:\n' >"$initramfs/etc/group"
cp "$here/ci/init" "$initramfs/init"
chmod 755 "$initramfs/init"
cp "$test_binary" "$initramfs/test/landlock_kernel"
cp "$coganchor" "$initramfs$coganchor"
chmod 755 "$initramfs/test/landlock_kernel" "$initramfs$coganchor"
find "$initramfs" -type d -exec chmod 755 {} +
printf 'HMZ_LANDLOCK_KERNEL=%s\nHMZ_LANDLOCK_MATRIX_ABI=%s\nexport HMZ_LANDLOCK_KERNEL HMZ_LANDLOCK_MATRIX_ABI\n' \
  "$version" "$abi" >"$initramfs/test/env"
(
  cd "$initramfs"
  find . -print0 | cpio --null --quiet --create --format=newc | gzip -9
) >"$initramfs.cpio.gz"

serial=$(mktemp "${TMPDIR:-/tmp}/hmz-landlock-serial.XXXXXX")
set +e
timeout --signal=TERM 15m "$qemu" \
  -machine 'pc,accel=tcg' \
  -cpu max \
  -m 1024 \
  -smp 2 \
  -display none \
  -monitor none \
  -serial stdio \
  -no-reboot \
  -kernel "$kernel" \
  -initrd "$initramfs.cpio.gz" \
  -append 'console=ttyS0 rdinit=/init panic=1 oops=panic' \
  2>&1 | tee "$serial"
status=${PIPESTATUS[0]}
set -e

if ! grep -Fq "LANDLOCK-MATRIX RUN PASS kernel=$version ABI=$abi" "$serial"; then
  echo "kernel $version (ABI $abi) did not pass; QEMU status $status" >&2
  exit 1
fi
echo "kernel $version (ABI $abi) passed"
