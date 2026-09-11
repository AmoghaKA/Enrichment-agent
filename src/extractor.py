import asyncio
import logging
import os
import re
from typing import List

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from src.models import CompanyIntelligence, UsageStats
from src.scraper import ScrapedCompany, search_linkedin_profile


# =========================================================
# Logging
# =========================================================

logger = logging.getLogger(__name__)


# =========================================================
# Configuration
# =========================================================

MODEL_NAME = "gemini-3.6-flash"

MAX_INPUT_CHARACTERS = 45_000

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 3

MAX_LINKEDIN_SEARCHES_PER_COMPANY = 5

# Gemini free tier means the actual API cost can be $0
# when usage remains within the applicable free quota.
#
# These values are intentionally configurable rather than
# hardcoded into the application logic.
INPUT_COST_PER_MILLION_TOKENS = 0.0

OUTPUT_COST_PER_MILLION_TOKENS = 0.0


# =========================================================
# Gemini extractor
# =========================================================

class GeminiExtractor:
    """
    Uses Gemini to extract structured company intelligence.
    """

    def __init__(self):
        load_dotenv()

        api_key = os.getenv(
            "GEMINI_API_KEY"
        )

        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY was not found.\n"
                "Please add it to your .env file."
            )

        self.client = genai.Client(
            api_key=api_key
        )

    # -----------------------------------------------------
    # Build evidence
    # -----------------------------------------------------

    def build_evidence(
        self,
        company: ScrapedCompany,
    ) -> str:
        """
        Convert scraped pages into compact evidence.

        Raw HTML is never sent to the LLM.
        """

        sections = []

        for page in company.pages:

            if not page.text.strip():
                continue

            section = (
                "\n"
                "===== SOURCE PAGE =====\n"
                f"URL: {page.url}\n"
                f"TITLE: {page.title}\n"
                f"STATUS: {page.status_code}\n"
                "\n"
                f"{page.text}\n"
            )

            sections.append(
                section
            )

        evidence = "\n".join(
            sections
        )

        if len(evidence) > MAX_INPUT_CHARACTERS:

            evidence = (
                evidence[:MAX_INPUT_CHARACTERS]
                + "\n\n[END OF AVAILABLE EVIDENCE]"
            )

        return evidence

    # -----------------------------------------------------
    # Email extraction
    # -----------------------------------------------------

    @staticmethod
    def extract_emails_from_text(
        text: str,
    ) -> List[str]:
        """
        Deterministically extract email addresses.
        """

        pattern = r"""
            [a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+
            @
            [a-zA-Z0-9-]+
            (?:
                \.
                [a-zA-Z0-9-]+
            )+
        """

        emails = re.findall(
            pattern,
            text,
            flags=re.VERBOSE,
        )

        cleaned = set()

        for email in emails:

            email = (
                email
                .strip()
                .lower()
                .rstrip(".,;:)]}>")
            )

            cleaned.add(email)

        return sorted(cleaned)

    # -----------------------------------------------------
    # Prompt
    # -----------------------------------------------------

    def build_prompt(
        self,
        company: ScrapedCompany,
        evidence: str,
    ) -> str:
        """
        Build the Gemini extraction prompt.
        """

        return f"""
You are an expert B2B company research analyst.

Extract structured company intelligence from PUBLIC
website content.

TARGET COMPANY DOMAIN:
{company.domain}

STRICT RULES:

1. Use ONLY the supplied website evidence.
2. Never invent facts.
3. Never guess names, roles, emails or URLs.
4. If information is missing, use an empty list or
   clearly indicate that it was not found.
5. Prefer generic/public emails such as contact@,
   sales@, support@, hello@ and info@.
6. Only include leadership/team members whose name
   and role are supported by the evidence.
7. Only include LinkedIn URLs explicitly present in
   the supplied evidence.
8. Do NOT manufacture LinkedIn URLs.
9. linkedin_source must be "website" for URLs found
   directly in the supplied website evidence.
10. The overview should be approximately two sentences.
11. The target audience should describe the company's
    likely ICP based only on evidence.
12. confidence_score must be between 0.0 and 1.0.
13. source_pages must contain actual URLs from the evidence.
14. Do not attempt to calculate token usage yourself.
15. Return structured JSON matching the supplied schema.

WEBSITE EVIDENCE:

{evidence}
"""

    # -----------------------------------------------------
    # Calculate cost
    # -----------------------------------------------------

    @staticmethod
    def calculate_cost(
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate estimated API cost.

        The current configuration uses zero as the cost
        because this project is intended to run using the
        applicable Gemini free tier.

        The calculation is kept separate so pricing can be
        changed later without modifying the pipeline.
        """

        input_cost = (
            input_tokens
            / 1_000_000
            * INPUT_COST_PER_MILLION_TOKENS
        )

        output_cost = (
            output_tokens
            / 1_000_000
            * OUTPUT_COST_PER_MILLION_TOKENS
        )

        return round(
            input_cost + output_cost,
            8,
        )

    # -----------------------------------------------------
    # Gemini request
    # -----------------------------------------------------

    async def request_extraction(
        self,
        prompt: str,
    ):
        """
        Send a structured request to Gemini.

        Returns:
            validated result
            usage metadata
        """

        last_error = None

        for attempt in range(
            1,
            MAX_RETRIES + 1,
        ):

            try:

                logger.info(
                    "Gemini extraction attempt %s/%s",
                    attempt,
                    MAX_RETRIES,
                )

                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=MODEL_NAME,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CompanyIntelligence,
                        temperature=0.1,
                    ),
                )

                if not response.text:

                    raise ValueError(
                        "Gemini returned an empty response."
                    )

                result = (
                    CompanyIntelligence
                    .model_validate_json(
                        response.text.strip()
                    )
                )

                # -------------------------------------------------
                # Token usage
                # -------------------------------------------------

                usage = getattr(
                    response,
                    "usage_metadata",
                    None,
                )

                input_tokens = 0
                output_tokens = 0

                if usage:

                    input_tokens = int(
                        getattr(
                            usage,
                            "prompt_token_count",
                            0,
                        )
                        or 0
                    )

                    output_tokens = int(
                        getattr(
                            usage,
                            "candidates_token_count",
                            0,
                        )
                        or 0
                    )

                total_tokens = (
                    input_tokens
                    + output_tokens
                )

                estimated_cost = (
                    self.calculate_cost(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                    )
                )

                usage_stats = UsageStats(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=estimated_cost,
                )

                return result, usage_stats

            except ValidationError as exc:

                last_error = exc

                logger.warning(
                    "Pydantic validation failed "
                    "on attempt %s: %s",
                    attempt,
                    exc,
                )

            except Exception as exc:

                last_error = exc

                logger.warning(
                    "Gemini request failed "
                    "on attempt %s: %s",
                    attempt,
                    exc,
                )

            if attempt < MAX_RETRIES:

                await asyncio.sleep(
                    RETRY_DELAY_SECONDS
                    * attempt
                )

        raise RuntimeError(
            "Gemini extraction failed after "
            f"{MAX_RETRIES} attempts: "
            f"{last_error}"
        )

    # -----------------------------------------------------
    # LinkedIn enrichment
    # -----------------------------------------------------

    async def enrich_linkedin_profiles(
        self,
        result: CompanyIntelligence,
    ) -> CompanyIntelligence:
        """
        Search for LinkedIn profiles that were not found
        on the company website.
        """

        if not result.leadership_team:
            return result

        from playwright.async_api import (
            async_playwright
        )

        async with async_playwright() as playwright:

            browser = await playwright.chromium.launch(
                headless=True
            )

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
            )

            try:

                searches_done = 0

                for member in result.leadership_team:

                    if searches_done >= (
                        MAX_LINKEDIN_SEARCHES_PER_COMPANY
                    ):
                        break

                    if member.linkedin_url:

                        member.linkedin_source = (
                            member.linkedin_source
                            or "website"
                        )

                        continue

                    searches_done += 1

                    linkedin_url = (
                        await search_linkedin_profile(
                            context=context,
                            person_name=member.name,
                            company_name=result.company_name,
                        )
                    )

                    if linkedin_url:

                        member.linkedin_url = (
                            linkedin_url
                        )

                        member.linkedin_source = (
                            "search"
                        )

            finally:

                await context.close()
                await browser.close()

        return result

    # -----------------------------------------------------
    # Extract one company
    # -----------------------------------------------------

    async def extract_company(
        self,
        company: ScrapedCompany,
    ) -> CompanyIntelligence:
        """
        Extract structured intelligence for one company.
        """

        evidence = self.build_evidence(
            company
        )

        if not evidence.strip():

            return CompanyIntelligence(
                domain=company.domain,
                company_name=company.domain,
                company_overview=(
                    "No usable website content was retrieved."
                ),
                target_audience=(
                    "Could not be determined from "
                    "the available website evidence."
                ),
                contact_emails=[],
                leadership_team=[],
                source_pages=[],
                confidence_score=0.0,
                usage=UsageStats(),
            )

        prompt = self.build_prompt(
            company=company,
            evidence=evidence,
        )

        try:

            result, usage_stats = (
                await self.request_extraction(
                    prompt
                )
            )

            # Store usage information.
            result.usage = usage_stats

            # -------------------------------------------------
            # Deterministic email backup
            # -------------------------------------------------

            all_scraped_text = "\n".join(
                page.text
                for page in company.pages
            )

            emails_from_text = (
                self.extract_emails_from_text(
                    all_scraped_text
                )
            )

            combined_emails = set(
                result.contact_emails
            )

            combined_emails.update(
                emails_from_text
            )

            result.contact_emails = sorted(
                combined_emails
            )

            # Always preserve actual domain.
            result.domain = company.domain

            if not result.source_pages:

                result.source_pages = [
                    page.url
                    for page in company.pages
                ]

            # -------------------------------------------------
            # LinkedIn bonus enrichment
            # -------------------------------------------------

            result = (
                await self.enrich_linkedin_profiles(
                    result
                )
            )

            return result

        except Exception as exc:

            logger.exception(
                "Extraction failed for %s: %s",
                company.domain,
                exc,
            )

            return CompanyIntelligence(
                domain=company.domain,
                company_name=company.domain,
                company_overview=(
                    "LLM extraction failed. "
                    "See application logs for details."
                ),
                target_audience=(
                    "Could not be determined because "
                    "LLM extraction failed."
                ),
                contact_emails=(
                    self.extract_emails_from_text(
                        "\n".join(
                            page.text
                            for page in company.pages
                        )
                    )
                ),
                leadership_team=[],
                source_pages=[
                    page.url
                    for page in company.pages
                ],
                confidence_score=0.1,
                usage=UsageStats(),
            )


# =========================================================
# Multiple companies
# =========================================================

async def extract_companies(
    companies: List[ScrapedCompany],
) -> List[CompanyIntelligence]:
    """
    Extract intelligence for multiple companies.
    """

    extractor = GeminiExtractor()

    results = []

    for company in companies:

        logger.info(
            "=" * 60
        )

        logger.info(
            "Extracting intelligence for %s",
            company.domain,
        )

        try:

            result = await extractor.extract_company(
                company
            )

            results.append(
                result
            )

        except Exception as exc:

            logger.exception(
                "Unexpected extraction error for %s: %s",
                company.domain,
                exc,
            )

            results.append(
                CompanyIntelligence(
                    domain=company.domain,
                    company_name=company.domain,
                    company_overview="Extraction failed.",
                    target_audience="Extraction failed.",
                    contact_emails=[],
                    leadership_team=[],
                    source_pages=[],
                    confidence_score=0.0,
                    usage=UsageStats(),
                )
            )

    return results