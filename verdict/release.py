"""Release preflight: compress the one-time publishing setup into one command.

It cannot click buttons on pypi.org for you, but it tells you exactly which are
left, and verifies everything that can be verified locally.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .i18n import t

WORKFLOW = ".github/workflows/publish-pypi.yml"


def _pyproject(root: Path) -> Tuple[str, str]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8")
    name = re.search(r'^name = "([^"]+)"', text, re.M)
    version = re.search(r'^version = "([^"]+)"', text, re.M)
    return (name.group(1) if name else ""), (version.group(1) if version else "")


def preflight(base_dir: str = ".", check_pypi: bool = True) -> Dict[str, Any]:
    root = Path(base_dir).resolve()
    name, version = _pyproject(root)
    checks: List[Tuple[str, bool, str]] = []

    checks.append((f"dist name = {name}", name == "ai-verdict", ""))
    init_path = root / "verdict" / "__init__.py"
    init = init_path.read_text(encoding="utf-8") if init_path.is_file() else ""
    m = re.search(r'__version__ = "([^"]+)"', init)
    checks.append((f"__version__ = {version}", bool(m and m.group(1) == version), ""))

    wf = root / WORKFLOW
    wf_ok = wf.is_file() and "id-token: write" in wf.read_text(encoding="utf-8")
    checks.append((f"{WORKFLOW} (OIDC)", wf_ok, ""))

    act = root / "action.yml"
    act_ok = act.is_file() and "ai-verdict" in act.read_text(encoding="utf-8")
    checks.append(("action.yml installs ai-verdict", act_ok, ""))

    tag = f"v{version}"
    try:
        tags = subprocess.run(["git", "-C", str(root), "tag", "-l", tag],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        tags = ""
    checks.append((f"local tag {tag}", bool(tags), ""))
    checks.append(("build backend available", importlib.util.find_spec("build") is not None,
                   "pip install build"))

    pypi_state = "unknown"
    if check_pypi:
        try:
            proc = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "8", f"https://pypi.org/pypi/{name}/json"],
                capture_output=True, text=True, timeout=12,
            )
            pypi_state = {"200": "published", "404": "available"}.get(proc.stdout.strip(), "unknown")
        except (OSError, subprocess.TimeoutExpired):
            pypi_state = "unknown"
    checks.append((f"PyPI {name}: {pypi_state}", pypi_state == "published", ""))

    env_state = "unknown"
    try:
        proc = subprocess.run(
            ["gh", "api", "repos/Roloria/verdict/environments",
             "--jq", ".environments[].name"],
            capture_output=True, text=True, timeout=12,
        )
        if proc.returncode == 0:
            env_state = "present" if "pypi" in proc.stdout.split() else "missing"
    except (OSError, subprocess.TimeoutExpired):
        pass
    checks.append((f"GitHub environment pypi: {env_state}", env_state == "present", ""))

    todo: List[str] = []
    if pypi_state != "published":
        todo.append("PyPI: create a pending trusted publisher for ai-verdict "
                    "(Roloria/verdict / publish-pypi.yml / env pypi)")
    if env_state != "present":
        todo.append("GitHub: create the `pypi` environment")
    if not tags:
        todo.append(f"git tag {tag} && git push origin {tag}")
    todo.append("Release: tick 'Publish to GitHub Marketplace', then move the v1 tag")

    return {
        "name": name, "version": version, "pypi": pypi_state,
        "environment": env_state, "checks": checks, "todo": todo,
        "ready": all(ok for _, ok, _ in checks) and not todo,
    }


def print_preflight(result: Dict[str, Any]) -> None:
    print(t("release.title"))
    for item, ok, detail in result["checks"]:
        line = t("release.ok" if ok else "release.missing", item=item)
        print(line + (f" ({detail})" if detail and not ok else ""))
    if result["todo"]:
        print("\n" + t("release.next"))
        for i, item in enumerate(result["todo"], 1):
            print(f"  {i}. {item}")
