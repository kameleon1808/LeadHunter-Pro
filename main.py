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

    # ── init command (default behaviour) ───────────────────────────────────
    subparsers.add_parser("init", help="Initialise the database")

    # ── campaign command ────────────────────────────────────────────────────
    campaign_parser = subparsers.add_parser(
        "campaign",
        help="Create a new campaign",
    )
    campaign_parser.add_argument("--name", type=str, required=True, help="Campaign name")
    campaign_parser.add_argument("--niche", type=str, required=True, help='Industry niche, e.g. "marketing agencies"')
    campaign_parser.add_argument("--country", type=str, default=None, help="Target country (optional)")

    # ── scrape command ──────────────────────────────────────────────────────
    scrape_parser = subparsers.add_parser(
        "scrape",
        help="Collect company URLs from Google search results",
    )
    scrape_parser.add_argument(
        "--campaign-id",
        type=int,
        required=True,
        help="ID of the campaign to attach collected URLs to",
    )
    scrape_parser.add_argument(
        "--query",
        type=str,
        required=True,
        help='Google search query, e.g. "marketing agencies in Serbia"',
    )
    scrape_parser.add_argument(
        "--pages",
        type=int,
        default=config.SEARCH_PAGES_DEFAULT,
        help=f"Number of Google result pages to scrape (default: {config.SEARCH_PAGES_DEFAULT})",
    )

    args = parser.parse_args()

    db = DatabaseManager(config.DATABASE_PATH)
    db.initialize_db()

    if args.command == "campaign":
        c = db.create_campaign(name=args.name, niche=args.niche, target_country=args.country)
        print(f"Campaign created — id={c.id} | name='{c.name}' | niche='{c.niche}'")
    elif args.command == "scrape":
        asyncio.run(_run_scrape(db, args.campaign_id, args.query, args.pages, logger))
    else:
        # Default: initialise only
        logger.info("LeadHunter Pro initialised successfully")
        print("LeadHunter Pro initialized successfully")
        if args.command not in (None, "init"):
            parser.print_help()


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


if __name__ == "__main__":
    main()
