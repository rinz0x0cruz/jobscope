#!/usr/bin/env python3
"""house_check.py — deterministic compliance checker for the house style.

Asserts the *checkable* rules from ai-tool-builder/references/house-style.md across one or
more tool repos. Language-aware: Python (pyproject/requirements) and Go (go.mod). It is the
deterministic "80%" gate — it does not judge code quality or whether AI is truly optional
(that is the job of the agent audit / secure-ai-review). Pair the two.

Severities:
  FAIL  a hard house rule is broken (no CI, hardcoded secret, data/ not gitignored,
        no example config). Exits non-zero.
  WARN  a should-fix gap (unpinned deps, no CI lint, no golden-set eval next to an AI
        client, missing pytest pythonpath, no selftest). Advisory by default.
  PASS / N/A  fine, or not applicable to this repo/language.

Usage:
    python house_check.py [PATH ...]        # default: current directory
    python house_check.py --strict PATH     # also exit non-zero on WARN
    python house_check.py --json PATH ...   # machine-readable output

Exit code: 1 if any FAIL (or any WARN under --strict), else 0.  Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

PASS, WARN, FAIL, NA = "PASS", "WARN", "FAIL", "N/A"

# Directories never worth scanning for source/secrets.
SKIP_DIRS = {
    ".git", "data", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "vendor", ".idea", ".vscode",
}
SOURCE_EXTS = {".py", ".go", ".js", ".ts", ".tsx", ".yml", ".yaml", ".toml", ".sh", ".ps1"}

# High-confidence secret literals (provider tokens). Kept deliberately narrow to avoid
# false positives on env-var *names* like os.environ["X_API_KEY"].
SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI-style secret key"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "Google API key"),
]


class Result:
    __slots__ = ("id", "name", "status", "detail")

    def __init__(self, id_, name, status, detail=""):
        self.id, self.name, self.status, self.detail = id_, name, status, detail


# --------------------------------------------------------------------------- helpers

def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def detect_lang(root: Path) -> str:
    if (root / "go.mod").exists():
        return "go"
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return "python"
    return "unknown"


def iter_source_files(root: Path):
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        if p.suffix in SOURCE_EXTS:
            yield p


def _split_dep(spec: str) -> tuple[str, bool]:
    """Return (name, is_pinned) for a PEP 508 / requirements dependency string."""
    spec = spec.strip().strip('"').strip("'")
    spec = spec.split(";", 1)[0].strip()          # drop environment markers
    spec = spec.split("#", 1)[0].strip()          # drop inline comment
    if not spec or spec.startswith("-"):
        return "", True                            # -r/-e lines: ignore
    if spec.startswith(("http://", "https://", "git+", "file:")):
        return spec, True                          # URL/VCS pins are exact
    m = re.split(r"[<>=!~]", spec, maxsplit=1)
    name = m[0].strip()
    pinned = "==" in spec or "===" in spec
    return name, pinned


# --------------------------------------------------------------------------- checks

def check_example_config(root: Path, lang: str) -> Result:
    has = list(root.glob("config.example.*")) or list(root.glob(".env.example")) \
        or list(root.glob("*.example.yaml")) or list(root.glob("*.example.json"))
    if lang == "go":
        has = has or list(root.glob("config.json"))
    if has:
        return Result("C2a", "Example config committed", PASS, has[0].name)
    return Result("C2a", "Example config committed", FAIL, "no config.example.* / .env.example found")


def check_gitignore(root: Path) -> Result:
    gi = read(root / ".gitignore")
    if not gi:
        return Result("C2b", "data/ and .env gitignored", FAIL, "no .gitignore")
    data_ok = re.search(r"(?m)^\s*/?data/?(\*)?\s*$", gi) or "data/" in gi
    env_ok = re.search(r"(?m)^\s*\.env", gi)
    if data_ok and env_ok:
        return Result("C2b", "data/ and .env gitignored", PASS)
    missing = []
    if not data_ok:
        missing.append("data/")
    if not env_ok:
        missing.append(".env")
    sev = FAIL if not data_ok else WARN   # leaking data/ is the serious one
    return Result("C2b", "data/ and .env gitignored", sev, "missing: " + ", ".join(missing))


def check_secrets(root: Path) -> Result:
    hits = []
    for p in iter_source_files(root):
        if ".example" in p.name or p.name == "house_check.py":
            continue
        text = read(p)
        for pat, label in SECRET_PATTERNS:
            if pat.search(text):
                hits.append(f"{p.relative_to(root).as_posix()} ({label})")
    if hits:
        return Result("C1", "No hardcoded secrets", FAIL, "; ".join(hits[:5]))
    return Result("C1", "No hardcoded secrets", PASS)


def check_selftest(root: Path, lang: str) -> Result:
    if lang == "go":
        found = any("selftest" in read(p).lower() for p in root.rglob("cmd/**/*.go"))
    else:
        found = bool(list(root.rglob("selftest.py")))
    return Result("F1", "selftest present", PASS if found else WARN,
                  "" if found else "no selftest found (should run with no network/keys)")


def _ci_files(root: Path):
    return list((root / ".github" / "workflows").glob("*.yml")) + \
        list((root / ".github" / "workflows").glob("*.yaml"))


def check_ci(root: Path, lang: str) -> list[Result]:
    files = _ci_files(root)
    if not files:
        return [Result("G2", "CI workflow present", FAIL, "no .github/workflows/*.yml")]
    blob = "\n".join(read(f) for f in files).lower()
    tests_re = "go test" if lang == "go" else "pytest"
    lint_re = r"go\s*vet|gofmt|golangci" if lang == "go" else r"ruff|flake8|black|mypy|pylint"
    res = [Result("G2", "CI workflow present", PASS, f"{len(files)} workflow(s)")]
    res.append(Result("G2b", "CI runs tests", PASS if tests_re in blob else WARN,
                      "" if tests_re in blob else f"no '{tests_re}' step found"))
    res.append(Result("G2c", "CI runs lint", PASS if re.search(lint_re, blob) else WARN,
                      "" if re.search(lint_re, blob) else "no lint step (ruff/flake8/vet)"))
    return res


def check_deps_pinned(root: Path, lang: str) -> Result:
    if lang == "go":
        ok = (root / "go.sum").exists()
        return Result("J1", "Dependencies pinned", PASS if ok else WARN,
                      "go.mod/go.sum" if ok else "go.sum missing")
    unpinned = []
    pyproject = root / "pyproject.toml"
    if pyproject.exists() and tomllib:
        try:
            data = tomllib.loads(read(pyproject))
            # runtime dependencies only; dev/test extras (optional-dependencies) are exempt
            for d in data.get("project", {}).get("dependencies", []):
                name, pinned = _split_dep(d)
                if name and not pinned:
                    unpinned.append(d.strip())
        except (tomllib.TOMLDecodeError, TypeError):
            pass
    req = root / "requirements.txt"
    if req.exists():
        for line in read(req).splitlines():
            name, pinned = _split_dep(line)
            if name and not pinned:
                unpinned.append(line.strip())
    if not unpinned:
        return Result("J1", "Dependencies pinned", PASS)
    return Result("J1", "Dependencies pinned", WARN,
                  f"{len(unpinned)} unpinned: " + ", ".join(unpinned[:6]))


def check_pytest_pythonpath(root: Path, lang: str) -> Result:
    if lang != "python":
        return Result("G1", "pytest pythonpath set", NA, "not a Python repo")
    pyproject = read(root / "pyproject.toml")
    has_tests = bool(list(root.rglob("test_*.py")) or list(root.rglob("tests")))
    if not has_tests:
        return Result("G1", "pytest pythonpath set", NA, "no tests found")
    if "pythonpath" in pyproject:
        return Result("G1", "pytest pythonpath set", PASS)
    return Result("G1", "pytest pythonpath set", WARN,
                  'add [tool.pytest.ini_options] pythonpath=["."] to avoid ModuleNotFoundError in CI')


def check_ai_eval(root: Path, lang: str) -> Result:
    if lang == "go":
        ai_present = (root / "internal" / "ai").exists()
    else:
        ai_present = bool(list(root.rglob("ai.py")))
    if not ai_present:
        return Result("H1", "Golden-set eval for AI layer", NA, "no AI client detected")
    # A real golden set is a fixture ('golden' in name), an eval data file under tests/fixtures,
    # or an eval-named test. A bare module like eval.py does NOT count.
    found = None
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = [x.lower() for x in p.relative_to(root).parts]
        if any(x in SKIP_DIRS for x in parts):
            continue
        name = p.name.lower()
        in_tests = any(d in ("test", "tests", "fixtures") for d in parts)
        if "golden" in name:
            found = p
        elif "eval" in name and p.suffix in (".jsonl", ".json") and in_tests:
            found = p
        elif "eval" in name and p.suffix == ".py" and (name.startswith("test_") or name.endswith("_test.py")):
            found = p
        if found:
            break
    if not found and lang == "go":
        go_tests = list(root.rglob("cmd/**/*_test.go")) + list(root.rglob("internal/ai/*_test.go"))
        found = go_tests[0] if go_tests else None
    if found:
        return Result("H1", "Golden-set eval for AI layer", PASS, found.name)
    return Result("H1", "Golden-set eval for AI layer", WARN,
                  "AI client present but no golden-set eval found (add input->expected fixtures)")


CHECKS_ORDER = ["C1", "C2a", "C2b", "F1", "G1", "G2", "G2b", "G2c", "J1", "H1"]


def audit_repo(root: Path) -> list[Result]:
    lang = detect_lang(root)
    results = [
        check_secrets(root),
        check_example_config(root, lang),
        check_gitignore(root),
        check_selftest(root, lang),
        check_pytest_pythonpath(root, lang),
        *check_ci(root, lang),
        check_deps_pinned(root, lang),
        check_ai_eval(root, lang),
    ]
    order = {cid: i for i, cid in enumerate(CHECKS_ORDER)}
    return sorted(results, key=lambda r: order.get(r.id, 99))


# --------------------------------------------------------------------------- reporting

def print_repo(root: Path, results: list[Result]) -> dict:
    lang = detect_lang(root)
    counts = {PASS: 0, WARN: 0, FAIL: 0, NA: 0}
    print(f"\n=== {root.name}  ({lang}) ===")
    for r in results:
        counts[r.status] += 1
        line = f"  {r.status:<4} {r.id:<4} {r.name}"
        if r.detail:
            line += f" - {r.detail}"
        print(line)
    print(f"  ---- {counts[PASS]} PASS / {counts[WARN]} WARN / {counts[FAIL]} FAIL / {counts[NA]} N/A")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Deterministic house-style compliance checker.")
    ap.add_argument("paths", nargs="*", default=["."], help="repo path(s) to check")
    ap.add_argument("--strict", action="store_true", help="also exit non-zero on WARN")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    roots = [Path(p).resolve() for p in (args.paths or ["."])]
    total = {PASS: 0, WARN: 0, FAIL: 0, NA: 0}
    payload = {}
    for root in roots:
        if not root.exists():
            print(f"skip (missing): {root}", file=sys.stderr)
            continue
        results = audit_repo(root)
        payload[root.name] = [
            {"id": r.id, "name": r.name, "status": r.status, "detail": r.detail} for r in results
        ]
        if not args.json:
            counts = print_repo(root, results)
            for k, v in counts.items():
                total[k] += v

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"\n== TOTAL: {total[PASS]} PASS / {total[WARN]} WARN / {total[FAIL]} FAIL / {total[NA]} N/A ==")

    fails = sum(1 for repo in payload.values() for r in repo if r["status"] == FAIL)
    warns = sum(1 for repo in payload.values() for r in repo if r["status"] == WARN)
    return 1 if fails or (args.strict and warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
