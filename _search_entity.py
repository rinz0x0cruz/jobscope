"""One-off: search both configured Gmail accounts for any mention of a term.
Read-only IMAP (BODY.PEEK). Reuses jobscope config + inbox MIME helpers."""
import re
import sys
import imaplib

sys.path.insert(0, ".")
from jobscope.core.config import load_config, inbox_password  # noqa: E402
from jobscope.ingest.inbox import (  # noqa: E402
    _dh, _fetch_headers, _fetch_snippet, _parse_date,
)

TERM = "entity"
BODY_LIMIT = 12000       # fetch enough body text to locate the term
RECENT_PER_FOLDER = 80   # cap body fetches to the most recent N matches/folder

cfg = load_config("config.yaml")
icfg = cfg["inbox"]
host = icfg.get("imap_host", "imap.gmail.com")
port = int(icfg.get("imap_port", 993))


def gmail_special_folders(M):
    """Return (all_mail, spam) mailbox names via LIST special-use flags."""
    all_mail = spam = None
    typ, data = M.list()
    if typ == "OK":
        for raw in data or []:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            names = re.findall(r'"((?:[^"\\]|\\.)*)"', line)
            name = names[-1] if names else line.split()[-1].strip('"')
            if r"\All" in line:
                all_mail = name
            elif r"\Junk" in line:
                spam = name
    return all_mail, spam


def context(text, term, width=180):
    low = text.lower()
    i = low.find(term.lower())
    if i < 0:
        return ""
    a = max(0, i - width)
    b = min(len(text), i + len(term) + width)
    return re.sub(r"\s+", " ", text[a:b]).strip()


results = []
for acct in icfg.get("accounts", []):
    addr = (acct.get("email") or "").strip()
    pw = inbox_password(cfg, acct)
    if not addr or not pw:
        print(f"  [skip] {addr or '(no email)'}: no app password")
        continue
    try:
        M = imaplib.IMAP4_SSL(host, port)
        M.login(addr, pw)
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] {addr}: login failed ({exc})")
        continue
    try:
        all_mail, spam = gmail_special_folders(M)
        folders = [f for f in (all_mail or "[Gmail]/All Mail", spam or "[Gmail]/Spam") if f]
        for folder in folders:
            # Mailbox names with spaces (e.g. "[Gmail]/All Mail") must be quoted.
            typ, _ = M.select(f'"{folder}"', readonly=True)
            if typ != "OK":
                continue
            typ, data = M.uid("search", None, "TEXT", TERM)
            if typ != "OK" or not data or not data[0]:
                print(f"  [{addr}] {folder}: 0 matches")
                continue
            uids = data[0].split()
            print(f"  [{addr}] {folder}: {len(uids)} raw match(es)")
            for uid in uids[-RECENT_PER_FOLDER:]:
                hdr = _fetch_headers(M, uid)
                if hdr is None:
                    continue
                frm = _dh(hdr.get("From", ""))
                subj = _dh(hdr.get("Subject", ""))
                date = _parse_date(hdr.get("Date", ""))
                body = _fetch_snippet(M, uid, limit=BODY_LIMIT)
                ctx = context(subj + " || " + body, TERM)
                results.append((date, addr, folder, frm, subj, ctx))
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass

results.sort(key=lambda r: r[0] or "", reverse=True)

print("\n" + "=" * 78)
print(f'MESSAGES MENTIONING "{TERM}": {len(results)} (most recent first)')
print("=" * 78)
for date, addr, folder, frm, subj, ctx in results[:40]:
    print(f"\n[{date or '??'}]  acct={addr}  ({folder})")
    print(f"  From:    {frm}")
    print(f"  Subject: {subj}")
    if ctx:
        print(f"  ...{ctx}...")
