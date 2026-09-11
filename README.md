# AI Lead Enrichment Agent

An autonomous Python-based lead enrichment agent that crawls public company websites, extracts useful website content, and uses an LLM to generate structured company intelligence.

---

## Features

* Automated browser-based website crawling with Playwright
* Support for JavaScript-rendered websites
* Automatic discovery of relevant internal pages
* Clean text extraction from HTML
* Removal of scripts, styles, SVGs, navigation, and other boilerplate
* LLM-based company intelligence extraction
* Structured output validation using Pydantic
* Public/generic email extraction
* Leadership and team member extraction
* LinkedIn URL discovery
* External Google search fallback for missing LinkedIn profiles
* Confidence scoring
* Error handling and retry logic
* Per-company token usage tracking
* Estimated API cost tracking
* JSON output generation
* Application logging

---

## Architecture

```
                     Company Domains
                            |
                            v
                +-----------------------+
                |       main.py         |
                |   Pipeline Controller |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                |      scraper.py       |
                |       Playwright      |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                |   HTML/Text Cleaning  |
                |      BeautifulSoup    |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                |     extractor.py      |
                |   Gemini + Pydantic   |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                | LinkedIn Enrichment   |
                |   Browser Search      |
                +-----------+-----------+
                            |
                            v
                +-----------------------+
                |     output.json       |
                | Structured Intelligence|
                +-----------------------+
```

---

## Project Structure

## Project Structure

