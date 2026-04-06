import re
import feedparser
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Upgrade-Insecure-Requests": "1"
}

# HTML named entities that are NOT valid XML 1.0 but commonly appear in RSS
# Map them to their Unicode equivalents so feedparser can parse cleanly
_HTML_ENTITY_MAP = {
    '&nbsp;':   '\u00a0',
    '&mdash;':  '\u2014',
    '&ndash;':  '\u2013',
    '&ldquo;':  '\u201c',
    '&rdquo;':  '\u201d',
    '&lsquo;':  '\u2018',
    '&rsquo;':  '\u2019',
    '&hellip;': '\u2026',
    '&bull;':   '\u2022',
    '&trade;':  '\u2122',
    '&reg;':    '\u00ae',
    '&copy;':   '\u00a9',
    '&deg;':    '\u00b0',
    '&middot;': '\u00b7',
    '&laquo;':  '\u00ab',
    '&raquo;':  '\u00bb',
    '&eacute;': '\u00e9',
    '&egrave;': '\u00e8',
    '&ecirc;':  '\u00ea',
    '&agrave;': '\u00e0',
    '&acirc;':  '\u00e2',
    '&ocirc;':  '\u00f4',
    '&uuml;':   '\u00fc',
    '&ouml;':   '\u00f6',
    '&auml;':   '\u00e4',
    '&szlig;':  '\u00df',
    '&ntilde;': '\u00f1',
    '&ccedil;': '\u00e7',
    '&euro;':   '\u20ac',
    '&pound;':  '\u00a3',
    '&yen;':    '\u00a5',
    '&frac12;': '\u00bd',
    '&frac14;': '\u00bc',
    '&frac34;': '\u00be',
    '&times;':  '\u00d7',
    '&divide;': '\u00f7',
    '&plusmn;': '\u00b1',
    '&micro;':  '\u00b5',
    '&para;':   '\u00b6',
    '&sect;':   '\u00a7',
    '&dagger;': '\u2020',
    '&Dagger;': '\u2021',
    '&permil;': '\u2030',
    '&ensp;':   '\u2002',
    '&emsp;':   '\u2003',
    '&thinsp;': '\u2009',
    '&zwnj;':   '\u200c',
    '&zwj;':    '\u200d',
    '&lrm;':    '\u200e',
    '&rlm;':    '\u200f',
    '&shy;':    '\u00ad',
}

# Valid XML 1.0 entities — do NOT replace these
_XML_SAFE_ENTITIES = {'&amp;', '&lt;', '&gt;', '&apos;', '&quot;'}


def sanitize_xml(raw_bytes: bytes) -> bytes:
    """
    Multi-pass XML healer for broken RSS feeds.

    Pass 1: Decode bytes, strip BOM, normalize encoding
    Pass 2: Remove XML-illegal control characters
    Pass 3: Translate known HTML named entities → Unicode (undefined entity errors)
    Pass 4: Escape any bare & that survived (catches undefined custom entities)
    Pass 5: Strip non-printable / surrogate Unicode codepoints
    Pass 6: Attempt feedparser parse; if bozo, try lxml recovery as final fallback
    """
    # --- Pass 1: Decode & strip BOM ---
    for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            text = raw_bytes.decode(enc, errors='ignore')
            break
        except Exception:
            continue
    else:
        text = raw_bytes.decode('utf-8', errors='replace')

    # Strip UTF-8 BOM if present as text artifact
    text = text.lstrip('\ufeff')

    # --- Pass 2: Remove XML 1.0 illegal control chars (keep \t \n \r) ---
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    # --- Pass 3: Replace known HTML named entities with Unicode equivalents ---
    for entity, char in _HTML_ENTITY_MAP.items():
        text = text.replace(entity, char)

    # --- Pass 4: Escape any remaining bare & not part of a valid XML/numeric entity ---
    # Matches & not followed by amp; lt; gt; apos; quot; #digits; or #xhex;
    text = re.sub(
        r'&(?!(?:amp|lt|gt|apos|quot|#[0-9]+|#x[0-9a-fA-F]+);)',
        '&amp;',
        text
    )

    # --- Pass 5: Strip Unicode surrogates and private-use chars that break expat ---
    text = re.sub(r'[\ud800-\udfff]', '', text)

    return text.encode('utf-8')


