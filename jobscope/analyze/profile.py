"""Search profile: an editable, résumé-derived statement of what to look for.

`resume import` seeds ``data/profiles/<name>.yaml`` from your parsed résumé
(target roles from titles + a skills-to-role map, locations, remote preference).
Local Settings or direct YAML edits can change search intent, and ``jobscope scan``
fetches from the active profile. config.search stays the fallback when none exists.

Deterministic + offline: it reads the parsed :class:`Resume` and writes plain YAML.
"""
from __future__ import annotations

import os
import re
import tempfile

from jobscope.core.model import Resume

MAX_PROFILES = 3

# Seniority words we strip so a résumé title broadens into a searchable role
# ("Security Researcher Intern" -> "Security Researcher").
_SENIORITY_WORDS = re.compile(
    r"(?i)\b(intern(ship)?|junior|jr|senior|sr|staff|principal|lead|entry[\s-]*level|"
    r"associate|head\s+of|chief|vp|director)\b")

# Skill/keyword clusters -> an adjacent role to also search for. Ordered: earlier,
# more specific roles win the cap. Purely additive to your résumé's own titles.
_ROLE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("application security", "appsec", "sast", "secure code", "owasp", "product security"),
     "Application Security Engineer"),
    (("cloud security", "kubernetes", "terraform", "devsecops"), "Cloud Security Engineer"),
    (("threat hunting", "threat hunter"), "Threat Hunter"),
    (("detection", "siem", "splunk", "threat hunting", "soc", "kql"), "Detection Engineer"),
    (("penetration testing", "pentest", "burp", "metasploit", "red team", "offensive"),
     "Penetration Tester"),
    (("malware", "reverse engineering", "ghidra", "ida pro", "x64dbg"), "Malware Analyst"),
    (("incident response", "forensics", "dfir"), "Incident Response Analyst"),
    (("vulnerability", "cve", "exploit", "threat"), "Security Researcher"),
    (("data engineering", "spark", "airflow", "etl"), "Data Engineer"),
    (("machine learning", "ml", "pytorch", "tensorflow"), "Machine Learning Engineer"),
    (("security", "iam", "cryptography", "pki"), "Security Engineer"),
]

_MAX_TERMS = 7
_MAX_EDITED_TERMS = 20
_MAX_LOCATIONS = 10


def _data_dir(cfg: dict) -> str:
    db = (cfg.get("output", {}) or {}).get("db_path", "data/jobscope.db")
    return os.path.dirname(db) or "."


def _profiles_dir(cfg: dict) -> str:
    """Directory holding one YAML per named search profile (the multi-profile store)."""
    return os.path.join(_data_dir(cfg), "profiles")


def _legacy_path(cfg: dict) -> str:
    """Pre-multi-profile single file, migrated into profiles/ on first access."""
    return os.path.join(_data_dir(cfg), "profile.yaml")


def _active_path(cfg: dict) -> str:
    return os.path.join(_profiles_dir(cfg), ".active")


_NAME_RE = re.compile(r"[^a-z0-9_-]+")


def _slug(name: str) -> str:
    s = _NAME_RE.sub("-", (name or "").strip().lower()).strip("-")
    return s or "default"


def _profile_file(cfg: dict, name: str) -> str:
    return os.path.join(_profiles_dir(cfg), f"{_slug(name)}.yaml")


def _profile_path(cfg: dict) -> str:
    """Filesystem path of the ACTIVE profile (back-compat helper)."""
    return _profile_file(cfg, active_name(cfg) or "default")


def _broaden_title(title: str) -> str:
    t = _SENIORITY_WORDS.sub("", title)
    t = re.sub(r"\s{2,}", " ", t).strip(" -\u2013\u2014,|")
    return t if 2 < len(t) <= 48 else ""


