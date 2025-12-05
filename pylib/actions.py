'''
Action handlers for web scout.

Implements different actions that can be taken on links:
- random-remind: Randomly select pages and generate summaries
- flag-update: Track content changes and flag updates
'''

import random
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass  # , asdict
from datetime import datetime

import wordloom
from ogbujipt.llm.wrapper import prompt_to_chat  # , openai_chat_api

from ooriscout.parser import LinkEntry
from ooriscout.fetcher import FetchResult


def _format_llm_error(exception: Exception, action_context: str = '') -> str:
    '''
    Format LLM API errors with specific error types.

    Args:
        exception: The exception that was raised
        action_context: Context about what action was being performed

    Returns:
        Formatted error message with specific error type
    '''
    error_str = str(exception)
    error_type = type(exception).__name__

    # Check for httpx exceptions (commonly used by ogbujipt)
    try:
        import httpx
        if isinstance(exception, httpx.ConnectError):
            return f'LLM connection failed: Cannot reach LLM server. Check if the server is running and the URL is correct.'
        elif isinstance(exception, httpx.ConnectTimeout):
            return f'LLM connection timeout: Could not establish connection to LLM server within timeout period.'
        elif isinstance(exception, httpx.TimeoutException):
            return f'LLM request timeout: Request to LLM server timed out. The server may be overloaded or slow.'
        elif isinstance(exception, httpx.HTTPStatusError):
            status_code = exception.response.status_code if hasattr(exception, 'response') else None
            if status_code == 401:
                return f'LLM authentication error (401): Invalid or missing API key. Check your API credentials.'
            elif status_code == 403:
                return f'LLM authorization error (403): Access forbidden. Check API key permissions.'
            elif status_code == 404:
                return f'LLM endpoint not found (404): The model or endpoint does not exist. Check model name and API URL.'
            elif status_code == 429:
                return f'LLM rate limit exceeded (429): Too many requests. Please wait before retrying.'
            elif status_code == 500:
                return f'LLM server error (500): Internal server error on LLM provider side.'
            elif status_code == 502:
                return f'LLM bad gateway (502): LLM provider gateway error. The service may be temporarily unavailable.'
            elif status_code == 503:
                return f'LLM service unavailable (503): LLM service is temporarily unavailable. Try again later.'
            elif status_code == 504:
                return f'LLM gateway timeout (504): LLM provider gateway timed out.'
            elif status_code:
                return f'LLM HTTP error ({status_code}): {error_str}'
            else:
                return f'LLM HTTP error: {error_str}'
        elif isinstance(exception, httpx.RequestError):
            return f'LLM request error: {error_str}'
    except ImportError:
        # httpx not available, fall through to generic handling
        pass

    # Check for common error patterns in error messages
    error_lower = error_str.lower()
    
    if 'connection' in error_lower or 'connect' in error_lower:
        if 'refused' in error_lower or 'cannot' in error_lower or "can't" in error_lower:
            return f'LLM connection refused: Cannot reach LLM server. Check if the server is running and the URL is correct.'
        elif 'timeout' in error_lower:
            return f'LLM connection timeout: Could not establish connection to LLM server within timeout period.'
        else:
            return f'LLM connection error: {error_str}'
    
    if 'timeout' in error_lower:
        return f'LLM timeout: Request to LLM server timed out. The server may be overloaded or slow.'
    
    if '401' in error_str or 'unauthorized' in error_lower:
        return f'LLM authentication error (401): Invalid or missing API key. Check your API credentials.'
    
    if '403' in error_str or 'forbidden' in error_lower:
        return f'LLM authorization error (403): Access forbidden. Check API key permissions.'
    
    if '404' in error_str or 'not found' in error_lower:
        return f'LLM endpoint not found (404): The model or endpoint does not exist. Check model name and API URL.'
    
    if '429' in error_str or 'rate limit' in error_lower:
        return f'LLM rate limit exceeded (429): Too many requests. Please wait before retrying.'
    
    if '500' in error_str or 'internal server error' in error_lower:
        return f'LLM server error (500): Internal server error on LLM provider side.'
    
    if '502' in error_str or 'bad gateway' in error_lower:
        return f'LLM bad gateway (502): LLM provider gateway error. The service may be temporarily unavailable.'
    
    if '503' in error_str or 'service unavailable' in error_lower:
        return f'LLM service unavailable (503): LLM service is temporarily unavailable. Try again later.'
    
    if '504' in error_str or 'gateway timeout' in error_lower:
        return f'LLM gateway timeout (504): LLM provider gateway timed out.'
    
    # Generic fallback
    return f'LLM API error ({error_type}): {error_str}'


