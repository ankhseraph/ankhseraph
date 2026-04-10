#!/usr/bin/env python3
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

README_PATH = Path(os.environ.get("PROFILE_README_PATH", "README.md")).resolve()
PAGES_OWNER = os.environ.get("PAGES_OWNER", "ankhseraph")
PAGES_REPO = os.environ.get("PAGES_REPO", "pages")
PAGES_BRANCH = os.environ.get("PAGES_BRANCH", "main")
CODEBERG_API_BASE = os.environ.get("CODEBERG_API_BASE", "https://codeberg.org/api/v1").rstrip("/")
PAGES_BASE_URL = os.environ.get("PAGES_BASE_URL", "https://ankhseraph.codeberg.page").rstrip("/")
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "projects")
LOGBOOK_DIR = os.environ.get("LOGBOOK_DIR", "logbook")
_env_local = os.environ.get("PAGES_LOCAL_PATH", "")
PAGES_LOCAL_PATH = _env_local or (str(Path.home() / "pages") if (Path.home() / "pages").exists() else "")

RAW_BASE = f"https://codeberg.org/{PAGES_OWNER}/{PAGES_REPO}/raw/branch/{PAGES_BRANCH}"


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"cache-control": "no-store"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"cache-control": "no-store"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

def read_local_text(base: Path, rel_path: str) -> str:
    return (base / rel_path).read_text(encoding="utf-8")

def read_local_json(base: Path, rel_path: str):
    return json.loads((base / rel_path).read_text(encoding="utf-8"))


def is_iso_date_md(name: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", str(name)))


def is_hidden_like(name: str) -> bool:
    lower = str(name).lower()
    return (
        name == "EXAMPLE.md"
        or lower.startswith("_")
        or lower.startswith("example")
        or lower.startswith("sample")
        or lower.startswith("template")
    )


def extract_first_paragraph(markdown: str) -> str:
    lines = str(markdown).splitlines()
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].startswith("#"):
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    paragraph = []
    while idx < len(lines):
        line = lines[idx]
        if line.strip() == "":
            break
        if line.startswith("#") or line.startswith("```") or line.startswith("- ") or line.startswith(">"):
            break
        paragraph.append(line.strip())
        idx += 1
    return " ".join(paragraph).strip()


def strip_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def to_one_sentence(text: str, max_len: int = 220) -> str:
    cleaned = strip_markdown(text)
    if not cleaned:
        return ""
    match = re.search(r"[.!?](\s|$)", cleaned)
    sentence = cleaned if not match else cleaned[: match.end()]
    if len(sentence) > max_len:
        sentence = sentence[: max_len - 1].rstrip() + "…"
    return sentence


def extract_h1(markdown: str) -> str:
    for line in str(markdown).splitlines():
        if line.strip().startswith("# "):
            return line.strip()[2:].strip()
    return ""


def extract_logbook_subtitle(markdown: str) -> str:
    lines = str(markdown).splitlines()
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].strip().startswith("#"):
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            break
        if line.startswith("#") or line.startswith("```") or line.startswith("- ") or line.startswith(">"):
            break
        return line
    return ""


def extract_logbook_body_excerpt(markdown: str) -> str:
    lines = str(markdown).splitlines()
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].strip().startswith("#"):
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and not lines[idx].strip().startswith("#"):
        idx += 1
    while idx < len(lines):
        line = lines[idx].strip()
        if not line:
            idx += 1
            continue
        if line.startswith("#") or line.startswith("```") or line.startswith("- ") or line.startswith(">"):
            idx += 1
            continue
        break
    paragraph = []
    while idx < len(lines):
        line = lines[idx]
        if line.strip() == "":
            break
        if line.startswith("#") or line.startswith("```") or line.startswith("- ") or line.startswith(">"):
            break
        paragraph.append(line.strip())
        idx += 1
    return " ".join(paragraph).strip()


def link_to_pages_md(rel_path: str) -> str:
    encoded = urllib.parse.quote(rel_path.replace("\\", "/"))
    return f"{PAGES_BASE_URL}/md.html?file={encoded}"


def render_strong_link(title: str, href: str) -> str:
    safe_title = html.escape(title)
    if not href:
        return f"<strong>{safe_title}</strong>"
    return f"<strong><a href=\"{html.escape(href)}\">{safe_title}</a></strong>"


