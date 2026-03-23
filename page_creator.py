"""
Programmatic Page Creator
--------------------------
Takes a keyword cluster and uses Claude to generate a full, publish-ready
HTML page optimised for both traditional SEO and AEO/SAIO:
  - Structured with correct heading hierarchy
  - FAQ section with JSON-LD schema
  - Snippet-bait answer paragraphs (40-60 words)
  - Entity-rich content for AI citation
  - Speakable schema markup
  - Article JSON-LD
"""

import json
import os
from pathlib import Path

import anthropic
from jinja2 import Template
from rich.console import Console

from dataforseo_client import DataForSEOClient

console = Console()

# ── HTML template ─────────────────────────────────────────────────────────────
PAGE_TEMPLATE = Template(
    """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <meta name="description" content="{{ description }}">
  <link rel="canonical" href="{{ canonical_url }}">

  <!-- Article Schema -->
  <script type="application/ld+json">
{{ article_schema | tojson(indent=2) }}
  </script>

  <!-- FAQPage Schema -->
  <script type="application/ld+json">
{{ faq_schema | tojson(indent=2) }}
  </script>

  <!-- Speakable Schema -->
  <script type="application/ld+json">
{{ speakable_schema | tojson(indent=2) }}
  </script>
</head>
<body>

  <article>
    <h1>{{ h1 }}</h1>

    <!-- Snippet-bait: direct answer paragraph for AI/featured snippets -->
    <p class="answer-block" id="direct-answer">
      {{ direct_answer }}
    </p>

    {{ body_html }}

    <!-- FAQ Section -->
    <section id="faq">
      <h2>Frequently Asked Questions</h2>
      {% for item in faq_items %}
      <div class="faq-item">
        <h3>{{ item.question }}</h3>
        <p>{{ item.answer }}</p>
      </div>
      {% endfor %}
    </section>
  </article>

</body>
</html>"""
)


def _build_schemas(page: dict) -> tuple[dict, dict, dict]:
    """Build Article, FAQPage, and Speakable JSON-LD objects."""
    faq_entities = [
        {
            "@type": "Question",
            "name": item["question"],
            "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
        }
        for item in page.get("faq_items", [])
    ]

    article_schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": page["h1"],
        "description": page["description"],
        "keywords": ", ".join(page.get("keywords_used", [])),
        "mainEntityOfPage": {"@type": "WebPage", "@id": page.get("canonical_url", "")},
    }

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_entities,
    }

    speakable_schema = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": page["title"],
        "speakable": {
            "@type": "SpeakableSpecification",
            "cssSelector": ["#direct-answer", "#faq"],
        },
    }

    return article_schema, faq_schema, speakable_schema