def sanitize_xml_lxml_fallback(raw_bytes: bytes) -> bytes:
    """
    Nuclear fallback: use lxml's error-recovery HTML parser to extract RSS/Atom
    content from feeds with mismatched tags or structural XML errors.
    Returns cleaned bytes suitable for feedparser, or original bytes on failure.
    """
    try:
        from lxml import etree
        # lxml's recovery mode tolerates mismatched tags, unclosed elements, etc.
        parser = etree.XMLParser(recover=True, remove_comments=True, resolve_entities=False)
        root = etree.fromstring(raw_bytes, parser=parser)
        cleaned = etree.tostring(root, encoding='unicode', xml_declaration=False)
        return cleaned.encode('utf-8')
    except ImportError:
        pass
    except Exception:
        pass

    # lxml not available or failed — try BeautifulSoup XML mode
    try:
        soup = BeautifulSoup(raw_bytes, 'lxml-xml')
        return str(soup).encode('utf-8')
    except Exception:
        pass

    return raw_bytes


def extract_links_from_html(html: str, base_url: str):
    """Fallback: Scrape the front page for obvious news articles if no RSS is available."""
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    seen = set()

    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().strip()

        if not text or len(text) < 15:
            continue

        if href.startswith('/'):
            from urllib.parse import urljoin
            href = urljoin(base_url, href)

        if not href.startswith('http'):
            continue

        # Ignore obvious non-article links
        if any(x in href.lower() for x in ['/tag/', '/category/', '/author/', '/about', '/contact', 'login', 'signup', '/rss']):
            continue

        # Simplistic article detection: usually have longer URLs or dates
        if len(href) > len(base_url) + 10:
            if href not in seen:
                seen.add(href)
                import time
                items.append({
                    'title': text,
                    'link': href,
                    'summary': text,
                    'published_parsed': time.gmtime()
                })
                if len(items) >= 15:
                    break

    class PseudoFeed:
        def __init__(self, entries):
            self.entries = entries
            self.status = 200
            self.bozo = 0
            self.feed = {'title': 'Scraped Fallback'}

    return PseudoFeed(items)


def fetch_feed_robust(url: str):
    """
    3-stage fetch pipeline:
      Stage 1 — HTTP GET with spoofed headers, multi-pass XML sanitization, feedparser parse
      Stage 2 — If bozo/no-entries: lxml recovery parse on original bytes
      Stage 3 — If still no entries: HTML scrape fallback (base domain or original URL)
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=12, verify=False)
    except Exception as e:
        class MockFeed:
            pass
        mf = MockFeed()
        mf.status = 500
        mf.entries = []
        mf.bozo = 1
        mf.bozo_exception = e
        return mf

    content_type = r.headers.get('Content-Type', '').lower()
    original_bytes = r.content

    # --- Stage 1: Multi-pass sanitize → feedparser ---
    safe_content = sanitize_xml(original_bytes)
    parsed = feedparser.parse(safe_content)

    # Success: entries found and no structural bozo error
    if parsed.entries and not getattr(parsed, 'bozo', False):
        return parsed

    # Partial success: has entries despite bozo warning (dirty XML still parsed)
    if parsed.entries and getattr(parsed, 'bozo', False):
        bozo_ex = str(getattr(parsed, 'bozo_exception', ''))
        # Tolerate minor bozo if we got real content
        if 'syntax error' not in bozo_ex and 'mismatched tag' not in bozo_ex:
            return parsed

    # --- Stage 2: lxml recovery on sanitized bytes ---
    if getattr(parsed, 'bozo', False) or not parsed.entries:
        recovered_bytes = sanitize_xml_lxml_fallback(safe_content)
        if recovered_bytes != safe_content:
            parsed2 = feedparser.parse(recovered_bytes)
            if parsed2.entries:
                return parsed2

    # --- Stage 3: HTML scrape fallback ---
    if hasattr(r, 'text'):
        target_html = r.text
        target_url = url

        if r.status_code in [404, 403, 410, 500]:
            from urllib.parse import urlparse
            domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
            try:
                base_r = requests.get(domain, headers=HEADERS, timeout=8, verify=False)
                if base_r.status_code == 200:
                    target_html = base_r.text
                    target_url = domain
            except Exception:
                pass

        html_parsed = extract_links_from_html(target_html, target_url)
        if html_parsed.entries:
            html_parsed.status = 200
            return html_parsed

    return parsed
