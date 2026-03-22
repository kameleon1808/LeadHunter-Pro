import argparse
import asyncio
import sys

import config
from database import DatabaseManager


def main():
    config.setup_logging()

    import logging
    logger = logging.getLogger(__name__)

    parser = argparse.ArgumentParser(
        prog="leadhunter",
        description="LeadHunter Pro — automated lead generation tool",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── init ────────────────────────────────────────────────────────────────
    subparsers.add_parser("init", help="Initialise the database")

    # ── campaign (with sub-commands: create / list) ──────────────────────────
    campaign_parser = subparsers.add_parser("campaign", help="Manage campaigns")
    campaign_sub    = campaign_parser.add_subparsers(dest="campaign_action")

    create_parser = campaign_sub.add_parser("create", help="Create a new campaign")
    create_parser.add_argument("--name",    type=str, required=True, help="Campaign name")
    create_parser.add_argument("--niche",   type=str, required=True, help='Industry niche, e.g. "marketing agencies"')
    create_parser.add_argument("--country", type=str, default=None,  help="Target country (optional)")

    campaign_sub.add_parser("list", help="List all campaigns")

    # ── scrape ───────────────────────────────────────────────────────────────
    scrape_parser = subparsers.add_parser("scrape", help="Collect company URLs from Google search results")
    scrape_parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    scrape_parser.add_argument("--query",       type=str, required=True, help='Google search query')
    scrape_parser.add_argument(
        "--pages", type=int, default=config.SEARCH_PAGES_DEFAULT,
        help=f"Number of Google result pages to scrape (default: {config.SEARCH_PAGES_DEFAULT})",
    )

    # ── enrich ───────────────────────────────────────────────────────────────
    enrich_parser = subparsers.add_parser("enrich", help="Visit scraped URLs and extract lead data using Claude AI")
    enrich_parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")

    # ── export ───────────────────────────────────────────────────────────────
    export_parser = subparsers.add_parser("export", help="Export leads to Excel")
    export_parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")
    export_parser.add_argument(
        "--output", type=str, default="./exports/",
        help="Output directory or full file path (default: ./exports/)",
    )

    # ── dashboard ────────────────────────────────────────────────────────────
    dashboard_parser = subparsers.add_parser("dashboard", help="Live progress dashboard (Ctrl+C to exit)")
    dashboard_parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")

    # ── status ───────────────────────────────────────────────────────────────
    status_parser = subparsers.add_parser("status", help="Show campaign statistics")
    status_parser.add_argument("--campaign-id", type=int, required=True, help="Campaign ID")

    # ── dispatch ─────────────────────────────────────────────────────────────
    args = parser.parse_args()

    db = DatabaseManager(config.DATABASE_PATH)
    db.initialize_db()

    if args.command == "campaign":
        _run_campaign(db, args)

    elif args.command == "scrape":
        asyncio.run(_run_scrape(db, args.campaign_id, args.query, args.pages, logger))

    elif args.command == "enrich":
        asyncio.run(_run_enrich(db, args.campaign_id, logger))

    elif args.command == "export":
        _run_export(db, args.campaign_id, args.output)

    elif args.command == "dashboard":
        _run_dashboard(db, args.campaign_id)

    elif args.command == "status":
        _run_status(db, args.campaign_id)

    else:
        # init / default
        logger.info("LeadHunter Pro initialised successfully")
        print("LeadHunter Pro initialized successfully")
        if args.command not in (None, "init"):
            parser.print_help()


# ── Command handlers ─────────────────────────────────────────────────────────

def _run_campaign(db: DatabaseManager, args) -> None:
    from dashboard import CLIDashboard

    if args.campaign_action == "create":
        c = db.create_campaign(
            name=args.name,
            niche=args.niche,
            target_country=args.country,
        )
        print(f"Campaign created — id={c.id} | name='{c.name}' | niche='{c.niche}'")

    elif args.campaign_action == "list":
        CLIDashboard(db).show_campaigns_list()

    else:
        print("Usage: leadhunter campaign <create|list> [options]")
        print("  create --name '...' --niche '...' [--country '...']")
        print("  list")


def _run_export(db: DatabaseManager, campaign_id: int, output: str) -> None:
    from export import ExcelExporter

    campaign = db.get_campaign(campaign_id)
    if campaign is None:
        print(f"Error: campaign with id={campaign_id} not found.")
        sys.exit(1)

    leads_count = len(db.get_leads(campaign_id))
    print(f"\nCampaign : {campaign.name}")
    print(f"Leads    : {leads_count}")
    print(f"Output   : {output}\n")

    exporter  = ExcelExporter(db)
    file_path = exporter.export_campaign(campaign_id, output)
    print(f"Export complete: {file_path}")


def _run_dashboard(db: DatabaseManager, campaign_id: int) -> None:
    from dashboard import CLIDashboard

    campaign = db.get_campaign(campaign_id)
    if campaign is None:
        print(f"Error: campaign with id={campaign_id} not found.")
        sys.exit(1)

    CLIDashboard(db).show_campaign_progress(campaign_id)


def _run_status(db: DatabaseManager, campaign_id: int) -> None:
    from dashboard import CLIDashboard

    campaign = db.get_campaign(campaign_id)
    if campaign is None:
        print(f"Error: campaign with id={campaign_id} not found.")
        sys.exit(1)

    dash = CLIDashboard(db)
    dash.show_stats(campaign_id)
    dash.show_leads_preview(campaign_id, limit=10)


async def _run_scrape(db, campaign_id: int, query: str, pages: int, logger) -> None:
    from scrapers import URLScraper

    campaign = db.get_campaign(campaign_id)
    if campaign is None:
        print(f"Error: campaign with id={campaign_id} not found.")
        sys.exit(1)

    logger.info("Scraping campaign '%s' (id=%d) | query='%s' | pages=%d",
                campaign.name, campaign_id, query, pages)
    print(f"\nCampaign  : {campaign.name}")
    print(f"Query     : {query}")
    print(f"Pages     : {pages}")
    print(f"Headless  : {config.PLAYWRIGHT_HEADLESS}\n")

    scraper = URLScraper(db_manager=db, campaign_id=campaign_id)
    await scraper.start_browser()
    try:
        urls = await scraper.search_and_collect(query=query, num_pages=pages)
        print(f"\nDone. Collected {len(urls)} unique URLs.")
        logger.info("Scraping finished. %d URLs collected for campaign %d.", len(urls), campaign_id)
    finally:
        await scraper.close_browser()


async def _run_enrich(db, campaign_id: int, logger) -> None:
    from enrichment import AIExtractor, ClaudeCodeExtractor, EnrichmentPipeline

    campaign = db.get_campaign(campaign_id)
    if campaign is None:
        print(f"Error: campaign with id={campaign_id} not found.")
        sys.exit(1)

    api_key = config.ANTHROPIC_API_KEY
    if api_key:
        extractor = AIExtractor(api_key=api_key)
        extractor_label = f"Anthropic API (model: {config.CLAUDE_MODEL})"
    else:
        extractor = ClaudeCodeExtractor()
        extractor_label = f"Claude Code CLI — besplatno (model: {config.CLAUDE_MODEL})"

    stats   = db.get_campaign_stats(campaign_id)
    pending = stats["pending_urls"]

    logger.info(
        "Enriching campaign '%s' (id=%d) | pending_urls=%d | extractor=%s",
        campaign.name, campaign_id, pending, extractor_label,
    )
    print(f"\nCampaign  : {campaign.name}")
    print(f"Pending   : {pending} URLs to enrich")
    print(f"Ekstraktor: {extractor_label}\n")

    if pending == 0:
        print("No pending URLs to enrich. Run 'scrape' first.")
        return

    pipeline = EnrichmentPipeline(
        db_manager=db,
        ai_extractor=extractor,
        campaign_id=campaign_id,
    )
    await pipeline.process_campaign(campaign_id)

    final_stats = db.get_campaign_stats(campaign_id)
    print(f"\nEnrichment complete.")
    print(f"Leads found : {final_stats['total_leads']}")
    print(f"Completed   : {final_stats['completed_urls']}")
    print(f"Failed      : {final_stats['failed_urls']}")


if __name__ == "__main__":
    main()
