import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import List, Set
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


# =========================================================
# Logging
# =========================================================

logger = logging.getLogger(__name__)


# =========================================================
# Data classes
# =========================================================

@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    status_code: int


@dataclass
class ScrapedCompany:
    domain: str
    pages: List[ScrapedPage] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# =========================================================
# Configuration
# =========================================================

MAX_PAGES_PER_DOMAIN = 8

PAGE_TIMEOUT_MS = 20_000

SEARCH_TIMEOUT_MS = 15_000

RELEVANT_PATH_KEYWORDS = {
    "about",
    "about-us",
    "company",
    "team",
    "people",
    "leadership",
    "founders",
    "founder",
    "contact",
    "pricing",
    "product",
    "products",
    "solutions",
    "customers",
    "customer",
    "enterprise",
    "careers",
}

IGNORED_PATH_KEYWORDS = {
    "blog",
    "news",
    "press",
    "changelog",
    "docs",
    "documentation",
    "login",
    "signin",
    "signup",
    "register",
    "privacy",
    "terms",
    "legal",
    "security",
    "status",
}


# =========================================================
# URL helpers
# =========================================================

def normalize_domain(domain: str) -> str:
    """
    Normalize a company domain.
    """

    domain = domain.strip()

    if not domain:
        raise ValueError(
            "Domain cannot be empty."
        )

    if not domain.startswith(
        ("http://", "https://")
    ):
        domain = f"https://{domain}"

    parsed = urlparse(domain)

    hostname = parsed.netloc.lower()

    if hostname.startswith("www."):
        hostname = hostname[4:]

    return hostname


def build_homepage_url(domain: str) -> str:
    """
    Build the homepage URL.
    """

    hostname = normalize_domain(domain)

    return f"https://{hostname}"


