#!/bin/sh
# Publish site/ (made by `cite-or-silence export`) to the gh-pages branch, which GitHub Pages serves.
# The demo needs the SEP index and the model, so it is built here and not in Actions. The branch holds
# only the latest export: each run replaces it.
set -eu
cd "$(git rev-parse --show-toplevel)"
test -f site/index.html || { echo "no site/: run 'uv run cite-or-silence export' first" >&2; exit 1; }
remote=$(git remote get-url origin)
source=$(git rev-parse --short HEAD)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -R site/. "$tmp"
touch "$tmp/.nojekyll"
cd "$tmp"
git init -q -b gh-pages
git add -A
git commit -q -m "Public demo from $source"
git push -q -f "$remote" gh-pages
echo "published site/ from $source to gh-pages"
