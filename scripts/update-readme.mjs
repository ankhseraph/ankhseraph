#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const README_PATH = path.resolve(process.env.PROFILE_README_PATH ?? "README.md");
const PAGES_OWNER = process.env.PAGES_OWNER ?? "ankhseraph";
const PAGES_REPO = process.env.PAGES_REPO ?? "pages";
const PAGES_BRANCH = process.env.PAGES_BRANCH ?? "main";
const CODEBERG_API_BASE = (process.env.CODEBERG_API_BASE ?? "https://codeberg.org/api/v1").replace(/\/+$/, "");
const PAGES_BASE_URL = (process.env.PAGES_BASE_URL ?? "https://ankhseraph.codeberg.page").replace(/\/+$/, "");
const PROJECTS_DIR = process.env.PROJECTS_DIR ?? "projects";
const LOGBOOK_DIR = process.env.LOGBOOK_DIR ?? "logbook";
const defaultLocalPath = path.join(process.env.HOME ?? "", "pages");
const PAGES_LOCAL_PATH = process.env.PAGES_LOCAL_PATH ?? (fs.existsSync(defaultLocalPath) ? defaultLocalPath : "");

const RAW_BASE = `https://codeberg.org/${PAGES_OWNER}/${PAGES_REPO}/raw/branch/${PAGES_BRANCH}`;
const LATEST_PROJECTS_COUNT = Number(process.env.LATEST_PROJECTS_COUNT ?? "2");
const LATEST_LOGBOOK_COUNT = Number(process.env.LATEST_LOGBOOK_COUNT ?? "2");

function isIsoDateMd(name) {
  return /^\d{4}-\d{2}-\d{2}\.md$/.test(String(name));
}

function isHiddenLike(name) {
  const lower = String(name).toLowerCase();
  return (
    name === "EXAMPLE.md" ||
    lower.startsWith("_") ||
    lower.startsWith("example") ||
    lower.startsWith("sample") ||
    lower.startsWith("template")
  );
}

function extractFirstParagraph(markdown) {
  const lines = String(markdown).split(/\r?\n/);
  let index = 0;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index < lines.length && lines[index].startsWith("#")) index += 1;
  while (index < lines.length && lines[index].trim() === "") index += 1;

  const paragraph = [];
  while (index < lines.length) {
    const line = lines[index];
    if (line.trim() === "") break;
    if (line.startsWith("#") || line.startsWith("```") || line.startsWith("- ") || line.startsWith(">")) break;
    paragraph.push(line.trim());
    index += 1;
  }
  return paragraph.join(" ").trim();
}

function stripMarkdown(text) {
  return String(text)
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function toOneSentence(text, maxLen = 220) {
  const cleaned = stripMarkdown(text);
  if (!cleaned) return "";
  const end = cleaned.search(/[.!?](\s|$)/);
  let sentence = end === -1 ? cleaned : cleaned.slice(0, end + 1);
  if (sentence.length > maxLen) sentence = `${sentence.slice(0, maxLen - 1).trimEnd()}…`;
  return sentence;
}

function extractH1(markdown) {
  const lines = String(markdown).split(/\r?\n/);
  for (const line of lines) {
    if (line.trim().startsWith("# ")) return line.trim().slice(2).trim();
  }
  return "";
}

function extractLogbookSubtitle(markdown) {
  const lines = String(markdown).split(/\r?\n/);
  let index = 0;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index < lines.length && lines[index].trim().startsWith("#")) index += 1;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) break;
    if (line.startsWith("#") || line.startsWith("```") || line.startsWith("- ") || line.startsWith(">")) break;
    return line;
  }
  return "";
}

function extractLogbookBodyExcerpt(markdown) {
  const lines = String(markdown).split(/\r?\n/);
  let index = 0;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index < lines.length && lines[index].trim().startsWith("#")) index += 1;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index < lines.length && !lines[index].trim().startsWith("#")) index += 1; // subtitle line
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    if (line.startsWith("#") || line.startsWith("```") || line.startsWith("- ") || line.startsWith(">")) {
      index += 1;
      continue;
    }
    break;
  }

  const paragraph = [];
  while (index < lines.length) {
    const line = lines[index];
    if (line.trim() === "") break;
    if (line.startsWith("#") || line.startsWith("```") || line.startsWith("- ") || line.startsWith(">")) break;
    paragraph.push(line.trim());
    index += 1;
  }
  return paragraph.join(" ").trim();
}

