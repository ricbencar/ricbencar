from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

USERNAME = os.environ.get("GITHUB_USERNAME", "ricbencar")

START_MARKER = "<!-- REPO-LIST:START -->"
END_MARKER = "<!-- REPO-LIST:END -->"
FALLBACK_CATEGORY = "Other Projects"
HTTP_TIMEOUT_SECONDS = 30

CATEGORY_RULES = {
    "Coastal & Maritime Hydraulic Design": [
        "breakwater",
        "rock slope",
        "coastal protection",
        "revetment",
        "groyne",
        "navigation",
        "under keel",
        "ukc",
        "pianc",
        "ship dimensions",
        "depth of closure",
        "overtopping",
        "maritime hydraulics",
        "coastal hydraulics",
        "coastal maritime hydraulic design",
    ],
    "Wave Mechanics, Transformation & Coastal Processes": [
        "wave mechanics",
        "wave dispersion",
        "dispersion equation",
        "nonlinear wave",
        "fenton",
        "nearshore",
        "offshore to nearshore",
        "shallow water waves",
        "wave forces",
        "wave loading",
        "wind waves",
        "wind wave",
        "wind generated wave",
        "wave generation",
        "wind wave generation",
        "smb",
        "sverdrup",
        "bretschneider",
        "sverdrup munk bretschneider",
        "wave transformation",
        "shoaling",
        "refraction",
        "wave kinematics",
        "coastal processes",
    ],
    "Metocean Data, Extremes & Statistical Analysis": [
        "metocean",
        "era5",
        "climate data",
        "wave wind",
        "storm",
        "extreme",
        "extreme value",
        "environmental contour",
        "joint distribution",
        "joint probability",
        "statistics",
        "trend",
        "climatology",
    ],
    "Engineering Automation, Data Utilities & Technical Productivity": [
        "pandoc",
        "markdown",
        "translator",
        "translation",
        "glossary",
        "cad",
        "dxf",
        "xyz",
        "data utilities",
        "engineering automation",
        "technical productivity",
    ],
}

SECTION_INTROS = {
    "Coastal & Maritime Hydraulic Design": (
        "Breakwater design, coastal protection, navigation safety, overtopping, and applied maritime hydraulic engineering."
    ),
    "Wave Mechanics, Transformation & Coastal Processes": (
        "Wave theory, dispersion, nonlinear waves, wave loading, offshore-to-nearshore transformation, and shallow-water processes."
    ),
    "Metocean Data, Extremes & Statistical Analysis": (
        "ERA5 workflows, wave and wind statistics, storm characterization, long-term trends, and probabilistic sea-state analysis."
    ),
    "Engineering Automation, Data Utilities & Technical Productivity": (
        "Utilities for technical documentation, translation, glossary generation, and engineering data conversion."
    ),
}


def find_readme_path() -> Path:
    """
    Locate README.md whether this script is stored at the repository root
    or under .github/scripts/.
    """
    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        candidate = Path(workspace) / "README.md"
        if candidate.is_file():
            return candidate

    here = Path(__file__).resolve()
    for parent in [here.parent] + list(here.parents):
        candidate = parent / "README.md"
        if candidate.is_file():
            return candidate

    raise RuntimeError("README.md not found.")


