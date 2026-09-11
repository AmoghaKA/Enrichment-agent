import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import List

from src.extractor import extract_companies
from src.scraper import scrape_domains


# =========================================================
# Configuration
# =========================================================

DEFAULT_DOMAINS = [
    "postman.com",
    "supabase.com",
    "vapi.ai",
]

DEFAULT_OUTPUT_PATH = Path(
    "output/output.json"
)

LOG_DIRECTORY = Path(
    "logs"
)

LOG_FILE = LOG_DIRECTORY / "agent.log"


# =========================================================
# Logging
# =========================================================

def setup_logging() -> None:
    """
    Configure console and file logging.
    """

    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                LOG_FILE,
                encoding="utf-8",
            ),
        ],
    )


logger = logging.getLogger(__name__)


# =========================================================
# Arguments
# =========================================================

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Autonomous AI Lead Enrichment Agent"
        )
    )

    parser.add_argument(
        "domains",
        nargs="*",
        help=(
            "Company domains to analyze. "
            "If omitted, the three assignment "
            "domains are used."
        ),
    )

    parser.add_argument(
        "--output",
        default=str(
            DEFAULT_OUTPUT_PATH
        ),
        help=(
            "Path where JSON output will be saved."
        ),
    )

    return parser.parse_args()


# =========================================================
# Domain validation
# =========================================================

def validate_domains(
    domains: List[str],
) -> List[str]:
    """
    Clean and validate supplied domains.
    """

    cleaned_domains = []

    for domain in domains:

        domain = domain.strip()

        if not domain:
            continue

        domain = domain.replace(
            "https://",
            "",
        )

        domain = domain.replace(
            "http://",
            "",
        )

        domain = domain.rstrip(
            "/"
        )

        if domain:
            cleaned_domains.append(
                domain
            )

    unique_domains = list(
        dict.fromkeys(
            cleaned_domains
        )
    )

    if not unique_domains:

        raise ValueError(
            "No valid company domains were supplied."
        )

    return unique_domains


# =========================================================
# Save JSON
# =========================================================

def save_results(
    results,
    output_path: Path,
) -> None:
    """
    Save structured results to JSON.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = [
        result.model_dump(
            mode="json"
        )
        for result in results
    ]

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(
        "Output saved to: %s",
        output_path,
    )


# =========================================================
# Summary
# =========================================================

def print_final_summary(
    results,
    elapsed_seconds: float,
) -> None:
    """
    Print final pipeline summary.
    """

    total_input_tokens = sum(
        result.usage.input_tokens
        for result in results
    )

    total_output_tokens = sum(
        result.usage.output_tokens
        for result in results
    )

    total_tokens = sum(
        result.usage.total_tokens
        for result in results
    )

    total_cost = sum(
        result.usage.estimated_cost_usd
        for result in results
    )

    print("\n")
    print("=" * 70)
    print("AI LEAD ENRICHMENT AGENT")
    print("=" * 70)

    print(
        f"\nCompanies processed: "
        f"{len(results)}"
    )

    print(
        f"Total execution time: "
        f"{elapsed_seconds:.2f} seconds"
    )

    print(
        f"Total input tokens: "
        f"{total_input_tokens}"
    )

    print(
        f"Total output tokens: "
        f"{total_output_tokens}"
    )

    print(
        f"Total tokens: "
        f"{total_tokens}"
    )

    print(
        f"Estimated API cost: "
        f"${total_cost:.8f}"
    )

    print("\nPer-company results:")

    for result in results:

        print(
            f"\n  {result.company_name}"
            f" ({result.domain})"
        )

        print(
            f"    Confidence: "
            f"{result.confidence_score:.2f}"
        )

        print(
            f"    Emails found: "
            f"{len(result.contact_emails)}"
        )

        print(
            f"    Team members: "
            f"{len(result.leadership_team)}"
        )

        print(
            f"    Source pages: "
            f"{len(result.source_pages)}"
        )

        print(
            f"    Input tokens: "
            f"{result.usage.input_tokens}"
        )

        print(
            f"    Output tokens: "
            f"{result.usage.output_tokens}"
        )

        print(
            f"    Total tokens: "
            f"{result.usage.total_tokens}"
        )

        print(
            f"    Estimated cost: "
            f"${result.usage.estimated_cost_usd:.8f}"
        )

    print("\n" + "=" * 70)


# =========================================================
# Main pipeline
# =========================================================

async def run_pipeline(
    domains: List[str],
    output_path: Path,
) -> None:
    """
    Execute the complete enrichment pipeline.
    """

    start_time = time.perf_counter()

    logger.info(
        "Starting AI Lead Enrichment Agent."
    )

    logger.info(
        "Domains: %s",
        ", ".join(domains),
    )

    # -----------------------------------------------------
    # Step 1 — Scraping
    # -----------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 1/2 — WEBSITE SCRAPING")
    print("=" * 70)

    logger.info(
        "Starting website scraping..."
    )

    scraped_companies = await scrape_domains(
        domains
    )

    successful_scrapes = sum(
        1
        for company in scraped_companies
        if company.pages
    )

    logger.info(
        "Scraping finished. "
        "%s/%s companies returned usable pages.",
        successful_scrapes,
        len(domains),
    )

    # -----------------------------------------------------
    # Step 2 — Gemini extraction
    # -----------------------------------------------------

    print("\n")
    print("=" * 70)
    print("STEP 2/2 — GEMINI STRUCTURED EXTRACTION")
    print("=" * 70)

    logger.info(
        "Starting Gemini extraction..."
    )

    results = await extract_companies(
        scraped_companies
    )

    logger.info(
        "Gemini extraction finished."
    )

    # -----------------------------------------------------
    # Step 3 — Save
    # -----------------------------------------------------

    print("\n")
    print("=" * 70)
    print("SAVING RESULTS")
    print("=" * 70)

    save_results(
        results=results,
        output_path=output_path,
    )

    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    print_final_summary(
        results=results,
        elapsed_seconds=elapsed_seconds,
    )


# =========================================================
# Entry point
# =========================================================

def main() -> None:
    """
    Application entry point.
    """

    setup_logging()

    args = parse_arguments()

    try:

        domains = (
            args.domains
            if args.domains
            else DEFAULT_DOMAINS
        )

        domains = validate_domains(
            domains
        )

        output_path = Path(
            args.output
        )

        asyncio.run(
            run_pipeline(
                domains=domains,
                output_path=output_path,
            )
        )

    except KeyboardInterrupt:

        logger.warning(
            "Execution interrupted by user."
        )

        sys.exit(1)

    except Exception as exc:

        logger.exception(
            "Fatal application error: %s",
            exc,
        )

        print(
            "\nThe application encountered an error."
        )

        print(
            f"Error: {exc}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()