function htmlEscape(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function linkToPagesMd(relPath) {
  const encoded = encodeURIComponent(relPath.replace(/\\/g, "/"));
  return `${PAGES_BASE_URL}/md.html?file=${encoded}`;
}

function pluralize(n, singular, plural = `${singular}s`) {
  return n === 1 ? singular : plural;
}

function renderStrongLink({ title, href }) {
  const safeTitle = htmlEscape(title);
  if (!href) return `<strong>${safeTitle}</strong>`;
  return `<strong><a href="${htmlEscape(href)}">${safeTitle}</a></strong>`;
}

function renderLinksList(items) {
  if (!items || items.length === 0) return `<div class="muted">None yet.</div>`;
  const lis = items
    .map((item) => `<li><a href="${htmlEscape(item.href)}">${htmlEscape(item.title)}</a></li>`)
    .join("");
  return `<ul>${lis}</ul>`;
}

function updateReadmeGeneratedBlock(newBlock) {
  const readme = fs.readFileSync(README_PATH, "utf8");
  const start = "<!-- AUTO-GENERATED:START";
  const end = "<!-- AUTO-GENERATED:END -->";
  const startIndex = readme.indexOf(start);
  const endIndex = readme.indexOf(end);

  if (startIndex === -1 || endIndex === -1 || endIndex < startIndex) {
    throw new Error(`Could not find AUTO-GENERATED markers in ${README_PATH}`);
  }

  const before = readme.slice(0, startIndex);
  const after = readme.slice(endIndex + end.length);
  fs.writeFileSync(README_PATH, `${before}${newBlock}${after}`, "utf8");
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { "cache-control": "no-store" } });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  return response.json();
}

