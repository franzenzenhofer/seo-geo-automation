---
name: seo-geo-audit
description: Use when someone wants an SEO or GEO audit of a website or URL, asks "what is wrong with the SEO of this page", wants technical SEO checks (title, canonical, robots.txt, sitemap, structured data, Core Web Vitals, redirects, internal links, rendering), or wants audit findings turned into a prioritised fix list. Runs the open-source seo-geo-automation tool and reads its JSON report.
---

# SEO/GEO audit with seo-geo-automation

The tool lives in a git checkout of https://github.com/franzenzenhofer/seo-geo-automation.
It runs 32 tool modules (223 checks) against a URL and writes JSON plus a self-contained HTML report.

## 1. Locate or set up the tool

1. Find the checkout: the folder that contains `run.py`, `tools/` and `shared/`. If there is none, clone the repo.
2. Use a virtual environment inside it. Create it once:
   - macOS / Linux: `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
   - Windows: `py -m venv .venv` then `.venv\Scripts\python -m pip install -r requirements.txt`
3. Run every command from the repository root with that interpreter (`.venv/bin/python` or `.venv\Scripts\python`).

## 2. Run the audit

Start without AI. It needs no keys and is the reliable baseline:

```bash
python run.py --url https://example.com/ --no-ai
```

- Several pages of one site: create a config (copy `configs/example.config.json`, set `domain`, `start_url`,
  `important_pages`, `targeted_phrases`, `brand_name`) and run `python run.py --config my-site.config.json --no-ai`.
- Only some areas: `--tools HEAD,HTTP,BODY,SCHEMA,SITEMAP,ROBOTS`.
- Crawl as Googlebot: `--ua googlebot-mobile`.
- AI executive summary: only if `OPENROUTER_API_KEY` is set in the environment; then drop `--no-ai`.
  Never write a key into a file; pass it as an environment variable.
- PSI scores and Core Web Vitals need `PSI_API_KEY`; Search Console data needs `GSC_CREDENTIALS` plus
  `gsc_property` in the config. Without them those checks report INFO and the audit continues.

A full run takes about 30-90 seconds. Run it in the foreground with a generous timeout (10 minutes).
The last lines print the report path: `output/<domain>/<timestamp>/report.html`.

## 3. Read the results

Read `full-report.json` from that folder, not the HTML. Structure:

- `summary`: totals for `pass`, `warn`, `fail`.
- `categories[]`: one per tool (`category`, `checks[]`).
- each check: `check_id` (e.g. `HEAD-006`), `name`, `severity`, `message`, `details`.

Severity meaning:

| Severity | Meaning | Action |
|----------|---------|--------|
| FAIL | A rule is clearly broken | Candidate fix |
| WARN | Likely problem or missed opportunity | Verify, then fix or dismiss |
| ERROR | The check itself could not run (network, timeout) | Re-run that tool once; report if it persists |
| INFO | Informational, or skipped (missing key/config) | Mention skipped areas as coverage gaps |
| PASS | Fine | Ignore |

Before you call something a problem, open the `details` and, when it matters, verify it against the live page
(fetch the URL, read the HTML or headers). Heuristic checks can misfire, for example a WARN about missing
lists on a page where lists make no sense, or a missing news sitemap on a site that does not publish news.

## 4. Turn findings into a prioritised list

Group by impact on crawling, indexing and ranking, in this order:

1. **Critical**: anything that blocks indexing or crawling. Non-200 status, `noindex` on a page that should rank,
   robots.txt blocking the page or its CSS/JS, canonical pointing elsewhere, redirect chains or loops,
   content invisible without JavaScript, sitemap missing or broken.
2. **High**: title / H1 / meta description missing or duplicated, targeted phrase absent from title and H1,
   broken internal links, missing or invalid structured data for the page type, poor Core Web Vitals (field data).
3. **Medium**: image alt texts and dimensions, lazy loading mistakes, thin content, missing internal links,
   HSTS and security headers, hreflang errors on multilingual sites.
4. **Low**: Open Graph and Twitter tags, favicon, analytics hygiene, cosmetic URL issues.

For every item write: the check ID(s), what is wrong (with the concrete value from `details`), why it matters
in one sentence, and the exact fix (the HTML tag, header or config line to change). Merge checks that describe
the same root cause (for example HEAD-006 and HREFLANG-005 for one canonical problem) into one item.
Keep a separate short list of skipped areas (PSI, GSC, AI) and what is needed to enable them.

## 5. Report back

Give the prioritised list first, then the totals (PASS/WARN/FAIL), then the report path so the user can open
`report.html`. Do not paste the raw JSON. Do not invent numbers that are not in the report.
