import httpx
import json
import jmespath
from loguru import logger

BASE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

client = httpx.Client(
    headers=BASE_HEADERS,
    timeout=30.0,
    follow_redirects=True,
    http2=True,  # Crunchbase servers prefer HTTP/2
)

import gzip
from parsel import Selector

def get_company_urls(client, max_urls=100):
    """Fetch company URLs from Crunchbase sitemap."""
    logger.info("Fetching sitemap index...")
    resp = client.get(
        "https://www.crunchbase.com/www-sitemaps/sitemap-index.xml"
    )
    sel = Selector(text=resp.text)
    # grab only the organization sitemap files
    sitemap_urls = [
        url for url in sel.css("sitemap loc::text").getall()
        if "sitemap-organizations" in url
    ]
    
    company_urls = []
    for sitemap_url in sitemap_urls[:2]:  # limit for demo
        resp = client.get(sitemap_url)
        xml = gzip.decompress(resp.content).decode()
        sel = Selector(text=xml)
        urls = sel.css("url loc::text").getall()
        company_urls.extend(urls)
        if len(company_urls) >= max_urls:
            break
    
    logger.info(f"Collected {len(company_urls)} company URLs")
    return company_urls[:max_urls]


def main():
    urls = get_company_urls(client)
    out_path = "company_urls.json"
    with open(out_path, "w") as f:
        json.dump(urls, f, indent=2)
    logger.info(f"Saved {len(urls)} URLs to {out_path}")


if __name__ == "__main__":
    main()