async function fetchText(url) {
  const response = await fetch(url, { headers: { "cache-control": "no-store" } });
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`);
  return response.text();
}

function readLocalText(basePath, relPath) {
  return fs.readFileSync(path.join(basePath, relPath), "utf8");
}

function readLocalJson(basePath, relPath) {
  return JSON.parse(fs.readFileSync(path.join(basePath, relPath), "utf8"));
}

function readLocalDirFiles(basePath, relPath) {
  return fs
    .readdirSync(path.join(basePath, relPath), { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name);
}

function localMtimeDateForPath(basePath, relPath) {
  try {
    const stat = fs.statSync(path.join(basePath, relPath));
    return stat?.mtime ? new Date(stat.mtime) : null;
  } catch {
    return null;
  }
}

async function fetchRepoContents(repoPath) {
  const query = new URLSearchParams({ ref: PAGES_BRANCH });
  const url = `${CODEBERG_API_BASE}/repos/${PAGES_OWNER}/${PAGES_REPO}/contents/${repoPath}?${query.toString()}`;
  return fetchJson(url);
}

async function latestCommitDateForPath(repoPath) {
  const query = new URLSearchParams({ path: repoPath, limit: "1" });
  const url = `${CODEBERG_API_BASE}/repos/${PAGES_OWNER}/${PAGES_REPO}/commits?${query.toString()}`;
  const commits = await fetchJson(url);
  const dateString = commits?.[0]?.commit?.committer?.date;
  const date = dateString ? new Date(dateString) : null;
  return Number.isFinite(date?.valueOf()) ? date : null;
}

async function main() {
  const localBase = PAGES_LOCAL_PATH ? path.resolve(PAGES_LOCAL_PATH) : "";
  const useLocal = Boolean(localBase) && fs.existsSync(localBase);

  let projectsIndex = [];
  let logbookIndex = [];

  if (useLocal) {
    projectsIndex = (() => {
      try {
        return readLocalJson(localBase, `${PROJECTS_DIR}/index.json`);
      } catch {
        return [];
      }
    })();
    logbookIndex = (() => {
      try {
        return readLocalJson(localBase, `${LOGBOOK_DIR}/index.json`);
      } catch {
        return [];
      }
    })();
  } else {
    projectsIndex = await fetchJson(`${RAW_BASE}/${PROJECTS_DIR}/index.json`).catch(() => []);
    logbookIndex = await fetchJson(`${RAW_BASE}/${LOGBOOK_DIR}/index.json`).catch(() => []);
  }

  if (!Array.isArray(projectsIndex) || projectsIndex.length === 0) {
    if (useLocal) {
      projectsIndex = readLocalDirFiles(localBase, PROJECTS_DIR);
    } else {
      projectsIndex = await fetchRepoContents(PROJECTS_DIR)
        .then((items) => items.filter((item) => item?.type === "file").map((item) => item?.name))
        .catch(() => projectsIndex);
    }
  }

  if (!Array.isArray(logbookIndex) || logbookIndex.length === 0) {
    if (useLocal) {
      logbookIndex = readLocalDirFiles(localBase, LOGBOOK_DIR);
    } else {
      logbookIndex = await fetchRepoContents(LOGBOOK_DIR)
        .then((items) => items.filter((item) => item?.type === "file").map((item) => item?.name))
        .catch(() => logbookIndex);
    }
  }

  const logbookFiles = Array.isArray(logbookIndex) ? logbookIndex.filter((name) => isIsoDateMd(name)) : [];
  logbookFiles.sort((a, b) => String(b).localeCompare(String(a)));

  const projectFiles = Array.isArray(projectsIndex)
    ? projectsIndex
        .filter((name) => String(name).toLowerCase().endsWith(".md"))
        .filter((name) => !isHiddenLike(name))
    : [];

  const projectsCount = projectFiles.length;
  const logbookCount = logbookFiles.length;

  const latestLogbookFile = logbookFiles[0] ?? null;
  const projectCandidates = await (async () => {
    if (projectFiles.length === 0) return [];

    const candidates = await Promise.all(
      projectFiles.map(async (name) => {
        const repoPath = `${PROJECTS_DIR}/${name}`;
        const date = useLocal ? localMtimeDateForPath(localBase, repoPath) : await latestCommitDateForPath(repoPath).catch(() => null);
        return { name, date };
      }),
    );

    candidates.sort((a, b) => {
      const ad = a.date?.valueOf() ?? 0;
      const bd = b.date?.valueOf() ?? 0;
      return bd - ad || String(b.name).localeCompare(String(a.name));
    });

    return candidates;
  })();

  const latestProjectFile = projectCandidates[0]?.name ?? null;

  let latestProjectTitle = "—";
  let latestProjectDesc = "";
  let latestProjectLink = "";

  if (latestProjectFile) {
    const rel = `${PROJECTS_DIR}/${latestProjectFile}`;
    const md = useLocal ? readLocalText(localBase, rel) : await fetchText(`${RAW_BASE}/${rel}`);
    latestProjectTitle = extractH1(md) || latestProjectFile.replace(/\.md$/i, "");
    latestProjectDesc = toOneSentence(extractFirstParagraph(md));
    latestProjectLink = linkToPagesMd(rel);
  }

  let latestLogbookTitle = "—";
  let latestLogbookDesc = "";
  let latestLogbookLink = "";

  if (latestLogbookFile) {
    const rel = `${LOGBOOK_DIR}/${latestLogbookFile}`;
    const md = useLocal ? readLocalText(localBase, rel) : await fetchText(`${RAW_BASE}/${rel}`);
    const date = latestLogbookFile.replace(/\.md$/i, "");
    const subtitle = extractLogbookSubtitle(md);
    latestLogbookTitle = subtitle ? `${date} — ${subtitle}` : date;
    latestLogbookDesc = toOneSentence(extractLogbookBodyExcerpt(md));
    latestLogbookLink = linkToPagesMd(rel);
  }

  const cleanProjectDesc = htmlEscape(latestProjectDesc).trim();
  const cleanLogbookDesc = htmlEscape(latestLogbookDesc).trim();

  const newBlock = `<!-- AUTO-GENERATED:START (do not edit by hand) -->
<div align="center">
<h2>Latest highlights</h2>

<table width="100%">
  <tr>
    <td width="50%" valign="top" align="center">
      <h3>Latest project writeup</h3>
      <p>${renderStrongLink({ title: latestProjectTitle, href: latestProjectLink })}</p>
      <p>${cleanProjectDesc}</p>
    </td>
    <td width="50%" valign="top" align="center">
      <h3>Latest logbook entry</h3>
      <p>${renderStrongLink({ title: latestLogbookTitle, href: latestLogbookLink })}</p>
      <p>${cleanLogbookDesc}</p>
    </td>
  </tr>
</table>

<p><strong>Total project writeups</strong>: ${projectsCount} • <strong>Total logbook entries</strong>: ${logbookCount}</p>

<p align="center"><small>Auto-updated from my <a href="https://codeberg.org/ankhseraph/pages">pages repo</a>.</small></p>
</div>
<!-- AUTO-GENERATED:END -->`;

  updateReadmeGeneratedBlock(newBlock);
}

try {
  await main();
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
