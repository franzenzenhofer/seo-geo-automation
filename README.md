# seo-geo-automation

Automated SEO and GEO (generative engine optimisation) audit for any public URL.
32 tool modules, 223 built-in checks, one self-contained HTML report plus JSON per run,
an optional AI executive summary via [OpenRouter](https://openrouter.ai/), and optional
Google Search Console and PageSpeed Insights data.

Runs on macOS, Linux and Windows with Python 3.10 or newer. No API key is needed for the core audit.

## Quickstart

```bash
git clone https://github.com/franzenzenhofer/seo-geo-automation.git
cd seo-geo-automation
python -m venv .venv
```

Activate the virtual environment:

| OS | Command |
|----|---------|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |

Then install and run your first audit (no keys needed):

```bash
python -m pip install -r requirements.txt
python run.py --url https://loremipsum.franzai.com/ --no-ai
```

The run prints one line per tool and ends with the path of `report.html`. Open it in a browser.

## Usage

```bash
# Single URL, no AI
python run.py --url https://example.com/ --no-ai

# Only some tools (names = file names without check_, upper case)
python run.py --url https://example.com/ --tools HEAD,HTTP,BODY,SCHEMA --no-ai

# With a site config: targeted phrases, brand, important pages (multi-page audit)
python run.py --config configs/example.config.json --no-ai

# Config context, but only one URL
python run.py --config configs/example.config.json --url https://loremipsum.franzai.com/ --no-ai

# Crawl as Googlebot smartphone instead of a normal mobile browser
python run.py --url https://example.com/ --ua googlebot-mobile --no-ai

# With AI synthesis (needs OPENROUTER_API_KEY, see below)
python run.py --url https://example.com/

# One tool on its own, from the repository root
python -m tools.check_head --url https://example.com/
python -m tools.check_head --url https://example.com/ --check HEAD-001
```

| Flag | Meaning |
|------|---------|
| `--url` | URL to audit. Overrides `important_pages` from the config. |
| `--config` | Site config JSON (see `configs/example.config.json`). |
| `--tools` | Comma-separated tool names. Unknown names abort the run. |
| `--no-ai` | Skip every AI feature. Works with zero keys. |
| `--ua` | `mobile` (default), `desktop`, `googlebot-mobile`, `googlebot-desktop`. |
| `--output-base` | Where results go (default `output/`). |

## Output

Every run writes to `output/<domain>/<timestamp>/`:

| File | Content |
|------|---------|
| `report.html` | Self-contained report (no external assets): summary, one section per tool, every check with severity, message and details. |
| `full-report.json` | All results in one JSON document (`categories[].checks[]` with `check_id`, `severity`, `message`, `details`). |
| `<tool>.json` | Raw result of each tool, e.g. `head.json`, `sitemap.json`. |
| `ai-synthesis.md` | Prioritised executive summary (only when AI is on). |
| `index.html`, `multi-report.json` | Aggregate over all pages (multi-page config runs only; per-page folders sit next to them). |

Severities: `PASS`, `WARN`, `FAIL`, `INFO` (informational or skipped) and `ERROR` (the check itself could not run).

## What it checks

| Tool | Checks | What it covers |
|------|-------:|----------------|
| check_head.py | 19 | Title, meta description, canonical, robots meta, viewport, charset, lang, favicon, blocking scripts |
| check_speed.py | 19 | Response time, render-blocking, fonts, image dimensions and lazy loading, HTML size, PSI scores and Core Web Vitals (LCP, CLS, INP, FCP, TTFB; needs `PSI_API_KEY`) |
| check_body.py | 17 | H1, subheadings, images, internal links, content diversity, word count, lists, tables, TOC, freshness, anchor texts |
| check_sitemap.py | 15 | Sitemap exists, valid XML, URL count, lastmod, page presence, noindex conflicts, totals, sitemap registered in GSC, important pages, news sitemap, RSS/Atom, robots.txt declaration, completeness, segmentation |
| check_http.py | 14 | Status, HTTPS, HSTS, compression, mixed content, redirects, response time, security headers, X-Robots-Tag, soft 404, www redirect, HTTP/2-3 |
| check_schema.py | 12 | JSON-LD: Article, Breadcrumb, Organization, Product, VideoObject, FAQPage, WebSite SearchAction, Event, Recipe, AggregateRating |
| check_url.py | 11 | Length, phrase in URL, parameters, lowercase, characters, trailing slash, single-hop redirects, hyphens, URL variants, permanence |
| check_images.py | 10 | Alt text, dimensions, lazy loading, filenames, modern formats, srcset, primary image size, phrase in alt |
| check_discover.py | 8 | max-image-preview, Article data, dates, author, headline length, indexability, large OG image, language |
| check_interlinking.py | 8 | Internal link count, sampled link status, nofollow, startpage link, parameterised links, canonical targets, dead-weight targets, per-section sampling |
| check_robots.py | 7 | robots.txt exists, size, sitemap directives, Googlebot access, complexity, blocked assets |
| check_rendering.py | 7 | SPA signals, noscript, JS framework, content without JS, overlays, nav links without JS, consent banners (Playwright comparison if installed) |
| check_dom.py | 6 | JSON-LD blocks, DOM size and depth, data-nosnippet, client-side rendering heuristic, top words |
| check_hreflang.py | 6 | Presence, self-reference, valid codes, x-default, canonical alignment, page language |
| check_targeting.py | 6 | Targeted phrase in title, H1, meta description; brand in title; number in description (needs config) |
| check_crawl.py | 5 | Important pages reachable, inbound links, link importance, dead links, GSC indexing (needs config) |
| check_crawl_budget.py | 5 | Crawl time estimate, targeted share of sitemap URLs, page count ceiling, sitemap efficiency, GSC submitted vs live sitemap URLs |
| check_gsc.py | 5 | PSI mobile/desktop score, GSC connection, URL Inspection index status, top queries |
| check_homepage.py | 5 | Root path, no redirect, links to important pages, brand in title, navigation |
| check_og.py | 5 | og:title, og:description, og:url, og:image, twitter:card |
| check_redirects.py | 5 | Chain depth, permanent redirects, HTTP to HTTPS, www/non-www, trailing slash |
| check_deadweight.py | 4 | Page purpose, noindex on thin pages, soft 404, status of noindex pages |
| check_mobile.py | 4 | Responsive viewport, separate mobile URLs, touch icon, zoom allowed |
| check_analytics.py | 3 | GA4/GTM/UA detection, other trackers, tracking IDs |
| check_autocomplete.py | 3 | Google Autocomplete for the targeted phrase, brand in suggestions, long-tail variations |
| check_external_links.py | 3 | External links present, unnecessary nofollow, external link ratio |
| check_screenshots.py | 3 | PSI Lighthouse screenshots (mobile/desktop), GSC render verdict |
| check_video.py | 3 | Embedded videos, VideoObject schema, lazy-loaded video iframes |
| check_favicon.py | 2 | Favicon reachable, format |
| check_trends.py | 2 | AI assessment of search interest and competing phrases (needs `OPENROUTER_API_KEY`, INFO only) |
| check_mobile_strategy.py | 1 | Responsive vs dynamic serving vs separate mobile URLs (mobile vs desktop fetch) |
| check_livetest.py | varies | Optional wrapper around the open-source [SEO Live Test](https://github.com/franzenzenhofer/franz-enzenhofer-seo-live-test-v7) CLI |

Checks that need a key or a config never fail because of it: they report `INFO` with the reason and the run goes on.

## Site config

Copy `configs/example.config.json` and adapt it:

| Field | Required | Used for |
|-------|----------|----------|
| `domain`, `start_url` | yes | Output folder, defaults |
| `brand_name` | no | Brand-in-title and autocomplete checks |
| `language` | no | Autocomplete and trend prompts (default `en`) |
| `targeted_phrases` | no | `{url: phrase}` for targeting, URL, image and AI checks |
| `important_pages` | no | Multi-page audit and crawl checks (`{"url": ..., "type": "homepage"}`) |
| `sitemap_url`, `robots_url` | no | Defaults: first `Sitemap:` line in robots.txt, then `/sitemap.xml`; `https://<domain>/robots.txt` |
| `gsc_property` | no | GSC property, e.g. `sc-domain:example.com` or `https://www.example.com/` |

## Optional integrations

All of them are configured with environment variables only. Never put keys into files in this repository.

### AI synthesis (OpenRouter)

```bash
export OPENROUTER_API_KEY=sk-or-...           # macOS / Linux
$env:OPENROUTER_API_KEY = "sk-or-..."         # Windows PowerShell
python run.py --url https://example.com/
```

- Uses the OpenAI-compatible [OpenRouter chat completions API](https://openrouter.ai/docs/api-reference/chat-completion).
- Default model: `google/gemini-3.1-flash-lite` (cheap). Override with `OPENROUTER_MODEL`, e.g. `OPENROUTER_MODEL=google/gemini-2.5-flash`.
- Without a key the run stops immediately and tells you to set the key or pass `--no-ai`.
- Give each participant a key with a hard credit limit (OpenRouter key settings) so nobody can overspend.

### PageSpeed Insights

```bash
export PSI_API_KEY=AIza...
```

Keyless PSI requests share an exhausted global quota, so the PSI-based checks (scores, Core Web Vitals, screenshots)
report `INFO` until you set a free key. How to get one:
[PSI API: get started](https://developers.google.com/speed/docs/insights/v5/get-started).

### Google Search Console

```bash
export GSC_CREDENTIALS=/path/to/credentials.json
```

and set `gsc_property` in the config. The JSON file can be either

- a **service account key**: create a service account in Google Cloud, enable the Search Console API, download a JSON key,
  then add the service account e-mail as a user of the property in Search Console; or
- an **OAuth authorized-user file** (`{"type": "authorized_user", "client_id": ..., "client_secret": ..., "refresh_token": ...}`),
  for example the file `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/webmasters.readonly,https://www.googleapis.com/auth/cloud-platform` writes.

The scope used is read-only (`webmasters.readonly`). API reference:
[Search Console API](https://developers.google.com/webmaster-tools/v1/api_reference_index).
Without `GSC_CREDENTIALS` the GSC checks report `INFO: GSC skipped`.

### JS rendering comparison (Playwright)

```bash
python -m pip install playwright
python -m playwright install chromium
```

`check_rendering.py` then renders the page in headless Chromium and compares word and link counts with the raw HTML.

### SEO Live Test

Clone [franz-enzenhofer-seo-live-test-v7](https://github.com/franzenzenhofer/franz-enzenhofer-seo-live-test-v7),
run `npm install` in its `v7` folder (Node.js required) and set `LIVETEST_PATH` to that `v7` folder.

## Claude skill

`skills/seo-geo-audit/SKILL.md` teaches an AI agent (Claude Code or any agent that reads skills) how to run the audit,
read `full-report.json` and turn the findings into a prioritised fix list. Install it for Claude Code:

```bash
# macOS / Linux
ln -s "$(pwd)/skills/seo-geo-audit" ~/.claude/skills/seo-geo-audit
```

On Windows copy the `skills/seo-geo-audit` folder to `%USERPROFILE%\.claude\skills\`.

## Development

```bash
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy .
pytest
```

Tests hit real public pages (`loremipsum.franzai.com`, `example.com`); there are no mocks, so they need internet access.
Live OpenRouter and GSC tests run only when `OPENROUTER_API_KEY`, or `GSC_CREDENTIALS` plus `GSC_TEST_PROPERTY`, are set.
CI runs lint, types, tests and a `--no-ai` smoke run on Ubuntu, Windows and macOS (`.github/workflows/ci.yml`).

Adding a check: add a function `check_x(page, response, config) -> CheckResult` to a `tools/check_*.py` module and
register it in that module's `checks` dict. A new tool is a new `tools/check_<name>.py` file whose category constant
is `<NAME>`; `run.py` discovers it automatically.

## License

MIT, see [LICENSE](LICENSE).
