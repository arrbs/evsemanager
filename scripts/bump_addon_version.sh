#!/usr/bin/env bash
# Helper to bump the addon version (patch) in evse_manager/config.yaml
# Usage: scripts/bump_addon_version.sh [major|minor|patch]
set -euo pipefail

type=${1:-patch}
file="evse_manager/config.yaml"
if [ ! -f "$file" ]; then
    echo "Cannot find $file" >&2
    exit 1
fi
current=$(grep '^version:' "$file" | sed -E 's/version:[[:space:]]*"([^"]+)"/\1/')
if [ -z "$current" ]; then
    echo "No version found in $file" >&2
    exit 1
fi
IFS=. read -r a b c <<<"$current"
a=${a:-0}; b=${b:-0}; c=${c:-0}
case "$type" in
    major)
        a=$((a+1)); b=0; c=0 ;;
    minor)
        b=$((b+1)); c=0 ;;
    patch)
        c=$((c+1)) ;;
    *) echo "Unknown bump type: $type" >&2; exit 1 ;;
esac
new="$a.$b.$c"
# update in place
sed -E -i.bak "s/version:[[:space:]]*\"[0-9]+\.[0-9]+\.[0-9]+\"/version: \"$new\"/" "$file"
rm -f "$file.bak"

echo "Bumped version: $current -> $new"

echo "Next: git add $file && git commit -m 'chore(release): bump add-on version to $new'" 