def _derive_terms(resume: Resume) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        key = term.lower().strip()
        if key and key not in seen and len(terms) < _MAX_TERMS:
            seen.add(key)
            terms.append(term)

    for title in resume.titles:
        add(_broaden_title(title))
    haystack = (" ".join(resume.skills) + " " + " ".join(resume.titles)).lower()
    for keywords, role in _ROLE_HINTS:
        if any(k in haystack for k in keywords):
            add(role)
    if not terms:
        add("Software Engineer")
    return terms


def _derive_locations(resume: Resume, cfg: dict) -> list[str]:
    search = cfg.get("search", {}) or {}
    locs: list[str] = []
    if search.get("is_remote", True):
        locs.append("Remote")
    if resume.location:
        locs.append(resume.location)
    if not locs:
        locs.append(search.get("location", "Remote"))
    return list(dict.fromkeys(locs))  # dedupe, keep order


def build_profile(resume: Resume, cfg: dict, name: str) -> dict:
    """Derive the editable search profile dict from a parsed résumé."""
    return {
        "resume": name or "default",
        "seniority": resume.seniority or "",
        "years_experience": round(resume.years_experience, 1),
        "search_terms": _derive_terms(resume),
        "locations": _derive_locations(resume, cfg),
        "remote": bool((cfg.get("search", {}) or {}).get("is_remote", True)),
        "top_skills": list(resume.skills[:12]),
    }


def write_profile(path: str, prof: dict) -> str:
    import yaml
    header = (
        f'# jobscope search profile "{prof.get("resume", "default")}".\n'
        "# `jobscope scan` fetches jobs from the ACTIVE profile. Edit search_terms /\n"
        "# locations / remote below, then re-run scan. Keep several profiles side by side\n"
        "# and switch with `jobscope profile use <name>` (`profile list` to see them).\n"
        "# Regenerate with `profile build --force`. top_skills/seniority mirror your\n"
        "# résumé for reference -- matching reads the résumé itself, not this file.\n\n")
    body = yaml.safe_dump(prof, sort_keys=False, allow_unicode=True, default_flow_style=False)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    directory = os.path.dirname(os.path.abspath(path))
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(header + body)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return path


def update_profile(cfg: dict, name: str, *, search_terms, locations, remote) -> dict:
    """Update editable search intent while preserving résumé-derived facts."""
    normalized = _slug(name)
    current = _load_named(cfg, normalized)
    if current is None:
        raise ValueError(f"no profile named '{normalized}'")

    def clean_list(value, label: str, *, limit: int, max_length: int) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{label} must be a list")
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, str):
                raise ValueError(f"{label} must contain only text")
            item = " ".join(raw.split()).strip()
            if not item:
                continue
            if len(item) > max_length:
                raise ValueError(f"{label} entries must be at most {max_length} characters")
            key = item.casefold()
            if key not in seen:
                seen.add(key)
                cleaned.append(item)
        if not cleaned:
            raise ValueError(f"{label} must contain at least one entry")
        if len(cleaned) > limit:
            raise ValueError(f"{label} supports at most {limit} entries")
        return cleaned

    if not isinstance(remote, bool):
        raise ValueError("remote must be true or false")
    updated = {
        **current,
        "search_terms": clean_list(
            search_terms, "search_terms", limit=_MAX_EDITED_TERMS, max_length=80,
        ),
        "locations": clean_list(
            locations, "locations", limit=_MAX_LOCATIONS, max_length=100,
        ),
        "remote": remote,
    }
    write_profile(_profile_file(cfg, normalized), updated)
    return updated


def reset_profile(cfg: dict, store, name: str) -> dict:
    """Regenerate one profile from its stored résumé after explicit confirmation."""
    normalized = _slug(name)
    resume = store.get_named_resume(normalized)
    if resume is None:
        raise ValueError(f"no résumé named '{normalized}'")
    rebuilt = build_profile(resume, cfg, normalized)
    write_profile(_profile_file(cfg, normalized), rebuilt)
    return rebuilt


