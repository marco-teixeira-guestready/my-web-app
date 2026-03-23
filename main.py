#!/usr/bin/env python3
"""
SEO/AEO Tools — powered by DataForSEO + Claude
================================================

Usage:
  python main.py universe "your seed keyword"
  python main.py optimize https://example.com/page --keyword "target keyword"
  python main.py create "primary keyword" --cluster "Topic Name"
  python main.py batch-create "seed keyword" --base-url https://example.com
"""

import json
import os
import sys

import click
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

console = Console()


def _check_env() -> None:
    missing = [
        k for k in ("ANTHROPIC_API_KEY", "DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD")
        if not os.getenv(k)
    ]
    if missing:
        console.print(f"[red]Missing environment variables:[/] {', '.join(missing)}")
        console.print("Copy [bold].env.example[/] to [bold].env[/] and fill in your credentials.")
        sys.exit(1)


@click.group()
def cli():
    """SEO/AEO tool suite powered by DataForSEO + Claude."""
    pass


@cli.command()
@click.argument("seed_keyword")
@click.option("--location", default=2840, help="DataForSEO location code (default: 2840 = USA)")
@click.option("--language", default="en", help="Language code (default: en)")
@click.option("--limit", default=100, help="Max keywords to fetch per source (default: 100)")
@click.option("--output", default="keyword_universe.json", help="Output JSON file")
def universe(seed_keyword, location, language, limit, output):
    """Build a keyword universe from a seed keyword and cluster it with Claude."""
    _check_env()
    from keyword_universe import build_keyword_universe, display_universe, save_universe

    clusters = build_keyword_universe(seed_keyword, location, language, limit)
    display_universe(clusters)
    save_universe(clusters, output)


@cli.command()
@click.argument("url")
@click.option("--keyword", required=True, help="Primary target keyword for the page")
@click.option("--secondary", multiple=True, help="Secondary keywords (can be repeated)")
@click.option("--output", default="optimization_brief.json", help="Output JSON file")
def optimize(url, keyword, secondary, output):
    """Audit a URL and generate SEO + AEO optimisation recommendations."""
    _check_env()
    from page_optimizer import optimize_page, display_optimizations, save_optimization

    result = optimize_page(url, keyword, list(secondary))
    display_optimizations(result)
    save_optimization(result, output)


@cli.command()
@click.argument("primary_keyword")
@click.option("--cluster", default="", help="Cluster / topic name")
@click.option("--keywords", default="", help="Comma-separated secondary keywords")
@click.option("--content-type", default="pillar page", help="Content type (e.g. 'pillar page', 'FAQ page')")
@click.option("--words", default=1200, help="Target word count (default: 1200)")
@click.option("--url", default="", help="Canonical URL for the page")
@click.option("--output-dir", default="generated_pages", help="Output directory")
def create(primary_keyword, cluster, keywords, content_type, words, url, output_dir):
    """Programmatically create an AEO-optimised page for a keyword."""
    _check_env()
    from page_creator import create_page, save_page

    secondary = [k.strip() for k in keywords.split(",") if k.strip()]
    result = create_page(
        cluster_name=cluster or primary_keyword,
        primary_keyword=primary_keyword,
        keywords=secondary,
        content_type=content_type,
        target_word_count=words,
        canonical_url=url,
    )
    path = save_page(result, output_dir)
    console.print(f"\n[bold green]Page created:[/] {path}")


@cli.command("batch-create")
@click.argument("seed_keyword")
@click.option("--base-url", default="", help="Base URL for canonical links")
@click.option("--location", default=2840, help="DataForSEO location code")
@click.option("--language", default="en", help="Language code")
@click.option("--universe-file", default="", help="Use existing keyword universe JSON file")
@click.option("--output-dir", default="generated_pages", help="Output directory")
def batch_create(seed_keyword, base_url, location, language, universe_file, output_dir):
    """
    Full pipeline: build keyword universe, then create pages for all
    high-priority AEO clusters automatically.
    """
    _check_env()
    from keyword_universe import build_keyword_universe, display_universe, save_universe
    from page_creator import batch_create_pages

    if universe_file and os.path.exists(universe_file):
        console.print(f"[cyan]Loading existing universe from:[/] {universe_file}")
        with open(universe_file) as f:
            clusters_raw = json.load(f)
    else:
        clusters_obj = build_keyword_universe(seed_keyword, location, language)
        display_universe(clusters_obj)
        save_universe(clusters_obj, "keyword_universe.json")
        clusters_raw = [
            {
                "name": c.name,
                "intent": c.intent,
                "aeo_opportunity": c.aeo_opportunity,
                "content_type": c.content_type,
                "priority": c.priority,
                "keywords": c.keywords,
            }
            for c in clusters_obj
        ]

    paths = batch_create_pages(clusters_raw, base_url, output_dir)
    console.print(f"\n[bold green]✓ Created {len(paths)} pages in {output_dir}/[/]")


if __name__ == "__main__":
    cli()
