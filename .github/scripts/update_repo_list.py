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
    with urllib.request.urlopen(request) as response:
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

    - lowercases
    - replaces hyphens, underscores, slashes and punctuation with spaces
    - collapses repeated whitespace
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
    p = normalize_phrase(phrase)
    if not p:
        return False
    padded_text = f" {text} "
    padded_phrase = f" {p} "
    return padded_phrase in padded_text



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
    norm_keyword = normalize_phrase(keyword)
    if not norm_keyword:
        return 0

    kw_tokens = set(norm_keyword.split())

    if phrase_in_text(keyword, topics_text):
        score += 8
    elif kw_tokens and kw_tokens.issubset(topics_tokens):
        score += 6

    if phrase_in_text(keyword, name_text):
        score += 6
    elif kw_tokens and kw_tokens.issubset(name_tokens):
        score += 4

    if phrase_in_text(keyword, desc_text):
        score += 4
    elif kw_tokens and kw_tokens.issubset(desc_tokens):
        score += 2

    if phrase_in_text(keyword, homepage_text):
        score += 2
    elif kw_tokens and kw_tokens.issubset(homepage_tokens):
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



def repo_meta_line(repo: Dict[str, Any]) -> str:
    parts: List[str] = []
    if repo.get("language"):
        parts.append(f"Language: `{repo['language']}`")
    parts.append(f"Updated: `{format_date(repo.get('updated_at'))}`")
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
    lines.append(f"Automatically generated from my public GitHub repositories ({len(repos)} current projects).")
    lines.append("")

    for category in ordered_categories:
        items = grouped.get(category, [])
        if not items:
            continue

        items.sort(
            key=lambda r: (r.get("updated_at", ""), r.get("stargazers_count", 0)),
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

    return "\n".join(lines).rstrip() + "\n"



def replace_between_markers(readme_text: str, new_section: str) -> str:
    start = readme_text.find(START_MARKER)
    end = readme_text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("README markers not found.")

    before = readme_text[: start + len(START_MARKER)]
    after = readme_text[end:]
    return before + "\n\n" + new_section + "\n" + after



def main() -> int:
    readme_path = find_readme_path()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

    repos = fetch_repositories(USERNAME, token=token)
    section = build_section(repos)

    readme = readme_path.read_text(encoding="utf-8")
    updated = replace_between_markers(readme, section)

    with readme_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print(f"Updated {readme_path} with {len(repos)} repositories.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