def update_readme_generated_block(new_block: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    start = "<!-- AUTO-GENERATED:START"
    end = "<!-- AUTO-GENERATED:END -->"
    start_idx = readme.find(start)
    end_idx = readme.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise RuntimeError(f"Could not find AUTO-GENERATED markers in {README_PATH}")
    before = readme[:start_idx]
    after = readme[end_idx + len(end) :]
    README_PATH.write_text(f"{before}{new_block}{after}", encoding="utf-8")


def latest_commit_date_for_path(repo_path: str):
    query = urllib.parse.urlencode({"path": repo_path, "limit": "1"})
    url = f"{CODEBERG_API_BASE}/repos/{PAGES_OWNER}/{PAGES_REPO}/commits?{query}"
    commits = fetch_json(url)
    date_string = None
    if isinstance(commits, list) and commits:
        date_string = commits[0].get("commit", {}).get("committer", {}).get("date")
    if not date_string:
        return None
    try:
        dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def latest_git_commit_date_local(repo_root: Path, rel_path: str):
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%cI", "--", rel_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        date_string = result.stdout.strip()
        if not date_string:
            return None
        dt = datetime.fromisoformat(date_string.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def latest_mtime_date_local(repo_root: Path, rel_path: str):
    try:
        ts = (repo_root / rel_path).stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def main():
    local_base = Path(PAGES_LOCAL_PATH).expanduser().resolve() if PAGES_LOCAL_PATH else None
    use_local = bool(local_base and local_base.exists())

    def fetch_contents(path: str):
        url = f"{CODEBERG_API_BASE}/repos/{PAGES_OWNER}/{PAGES_REPO}/contents/{path}?ref={PAGES_BRANCH}"
        return fetch_json(url)

    projects_index = []
    logbook_index = []
    if use_local:
        try:
            projects_index = read_local_json(local_base, f"{PROJECTS_DIR}/index.json")
        except Exception:
            projects_index = []
        try:
            logbook_index = read_local_json(local_base, f"{LOGBOOK_DIR}/index.json")
        except Exception:
            logbook_index = []
    else:
        try:
            projects_index = fetch_json(f"{RAW_BASE}/{PROJECTS_DIR}/index.json")
        except Exception:
            projects_index = []
        try:
            logbook_index = fetch_json(f"{RAW_BASE}/{LOGBOOK_DIR}/index.json")
        except Exception:
            logbook_index = []

    if not isinstance(projects_index, list) or not projects_index:
        if use_local:
            try:
                contents = (local_base / PROJECTS_DIR).iterdir()
                projects_index = [p.name for p in contents if p.is_file()]
            except Exception:
                projects_index = projects_index if isinstance(projects_index, list) else []
        else:
            try:
                contents = fetch_contents(PROJECTS_DIR)
                projects_index = [item.get("name") for item in contents if item.get("type") == "file"]
            except Exception:
                projects_index = projects_index if isinstance(projects_index, list) else []

    if not isinstance(logbook_index, list) or not logbook_index:
        if use_local:
            try:
                contents = (local_base / LOGBOOK_DIR).iterdir()
                logbook_index = [p.name for p in contents if p.is_file()]
            except Exception:
                logbook_index = logbook_index if isinstance(logbook_index, list) else []
        else:
            try:
                contents = fetch_contents(LOGBOOK_DIR)
                logbook_index = [item.get("name") for item in contents if item.get("type") == "file"]
            except Exception:
                logbook_index = logbook_index if isinstance(logbook_index, list) else []

    logbook_files = [name for name in logbook_index if is_iso_date_md(name)] if isinstance(logbook_index, list) else []
    logbook_files.sort(reverse=True)

    project_files = (
        [name for name in projects_index if str(name).lower().endswith(".md") and not is_hidden_like(name)]
        if isinstance(projects_index, list)
        else []
    )

    projects_count = len(project_files)
    logbook_count = len(logbook_files)

    latest_logbook_file = logbook_files[0] if logbook_files else None

    project_candidates = []
    for name in project_files:
        repo_path = f"{PROJECTS_DIR}/{name}"
        date = None
        if use_local:
            date = latest_git_commit_date_local(local_base, repo_path) or latest_mtime_date_local(local_base, repo_path)
        else:
            try:
                date = latest_commit_date_for_path(repo_path)
            except Exception:
                date = None
        project_candidates.append({"name": name, "date": date})
    project_candidates.sort(
        key=lambda item: (
            -(item["date"].timestamp() if item["date"] else 0),
            str(item["name"]).lower(),
        )
    )

    latest_project_file = project_candidates[0]["name"] if project_candidates else None

    latest_project_title = "—"
    latest_project_desc = ""
    latest_project_link = ""
    if latest_project_file:
        rel = f"{PROJECTS_DIR}/{latest_project_file}"
        md = read_local_text(local_base, rel) if use_local else fetch_text(f"{RAW_BASE}/{rel}")
        latest_project_title = extract_h1(md) or latest_project_file.replace(".md", "")
        latest_project_desc = to_one_sentence(extract_first_paragraph(md))
        latest_project_link = link_to_pages_md(rel)

    latest_logbook_title = "—"
    latest_logbook_desc = ""
    latest_logbook_link = ""
    if latest_logbook_file:
        rel = f"{LOGBOOK_DIR}/{latest_logbook_file}"
        md = read_local_text(local_base, rel) if use_local else fetch_text(f"{RAW_BASE}/{rel}")
        date = latest_logbook_file.replace(".md", "")
        subtitle = extract_logbook_subtitle(md)
        latest_logbook_title = f"{date} — {subtitle}" if subtitle else date
        latest_logbook_desc = to_one_sentence(extract_logbook_body_excerpt(md))
        latest_logbook_link = link_to_pages_md(rel)

    clean_project_desc = html.escape(latest_project_desc).strip()
    clean_logbook_desc = html.escape(latest_logbook_desc).strip()

    new_block = f"""<!-- AUTO-GENERATED:START (do not edit by hand) -->
<div align="center">
<h2>Latest highlights</h2>

<table width="100%">
  <tr>
    <td width="50%" valign="top" align="center">
      <h3>Latest project writeup</h3>
      <p>{render_strong_link(latest_project_title, latest_project_link)}</p>
      <p>{clean_project_desc}</p>
    </td>
    <td width="50%" valign="top" align="center">
      <h3>Latest logbook entry</h3>
      <p>{render_strong_link(latest_logbook_title, latest_logbook_link)}</p>
      <p>{clean_logbook_desc}</p>
    </td>
  </tr>
</table>

<p><strong>Total project writeups</strong>: {projects_count} • <strong>Total logbook entries</strong>: {logbook_count}</p>

<p align="center"><small>Auto-updated from my <a href="https://codeberg.org/ankhseraph/pages">pages repo</a>.</small></p>
</div>
<!-- AUTO-GENERATED:END -->"""

    update_readme_generated_block(new_block)


if __name__ == "__main__":
    main()
