import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

BLOCKED_DOMAINS = [
    "google.com",
    "google.co",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "yelp.com",
    "wikipedia.org",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "amazon.com",
    "trustpilot.com",
    "glassdoor.com",
    "indeed.com",
    "yellowpages.com",
    "bbb.org",
    "crunchbase.com",
    "clutch.co",
    "g2.com",
    "capterra.com",
    "tripadvisor.com",
    "mapquest.com",
    "bing.com",
    "yahoo.com",
    "apple.com",
    "microsoft.com",
]

_UTM_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "utm_id", "fbclid", "gclid", "msclkid",
    "ref", "referrer",
}


def normalize_url(url: str) -> str:
    """Ensure https://, remove trailing slashes, strip UTM/tracking params."""
    url = url.strip()
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)

    # Upgrade http to https
    scheme = "https"

    # Strip UTM and tracking query params
    query_params = parse_qs(parsed.query, keep_blank_values=True)
    clean_params = {k: v for k, v in query_params.items() if k.lower() not in _UTM_PARAMS}
    clean_query = urlencode(clean_params, doseq=True)

    # Remove trailing slash from path (keep root as empty)
    path = parsed.path.rstrip("/")

    normalized = urlunparse((
        scheme,
        parsed.netloc.lower(),
        path,
        parsed.params,
        clean_query,
        "",  # strip fragment
    ))
    return normalized


def is_valid_url(url: str) -> bool:
    """Return True if url is a well-formed http/https URL with a netloc."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def extract_domain(url: str) -> str:
    """Return the bare domain (without www.) from a URL."""
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower()
        # Strip port
        netloc = netloc.split(":")[0]
        # Strip leading www.
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""


def deduplicate_urls(urls: list[str]) -> list[str]:
    """Remove duplicate URLs by domain, preserving first-seen order."""
    seen_domains: set[str] = set()
    result: list[str] = []
    for url in urls:
        domain = extract_domain(url)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            result.append(url)
    return result


def is_blocked_domain(url: str) -> bool:
    """Return True if the URL's domain matches any entry in BLOCKED_DOMAINS."""
    domain = extract_domain(url)
    if not domain:
        return True
    for blocked in BLOCKED_DOMAINS:
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False
