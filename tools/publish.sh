#!/bin/sh
# One-command release AFTER the one-time PyPI setup is done.
#
#   1. pypi.org -> Your account -> Publishing -> Add a pending publisher:
#        PyPI project: ai-verdict
#        Owner: Roloria | Repository: verdict
#        Workflow: publish-pypi.yml | Environment: pypi
#   2. sh tools/publish.sh
#
# The script is idempotent: it refuses to run on a dirty tree, reuses an
# existing tag, and never force-pushes.
set -eu

cd "$(dirname "$0")/.."

version=$(python3 -c 'import re,pathlib; print(re.search(r"^version = \"([^\"]+)\"", pathlib.Path("pyproject.toml").read_text(), re.M).group(1))')
tag="v$version"

if [ -n "$(git status --porcelain)" ]; then
  echo "working tree is dirty; commit first" >&2
  exit 1
fi

echo "release $tag"
echo "checking local preconditions..."
python3 -c '
import sys
from verdict.release import preflight
r = preflight(".", check_pypi=False)
fails = [item for item, ok, _ in r["checks"] if not ok and "PyPI" not in item and "local tag" not in item]
if fails:
    print("not ready:", ", ".join(fails), file=sys.stderr)
    sys.exit(1)
' || exit 1

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "tag $tag already exists locally"
else
  git tag -a "$tag" -m "release $tag"
  echo "created $tag"
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
  echo "tag $tag is already on origin"
else
  git push origin "$tag"
  echo "pushed $tag -> publish-pypi.yml will upload via OIDC"
fi

cat <<EOF

Next (manual, one time):
  1. Create a GitHub Release for $tag and tick "Publish to GitHub Marketplace"
  2. git tag -f v1 $tag && git push -f origin v1
  3. Verify: pipx install ai-verdict && verdict --version && verdict rules list
EOF