def github_api_get(url: str, token: Optional[str] = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USERNAME}-profile-readme-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_repositories(username: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    page = 1

    while True:
        url = (
            f"https://api.github.com/users/{username}/repos"
            f"?type=owner&sort=updated&per_page=100&page={page}"
        )

        batch = github_api_get(url, token)
        if not batch:
            break

        repos.extend(batch)

        if len(batch) < 100:
            break

        page += 1

    return [
        repo
        for repo in repos
        if not repo.get("fork", False)
        and not repo.get("archived", False)
        and repo.get("name", "").lower() != username.lower()
    ]


def fetch_repo_languages(repo: Dict[str, Any], token: Optional[str] = None) -> List[str]:
    languages_url = repo.get("languages_url")
    if not languages_url:
        primary_language = repo.get("language")
        return [primary_language] if primary_language else []

    try:
        payload = github_api_get(languages_url, token)
    except Exception:
        primary_language = repo.get("language")
        return [primary_language] if primary_language else []

    if not isinstance(payload, dict):
        primary_language = repo.get("language")
        return [primary_language] if primary_language else []

    language_items = sorted(
        ((language, bytes_of_code) for language, bytes_of_code in payload.items()),
        key=lambda item: (-int(item[1]), item[0].lower()),
    )
    languages = [language for language, _ in language_items if language]

    if languages:
        return languages

    primary_language = repo.get("language")
    return [primary_language] if primary_language else []


def enrich_repositories(repos: List[Dict[str, Any]], token: Optional[str] = None) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for repo in repos:
        repo_copy = dict(repo)
        repo_copy["display_languages"] = fetch_repo_languages(repo_copy, token)
        enriched.append(repo_copy)
    return enriched


def clean_description(desc: Optional[str]) -> str:
    if not desc:
        return "Repository description to be added."
    desc = " ".join(desc.strip().split())
    if not desc.endswith("."):
        desc += "."
    return desc


def normalize_text(parts: Iterable[str]) -> str:
    """
    Normalize text for category matching.

    - lowercase
    - replace hyphens, underscores, and slashes with spaces
    - strip other punctuation
    - collapse repeated whitespace
    """
    text = " ".join(part for part in parts if part)
    text = text.lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_phrase(text: str) -> str:
    return normalize_text([text])


def tokenize(text: str) -> Set[str]:
    return set(normalize_text([text]).split())


def phrase_in_text(phrase: str, text: str) -> bool:
    """
    Whole-phrase match over normalized text.
    """
    normalized_phrase = normalize_phrase(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in f" {text} "


def score_keyword_against_fields(
    keyword: str,
    *,
    name_text: str,
    desc_text: str,
    topics_text: str,
    homepage_text: str,
    name_tokens: Set[str],
    desc_tokens: Set[str],
    topics_tokens: Set[str],
    homepage_tokens: Set[str],
) -> int:
    """
    Weighted scoring:
    - topics are the strongest semantic signal
    - repository name is next
    - description is useful but weaker
    - homepage is weakest
    - token-set support helps when phrase order varies
    """
    score = 0
    normalized_keyword = normalize_phrase(keyword)
    if not normalized_keyword:
        return 0

    keyword_tokens = set(normalized_keyword.split())

    if phrase_in_text(keyword, topics_text):
        score += 8
    elif keyword_tokens and keyword_tokens.issubset(topics_tokens):
        score += 6

    if phrase_in_text(keyword, name_text):
        score += 6
    elif keyword_tokens and keyword_tokens.issubset(name_tokens):
        score += 4

    if phrase_in_text(keyword, desc_text):
        score += 4
    elif keyword_tokens and keyword_tokens.issubset(desc_tokens):
        score += 2

    if phrase_in_text(keyword, homepage_text):
        score += 2
    elif keyword_tokens and keyword_tokens.issubset(homepage_tokens):
        score += 1

    return score


def pick_category(repo: Dict[str, Any]) -> str:
    raw_name = repo.get("name", "") or ""
    raw_desc = repo.get("description", "") or ""
    raw_topics = " ".join(repo.get("topics", []) or [])
    raw_homepage = repo.get("homepage", "") or ""

    name_text = normalize_text([raw_name])
    desc_text = normalize_text([raw_desc])
    topics_text = normalize_text([raw_topics])
    homepage_text = normalize_text([raw_homepage])

    name_tokens = tokenize(raw_name)
    desc_tokens = tokenize(raw_desc)
    topics_tokens = tokenize(raw_topics)
    homepage_tokens = tokenize(raw_homepage)

    best_category = FALLBACK_CATEGORY
    best_score = 0

    for category, keywords in CATEGORY_RULES.items():
        category_score = 0
        for keyword in keywords:
            category_score += score_keyword_against_fields(
                keyword,
                name_text=name_text,
                desc_text=desc_text,
                topics_text=topics_text,
                homepage_text=homepage_text,
                name_tokens=name_tokens,
                desc_tokens=desc_tokens,
                topics_tokens=topics_tokens,
                homepage_tokens=homepage_tokens,
            )

        if category_score > best_score:
            best_score = category_score
            best_category = category

    return best_category


def format_date(iso_value: Optional[str]) -> str:
    if not iso_value:
        return "unknown"
    try:
        dt = datetime.strptime(iso_value, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso_value[:10]


def format_languages(repo: Dict[str, Any]) -> str:
    languages = [language for language in repo.get("display_languages", []) if language]
    if not languages and repo.get("language"):
        languages = [repo["language"]]
    if not languages:
        return "unknown"
    return ", ".join(languages)


def repo_meta_line(repo: Dict[str, Any]) -> str:
    parts: List[str] = []
    parts.append(f"Languages: `{format_languages(repo)}`")
    parts.append(f"Updated: `{format_date(repo.get('pushed_at') or repo.get('updated_at'))}`")
    if repo.get("stargazers_count", 0):
        parts.append(f"Stars: `{repo['stargazers_count']}`")
    return " · ".join(parts)


def build_section(repos: List[Dict[str, Any]]) -> str:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for repo in repos:
        grouped[pick_category(repo)].append(repo)

    ordered_categories = [
        "Coastal & Maritime Hydraulic Design",
        "Wave Mechanics, Transformation & Coastal Processes",
        "Metocean Data, Extremes & Statistical Analysis",
        "Engineering Automation, Data Utilities & Technical Productivity",
    ]
    if grouped.get(FALLBACK_CATEGORY):
        ordered_categories.append(FALLBACK_CATEGORY)

    lines: List[str] = []

    for category in ordered_categories:
        items = grouped.get(category, [])
        if not items:
            continue

        items.sort(
            key=lambda repo: (
                repo.get("pushed_at", "") or repo.get("updated_at", ""),
                repo.get("stargazers_count", 0),
            ),
            reverse=True,
        )

        lines.append(f"### {category}")
        lines.append("")

        intro = SECTION_INTROS.get(category)
        if intro:
            lines.append(intro)
            lines.append("")

        for repo in items:
            lines.append(f"- [**{repo['name']}**]({repo['html_url']})")
            lines.append(f"  {clean_description(repo.get('description'))}")
            lines.append(f"  {repo_meta_line(repo)}")
            lines.append("")

    return "
".join(lines).rstrip() + "
"


def replace_between_markers(readme_text: str, new_section: str) -> str:
    start = readme_text.find(START_MARKER)
    end = readme_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("README markers not found.")

    before = readme_text[: start + len(START_MARKER)]
    after = readme_text[end:]
    return before + "

" + new_section + "
" + after


def apply_static_readme_edits(readme_text: str) -> str:
    readme_text = readme_text.replace(
        "Focus-Wave%20Mechanics",
        "Focus-AI%20programming",
    )
    readme_text = readme_text.replace(
        'alt="Wave Mechanics"',
        'alt="AI programming"',
    )
    readme_text = readme_text.replace(
        "Together, these repositories are intended to support **more consistent, traceable, efficient, and professionally robust technical work**.

",
        "",
    )
    return readme_text


def main() -> int:
    readme_path = find_readme_path()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    repos = fetch_repositories(USERNAME, token=token)
    repos = enrich_repositories(repos, token=token)
    section = build_section(repos)

    readme = readme_path.read_text(encoding="utf-8")
    readme = apply_static_readme_edits(readme)
    updated = replace_between_markers(readme, section)

    with readme_path.open("w", encoding="utf-8", newline="
") as file_handle:
        file_handle.write(updated)

    print(f"Updated {readme_path} with {len(repos)} repositories.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