def _load_named(cfg: dict, name: str) -> dict | None:
    path = _profile_file(cfg, name)
    if not os.path.exists(path):
        return None
    import yaml
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else None


def load(cfg: dict) -> dict | None:
    """Return the ACTIVE search profile dict, or None if there isn't one."""
    _migrate_legacy(cfg)
    name = active_name(cfg)
    return _load_named(cfg, name) if name else None


def _migrate_legacy(cfg: dict) -> None:
    """Move a pre-multi-profile ``profile.yaml`` into ``profiles/<name>.yaml`` once,
    so upgrading keeps your existing (possibly edited) profile as the active one."""
    legacy = _legacy_path(cfg)
    if not os.path.exists(legacy):
        return
    dirp = _profiles_dir(cfg)
    if os.path.isdir(dirp) and any(f.endswith(".yaml") for f in os.listdir(dirp)):
        return  # already on the multi-profile layout
    name = "default"
    try:
        import yaml
        with open(legacy, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if isinstance(data, dict) and data.get("resume"):
            name = _slug(str(data["resume"]))
    except Exception:  # noqa: BLE001
        pass
    os.makedirs(dirp, exist_ok=True)
    try:
        os.replace(legacy, _profile_file(cfg, name))
    except OSError:
        return
    _write_active(cfg, name)


def list_profiles(cfg: dict) -> list[str]:
    """All stored profile names, sorted (migrates a legacy single file first)."""
    _migrate_legacy(cfg)
    dirp = _profiles_dir(cfg)
    if not os.path.isdir(dirp):
        return []
    return sorted(f[:-5] for f in os.listdir(dirp) if f.endswith(".yaml"))


def can_create_profile(cfg: dict, name: str) -> bool:
    """Whether a named profile may be created without exceeding the product cap."""
    normalized = _slug(name)
    names = list_profiles(cfg)
    return normalized in names or len(names) < MAX_PROFILES


def active_name(cfg: dict) -> str | None:
    """The active profile name: the ``.active`` pointer, else the first stored one."""
    _migrate_legacy(cfg)
    ap = _active_path(cfg)
    if os.path.exists(ap):
        try:
            with open(ap, "r", encoding="utf-8") as fh:
                n = _slug(fh.read())
            if os.path.exists(_profile_file(cfg, n)):
                return n
        except Exception:  # noqa: BLE001
            pass
    names = list_profiles(cfg)
    return names[0] if names else None


def _write_active(cfg: dict, name: str) -> None:
    os.makedirs(_profiles_dir(cfg), exist_ok=True)
    with open(_active_path(cfg), "w", encoding="utf-8") as fh:
        fh.write(_slug(name))


def set_active(cfg: dict, name: str) -> bool:
    """Switch the active profile. Returns False when ``name`` has no stored profile."""
    if not os.path.exists(_profile_file(cfg, name)):
        return False
    _write_active(cfg, name)
    return True


def ensure_seeded(cfg: dict, resume: Resume, name: str) -> str | None:
    """Seed ``profiles/<name>.yaml`` the first time that résumé name is imported;
    never clobbers an existing profile. Makes it active when nothing else is."""
    _migrate_legacy(cfg)
    path = _profile_file(cfg, name)
    if os.path.exists(path):
        return None
    if not can_create_profile(cfg, name):
        return None
    write_profile(path, build_profile(resume, cfg, name))
    if not os.path.exists(_active_path(cfg)):
        _write_active(cfg, name)
    return path


def apply_to_search(search: dict, prof: dict) -> dict:
    """Overlay a profile's fetch intent onto the base search dict (for `scan`).

    Non-empty ``search_terms`` replace the config terms; ``locations`` become one
    search profile each (reusing scan's per-profile mechanism); ``remote`` sets the
    remote flag. Empty profile fields leave the config value untouched.
    """
    s = dict(search)
    terms = [t for t in (prof.get("search_terms") or []) if str(t).strip()]
    if terms:
        s["terms"] = terms
    locations = [loc for loc in (prof.get("locations") or []) if str(loc).strip()]
    if locations:
        s["profiles"] = [{"name": loc, "location": loc} for loc in locations]
    if "remote" in prof:
        s["is_remote"] = bool(prof["remote"])
    return s


def render(prof: dict, path: str) -> str:
    years = prof.get("years_experience") or 0
    terms = prof.get("search_terms") or []
    locs = prof.get("locations") or []
    return "\n".join([
        f"  search profile ({path}):",
        f"    résumé: {prof.get('resume', '?')}   seniority: {prof.get('seniority') or '?'}"
        f"   ~{years:g}y",
        f"    search terms ({len(terms)}): {', '.join(terms) or '(none)'}",
        f"    locations: {', '.join(locs) or '(none)'}   remote: {prof.get('remote', True)}",
        "    edit this file, then `jobscope scan` fetches jobs from it.",
    ])


def run(cfg: dict, store, *, action: str = "show",
        resume_name: str | None = None, name: str | None = None,
        force: bool = False) -> int:
    _migrate_legacy(cfg)

    if action == "list":
        names = list_profiles(cfg)
        if not names:
            print("  no search profiles yet. Run `jobscope profile build` to create one.")
            return 0
        active = active_name(cfg)
        print(f"  search profiles ({len(names)}):")
        for n in names:
            prof = _load_named(cfg, n) or {}
            terms = prof.get("search_terms") or []
            mark = "*" if n == active else " "
            print(f"   {mark} {n:<16} {len(terms)} role(s): {', '.join(terms[:4]) or '(none)'}")
        print("  switch the active one with `jobscope profile use <name>`.")
        return 0

    if action == "use":
        target = name or resume_name
        if not target:
            print("  usage: jobscope profile use <name>   (`jobscope profile list` to see them)")
            return 1
        if set_active(cfg, target):
            print(f"  active search profile -> {_slug(target)}   `jobscope scan` now uses it.")
            return 0
        print(f"  no profile named '{target}'. Run `jobscope profile list` to see options.")
        return 1

    if action == "build":
        resume = store.get_resume(resume_name) if resume_name else store.get_resume()
        if resume is None:
            print("  no résumé found. Run `resume import <path>` first.")
            return 1
        built_from = resume_name or _primary_name(store)
        pname = _slug(name or built_from)
        if not can_create_profile(cfg, pname):
            print(f"  profile limit reached ({MAX_PROFILES}); remove or reuse a profile name.")
            return 1
        path = _profile_file(cfg, pname)
        if os.path.exists(path) and not force:
            print(f"  profile '{pname}' already exists: {path}")
            print("  edit it directly, regenerate with `--force`, or switch with `profile use`.")
            return 0
        prof = build_profile(resume, cfg, built_from)
        write_profile(path, prof)
        if not os.path.exists(_active_path(cfg)):
            _write_active(cfg, pname)
        print(f"  built search profile '{pname}' -> {path}")
        print(render(prof, path))
        if active_name(cfg) != pname:
            print(f"  make it active with `jobscope profile use {pname}`.")
        return 0

    # show (default) -- the active profile, or a named one when `name` is given
    target = name or active_name(cfg)
    prof = _load_named(cfg, target) if target else None
    if prof is None:
        print("  no search profile yet. Run `jobscope profile build` to create one.")
        return 1
    print(render(prof, _profile_file(cfg, target)))
    others = [n for n in list_profiles(cfg) if n != target]
    if others:
        print(f"  other profiles: {', '.join(others)}   (switch with `profile use <name>`)")
    return 0


def _primary_name(store) -> str:
    try:
        names = store.list_resumes()
        return names[0][0] if names else "default"
    except Exception:  # noqa: BLE001 - store without list_resumes
        return "default"