```
ai-lead-enrichment-agent/
│
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── scraper.py
│   ├── extractor.py
│   └── models.py
│
├── output/
│   └── output.json
│
├── logs/
│   └── agent.log
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Technology Stack

### Python

The core application is implemented in Python.

### Playwright

Playwright is used for browser automation and JavaScript-rendered website retrieval.

### BeautifulSoup

BeautifulSoup is used to convert retrieved HTML into clean text and remove unnecessary content.

### Gemini

Google Gemini is used as the LLM for structured company intelligence extraction.

### Pydantic

Pydantic is used to define and validate the structured output schema.

### Google Search

Browser-based Google search is used as an optional fallback to discover public LinkedIn profiles when they are not available directly on the company website.

---

# Setup

## 1. Clone the repository

git clone <YOUR_GITHUB_REPOSITORY_URL>

cd ai-lead-enrichment-agent

---

## 2. Create a virtual environment

### Windows PowerShell

python -m venv venv

Activate it:

venv\Scripts\activate

### macOS/Linux

python3 -m venv venv

source venv/bin/activate

---

## 3. Install Python dependencies

pip install -r requirements.txt

---

## 4. Install Playwright Chromium

python -m playwright install chromium

---

# Gemini API Configuration

The application uses the Gemini API for AI-powered company intelligence extraction.

Create a Gemini API key through Google AI Studio.

Copy `.env.example` to `.env`.

### Windows PowerShell

Copy-Item .env.example .env

### macOS/Linux

cp .env.example .env

Then open `.env` and add:

GEMINI_API_KEY=your_gemini_api_key_here

Replace the placeholder with your actual API key.

Never commit your `.env` file or expose your API key publicly.

---

# Running the Application

The default test domains are:

postman.com
supabase.com
vapi.ai

Run the application:

python -m src.main

The application will:

1. Crawl each company website.
2. Discover relevant internal pages.
3. Extract clean website text.
4. Send the collected evidence to Gemini.
5. Validate the structured response using Pydantic.
6. Search for missing public LinkedIn profiles.
7. Save the final results to `output/output.json`.

---

# Using Custom Domains

The application also accepts company domains from the command line.

Example:

python -m src.main stripe.com notion.so

Another example:

python -m src.main github.com vercel.com

---

# Custom Output Path

A custom output path can be supplied using `--output`.

Example:

python -m src.main postman.com supabase.com --output output/custom.json

---

# Output

The application generates:

output/output.json

The output contains structured company intelligence.

Example structure:

[
{
"domain": "example.com",
"company_name": "Example Company",
"company_overview": "Example Company provides...",
"target_audience": "Developers and engineering teams...",
"contact_emails": [
"[contact@example.com](mailto:contact@example.com)"
],
"leadership_team": [
{
"name": "Example Person",
"role": "CEO",
"linkedin_url": "https://www.linkedin.com/in/example",
"linkedin_source": "search"
}
],
"source_pages": [
"https://example.com",
"https://example.com/about"
],
"confidence_score": 0.91,
"usage": {
"input_tokens": 5000,
"output_tokens": 700,
"total_tokens": 5700,
"estimated_cost_usd": 0.0
}
}
]

The actual values depend on the public information available on the websites at runtime.

---

# Data Fields

## Company Overview

A concise description of what the company does.

## Target Audience

The company's likely ideal customer profile based on available website evidence.

## Contact Emails

Public or generic contact email addresses discovered from the website.

Examples:

[contact@example.com](mailto:contact@example.com)
[sales@example.com](mailto:sales@example.com)
[support@example.com](mailto:support@example.com)

## Leadership / Team

Leadership or important team members found in the website content.

Each team member contains:

name
role
linkedin_url
linkedin_source

`linkedin_source` can be:

website
search
null

## Source Pages

URLs that contributed useful evidence to the extraction.

## Confidence Score

A value between 0.0 and 1.0 representing the estimated quality and completeness of the extracted information.

## Usage

The application records:

input_tokens
output_tokens
total_tokens
estimated_cost_usd

---

# Web Crawling Strategy

The crawler first loads the company homepage using Playwright.

It then discovers internal links and ranks them based on relevance.

High-value paths include:

/about
/company
/team
/people
/leadership
/founders
/contact
/pricing
/product
/products
/solutions
/customers
/enterprise
/careers

The crawler avoids unnecessary pages such as:

/blog
/news
/docs
/login
/signup
/privacy
/terms
/security

The number of crawled pages per domain is limited to prevent excessive browsing.

---

# Content Preprocessing

Raw HTML is not directly sent to the LLM.

The preprocessing pipeline is:

Raw HTML
|
v
Remove scripts
|
v
Remove styles
|
v
Remove SVGs
|
v
Remove navigation
|
v
Remove footer/forms
|
v
Remove common cookie/popup elements
|
v
Extract text
|
v
Normalize whitespace
|
v
Limit content size
|
v
Gemini

This reduces unnecessary LLM input and improves extraction quality.

---

# Structured LLM Output

Gemini is configured to return structured JSON matching the application's Pydantic schema.

The result is validated before it is accepted by the application.

This prevents the pipeline from relying on arbitrary free-form LLM responses.

The LLM is instructed to extract information only from the provided evidence and avoid fabricating missing information.

---

# Error Handling

The application is designed to continue processing when individual pages or companies fail.

Handled conditions include:

* Page timeouts
* HTTP errors
* Missing pages
* Empty page content
* Search failures
* LLM failures
* LLM retries
* Pydantic validation errors
* Browser errors

For example:

Company A
|
+-- Homepage ✓
+-- About ✓
+-- Team ✗ timeout
|
v
Continue processing

Company B
|
v
Still processed normally

One failed page does not terminate the entire application.

---

# LinkedIn Enrichment

When a leadership member is identified but does not have a LinkedIn URL in the company website content, the application performs an external search.

The search is constrained to LinkedIn profile URLs.

Example query concept:

site:linkedin.com/in/ "Person Name" "Company Name"

The application does not manufacture LinkedIn URLs.

If a profile cannot be reliably discovered, the field remains:

"linkedin_url": null

---

# Token and Cost Tracking

The application records LLM usage returned by the Gemini API.

For each company:

Input tokens
Output tokens
Total tokens
Estimated cost

The cost calculation is separated from the extraction logic so the pricing configuration can be changed independently if required.

---

# Logging

Runtime logs are stored in:

logs/agent.log

The logs include information such as:

* Website being crawled
* Pages discovered
* Pages that failed
* Gemini extraction attempts
* LinkedIn searches
* Pipeline errors

Logging makes it easier to understand what happened during each run and diagnose failures.

---

# Testing

The three required assignment domains are:

postman.com
supabase.com
vapi.ai

Run:

python -m src.main

Then inspect:

output/output.json

You can also inspect the application logs:

logs/agent.log

---

# Security

The Gemini API key is loaded from an environment variable.

The following file must never be committed:

.env

The `.gitignore` file excludes it.

Before pushing the repository, verify:

git status

Make sure `.env` is not included in the files to be committed.

If an API key is accidentally exposed, revoke it immediately and generate a new one.

---

# Limitations

This project relies on publicly accessible website content.

Some websites may:

* Block automated browsers
* Require authentication
* Use aggressive bot protection
* Render content differently depending on location
* Change their page structure
* Hide contact information
* Not publicly expose leadership information
* Return incomplete or dynamically generated content

When information cannot be reliably retrieved, the application records the missing information rather than intentionally fabricating it.

---

# Future Improvements

Possible future improvements include:

* Multi-level crawling
* Better relevance ranking
* Additional search providers
* More sophisticated browser-agent navigation
* Persistent caching
* Concurrent company processing
* Database storage
* Lead scoring
* Additional company intelligence fields
* More detailed API cost reporting
* Automated unit and integration tests
* Configurable crawling limits
* Better duplicate content detection

---

# Assignment Deliverables

The repository provides:

* Modular Python implementation
* `requirements.txt`
* Environment variable configuration
* README documentation
* JSON output
* Browser automation
* LLM structured extraction
* Pydantic validation
* Error handling
* LinkedIn search enrichment
* Token usage tracking
* API cost estimation
* Application logging

---

# Author

**Amogha K A**

GitHub: `https://github.com/AmoghaKA`

LinkedIn: `https://www.linkedin.com/in/amogha-k-a-13224632a/`
