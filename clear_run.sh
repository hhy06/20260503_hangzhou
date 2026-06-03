#!/usr/bin/env bash
set -euo pipefail

for dir in scenario/*/run_*; do
    [ -d "$dir" ] || continue
    echo "Removing $dir"
    rm -rf "$dir"
done