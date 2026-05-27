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
PAGES_OWNER = os.environ.get("PAGES_OWNER", "user")
PAGES_REPO = os.environ.get("PAGES_REPO", "pages")
PAGES_BRANCH = os.environ.get("PAGES_BRANCH", "pages")
CODEBERG_API_BASE = os.environ.get("CODEBERG_API_BASE", "https://codeberg.org/api/v1").rstrip("/")
PAGES_BASE_URL = os.environ.get("PAGES_BASE_URL", "https://user.codeberg.page").rstrip("/")
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "projects")
LOGBOOK_DIR = os.environ.get("LOGBOOK_DIR", "logbook")
_env_local = os.environ.get("PAGES_LOCAL_PATH", "")
PAGES_LOCAL_PATH = _env_local or (str(Path.home() / "pages") if (Path.home() / "pages").exists() else "")


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"cache-control": "no-store"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def read_local_json(base: Path, rel_path: str):
    return json.loads((base / rel_path).read_text(encoding="utf-8"))


def fetch_api_file_json(path: str):
    import base64
    url = f"{CODEBERG_API_BASE}/repos/{PAGES_OWNER}/{PAGES_REPO}/contents/{path}?ref={PAGES_BRANCH}"
    data = fetch_json(url)
    return json.loads(base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace"))


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


def link_to_pages_md(rel_path: str) -> str:
    encoded = urllib.parse.quote(rel_path.replace("\\", "/"))
    return f"{PAGES_BASE_URL}/md.html?file={encoded}"


def update_readme_generated_block(new_block: str) -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    start = "<!-- AUTO-GENERATED:START"
    end = "<!-- AUTO-GENERATED:END -->"
    start_idx = readme.find(start)
    end_idx = readme.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        raise RuntimeError(f"Could not find AUTO-GENERATED markers in {README_PATH}")
    before = readme[:start_idx]
    after = readme[end_idx + len(end):]
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
            check=False, capture_output=True, text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        dt = datetime.fromisoformat(result.stdout.strip().replace("Z", "+00:00"))
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
            pass
        try:
            logbook_index = read_local_json(local_base, f"{LOGBOOK_DIR}/index.json")
        except Exception:
            pass
    else:
        try:
            projects_index = fetch_api_file_json(f"{PROJECTS_DIR}/index.json")
        except Exception:
            pass
        try:
            logbook_index = fetch_api_file_json(f"{LOGBOOK_DIR}/index.json")
        except Exception:
            pass

    if not isinstance(projects_index, list) or not projects_index:
        try:
            if use_local:
                projects_index = [p.name for p in (local_base / PROJECTS_DIR).iterdir() if p.is_file()]
            else:
                projects_index = [item.get("name") for item in fetch_contents(PROJECTS_DIR) if item.get("type") == "file"]
        except Exception:
            projects_index = []

    if not isinstance(logbook_index, list) or not logbook_index:
        try:
            if use_local:
                logbook_index = [p.name for p in (local_base / LOGBOOK_DIR).iterdir() if p.is_file()]
            else:
                logbook_index = [item.get("name") for item in fetch_contents(LOGBOOK_DIR) if item.get("type") == "file"]
        except Exception:
            logbook_index = []

    logbook_files = sorted(
        [name for name in logbook_index if is_iso_date_md(name)],
        reverse=True,
    )
    project_files = [
        name for name in projects_index
        if str(name).lower().endswith(".md") and not is_hidden_like(name)
    ]

    projects_count = len(project_files)
    logbook_count = len(logbook_files)

    latest_logbook_file = logbook_files[0] if logbook_files else None
    latest_logbook_link = link_to_pages_md(f"{LOGBOOK_DIR}/{latest_logbook_file}") if latest_logbook_file else ""

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
                pass
        project_candidates.append({"name": name, "date": date})
    project_candidates.sort(key=lambda item: (-(item["date"].timestamp() if item["date"] else 0), str(item["name"]).lower()))

    latest_project_file = project_candidates[0]["name"] if project_candidates else None
    latest_project_link = link_to_pages_md(f"{PROJECTS_DIR}/{latest_project_file}") if latest_project_file else ""

    project_href = html.escape(latest_project_link)
    logbook_href = html.escape(latest_logbook_link)

    new_block = f"""<!-- AUTO-GENERATED:START (do not edit by hand) -->
<p><a href="{project_href}">latest project writeup</a> · <a href="{logbook_href}">latest logbook entry</a></p>

<p>total project writeups: {projects_count} · total logbook entries: {logbook_count}</p>

<p><small>auto-updated from my <a href="https://codeberg.org/user/pages">pages repo</a>.</small></p>
<!-- AUTO-GENERATED:END -->"""

    update_readme_generated_block(new_block)


if __name__ == "__main__":
    main()