def _get_resource_path() -> Path:
    '''Get the path to the resource directory at runtime.'''
    # Try using importlib.resources first (works for installed packages)
    try:
        import importlib.resources
        with importlib.resources.path('ooriscout.resource', 'language.toml') as p:
            return Path(p)
    except (ModuleNotFoundError, TypeError, ValueError):
        pass

    # Fallback: try relative to package directory (for installed packages)
    # In installed package, resources are at ooriscout/resource/language.toml
    try:
        import sys
        package_module = sys.modules.get('ooriscout')
        if package_module and hasattr(package_module, '__file__') and package_module.__file__:
            package_dir = Path(package_module.__file__).parent
            resource_path = package_dir / 'resource' / 'language.toml'
            if resource_path.exists():
                return resource_path
    except Exception:
        pass

    # Last resort: try relative to current file (for development)
    resource_path = Path(__file__).parent.parent.parent / 'resource' / 'language.toml'
    if resource_path.exists():
        return resource_path

    raise FileNotFoundError('Could not locate resource/language.toml')


def _load_prompts():
    '''Load prompts from Word Loom resource file.'''
    resource_path = _get_resource_path()
    with open(resource_path, 'rb') as f:
        loom = wordloom.load(f)
    return loom


# Load prompts at module level
_PROMPTS = _load_prompts()


@dataclass
class ActionResult:
    '''Result of processing an action on a link.'''
    entry: LinkEntry
    action: str
    summary: str | None = None
    status: str = 'success'  # success, skipped, error
    message: str | None = None
    timestamp: str = None

    def __post_init__(self):
        '''Set timestamp if not provided.'''
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class RandomRemindHandler:
    '''
    Handler for random-remind action.

    Randomly selects N pages and generates reminders with LLM summaries.
    '''

    def __init__(self, llm_wrapper, num_picks: int = 3):
        '''
        Initialize the random remind handler.

        Args:
            llm_wrapper: LLM wrapper for generating summaries
            num_picks: Number of pages to randomly select
        '''
        self.llm = llm_wrapper
        self.num_picks = num_picks

    async def process(self, entries: list[tuple[LinkEntry, FetchResult]]) -> list[ActionResult]:
        '''
        Process entries with random-remind action.

        Args:
            entries: List of (LinkEntry, FetchResult) tuples

        Returns:
            List of ActionResult objects
        '''
        results = []

        # Filter successful fetches
        valid_entries = [(e, f) for e, f in entries if f.success and f.markdown.strip()]

        if not valid_entries:
            return results

        # Randomly select entries
        num_to_pick = min(self.num_picks, len(valid_entries))
        selected = random.sample(valid_entries, num_to_pick)

        # Generate summaries for selected entries
        for entry, fetch_result in selected:
            try:
                # Truncate content if too long (keep first 3000 chars)
                content = fetch_result.markdown[:3000]

                # Build prompt with context from entry
                context_parts = [f'URL: {entry.url}']
                if entry.title:
                    context_parts.append(f'Title: {entry.title}')
                if entry.description:
                    context_parts.append(f'Description: {entry.description}')
                if entry.key_quote:
                    context_parts.append(f'Key Quote: {entry.key_quote}')
                if entry.tags:
                    context_parts.append(f'Tags: {", ".join(entry.tags)}')

                context = '\n'.join(context_parts)

                # Load prompt template from Word Loom
                prompt_template = _PROMPTS['random-remind-prompt']
                prompt = str(prompt_template).format(context=context, content=content)

                messages = prompt_to_chat(prompt)
                response = await self.llm(messages, max_tokens=200, temperature=0.7)

                summary = response.first_choice_text.strip()

                results.append(ActionResult(
                    entry=entry,
                    action='random-remind',
                    summary=summary,
                    status='success',
                    message=f'Reminder generated for: {entry.url}'
                ))

            except Exception as e:
                error_msg = _format_llm_error(e, 'summary generation')
                results.append(ActionResult(
                    entry=entry,
                    action='random-remind',
                    status='error',
                    message=f'Failed to generate summary: {error_msg}'
                ))

        return results


