"""
Keyword Universe Generator
--------------------------
Uses DataForSEO to gather keyword data and Claude to:
- Cluster keywords by topic / search intent
- Flag AEO/SAIO opportunities (question keywords, featured snippet targets)
- Assign content type recommendations
- Output a prioritised keyword universe
"""

import json
import os
from dataclasses import dataclass, field

import anthropic
from rich.console import Console
from rich.table import Table

from dataforseo_client import DataForSEOClient

console = Console()


@dataclass
class KeywordCluster:
    name: str
    intent: str          # informational | navigational | commercial | transactional
    aeo_opportunity: bool
    keywords: list[dict] = field(default_factory=list)
    content_type: str = ""
    priority: str = ""   # high | medium | low


def build_keyword_universe(
    seed_keyword: str,
    location_code: int = 2840,
    language_code: str = "en",
    limit: int = 100,
) -> list[KeywordCluster]:
    """
    Full pipeline:
    1. Pull keyword suggestions + related keywords from DataForSEO
    2. Send raw keyword list to Claude for clustering, intent labelling,
       AEO/SAIO opportunity scoring, and content type recommendations
    3. Return structured clusters
    """
    dfs = DataForSEOClient()
    claude = anthropic.Anthropic()

    # ── 1. Gather keywords ──────────────────────────────────────────────────
    console.print(f"\n[bold cyan]Fetching keyword data for:[/] {seed_keyword}")

    suggestions = dfs.keyword_suggestions(
        seed_keyword, location_code, language_code, limit
    )
    related = dfs.related_keywords(
        seed_keyword, location_code, language_code, limit
    )

    # Combine and deduplicate
    seen = set()
    all_keywords = []
    for item in suggestions + related:
        kw = item.get("keyword_data", item)  # handle both response shapes
        word = kw.get("keyword", "")
        if word and word not in seen:
            seen.add(word)
            all_keywords.append(
                {
                    "keyword": word,
                    "search_volume": (
                        kw.get("keyword_info", {}).get("search_volume")
                        or kw.get("search_volume")
                        or 0
                    ),
                    "cpc": (
                        kw.get("keyword_info", {}).get("cpc")
                        or kw.get("cpc")
                        or 0
                    ),
                    "competition": (
                        kw.get("keyword_info", {}).get("competition")
                        or kw.get("competition")
                        or 0
                    ),
                }
            )

    console.print(f"[green]✓[/] Collected {len(all_keywords)} unique keywords")

    # ── 2. Claude analysis ──────────────────────────────────────────────────
    console.print("\n[bold cyan]Analysing with Claude (adaptive thinking)…[/]")

    kw_json = json.dumps(all_keywords[:200], indent=2)  # cap at 200 for token budget

    prompt = f"""You are an expert SEO and AEO (Answer Engine Optimization) strategist.

I have collected the following keyword data for the seed topic: "{seed_keyword}"

{kw_json}

Your task:
1. Group these keywords into logical topic clusters (max 10 clusters).
2. For each cluster assign:
   - `name`: short descriptive cluster name
   - `intent`: one of [informational, navigational, commercial, transactional]
   - `aeo_opportunity`: true if the cluster contains question-based or definition queries
     that could win featured snippets, People Also Ask boxes, or AI answer citations
   - `content_type`: best content format (e.g. "pillar page", "FAQ page",
     "comparison article", "product landing page", "how-to guide", "glossary")
   - `priority`: high / medium / low based on combined search volume, commercial value,
     and AEO opportunity
   - `keywords`: the list of keyword objects that belong to this cluster

Return ONLY valid JSON — an array of cluster objects. No prose, no markdown fences.
"""

    with claude.messages.stream(
        model="claude-opus-4-6",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response_text = ""
        for event in stream:
            if (
                event.type == "content_block_delta"
                and event.delta.type == "text_delta"
            ):
                response_text += event.delta.text

    # ── 3. Parse and return ─────────────────────────────────────────────────
    try:
        clusters_raw = json.loads(response_text)
    except json.JSONDecodeError:
        # Try to salvage JSON from the response
        start = response_text.find("[")
        end = response_text.rfind("]") + 1
        clusters_raw = json.loads(response_text[start:end])

    clusters = [
        KeywordCluster(
            name=c.get("name", "Unnamed"),
            intent=c.get("intent", "informational"),
            aeo_opportunity=bool(c.get("aeo_opportunity", False)),
            keywords=c.get("keywords", []),
            content_type=c.get("content_type", ""),
            priority=c.get("priority", "medium"),
        )
        for c in clusters_raw
    ]

    return clusters


def display_universe(clusters: list[KeywordCluster]) -> None:
    table = Table(title="Keyword Universe", show_lines=True)
    table.add_column("Cluster", style="bold")
    table.add_column("Intent")
    table.add_column("AEO?", justify="center")
    table.add_column("Content Type")
    table.add_column("Priority")
    table.add_column("# Keywords", justify="right")
    table.add_column("Top Keyword")

    priority_style = {"high": "green", "medium": "yellow", "low": "red"}

    for c in sorted(clusters, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.priority, 1)):
        top = sorted(c.keywords, key=lambda k: k.get("search_volume", 0), reverse=True)
        top_kw = top[0]["keyword"] if top else "—"
        style = priority_style.get(c.priority, "white")
        table.add_row(
            c.name,
            c.intent,
            "✓" if c.aeo_opportunity else "",
            c.content_type,
            f"[{style}]{c.priority}[/{style}]",
            str(len(c.keywords)),
            top_kw,
        )

    console.print(table)


def save_universe(clusters: list[KeywordCluster], output_path: str = "keyword_universe.json") -> None:
    data = [
        {
            "name": c.name,
            "intent": c.intent,
            "aeo_opportunity": c.aeo_opportunity,
            "content_type": c.content_type,
            "priority": c.priority,
            "keywords": c.keywords,
        }
        for c in clusters
    ]
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    console.print(f"\n[green]✓[/] Saved keyword universe to [bold]{output_path}[/]")
