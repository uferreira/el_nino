#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
source_root="$repo_root/legacy-java"
output_root="$repo_root/docs/java"
build_root="$(mktemp -d "${TMPDIR:-/tmp}/el-nino-java.XXXXXX")"
trap 'rm -rf "$build_root"' EXIT

build_applet() {
  local source_dir="$1"
  local output_dir="$2"
  local jar_name="$3"
  shift 3

  mkdir -p "$build_root/$output_dir" "$output_root/$output_dir"
  javac --release 8 -encoding ISO-8859-1 \
    -d "$build_root/$output_dir" \
    "$@"
  jar cf "$output_root/$output_dir/$jar_name" \
    -C "$build_root/$output_dir" .
}

build_applet \
  "$source_root/double-well" \
  "double-well" \
  "double-well.jar" \
  "$source_root/double-well/Timed3dVector.java" \
  "$source_root/double-well/NL3System.java" \
  "$source_root/double-well/DoubleWell.java" \
  "$source_root/double-well/DoubleWellCanvas.java" \
  "$source_root/double-well/DoubleWellApplet.java"

build_applet \
  "$source_root/observations-2013" \
  "observations-2013" \
  "observations-2013.jar" \
  "$source_root/observations-2013/Timed3dVector.java" \
  "$source_root/observations-2013/NL3System.java" \
  "$source_root/observations-2013/DoubleWell.java" \
  "$source_root/observations-2013/DoubleWellCanvas.java" \
  "$source_root/observations-2013/DoubleWellApplet.java"

echo "Legacy Java applets built in $output_root"
