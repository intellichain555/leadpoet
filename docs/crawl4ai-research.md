# Crawl4AI Research Notes

**Date:** 2026-02-28

## What It Is

Crawl4AI is an open-source Python library for web scraping that outputs LLM-friendly markdown. It uses Playwright (headless Chromium) under the hood for JavaScript rendering. Current stable version is v0.8.0. GitHub: https://github.com/unclecode/crawl4ai

It is fully self-hosted -- no API keys, no cloud service, no usage fees. You run it locally.

---

## 1. JavaScript Rendering

- Uses **Playwright** with headless Chromium by default (also supports Firefox and WebKit)
- Full JavaScript execution -- pages are rendered in a real browser before content extraction
- You can inject custom JS code to click tabs, scroll, wait for elements, etc:
  ```python
  config = CrawlerRunConfig(
      js_code=["""
          document.querySelector('.load-more').click();
          await new Promise(r => setTimeout(r, 1000));
      """]
  )
  ```
- Has an "undetected browser" mode for sites with bot detection
- Supports waiting for specific selectors or conditions before extracting content

---

## 2. Markdown Output

Yes, it returns clean markdown. This is its primary selling point.

**Result object fields:**
- `result.markdown` -- full HTML-to-markdown conversion
- `result.markdown.raw_markdown` -- raw converted content
- `result.markdown.fit_markdown` -- content after noise filtering (removes navs, footers, ads)
- `result.extracted_content` -- JSON extraction results (if using structured extraction)
- `result.success` -- boolean
- `result.error_message` -- error details if failed

**Content filtering for cleaner output:**
```python
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

md_generator = DefaultMarkdownGenerator(
    content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
)
config = CrawlerRunConfig(markdown_generator=md_generator)
```

The `fit_markdown` field uses a pruning filter to strip boilerplate (navigation, sidebars, footers) and return only the main content. The threshold controls aggressiveness of pruning.

---

## 3. System Requirements -- Can It Run on 8 vCPU / No GPU?

**Yes.** No GPU needed at all. Crawl4AI is CPU-only for its core functionality (browser automation + HTML parsing).

Specific requirements:
- **Python:** 3.10, 3.11, 3.12, or 3.13
- **RAM:** Not officially documented, but headless Chromium typically uses 200-500 MB per browser instance. With 8 vCPUs and reasonable RAM (16 GB+), you can run multiple concurrent crawls easily
- **Disk:** Chromium browser binaries (~300-400 MB), plus library deps
- **Docker note:** If using Docker, requires `--shm-size=1g` minimum (Chromium needs shared memory)
- **No GPU:** Core features (scraping, markdown generation, CSS/XPath extraction) need no GPU. Only the optional `[torch]` and `[transformer]` extras (for local LLM-based semantic extraction) would benefit from GPU, but those are entirely optional

**For your server (8 vCPU AMD EPYC, no GPU):** This is fine. You only need the base install. The heavy lifting is browser rendering (CPU-bound) and you have plenty of cores.

---

## 4. Crawl4AI vs Firecrawl for Company Website Scraping

| Aspect | Crawl4AI | Firecrawl |
|---|---|---|
| **Hosting** | Self-hosted, free | Cloud SaaS, paid plans (or self-host open-source version) |
| **Cost** | $0 (your server resources only) | Free tier limited; paid plans $19-$399/mo |
| **JavaScript** | Playwright/Chromium, full rendering | Auto-detects if JS needed, handles it |
| **Markdown quality** | Clean, with configurable content filtering | Raw output can be messy; Extract tier is cleaner |
| **Speed (simple pages)** | ~4x faster than Firecrawl for basic extraction | Slower due to API overhead |
| **Speed (with LLM extraction)** | ~25 sec per page (LLM bottleneck) | Varies by plan |
| **Structured extraction** | CSS/XPath selectors built-in; LLM-based optional | Built-in via Extract endpoint |
| **Bot detection bypass** | Undetected browser mode, stealth options | Handled server-side |
| **Sitemap/crawl planning** | Manual or use built-in deep crawl | "Map" endpoint auto-generates sitemaps |
| **Reliability** | You manage retries, error handling | Managed for you |
| **Compliance** | Your responsibility | Some built-in features |

