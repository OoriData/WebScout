'''
Web fetcher protocol for retrieving and converting web content to markdown.

Provides a pluggable interface for different web scraping tools.
'''

from abc import ABC, abstractmethod
from dataclasses import dataclass
import httpx
import structlog
from ogbujipt.text.html import clean_html, html2markdown


logger = structlog.get_logger()


@dataclass
class FetchResult:
    '''Result of fetching a web page.'''
    url: str
    markdown: str
    title: str | None = None
    success: bool = True
    error: str | None = None


class WebFetcher(ABC):
    '''Protocol for web content fetchers.'''

    @abstractmethod
    async def fetch(self, url: str) -> FetchResult:
        '''
        Fetch a URL and return markdown content.

        Args:
            url: URL to fetch

        Returns:
            FetchResult with markdown content
        '''
        pass


class SimpleHttpFetcher(WebFetcher):
    '''
    Simple HTTP fetcher using httpx and OgbujiPT HTML processing.

    Best for: Static HTML pages without heavy JavaScript.
    '''

    def __init__(self, timeout: float = 30.0, follow_redirects: bool = True):
        '''
        Initialize the simple HTTP fetcher.

        Args:
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow HTTP redirects
        '''
        self.timeout = timeout
        self.follow_redirects = follow_redirects

    async def fetch(self, url: str) -> FetchResult:
        '''Fetch URL with httpx and convert HTML to markdown.'''
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=self.follow_redirects,
                verify=False  # Some sites have SSL issues
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Decode content
                html = response.content.decode(response.encoding or 'utf-8')

                # Clean and convert HTML
                tree, _ = clean_html(html)
                markdown = html2markdown(tree)

                # Try to extract title from tree
                title = None
                title_elem = tree.css_first('title')
                if title_elem:
                    title = title_elem.text(strip=True)

                return FetchResult(
                    url=url,
                    markdown=markdown,
                    title=title,
                    success=True
                )

        except Exception as e:
            return FetchResult(
                url=url,
                markdown='',
                success=False,
                error=str(e)
            )


class Crawl4AIFetcher(WebFetcher):
    '''
    Fetcher using Crawl4AI for JavaScript-heavy sites.

    Requires: crawl4ai running (via docker or local install)
    Best for: Dynamic sites with JavaScript, sites that block scrapers
    '''

    def __init__(self, base_url: str = 'http://localhost:11235'):
        '''
        Initialize the Crawl4AI fetcher.

        Args:
            base_url: Base URL of the Crawl4AI service
        '''
        self.base_url = base_url.rstrip('/')

    async def fetch(self, url: str) -> FetchResult:
        '''
        Fetch URL using Crawl4AI service.

        The Crawl4AI service should be running (via docker):
        docker run -p 11235:11235 unclecode/crawl4ai:basic
        '''
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Crawl4AI API endpoint
                response = await client.post(
                    f'{self.base_url}/crawl',
                    json={
                        'urls': [url],
                        'word_count_threshold': 10,  # Filter out very short text
                        'only_text': False,  # Get markdown
                        'bypass_cache': False
                    }
                )
                response.raise_for_status()
                result = response.json()

                # Extract markdown from response
                if result.get('success') and result.get('results'):
                    page_result = result['results'][0]

                    # Extract markdown - handle different possible structures
                    markdown_data = page_result.get('markdown', '')

                    # If markdown is a dict, try to extract the actual content
                    if isinstance(markdown_data, dict):
                        logger.debug('markdown_is_dict', url=url, keys=list(markdown_data.keys()))
                        # Try common keys for markdown content
                        markdown = (markdown_data.get('raw_markdown') or
                                   markdown_data.get('markdown') or
                                   markdown_data.get('content') or
                                   markdown_data.get('text') or '')
                        if not markdown:
                            logger.warning('no_markdown_extracted_from_dict', url=url, available_keys=list(markdown_data.keys()))
                    elif isinstance(markdown_data, str):
                        markdown = markdown_data
                    else:
                        # Fallback: convert to string
                        logger.warning('unexpected_markdown_type', url=url, type=type(markdown_data).__name__)
                        markdown = str(markdown_data) if markdown_data else ''

                    title = page_result.get('title')

                    return FetchResult(
                        url=url,
                        markdown=markdown,
                        title=title,
                        success=True
                    )
                else:
                    error = result.get('error', 'Unknown error')
                    return FetchResult(
                        url=url,
                        markdown='',
                        success=False,
                        error=error
                    )

        except Exception as e:
            return FetchResult(
                url=url,
                markdown='',
                success=False,
                error=f'Crawl4AI fetch failed: {str(e)}'
            )


class FallbackFetcher(WebFetcher):
    '''
    Fetcher that tries multiple fetchers in sequence.

    Tries simple HTTP first, falls back to Crawl4AI if it fails.
    '''

    def __init__(self, primary: WebFetcher = None, fallback: WebFetcher = None):
        '''
        Initialize the fallback fetcher.

        Args:
            primary: Primary fetcher to try first (defaults to SimpleHttpFetcher)
            fallback: Fallback fetcher if primary fails (defaults to Crawl4AIFetcher)
        '''
        self.primary = primary or SimpleHttpFetcher()
        self.fallback = fallback or Crawl4AIFetcher()

    async def fetch(self, url: str) -> FetchResult:
        '''Try primary fetcher first, fall back to secondary if it fails.'''
        result = await self.primary.fetch(url)

        if result.success and result.markdown.strip():
            return result

        # Primary failed or returned empty content, try fallback
        fallback_result = await self.fallback.fetch(url)

        # If fallback succeeds, return it
        if fallback_result.success:
            return fallback_result

        # Both failed, return the primary result with its error
        return result


def create_fetcher(fetcher_type: str = 'simple', **kwargs) -> WebFetcher:
    '''
    Factory function to create a web fetcher.

    Args:
        fetcher_type: Type of fetcher ('simple', 'crawl4ai', 'fallback')
        **kwargs: Additional arguments for the fetcher

    Returns:
        WebFetcher instance
    '''
    if fetcher_type == 'simple':
        return SimpleHttpFetcher(**kwargs)
    elif fetcher_type == 'crawl4ai':
        return Crawl4AIFetcher(**kwargs)
    elif fetcher_type == 'fallback':
        return FallbackFetcher(**kwargs)
    else:
        raise ValueError(f'Unknown fetcher type: {fetcher_type}')
