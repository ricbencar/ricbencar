from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from typing import Iterable

USERNAME = os.environ.get("GITHUB_USERNAME", "ricbencar")
README_PATH = "README.md"

START_MARKER = "<!-- REPO-LIST:START -->"
END_MARKER = "<!-- REPO-LIST:END -->"
FALLBACK_CATEGORY = "Other Projects"

CATEGORY_RULES = {
    "Coastal & Maritime Hydraulic Design": [
        "breakwater",
        "rock-slope",
        "rock slope",
        "coastal protection",
        "revetment",
        "groyne",
        "navigation",
        "under keel",
        "ukc",
        "pianc",
        "ship-dimensions",
        "ship dimensions",
        "depth-of-closure",
        "depth of closure",
        "overtopping",
        "maritime",
        "coastal-hydraulics",
        "coastal-maritime-hydraulic-design",
    ],
    "Wave Mechanics, Transformation & Coastal Processes": [
        "wave mechanics",
        "wave-mechanics",
        "wave-dispersion",
        "dispersion",
        "nonlinear wave",
        "fenton",
        "nearshore",
        "offshore-to-nearshore",
        "offshore to nearshore",
        "shallow-water-waves",
        "shallow water waves",
        "wave-forces",
        "wave forces",
        "wind-waves",
        "wave-transformation",
        "wave transformation",
    ],
    "Metocean Data, Extremes & Statistical Analysis": [
        "metocean",
        "era5",
        "climate data",
        "wave-wind",
        "wave wind",
        "storm",
        "extreme",
        "extreme-value-analysis",
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


def github_api_get(url: str, token: str | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USERNAME}-profile-readme-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))



def fetch_repositories(username: str, token: str | None = None) -> list[dict]:
    repos: list[dict] = []
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



def clean_description(desc: str | None) -> str:
    if not desc:
        return "Repository description to be added."
    desc = " ".join(desc.strip().split())
    if not desc.endswith("."):
        desc += "."
    return desc



def normalize_text(parts: Iterable[str]) -> str:
    return " ".join(part.strip().lower() for part in parts if part).strip()



def pick_category(repo: dict) -> str:
    haystack = normalize_text(
        [
            repo.get("name", "").replace("-", " "),
            repo.get("description", ""),
            " ".join(repo.get("topics", [])),
            repo.get("homepage", "") or "",
        ]
    )

    best_category = FALLBACK_CATEGORY
    best_score = 0

    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for keyword in keywords if keyword.lower() in haystack)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category



def format_date(iso_value: str | None) -> str:
    if not iso_value:
        return "unknown"
    try:
        dt = datetime.strptime(iso_value, "%Y-%m-%dT%H:%M:%SZ")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return iso_value[:10]



def repo_meta_line(repo: dict) -> str:
    parts: list[str] = []
    language = repo.get("language")
    if language:
        parts.append(f"Language: `{language}`")
    updated_at = format_date(repo.get("updated_at"))
    parts.append(f"Updated: `{updated_at}`")
    stars = repo.get("stargazers_count", 0)
    if stars:
        parts.append(f"Stars: `{stars}`")
    return " · ".join(parts)



def build_section(repos: list[dict]) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)

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

    lines: list[str] = []
    total_repos = len(repos)
    lines.append("## Repositories")
    lines.append("")
    lines.append(
        f"Automatically generated from my public GitHub repositories ({total_repos} current projects)."
    )
    lines.append("")

    for category in ordered_categories:
        items = grouped.get(category, [])
        if not items:
            continue

        items.sort(key=lambda r: (r.get("updated_at", ""), r.get("stargazers_count", 0)), reverse=True)

        lines.append(f"### {category}")
        lines.append("")
        intro = SECTION_INTROS.get(category)
        if intro:
            lines.append(intro)
            lines.append("")

        for repo in items:
            name = repo["name"]
            html_url = repo["html_url"]
            desc = clean_description(repo.get("description"))
            meta = repo_meta_line(repo)
            lines.append(f"- [**{name}**]({html_url})")
            lines.append(f"  {desc}")
            lines.append(f"  {meta}")
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
    token = os.environ.get("GH_TOKEN")
    repos = fetch_repositories(USERNAME, token=token)
    section = build_section(repos)

    with open(README_PATH, "r", encoding="utf-8") as f:
        readme = f.read()

    updated = replace_between_markers(readme, section)

    with open(README_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(updated)

    print(f"Updated README with {len(repos)} repositories.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
