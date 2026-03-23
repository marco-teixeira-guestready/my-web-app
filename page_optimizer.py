"""
Page Optimizer
--------------
Given a URL (or raw HTML content), uses DataForSEO to audit the page
and Claude to generate specific, actionable optimisations for:
  - SEO: title, meta description, heading structure, keyword usage
  - AEO/SAIO: FAQ schema, snippet-bait paragraphs, entity coverage,
    Speakable markup, E-E-A-T signals
"""

import json

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from dataforseo_client import DataForSEOClient

console = Console()


def _extract_page_signals(audit: dict) -> dict:
    """Pull the most relevant signals from a DataForSEO on-page audit result."""
    meta = audit.get("meta", {}) or {}
    return {
        "url": audit.get("url", ""),
        "title": meta.get("title", ""),
        "description": meta.get("description", ""),
        "h1": meta.get("htags", {}).get("h1", []),
        "h2": meta.get("htags", {}).get("h2", []),
        "word_count": meta.get("content", {}).get("plain_text_word_count", 0),
        "canonical": meta.get("canonical", ""),
        "charset": meta.get("charset", ""),
        "schema_types": [
            s.get("@type", "") for s in (meta.get("structured_data", {}).get("items", []) or [])
        ],
        "internal_links": audit.get("internal_links_count", 0),
        "external_links": audit.get("external_links_count", 0),
        "load_time": audit.get("checks", {}).get("load_time", None),
        "checks": audit.get("checks", {}),
    }


def optimize_page(
    url: str,
    target_keyword: str,
    secondary_keywords: list[str] = None,
) -> dict:
    """
    1. Fetch page audit from DataForSEO
    2. Pass signals + keyword context to Claude
    3. Return structured optimisation recommendations
    """
    dfs = DataForSEOClient()
    claude = anthropic.Anthropic()

    # ── 1. Audit ─────────────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]Auditing page:[/] {url}")
    audit_raw = dfs.on_page_audit(url)
    signals = _extract_page_signals(audit_raw)
    console.print("[green]✓[/] Page audit complete")

    # ── 2. SERP overview for target keyword ──────────────────────────────────
    console.print(f"[bold cyan]Fetching SERP context for:[/] {target_keyword}")
    serp_items = dfs.serp_overview(target_keyword)
    featured_snippets = [
        i for i in serp_items if i.get("type") in ("featured_snippet", "answer_box")
    ]
    top_urls = [
        i.get("url", "") for i in serp_items
        if i.get("type") == "organic" and i.get("rank_group", 99) <= 5
    ]
    console.print("[green]✓[/] SERP data retrieved")

    # ── 3. Claude optimisation ────────────────────────────────────────────────
    console.print("\n[bold cyan]Generating optimisation recommendations…[/]")

    secondary = secondary_keywords or []
    prompt = f"""You are a senior SEO and AEO (Answer Engine Optimization) specialist.

## Current Page Signals
{json.dumps(signals, indent=2)}

## Target Keyword
{target_keyword}

## Secondary Keywords
{json.dumps(secondary)}

## SERP Context
Featured snippets present: {len(featured_snippets) > 0}
Top-ranking competitor URLs: {json.dumps(top_urls)}

## Your Task
Provide a comprehensive optimisation brief covering ALL of the following sections.
Return ONLY valid JSON with this exact structure — no prose, no markdown fences:

{{
  "seo": {{
    "title_tag": "Rewritten title tag (50-60 chars, primary keyword near start)",
    "meta_description": "Rewritten meta description (150-160 chars, includes CTA)",
    "h1": "Recommended H1",
    "heading_structure": ["H2 suggestion 1", "H2 suggestion 2", "..."],
    "keyword_gaps": ["missing keyword 1", "missing keyword 2"],
    "internal_linking_suggestions": ["anchor text → /suggested-url"]
  }},
  "aeo": {{
    "faq_schema_questions": [
      {{"question": "...", "answer": "40-60 word direct answer suitable for featured snippet"}}
    ],
    "snippet_bait_paragraphs": [
      "A concise 40-60 word paragraph that directly answers the primary keyword query and is formatted for AI citation"
    ],
    "missing_entities": ["entity 1", "entity 2"],
    "eeat_improvements": ["improvement 1", "improvement 2"],
    "speakable_sections": ["Describe which sections should get Speakable markup"]
  }},
  "schema_markup": {{
    "recommended_types": ["Article", "FAQPage", "etc"],
    "json_ld_snippet": "A ready-to-paste JSON-LD block as a string"
  }},
  "content_gaps": ["topic or section missing from the page"],
  "priority_actions": ["Top 3-5 highest-impact actions to take first"]
}}"""

    with claude.messages.stream(
        model="claude-sonnet-4-6",
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

    # ── 4. Parse ─────────────────────────────────────────────────────────────
    try:
        recommendations = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        recommendations = json.loads(response_text[start:end])

    return {"url": url, "target_keyword": target_keyword, "signals": signals, "recommendations": recommendations}


def display_optimizations(result: dict) -> None:
    rec = result["recommendations"]

    console.print(Panel.fit(f"[bold]Optimisation Brief:[/] {result['url']}", style="cyan"))

    # Priority actions first
    console.print("\n[bold yellow]⚡ Priority Actions[/]")
    for i, action in enumerate(rec.get("priority_actions", []), 1):
        console.print(f"  {i}. {action}")

    # SEO section
    seo = rec.get("seo", {})
    console.print("\n[bold green]📈 SEO Optimisations[/]")
    console.print(f"  Title:       {seo.get('title_tag', '—')}")
    console.print(f"  Description: {seo.get('meta_description', '—')}")
    console.print(f"  H1:          {seo.get('h1', '—')}")

    # AEO section
    aeo = rec.get("aeo", {})
    console.print("\n[bold blue]🤖 AEO / SAIO Optimisations[/]")
    for faq in aeo.get("faq_schema_questions", [])[:3]:
        console.print(f"  Q: {faq.get('question', '')}")
        console.print(f"  A: [dim]{faq.get('answer', '')}[/dim]\n")

    console.print(f"  Missing entities: {', '.join(aeo.get('missing_entities', []))}")

    console.print("\n[bold magenta]🏷️  Schema Recommendations[/]")
    schema = rec.get("schema_markup", {})
    console.print(f"  Types: {', '.join(schema.get('recommended_types', []))}")


def save_optimization(result: dict, output_path: str = "optimization_brief.json") -> None:
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    console.print(f"\n[green]✓[/] Saved optimisation brief to [bold]{output_path}[/]")