class FlagUpdateHandler:
    '''
    Handler for flag-update action.

    Tracks content changes and flags updates when substantive changes are detected.
    '''

    def __init__(self, llm_wrapper, cache_dir: Path):
        '''
        Initialize the flag update handler.

        Args:
            llm_wrapper: LLM wrapper for detecting substantive changes
            cache_dir: Directory for caching previous content
        '''
        self.llm = llm_wrapper
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, url: str) -> Path:
        '''Get cache file path for a URL.'''
        # Use hash of URL as filename to avoid filesystem issues
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f'{url_hash}.json'

    def _load_cached_content(self, url: str) -> dict | None:
        '''Load previously cached content for a URL.'''
        cache_path = self._get_cache_path(url)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _save_cached_content(self, url: str, markdown: str, timestamp: str = None):
        '''Save current content to cache.'''
        cache_path = self._get_cache_path(url)
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat()

        cache_data = {
            'url': url,
            'markdown': markdown,
            'timestamp': timestamp
        }

        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2)

    async def process(self, entries: list[tuple[LinkEntry, FetchResult]]) -> list[ActionResult]:
        '''
        Process entries with flag-update action.

        Args:
            entries: List of (LinkEntry, FetchResult) tuples

        Returns:
            List of ActionResult objects
        '''
        results = []

        for entry, fetch_result in entries:
            if not fetch_result.success or not fetch_result.markdown.strip():
                results.append(ActionResult(
                    entry=entry,
                    action='flag-update',
                    status='error',
                    message=f'Failed to fetch content: {fetch_result.error}'
                ))
                continue

            try:
                # Load cached content
                cached = self._load_cached_content(entry.url)

                if cached is None:
                    # First time seeing this URL, just cache it
                    self._save_cached_content(entry.url, fetch_result.markdown)
                    results.append(ActionResult(
                        entry=entry,
                        action='flag-update',
                        status='success',
                        message='First observation - content cached for future comparison'
                    ))
                    continue

                # Compare with cached content
                old_content = cached['markdown'][:2000]  # Truncate for LLM
                new_content = fetch_result.markdown[:2000]

                # Quick check: if content is identical, skip LLM
                if old_content == new_content:
                    results.append(ActionResult(
                        entry=entry,
                        action='flag-update',
                        status='success',
                        message='No changes detected'
                    ))
                    continue

                # Load prompt template from Word Loom
                prompt_template = _PROMPTS['flag-update-prompt']
                prompt = str(prompt_template).format(
                    previous_timestamp=cached['timestamp'],
                    old_content=old_content,
                    new_content=new_content
                )

                messages = prompt_to_chat(prompt)
                response = await self.llm(messages, max_tokens=250, temperature=0.5)

                analysis = response.first_choice_text.strip()

                if analysis.upper().startswith('SUBSTANTIVE'):
                    # Extract summary (everything after the first line/dash)
                    summary = analysis.split('-', 1)[1].strip() if '-' in analysis else analysis

                    # Update cache
                    self._save_cached_content(entry.url, fetch_result.markdown)

                    results.append(ActionResult(
                        entry=entry,
                        action='flag-update',
                        summary=summary,
                        status='success',
                        message=f'⚠️  Substantive update detected at {entry.url}'
                    ))
                else:
                    results.append(ActionResult(
                        entry=entry,
                        action='flag-update',
                        status='success',
                        message='Minor changes detected (not flagged)'
                    ))

            except Exception as e:
                error_msg = _format_llm_error(e, 'update detection')
                results.append(ActionResult(
                    entry=entry,
                    action='flag-update',
                    status='error',
                    message=f'Error processing update: {error_msg}'
                ))

        return results


class ActionProcessor:
    '''
    Main processor for handling all actions on link entries.
    '''

    def __init__(self, llm_wrapper, cache_dir: Path, random_remind_count: int = 3):
        '''
        Initialize the action processor.

        Args:
            llm_wrapper: LLM wrapper for generating content
            cache_dir: Directory for caching content
            random_remind_count: Number of random-remind entries to select
        '''
        self.random_remind_handler = RandomRemindHandler(llm_wrapper, random_remind_count)
        self.flag_update_handler = FlagUpdateHandler(llm_wrapper, cache_dir)

    async def process_all(self, entries_with_results: list[tuple[LinkEntry, FetchResult]]) \
        -> dict[str, list[ActionResult]]:
        '''
        Process all entries according to their actions.

        Args:
            entries_with_results: List of (LinkEntry, FetchResult) tuples

        Returns:
            Dictionary mapping action names to lists of ActionResult objects
        '''
        # Group entries by action
        by_action = {}
        for entry, result in entries_with_results:
            action = entry.action
            if action not in by_action:
                by_action[action] = []
            by_action[action].append((entry, result))

        # Process each action type
        all_results = {}

        if 'random-remind' in by_action:
            all_results['random-remind'] = await self.random_remind_handler.process(by_action['random-remind'])

        if 'flag-update' in by_action:
            all_results['flag-update'] = await self.flag_update_handler.process(by_action['flag-update'])

        return all_results
