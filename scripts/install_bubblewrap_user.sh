#!/usr/bin/env bash
set -euo pipefail

version="0.6.1-1ubuntu0.1"
install_root="$HOME/.local/share/bubblewrap/$version"
binary="$HOME/.local/bin/bwrap"

if [[ -x "$binary" ]] && "$binary" --version >/dev/null 2>&1; then
  "$binary" --version
  exit 0
fi

temp_dir="$(mktemp -d)"
case "$temp_dir" in
  /tmp/tmp.*) ;;
  *) echo "Unsafe temporary directory: $temp_dir" >&2; exit 1 ;;
esac
trap 'rm -r -- "$temp_dir"' EXIT

cd "$temp_dir"
apt-get download "bubblewrap=$version"
package="$(find . -maxdepth 1 -type f -name 'bubblewrap_*.deb' -print -quit)"
[[ -n "$package" ]]

mkdir -p "$install_root" "$HOME/.local/bin"
dpkg-deb -x "$package" "$install_root"
install -m 0755 "$install_root/usr/bin/bwrap" "$binary"
"$binary" --version
