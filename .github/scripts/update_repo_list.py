from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

USERNAME = os.environ.get("GITHUB_USERNAME", "ricbencar")

START_MARKER = "<!-- REPO-LIST:START -->"
END_MARKER = "<!-- REPO-LIST:END -->"
FALLBACK_CATEGORY = "Other Projects"

# Category order, introductions, and explicit assignments follow ricbencar.docx.
# Keywords classify future repositories that are not explicitly assigned below.
CATEGORY_RULES = {
    "Coastal & Maritime Hydraulic Design": [
        "breakwater",
        "antifer",
        "antifer-cubes-fine-tuning",
        "rock-slope",
        "rock slope",
        "coastal protection",
        "revetment",
        "groyne",
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
        "wind waves",
        "wind-generated wave",
        "wind generated wave",
        "sverdrup-munk-bretschneider",
        "sverdrup munk bretschneider",
        "wave-transformation",
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
        "wind-speed-conversion",
    ],
    "Navigation and Ship-Related Utilities": [
        "navigation",
        "under keel",
        "underkeel",
        "ukc",
        "pianc",
        "ship dimensions",
        "ship characteristics",
        "restricted water",
        "canal type waters",
    ],
    "GIS & CAD Processing Utilities": [
        "gis",
        "cad",
        "dxf",
        "dwg",
        "xyz",
        "epsg",
        "coordinate transformation",
        "coordinate conversion",
        "reference system",
        "geospatial",
        "vector datasets",
        "global mean sea level",
        "mean sea surface",
        "wgs84",
        "egm2008",
        "dtu25",
        "geoid",
        "vertical datum",
    ],
    "Engineering Utilities & Productivity": [
        "pandoc",
        "markdown",
        "translator",
        "translation",
        "glossary",
        "data utilities",
        "engineering automation",
        "prismoidal",
        "curve-expert",
        "technical productivity",
    ],
}

SECTION_INTROS = {
    "Coastal & Maritime Hydraulic Design": (
        "Breakwater design, coastal protection, overtopping, and applied maritime hydraulic engineering."
    ),
    "Wave Mechanics, Transformation & Coastal Processes": (
        "Wave theory, dispersion, nonlinear waves, wave loading, offshore-to-nearshore transformation, and shallow-water processes."
    ),
    "Metocean Data, Extremes & Statistical Analysis": (
        "ERA5 workflows, wave and wind statistics, storm characterization, long-term trends, and probabilistic sea-state analysis."
    ),
    "Navigation and Ship-Related Utilities": (
        "Under Keel Clearance (UKC) estimation for shallow, restricted, or canal-type waters and estimation of ship characteristics."
    ),
    "GIS & CAD Processing Utilities": (
        "Utilities for conversion of GIS & CAD among reference systems and conversion of CAD drawings into GIS vector datasets."
    ),
    "Engineering Utilities & Productivity": (
        "Utilities for technical documentation, glossary generation, and engineering data conversion."
    ),
}

# These assignments take priority over keywords in names, descriptions, topics,
# and homepages. Keep the exact repository slugs, including existing spellings.
# The reference document is not needed when running this script.
REPOSITORY_CATEGORIES = {
    "antifer-cubes-fine-tuning": "Coastal & Maritime Hydraulic Design",
    "depth-of-closure-calculator": "Coastal & Maritime Hydraulic Design",
    "rock-slope-calculator": "Coastal & Maritime Hydraulic Design",
    "breakwater-cubes-calculator": "Coastal & Maritime Hydraulic Design",
    "wave-overtopping-calculator": "Coastal & Maritime Hydraulic Design",

    "fenton-nolinear-calculator": "Wave Mechanics, Transformation & Coastal Processes",
    "wave-dispersion-equation": "Wave Mechanics, Transformation & Coastal Processes",
    "wave-forces-on-pontoon": "Wave Mechanics, Transformation & Coastal Processes",
    "wind-waves-generation": "Wave Mechanics, Transformation & Coastal Processes",
    "shallow-water-waves-calculator": "Wave Mechanics, Transformation & Coastal Processes",
    "transpose-offshore-to-nearshore": "Wave Mechanics, Transformation & Coastal Processes",
    "wave-forces-on-piles-calculator": "Wave Mechanics, Transformation & Coastal Processes",

    "wind-speed-conversion": "Metocean Data, Extremes & Statistical Analysis",
    "era5-wave-wind-data": "Metocean Data, Extremes & Statistical Analysis",
    "galton-board-statistics": "Metocean Data, Extremes & Statistical Analysis",
    "wave-wind-statistics": "Metocean Data, Extremes & Statistical Analysis",
    "extremes-joint-distribuiton": "Metocean Data, Extremes & Statistical Analysis",
    "storm-peaks-analysis": "Metocean Data, Extremes & Statistical Analysis",
    "wave-height-trends": "Metocean Data, Extremes & Statistical Analysis",

    "pianc-ship-dimensions": "Navigation and Ship-Related Utilities",
    "navigation-calculator": "Navigation and Ship-Related Utilities",

    "global-mean-sea-level": "GIS & CAD Processing Utilities",
    "cad-to-gis-convert": "GIS & CAD Processing Utilities",
    "cad-epsg-conversion": "GIS & CAD Processing Utilities",
    "xyz2dxf-points-to-cad": "GIS & CAD Processing Utilities",

    "prismoidal-volume-calculator": "Engineering Utilities & Productivity",
    "curve-expert-user-models": "Engineering Utilities & Productivity",
    "pandoc-markdown-converter": "Engineering Utilities & Productivity",
    "multilingual-engineering-glossary": "Engineering Utilities & Productivity",
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
    text = " ".join(part for part in parts if part).casefold()
    return " ".join(text.replace("-", " ").replace("_", " ").split())


def pick_category(repo: Dict[str, Any]) -> str:
    name = (repo.get("name") or "").strip().casefold()
    assigned_category = REPOSITORY_CATEGORIES.get(name)
    if assigned_category is not None:
        return assigned_category

    haystack = normalize_text(
        [
            name,
            repo.get("description", "") or "",
            " ".join(repo.get("topics", []) or []),
            repo.get("homepage", "") or "",
        ]
    )

    best_category = FALLBACK_CATEGORY
    best_score = 0

    for category, keywords in CATEGORY_RULES.items():
        # Match hyphens, underscores, and spaces consistently, without counting
        # equivalent keyword spellings more than once.
        normalized_keywords = {normalize_text([keyword]) for keyword in keywords}
        score = sum(1 for keyword in normalized_keywords if keyword in haystack)
        if score > best_score:
            best_score = score
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

    ordered_categories = list(CATEGORY_RULES)
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