def is_same_domain(
    url: str,
    domain: str,
) -> bool:
    """
    Check whether a URL belongs to the target domain.
    """

    try:

        parsed = urlparse(url)

        hostname = parsed.netloc.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        target = normalize_domain(domain)

        return (
            hostname == target
            or hostname.endswith(
                "." + target
            )
        )

    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Remove URL fragments and unnecessary trailing slashes.
    """

    parsed = urlparse(url)

    cleaned = parsed._replace(
        fragment=""
    ).geturl()

    if (
        cleaned.endswith("/")
        and parsed.path not in ("", "/")
    ):
        cleaned = cleaned[:-1]

    return cleaned


# =========================================================
# URL relevance
# =========================================================

def score_url(url: str) -> int:
    """
    Score URLs according to their usefulness for
    company intelligence extraction.
    """

    parsed = urlparse(url)

    path = parsed.path.lower()

    segments = [
        segment
        for segment in path.split("/")
        if segment
    ]

    if not segments:
        return 0

    score = 0

    for segment in segments:

        segment = re.sub(
            r"[^a-z0-9_-]",
            "",
            segment,
        )

        if segment in RELEVANT_PATH_KEYWORDS:
            score += 10

        if any(
            keyword in segment
            for keyword in RELEVANT_PATH_KEYWORDS
        ):
            score += 5

        if segment in IGNORED_PATH_KEYWORDS:
            score -= 20

        if any(
            keyword in segment
            for keyword in IGNORED_PATH_KEYWORDS
        ):
            score -= 10

    return score


def is_relevant_url(url: str) -> bool:
    """
    Determine whether a URL should be crawled.
    """

    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    path = parsed.path.lower()

    ignored_extensions = (
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".webp",
        ".zip",
        ".mp4",
        ".mp3",
        ".woff",
        ".woff2",
        ".css",
        ".js",
    )

    if path.endswith(
        ignored_extensions
    ):
        return False

    for keyword in IGNORED_PATH_KEYWORDS:

        if f"/{keyword}" in path:
            return False

    return True


# =========================================================
# Text cleaning
# =========================================================

def clean_text(
    html: str,
) -> str:
    """
    Convert raw HTML into clean text.

    Removes scripts, styles, SVGs, navigation,
    footers, forms and other boilerplate.
    """

    soup = BeautifulSoup(
        html,
        "lxml",
    )

    unwanted_tags = [
        "script",
        "style",
        "svg",
        "noscript",
        "iframe",
        "canvas",
        "template",
        "nav",
        "footer",
        "form",
    ]

    for tag_name in unwanted_tags:

        for tag in soup.find_all(
            tag_name
        ):
            tag.decompose()

    unwanted_patterns = re.compile(
        r"cookie|consent|popup|modal|"
        r"advertisement|subscribe|newsletter|"
        r"tracking|breadcrumb",
        re.IGNORECASE,
    )

    for tag in soup.find_all(
        attrs={
            "class": unwanted_patterns
        }
    ):
        tag.decompose()

    for tag in soup.find_all(
        attrs={
            "id": unwanted_patterns
        }
    ):
        tag.decompose()

    text = soup.get_text(
        separator="\n"
    )

    lines = []

    for line in text.splitlines():

        line = re.sub(
            r"\s+",
            " ",
            line,
        ).strip()

        if line:
            lines.append(line)

    cleaned_lines = []

    previous = None

    for line in lines:

        if line != previous:
            cleaned_lines.append(line)

        previous = line

    return "\n".join(
        cleaned_lines
    )


def limit_text(
    text: str,
    max_characters: int = 30_000,
) -> str:
    """
    Limit the amount of text retained per page.
    """

    if len(text) <= max_characters:
        return text

    return (
        text[:max_characters]
        + "\n[CONTENT TRUNCATED]"
    )


# =========================================================
# Browser context
# =========================================================

async def create_browser_context(
    browser: Browser,
) -> BrowserContext:
    """
    Create a browser context for normal web browsing.
    """

    context = await browser.new_context(
        viewport={
            "width": 1440,
            "height": 900,
        },
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        java_script_enabled=True,
        ignore_https_errors=True,
    )

    return context


# =========================================================
# Single page scraper
# =========================================================

async def scrape_single_page(
    context: BrowserContext,
    url: str,
) -> ScrapedPage | None:
    """
    Scrape a single webpage.
    """

    page: Page = await context.new_page()

    try:

        logger.info(
            "Fetching: %s",
            url,
        )

        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

        if response is None:

            logger.warning(
                "No response received for %s",
                url,
            )

            return None

        status_code = response.status

        if status_code >= 400:

            logger.warning(
                "HTTP %s for %s",
                status_code,
                url,
            )

            return ScrapedPage(
                url=url,
                title="",
                text="",
                status_code=status_code,
            )

        try:

            await page.wait_for_load_state(
                "networkidle",
                timeout=5_000,
            )

        except PlaywrightTimeoutError:

            logger.debug(
                "Network idle timeout for %s",
                url,
            )

        await page.wait_for_timeout(
            500
        )

        html = await page.content()

        title = await page.title()

        text = clean_text(
            html
        )

        text = limit_text(
            text
        )

        return ScrapedPage(
            url=url,
            title=title.strip(),
            text=text,
            status_code=status_code,
        )

    except PlaywrightTimeoutError:

        logger.warning(
            "Timeout while fetching %s",
            url,
        )

        return None

    except Exception as exc:

        logger.exception(
            "Unexpected error while fetching %s: %s",
            url,
            exc,
        )

        return None

    finally:

        await page.close()


# =========================================================
# Link discovery
# =========================================================

async def discover_links(
    context: BrowserContext,
    url: str,
    domain: str,
) -> Set[str]:
    """
    Discover useful internal links from a page.
    """

    page = await context.new_page()

    discovered: Set[str] = set()

    try:

        logger.info(
            "Discovering links from: %s",
            url,
        )

        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT_MS,
        )

        if response is None:
            return discovered

        if response.status >= 400:
            return discovered

        try:

            await page.wait_for_load_state(
                "networkidle",
                timeout=5_000,
            )

        except PlaywrightTimeoutError:
            pass

        links = await page.locator(
            "a"
        ).evaluate_all(
            """
            elements => elements.map(a => ({
                href: a.href,
                text: a.innerText || a.textContent || ""
            }))
            """
        )

        for item in links:

            href = item.get(
                "href",
                "",
            )

            if not href:
                continue

            href = normalize_url(
                urljoin(
                    url,
                    href,
                )
            )

            if not is_same_domain(
                href,
                domain,
            ):
                continue

            if not is_relevant_url(
                href
            ):
                continue

            discovered.add(
                href
            )

    except PlaywrightTimeoutError:

        logger.warning(
            "Timeout discovering links from %s",
            url,
        )

    except Exception as exc:

        logger.exception(
            "Error discovering links from %s: %s",
            url,
            exc,
        )

    finally:

        await page.close()

    return discovered


# =========================================================
# Search engine helper
# =========================================================

async def search_linkedin_profile(
    context: BrowserContext,
    person_name: str,
    company_name: str,
) -> str | None:
    """
    Search Google for a person's public LinkedIn profile.

    This is an optional enrichment step.

    If Google blocks the request or no LinkedIn result is
    found, None is returned.
    """

    page = await context.new_page()

    try:

        query = (
            f'site:linkedin.com/in/ '
            f'"{person_name}" '
            f'"{company_name}"'
        )

        search_url = (
            "https://www.google.com/search?q="
            + quote_plus(query)
        )

        logger.info(
            "Searching LinkedIn for: %s",
            person_name,
        )

        response = await page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=SEARCH_TIMEOUT_MS,
        )

        if response is None:
            return None

        if response.status >= 400:

            logger.warning(
                "Search engine returned HTTP %s",
                response.status,
            )

            return None

        try:

            await page.wait_for_load_state(
                "networkidle",
                timeout=5_000,
            )

        except PlaywrightTimeoutError:
            pass

        links = await page.locator(
            "a"
        ).evaluate_all(
            """
            elements => elements.map(a => ({
                href: a.href,
                text: a.innerText || a.textContent || ""
            }))
            """
        )

        linkedin_candidates = []

        for item in links:

            href = item.get(
                "href",
                "",
            )

            text = item.get(
                "text",
                "",
            )

            if not href:
                continue

            href = href.strip()

            # Direct LinkedIn profile.
            if (
                "linkedin.com/in/"
                in href.lower()
            ):

                linkedin_candidates.append(
                    href
                )

                continue

            # Google may sometimes wrap result URLs.
            if (
                "linkedin.com"
                in text.lower()
                and "linkedin.com/in/"
                in href.lower()
            ):

                linkedin_candidates.append(
                    href
                )

        # Remove duplicates.
        unique_candidates = list(
            dict.fromkeys(
                linkedin_candidates
            )
        )

        if unique_candidates:

            selected = unique_candidates[0]

            logger.info(
                "LinkedIn profile found for %s: %s",
                person_name,
                selected,
            )

            return selected

        logger.info(
            "No LinkedIn profile found for %s",
            person_name,
        )

        return None

    except PlaywrightTimeoutError:

        logger.warning(
            "LinkedIn search timed out for %s",
            person_name,
        )

        return None

    except Exception as exc:

        logger.warning(
            "LinkedIn search failed for %s: %s",
            person_name,
            exc,
        )

        return None

    finally:

        await page.close()


# =========================================================
# Company crawler
# =========================================================

async def scrape_company(
    domain: str,
    browser: Browser,
) -> ScrapedCompany:
    """
    Crawl a company website.
    """

    normalized_domain = normalize_domain(
        domain
    )

    homepage = build_homepage_url(
        normalized_domain
    )

    result = ScrapedCompany(
        domain=normalized_domain
    )

    context = await create_browser_context(
        browser
    )

    try:

        homepage_page = await scrape_single_page(
            context=context,
            url=homepage,
        )

        if homepage_page is None:

            result.errors.append(
                "Homepage could not be retrieved."
            )

            return result

        if homepage_page.status_code >= 400:

            result.errors.append(
                f"Homepage returned HTTP "
                f"{homepage_page.status_code}."
            )

            return result

        result.pages.append(
            homepage_page
        )

        discovered_links = await discover_links(
            context=context,
            url=homepage,
            domain=normalized_domain,
        )

        ranked_links = sorted(
            discovered_links,
            key=score_url,
            reverse=True,
        )

        remaining_slots = (
            MAX_PAGES_PER_DOMAIN
            - len(result.pages)
        )

        ranked_links = ranked_links[
            :max(
                0,
                remaining_slots,
            )
        ]

        visited_urls = {
            normalize_url(page.url)
            for page in result.pages
        }

        for link in ranked_links:

            normalized_link = normalize_url(
                link
            )

            if normalized_link in visited_urls:
                continue

            visited_urls.add(
                normalized_link
            )

            page_result = await scrape_single_page(
                context=context,
                url=normalized_link,
            )

            if page_result is None:

                result.errors.append(
                    f"Failed to retrieve "
                    f"{normalized_link}"
                )

                continue

            if page_result.status_code >= 400:

                result.errors.append(
                    f"{normalized_link} returned HTTP "
                    f"{page_result.status_code}"
                )

                continue

            if not page_result.text.strip():

                result.errors.append(
                    f"No useful text found at "
                    f"{normalized_link}"
                )

                continue

            result.pages.append(
                page_result
            )

    except Exception as exc:

        logger.exception(
            "Crawler failed for %s: %s",
            normalized_domain,
            exc,
        )

        result.errors.append(
            f"Unexpected crawler error: {exc}"
        )

    finally:

        await context.close()

    return result


# =========================================================
# Multiple companies
# =========================================================

async def scrape_domains(
    domains: List[str],
) -> List[ScrapedCompany]:
    """
    Scrape multiple company domains.

    One company failing does not stop the others.
    """

    results: List[ScrapedCompany] = []

    async with async_playwright() as playwright:

        browser = await playwright.chromium.launch(
            headless=True
        )

        try:

            for domain in domains:

                logger.info(
                    "=" * 60
                )

                logger.info(
                    "Starting crawl for %s",
                    domain,
                )

                try:

                    company_result = await scrape_company(
                        domain=domain,
                        browser=browser,
                    )

                    results.append(
                        company_result
                    )

                except Exception as exc:

                    logger.exception(
                        "Company crawl failed for %s: %s",
                        domain,
                        exc,
                    )

                    results.append(
                        ScrapedCompany(
                            domain=normalize_domain(
                                domain
                            ),
                            pages=[],
                            errors=[
                                f"Company crawl failed: {exc}"
                            ],
                        )
                    )

        finally:

            await browser.close()

    return results


# =========================================================
# Testing helper
# =========================================================

def print_scrape_summary(
    results: List[ScrapedCompany],
) -> None:
    """
    Print scraping results.
    """

    print("\n" + "=" * 70)
    print("SCRAPING SUMMARY")
    print("=" * 70)

    for company in results:

        print(
            f"\nDomain: {company.domain}"
        )

        print(
            f"Pages scraped: "
            f"{len(company.pages)}"
        )

        print(
            f"Errors: "
            f"{len(company.errors)}"
        )

        for page in company.pages:

            print(
                f"  - {page.url} "
                f"[HTTP {page.status_code}] "
                f"({len(page.text)} characters)"
            )

        if company.errors:

            print(
                "  Errors:"
            )

            for error in company.errors:

                print(
                    f"    - {error}"
                )


# =========================================================
# Development test
# =========================================================

async def main():
    """
    Development test for the scraper.
    """

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(message)s"
        ),
    )

    domains = [
        "postman.com",
        "supabase.com",
        "vapi.ai",
    ]

    results = await scrape_domains(
        domains
    )

    print_scrape_summary(
        results
    )

    for company in results:

        print("\n" + "=" * 70)

        print(
            f"TEXT PREVIEW: "
            f"{company.domain}"
        )

        print("=" * 70)

        for page in company.pages:

            print(
                f"\n--- {page.url} ---"
            )

            preview = page.text[:1_000]

            print(
                preview
            )

            if len(page.text) > 1_000:

                print(
                    "\n[PREVIEW TRUNCATED]"
                )


if __name__ == "__main__":
    asyncio.run(
        main()
    )