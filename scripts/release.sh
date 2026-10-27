#!/usr/bin/env bash
# Cut a release: bump the version, regenerate CHANGELOG.md, commit and tag.
#
#   scripts/release.sh            # next version from conventional commits
#   scripts/release.sh 0.3.0      # explicit version
#
# Pushing the tag (printed at the end) triggers .github/workflows/release.yml.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "error: working tree is not clean" >&2
  exit 1
fi
if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "error: releases are cut from main" >&2
  exit 1
fi

version="${1:-$(uv run git-cliff --bumped-version)}"
version="${version#v}"
tag="v${version}"
if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  echo "error: tag ${tag} already exists" >&2
  exit 1
fi

uv version "${version}"
uv run git-cliff --tag "${tag}" --output CHANGELOG.md
uv run pytest -q
uv run ruff check

git add pyproject.toml uv.lock CHANGELOG.md
git commit -m "chore(release): ${tag}"
git tag -a "${tag}" -m "kert ${tag}"

echo
echo "Release ${tag} committed and tagged. Publish it with:"
echo "  git push origin main ${tag}"
