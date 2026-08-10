#!/usr/bin/env bash
set -euo pipefail

socat_version="1.7.4.1-3ubuntu4"
libwrap_version="7.6.q-31build2"
install_root="$HOME/.local/share/socat/$socat_version"

if [[ -x "$HOME/.local/bin/socat" ]] && "$HOME/.local/bin/socat" -V >/dev/null 2>&1; then
  "$HOME/.local/bin/socat" -V | head -n 1
  exit 0
fi

temp_dir="$(mktemp -d)"
case "$temp_dir" in
  /tmp/tmp.*) ;;
  *) echo "Unsafe temporary directory: $temp_dir" >&2; exit 1 ;;
esac
trap 'rm -r -- "$temp_dir"' EXIT

cd "$temp_dir"
apt-get download "socat=$socat_version" "libwrap0=$libwrap_version"
mkdir -p "$install_root"
for package in ./*.deb; do
  dpkg-deb -x "$package" "$install_root"
done
test -x "$install_root/usr/bin/socat"
test -s "$install_root/usr/lib/x86_64-linux-gnu/libwrap.so.0"
"$HOME/.local/bin/socat" -V | head -n 1
