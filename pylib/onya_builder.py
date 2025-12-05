'''
Onya knowledge graph builder for web scout.

Creates .onya files representing the links and their content.
'''

from pathlib import Path
from datetime import datetime
import re

from ogbujipt.llm.wrapper import prompt_to_chat

from ooriscout.parser import LinkEntry
from ooriscout.fetcher import FetchResult


def sanitize_node_id(url: str) -> str:
    '''
    Create a valid node ID from a URL.

    Args:
        url: URL to convert

    Returns:
        Sanitized ID suitable for use as an Onya node ID
    '''
    # Remove protocol
    node_id = re.sub(r'^https?://', '', url)
    # Replace special chars with underscores
    node_id = re.sub(r'[^a-zA-Z0-9_-]', '_', node_id)
    # Remove trailing underscores
    node_id = node_id.strip('_')
    # Limit length
    if len(node_id) > 80:
        node_id = node_id[:80]
    return node_id


def escape_onya_value(value: str) -> str:
    '''
    Escape a value for use in Onya format.

    Args:
        value: Value to escape

    Returns:
        Escaped value
    '''
    # Replace newlines with spaces, collapse multiple spaces
    value = re.sub(r'\s+', ' ', value)
    # Trim
    value = value.strip()
    return value


class OnyaGraphBuilder:
    '''
    Builder for creating Onya knowledge graphs from web scout data.
    '''

    def __init__(self, llm_wrapper=None):
        '''
        Initialize the Onya graph builder.

        Args:
            llm_wrapper: Optional LLM wrapper for generating richer descriptions
        '''
        self.llm = llm_wrapper

    async def build_graph(self,
                         entries_with_results: list[tuple[LinkEntry, FetchResult]],
                         output_file: Path,
                         base_iri: str = 'http://webscout.example.org/pages/') -> Path:
        '''
        Build an Onya knowledge graph from link entries and their content.

        Args:
            entries_with_results: List of (LinkEntry, FetchResult) tuples
            output_file: Path to output .onya file
            base_iri: Base IRI for the nodes

        Returns:
            Path to the created .onya file
        '''
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Create document IRI from filename
        doc_iri = f'{base_iri.rstrip("/")}/doc/{output_file.stem}'

        with open(output_file, 'w', encoding='utf-8') as f:
            # Write document header
            f.write('# @docheader\n')
            f.write(f'* @document: {doc_iri}\n')
            f.write(f'* @base: {base_iri}\n')
            f.write(f'* @created: {datetime.utcnow().isoformat()}\n')
            f.write('\n')

            # Write nodes for each entry
            for entry, fetch_result in entries_with_results:
                await self._write_node(f, entry, fetch_result)

        return output_file

    async def _write_node(self, f, entry: LinkEntry, fetch_result: FetchResult):
        '''Write a single node to the Onya file.'''
        # Create node ID from URL
        node_id = sanitize_node_id(entry.url)

        # Determine node type based on entry type
        if entry.type == 'rss-feed':
            node_type = 'RSSFeed'
        else:
            node_type = 'WebPage'

        # Write node header
        f.write(f'# {node_id} [{node_type}]\n')

        # Write URL (always present)
        f.write(f'* url: {entry.url}\n')

        # Write title
        title = entry.title or fetch_result.title or 'Untitled'
        f.write(f'* title: {escape_onya_value(title)}\n')

        # Write action
        f.write(f'* action: {entry.action}\n')

        # Write tags if present
        if entry.tags:
            f.write(f'* tags: {", ".join(entry.tags)}\n')

        # Write description if present
        if entry.description:
            f.write(f'* description: {escape_onya_value(entry.description)}\n')

        # Write key quote if present
        if entry.key_quote:
            f.write(f'* key_quote: {escape_onya_value(entry.key_quote)}\n')

        # Write fetch status
        if fetch_result.success:
            f.write('* fetch_status: success\n')

            # Generate and write summary if we have an LLM
            if self.llm and fetch_result.markdown.strip():
                try:
                    summary = await self._generate_summary(entry, fetch_result)
                    if summary:
                        f.write(f'* summary: {escape_onya_value(summary)}\n')
                except Exception as e:
                    f.write(f'* summary_error: {escape_onya_value(str(e))}\n')
        else:
            f.write('* fetch_status: failed\n')
            if fetch_result.error:
                f.write(f'* fetch_error: {escape_onya_value(fetch_result.error)}\n')

        # Write custom fields if present
        for key, value in entry.custom_fields.items():
            safe_key = key.replace('-', '_')  # Convert hyphens to underscores
            f.write(f'* {safe_key}: {escape_onya_value(value)}\n')

        f.write('\n')

    async def _generate_summary(self, entry: LinkEntry, fetch_result: FetchResult) -> str | None:
        '''
        Generate a concise summary of the page content using LLM.

        Args:
            entry: LinkEntry with metadata
            fetch_result: FetchResult with page content

        Returns:
            Summary string or None if generation fails
        '''
        if not self.llm or not fetch_result.markdown.strip():
            return None

        try:
            # Truncate content for LLM (first 2500 chars)
            content = fetch_result.markdown[:2500]

            prompt = f'''\
Analyze this web page and create a concise 1-2 sentence summary capturing its main topic and purpose.

URL: {entry.url}
Title: {fetch_result.title or entry.title or 'Untitled'}

Content:
{content}

Provide only the summary, no preamble.'''

            messages = prompt_to_chat(prompt)
            response = await self.llm(messages, max_tokens=150, temperature=0.5)

            summary = response.first_choice_text.strip()
            return summary

        except Exception:
            return None


async def build_onya_graph(entries_with_results: list[tuple[LinkEntry, FetchResult]],
                          output_file: Path,
                          llm_wrapper=None) -> Path:
    '''
    Convenience function to build an Onya graph.

    Args:
        entries_with_results: List of (LinkEntry, FetchResult) tuples
        output_file: Path to output .onya file
        llm_wrapper: Optional LLM wrapper for richer descriptions

    Returns:
        Path to the created .onya file
    '''
    builder = OnyaGraphBuilder(llm_wrapper)
    return await builder.build_graph(entries_with_results, output_file)
