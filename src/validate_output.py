import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_OUTPUT_PATH = Path("output/output.json")

EXPECTED_DOMAINS = {
    "postman.com",
    "supabase.com",
    "vapi.ai",
}

REQUIRED_COMPANY_FIELDS = {
    "domain",
    "company_name",
    "company_overview",
    "target_audience",
    "contact_emails",
    "leadership_team",
    "source_pages",
    "confidence_score",
    "usage",
}

REQUIRED_TEAM_FIELDS = {
    "name",
    "role",
    "linkedin_url",
    "linkedin_source",
}

REQUIRED_USAGE_FIELDS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "estimated_cost_usd",
}

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


def is_valid_url(value: str) -> bool:
    """Return True when value looks like a valid HTTP/HTTPS URL."""
    if not isinstance(value, str):
        return False

    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def validate_usage(usage: object, index: int) -> list[str]:
    """Validate token/cost statistics."""
    errors = []

    if not isinstance(usage, dict):
        return [f"Company #{index}: 'usage' must be an object."]

    missing = REQUIRED_USAGE_FIELDS - set(usage.keys())

    for field in sorted(missing):
        errors.append(
            f"Company #{index}: usage is missing '{field}'."
        )

    for field in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
    ):
        if field in usage:
            value = usage[field]

            if not isinstance(value, int) or value < 0:
                errors.append(
                    f"Company #{index}: usage.{field} must be "
                    f"a non-negative integer."
                )

    if (
        "input_tokens" in usage
        and "output_tokens" in usage
        and "total_tokens" in usage
        and isinstance(usage["input_tokens"], int)
        and isinstance(usage["output_tokens"], int)
        and isinstance(usage["total_tokens"], int)
    ):
        expected_total = (
            usage["input_tokens"] + usage["output_tokens"]
        )

        if usage["total_tokens"] != expected_total:
            errors.append(
                f"Company #{index}: usage.total_tokens does not equal "
                f"input_tokens + output_tokens."
            )

    if "estimated_cost_usd" in usage:
        cost = usage["estimated_cost_usd"]

        if not isinstance(cost, (int, float)) or cost < 0:
            errors.append(
                f"Company #{index}: usage.estimated_cost_usd must be "
                f"a non-negative number."
            )

    return errors


def validate_team(team: object, index: int) -> list[str]:
    """Validate leadership/team information."""
    errors = []

    if not isinstance(team, list):
        return [
            f"Company #{index}: 'leadership_team' must be a list."
        ]

    for member_index, member in enumerate(team, start=1):
        if not isinstance(member, dict):
            errors.append(
                f"Company #{index}, team member #{member_index}: "
                f"must be an object."
            )
            continue

        missing = REQUIRED_TEAM_FIELDS - set(member.keys())

        for field in sorted(missing):
            errors.append(
                f"Company #{index}, team member #{member_index}: "
                f"missing '{field}'."
            )

        name = member.get("name")
        role = member.get("role")

        if not isinstance(name, str) or not name.strip():
            errors.append(
                f"Company #{index}, team member #{member_index}: "
                f"'name' must be a non-empty string."
            )

        if not isinstance(role, str) or not role.strip():
            errors.append(
                f"Company #{index}, team member #{member_index}: "
                f"'role' must be a non-empty string."
            )

        linkedin_url = member.get("linkedin_url")

        if linkedin_url is not None:
            if not is_valid_url(linkedin_url):
                errors.append(
                    f"Company #{index}, team member #{member_index}: "
                    f"'linkedin_url' is not a valid URL."
                )
            elif "linkedin.com/in/" not in linkedin_url.lower():
                errors.append(
                    f"Company #{index}, team member #{member_index}: "
                    f"'linkedin_url' should point to a LinkedIn profile."
                )

        linkedin_source = member.get("linkedin_source")

        if linkedin_source not in {
            None,
            "website",
            "search",
        }:
            errors.append(
                f"Company #{index}, team member #{member_index}: "
                f"'linkedin_source' must be 'website', 'search', or null."
            )

    return errors