def create_page(
    cluster_name: str,
    primary_keyword: str,
    keywords: list[str],
    content_type: str = "pillar page",
    target_word_count: int = 1200,
    canonical_url: str = "",
    tone: str = "professional, authoritative",
) -> dict:
    """
    1. Pull SERP context from DataForSEO for the primary keyword
    2. Use Claude to write a full AEO-optimised page
    3. Render to HTML with correct schema markup
    """
    dfs = DataForSEOClient()
    claude = anthropic.Anthropic()

    # ── 1. SERP context ───────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]Fetching SERP context for:[/] {primary_keyword}")
    serp_items = dfs.serp_overview(primary_keyword)
    featured_snippets = [
        i for i in serp_items
        if i.get("type") in ("featured_snippet", "answer_box", "people_also_ask")
    ]
    paa_questions = [
        i.get("title", "") for i in serp_items
        if i.get("type") == "people_also_ask"
    ][:8]
    console.print(f"[green]✓[/] SERP context fetched — {len(paa_questions)} PAA questions found")

    # ── 2. Claude content generation ─────────────────────────────────────────
    console.print("\n[bold cyan]Writing page with Claude…[/]")

    prompt = f"""You are an expert SEO copywriter and AEO (Answer Engine Optimization) specialist.
Write a complete, publish-ready page optimised for both traditional search engines AND
AI answer engines (ChatGPT, Perplexity, Google SGE, Bing Copilot).

## Brief
- Cluster / Topic: {cluster_name}
- Primary Keyword: {primary_keyword}
- Secondary Keywords: {json.dumps(keywords[:20])}
- Content Type: {content_type}
- Target Word Count: ~{target_word_count} words
- Tone: {tone}
- Canonical URL: {canonical_url or "(not set)"}

## People Also Ask Questions from SERP
{json.dumps(paa_questions)}

## AEO/SAIO Requirements
- Start with a 40-60 word "direct answer" paragraph that can be cited verbatim by AI engines
- Use clear, entity-rich language (define concepts, name real-world entities)
- Include a minimum of 5 FAQ items that mirror PAA questions where possible
- Ensure content is structured so AI can extract discrete facts
- Add E-E-A-T signals (statistics, named sources, dates where appropriate)

Return ONLY valid JSON with this exact structure:

{{
  "title": "SEO-optimised title tag (50-60 chars)",
  "description": "Meta description (150-160 chars, includes primary keyword)",
  "h1": "H1 heading",
  "direct_answer": "40-60 word answer paragraph for the primary keyword query",
  "body_html": "Full article body as HTML (h2s, h3s, p tags, lists) — approximately {target_word_count} words",
  "faq_items": [
    {{"question": "...", "answer": "Concise 40-80 word answer"}}
  ],
  "keywords_used": ["list", "of", "keywords", "naturally", "included"]
}}"""

    with claude.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=16000,
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

    # ── 3. Parse response ─────────────────────────────────────────────────────
    try:
        page = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        page = json.loads(response_text[start:end])

    page["canonical_url"] = canonical_url or ""
    article_schema, faq_schema, speakable_schema = _build_schemas(page)

    # ── 4. Render HTML ────────────────────────────────────────────────────────
    rendered_html = PAGE_TEMPLATE.render(
        title=page["title"],
        description=page["description"],
        canonical_url=page["canonical_url"],
        h1=page["h1"],
        direct_answer=page["direct_answer"],
        body_html=page["body_html"],
        faq_items=page.get("faq_items", []),
        article_schema=article_schema,
        faq_schema=faq_schema,
        speakable_schema=speakable_schema,
    )

    return {
        "primary_keyword": primary_keyword,
        "page_data": page,
        "html": rendered_html,
        "schemas": {
            "article": article_schema,
            "faq": faq_schema,
            "speakable": speakable_schema,
        },
    }


def save_page(result: dict, output_dir: str = "generated_pages") -> str:
    Path(output_dir).mkdir(exist_ok=True)
    slug = result["primary_keyword"].lower().replace(" ", "-").replace("/", "-")[:60]
    html_path = os.path.join(output_dir, f"{slug}.html")
    json_path = os.path.join(output_dir, f"{slug}.json")

    with open(html_path, "w") as f:
        f.write(result["html"])

    with open(json_path, "w") as f:
        json.dump({"page_data": result["page_data"], "schemas": result["schemas"]}, f, indent=2)

    console.print(f"[green]✓[/] Saved HTML to [bold]{html_path}[/]")
    console.print(f"[green]✓[/] Saved page data to [bold]{json_path}[/]")
    return html_path


def batch_create_pages(
    clusters: list[dict],
    base_url: str = "",
    output_dir: str = "generated_pages",
) -> list[str]:
    """Create pages for all high-priority AEO clusters."""
    generated = []
    for cluster in clusters:
        if cluster.get("priority") not in ("high", "medium"):
            continue
        if not cluster.get("aeo_opportunity"):
            continue

        keywords = [k["keyword"] for k in cluster.get("keywords", [])]
        if not keywords:
            continue

        primary = keywords[0]
        slug = primary.lower().replace(" ", "-")[:60]
        canonical = f"{base_url.rstrip('/')}/{slug}/" if base_url else ""

        console.print(f"\n[bold]Creating page for cluster:[/] {cluster['name']}")
        result = create_page(
            cluster_name=cluster["name"],
            primary_keyword=primary,
            keywords=keywords[1:],
            content_type=cluster.get("content_type", "pillar page"),
            canonical_url=canonical,
        )
        path = save_page(result, output_dir)
        generated.append(path)

    return generated
