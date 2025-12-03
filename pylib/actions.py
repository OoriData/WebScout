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
from dataclasses import dataclass, asdict
from datetime import datetime

from ogbujipt.llm.wrapper import openai_chat_api, prompt_to_chat

from parser import LinkEntry
from fetcher import FetchResult


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

                prompt = f'''Based on this web page content and context, create a concise reminder summary (2-3 sentences) about why this page might be of ongoing interest.

Context:
{context}

Page Content:
{content}

Generate a friendly reminder that captures the essence of why someone flagged this page for ongoing interest.'''

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
                results.append(ActionResult(
                    entry=entry,
                    action='random-remind',
                    status='error',
                    message=f'Failed to generate summary: {str(e)}'
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

                # Use LLM to determine if changes are substantive
                prompt = f'''Compare these two versions of a web page and determine if there are substantive changes.

Substantive changes include:
- New content, articles, or major updates
- Significant changes to existing content
- Important announcements or news

Non-substantive changes include:
- Minor wording tweaks
- Formatting changes
- Advertisements or navigation changes
- Timestamp updates

Previous version (from {cached['timestamp']}):
{old_content}

Current version:
{new_content}

Respond with:
1. "SUBSTANTIVE" or "MINOR" as the first word
2. If substantive, provide a brief summary (2-3 sentences) of the key changes

Example responses:
"SUBSTANTIVE - The site announced a new version 2.0 release with significant feature updates including..."
"MINOR - Only formatting and navigation changes detected."
'''

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
                results.append(ActionResult(
                    entry=entry,
                    action='flag-update',
                    status='error',
                    message=f'Error processing update: {str(e)}'
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

    async def process_all(self, entries_with_results: list[tuple[LinkEntry, FetchResult]]) -> dict[str, list[ActionResult]]:
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