**Bottom line for scraping company websites:**
- Crawl4AI is the better choice if you want free, self-hosted, and are comfortable managing the infrastructure. The markdown output for basic company pages (About, Team, Products) is solid.
- Firecrawl is better if you want zero maintenance and are willing to pay. Its structured extraction (Extract tier) produces cleaner JSON out of the box.
- For your use case (running on your own server, likely scraping a moderate number of company sites), Crawl4AI makes more sense -- no API costs, no rate limits from a third party.

---

## 5. Known Issues and Limitations

**Memory management:**
- Headless Chromium is memory-hungry. If crawling many pages concurrently, memory can accumulate
- AsyncWebCrawler instances must be properly closed (`async with` or `await crawler.stop()`)
- In Docker, memory isn't always released after crawling -- can accumulate over time
- Set `max_concurrent_tasks` to limit parallel browser tabs

**Content extraction edge cases:**
- Complex page structures can produce messy markdown
- Lazy-loaded images may not be captured without explicit scroll/wait JS
- Structured JSON extraction (without LLM) described as "limited and buggy" by reviewers

**Concurrent crawling:**
- Race conditions were fixed in recent versions but can still occur in Docker
- Maximum recursion depth errors reported when multiple crawl processes overlap

**Docker/server deployment:**
- The Docker deployment story is still maturing -- the team was working on a new Docker architecture as of late 2025
- Local (non-Docker) usage is more stable

**Documentation:**
- Some users report the docs are incomplete or confusing for advanced use cases
- The API has changed significantly between versions, so Stack Overflow answers may be outdated

---

## 6. Installation

```bash
# Create a venv (recommended)
python3 -m venv crawl4ai_venv
source crawl4ai_venv/bin/activate

# Install base package
pip install crawl4ai

# Run setup (installs Chromium browser + OS dependencies automatically)
crawl4ai-setup

# Verify installation
crawl4ai-doctor
```

If `crawl4ai-setup` doesn't install Playwright browsers automatically:
```bash
python -m playwright install --with-deps chromium
```

**Optional extras (NOT needed for basic scraping):**
```bash
pip install crawl4ai[torch]         # PyTorch-based features
pip install crawl4ai[transformer]   # Hugging Face models
pip install crawl4ai[all]           # Everything
```

For your use case, `pip install crawl4ai` + `crawl4ai-setup` is all you need.

---

## 7. Basic Usage Examples

### Minimal: Scrape a URL, Get Markdown

```python
import asyncio
from crawl4ai import AsyncWebCrawler

async def main():
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://example.com")
        if result.success:
            print(result.markdown)
        else:
            print(f"Failed: {result.error_message}")

asyncio.run(main())
```

### With Content Filtering (Cleaner Output)

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

async def main():
    md_generator = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
    )
    config = CrawlerRunConfig(
        markdown_generator=md_generator,
        cache_mode=CacheMode.BYPASS,  # Don't use cached results
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://example.com", config=config)
        if result.success:
            # raw_markdown = full page converted to markdown
            # fit_markdown = main content only (boilerplate removed)
            print(result.markdown.fit_markdown)

asyncio.run(main())
```

### With JavaScript Execution (Dynamic Pages)

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

async def main():
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        js_code=["""
            // Scroll to bottom to trigger lazy loading
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(r => setTimeout(r, 2000));
        """],
        wait_for="css:.content-loaded",  # Wait for specific element
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://example.com/dynamic-page", config=config)
        if result.success:
            print(result.markdown)

asyncio.run(main())
```

### Scrape Multiple URLs

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

async def main():
    urls = [
        "https://company1.com/about",
        "https://company2.com/team",
        "https://company3.com/products",
    ]

    config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler() as crawler:
        for url in urls:
            result = await crawler.arun(url, config=config)
            if result.success:
                print(f"--- {url} ---")
                print(result.markdown[:500])
                print()
            else:
                print(f"FAILED: {url} - {result.error_message}")

asyncio.run(main())
```

---

## Summary Assessment

**Should you use Crawl4AI on your 8 vCPU server?**

Yes. It is a practical Firecrawl alternative for self-hosted web scraping. The core value proposition:
- Free, no API keys needed
- Handles JavaScript-heavy sites via real Chromium browser
- Outputs clean markdown suitable for LLM ingestion
- Runs fine on CPU-only servers
- Active development (v0.8.0, frequent releases)

Main caveats:
- Memory management requires attention if doing high-concurrency crawling
- The API surface is still evolving (check docs for your installed version)
- For structured JSON extraction, the built-in CSS/XPath works; LLM-based extraction adds latency and cost