def validate_company(company: object, index: int) -> list[str]:
    """Validate one company record."""
    errors = []

    if not isinstance(company, dict):
        return [f"Company #{index} must be a JSON object."]

    missing = REQUIRED_COMPANY_FIELDS - set(company.keys())

    for field in sorted(missing):
        errors.append(
            f"Company #{index}: missing required field '{field}'."
        )

    domain = company.get("domain")

    if not isinstance(domain, str) or not domain.strip():
        errors.append(
            f"Company #{index}: 'domain' must be a non-empty string."
        )

    company_name = company.get("company_name")

    if not isinstance(company_name, str) or not company_name.strip():
        errors.append(
            f"Company #{index}: 'company_name' must be a non-empty string."
        )

    overview = company.get("company_overview")

    if not isinstance(overview, str) or not overview.strip():
        errors.append(
            f"Company #{index}: 'company_overview' must be a non-empty string."
        )

    target_audience = company.get("target_audience")

    if (
        not isinstance(target_audience, str)
        or not target_audience.strip()
    ):
        errors.append(
            f"Company #{index}: 'target_audience' must be "
            f"a non-empty string."
        )

    emails = company.get("contact_emails")

    if not isinstance(emails, list):
        errors.append(
            f"Company #{index}: 'contact_emails' must be a list."
        )
    else:
        for email in emails:
            if not isinstance(email, str):
                errors.append(
                    f"Company #{index}: every contact email must be a string."
                )
                continue

            if not EMAIL_PATTERN.match(email):
                errors.append(
                    f"Company #{index}: invalid email address: {email}"
                )

    source_pages = company.get("source_pages")

    if not isinstance(source_pages, list):
        errors.append(
            f"Company #{index}: 'source_pages' must be a list."
        )
    else:
        for url in source_pages:
            if not is_valid_url(url):
                errors.append(
                    f"Company #{index}: invalid source URL: {url}"
                )

    confidence = company.get("confidence_score")

    if not isinstance(confidence, (int, float)):
        errors.append(
            f"Company #{index}: 'confidence_score' must be a number."
        )
    elif not 0.0 <= confidence <= 1.0:
        errors.append(
            f"Company #{index}: confidence_score must be between "
            f"0.0 and 1.0."
        )

    errors.extend(
        validate_team(
            company.get("leadership_team"),
            index,
        )
    )

    errors.extend(
        validate_usage(
            company.get("usage"),
            index,
        )
    )

    return errors


def validate_output(
    output_path: Path,
    expected_domains: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate the complete output JSON file."""
    errors = []

    if not output_path.exists():
        return False, [
            f"Output file does not exist: {output_path}"
        ]

    if not output_path.is_file():
        return False, [
            f"Output path is not a file: {output_path}"
        ]

    try:
        with output_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        return False, [
            f"Invalid JSON: {exc}"
        ]
    except OSError as exc:
        return False, [
            f"Could not read output file: {exc}"
        ]

    if not isinstance(data, list):
        return False, [
            "Top-level JSON value must be a list of company objects."
        ]

    if not data:
        return False, [
            "Output JSON contains no company records."
        ]

    for index, company in enumerate(data, start=1):
        errors.extend(
            validate_company(
                company,
                index,
            )
        )

    domains = []

    for company in data:
        if isinstance(company, dict):
            domain = company.get("domain")

            if isinstance(domain, str):
                domains.append(domain.lower().strip())

    if len(domains) != len(set(domains)):
        errors.append(
            "Duplicate company domains were found in the output."
        )

    if expected_domains:
        expected = {
            domain.lower().strip()
            for domain in expected_domains
        }

        actual = set(domains)

        missing_domains = expected - actual
        unexpected_domains = actual - expected

        if missing_domains:
            errors.append(
                "Missing expected domains: "
                + ", ".join(sorted(missing_domains))
            )

        if unexpected_domains:
            errors.append(
                "Unexpected domains found: "
                + ", ".join(sorted(unexpected_domains))
            )

    return len(errors) == 0, errors


def print_summary(output_path: Path) -> None:
    """Print a useful summary after successful validation."""
    with output_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    total_input = 0
    total_output = 0
    total_tokens = 0
    total_cost = 0.0

    print()
    print("=" * 60)
    print("OUTPUT VALIDATION PASSED")
    print("=" * 60)
    print(f"File: {output_path}")
    print(f"Companies: {len(data)}")

    for company in data:
        usage = company.get("usage", {})

        total_input += usage.get("input_tokens", 0)
        total_output += usage.get("output_tokens", 0)
        total_tokens += usage.get("total_tokens", 0)
        total_cost += usage.get("estimated_cost_usd", 0.0)

        print()
        print(f"Domain: {company.get('domain')}")
        print(f"Company: {company.get('company_name')}")
        print(
            f"Confidence: "
            f"{company.get('confidence_score')}"
        )
        print(
            f"Emails: "
            f"{len(company.get('contact_emails', []))}"
        )
        print(
            f"Team members: "
            f"{len(company.get('leadership_team', []))}"
        )
        print(
            f"Source pages: "
            f"{len(company.get('source_pages', []))}"
        )

    print()
    print("-" * 60)
    print(f"Total input tokens:  {total_input}")
    print(f"Total output tokens: {total_output}")
    print(f"Total tokens:        {total_tokens}")
    print(f"Estimated cost:      ${total_cost:.6f}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate AI lead enrichment output JSON."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=(
            "Path to the output JSON file. "
            "Default: output/output.json"
        ),
    )

    parser.add_argument(
        "--skip-domain-check",
        action="store_true",
        help=(
            "Do not require the three assignment domains "
            "to be present."
        ),
    )

    args = parser.parse_args()

    expected_domains = None

    if not args.skip_domain_check:
        expected_domains = EXPECTED_DOMAINS

    success, errors = validate_output(
        args.input,
        expected_domains,
    )

    if not success:
        print()
        print("=" * 60)
        print("OUTPUT VALIDATION FAILED")
        print("=" * 60)
        print(f"File: {args.input}")
        print()

        for number, error in enumerate(errors, start=1):
            print(f"{number}. {error}")

        print()
        print("=" * 60)

        return 1

    print_summary(args.input)

    return 0


if __name__ == "__main__":
    sys.exit(main())