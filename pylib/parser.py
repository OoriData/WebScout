'''
Parser for web scout links file format.

The format is:
- Outer list items are URLs
- First level indents are details, interpreted by keyword:
  - type: webpage (default) or rss-feed
  - title: override title
  - action: identifier for action to take (random-remind, flag-update, etc.)
  - tags: space/pipe separated tags
  - description: override description
  - key-quote: a notable quote from the page
'''

import re
from dataclasses import dataclass, field
from typing import TextIO
from pathlib import Path


@dataclass
class LinkEntry:
    '''Represents a single link entry with its metadata.'''
    url: str
    type: str = 'webpage'  # webpage, rss-feed, etc.
    title: str | None = None
    action: str = 'random-remind'  # Default action
    tags: list[str] = field(default_factory=list)
    description: str | None = None
    key_quote: str | None = None
    custom_fields: dict[str, str] = field(default_factory=dict)  # For extensibility

    def __post_init__(self):
        '''Normalize data after initialization.'''
        # Split tags if they're a string
        if isinstance(self.tags, str):
            # Split by pipe or whitespace
            self.tags = [tag.strip() for tag in re.split(r'[|\s]+', self.tags) if tag.strip()]


def parse_links_file(file_input: str | Path | TextIO) -> list[LinkEntry]:
    '''
    Parse a links file into structured LinkEntry objects.

    Args:
        file_input: Path to the links.md file (str/Path) or file-like object (TextIO)

    Returns:
        List of LinkEntry objects
    '''
    # Handle file-like objects vs file paths
    if hasattr(file_input, 'read'):
        # It's a file-like object
        lines = file_input.readlines()
        # Reset file pointer if possible (for re-reading)
        if hasattr(file_input, 'seek'):
            file_input.seek(0)
    else:
        # It's a file path
        with open(file_input, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    entries = []
    current_entry = None

    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Check indentation
        indent_level = len(line) - len(line.lstrip())
        content = line.strip()

        # Skip comments
        if content.startswith('#'):
            continue

        if indent_level == 0 and content.startswith('-'):
            # This is a URL line
            url = content[1:].strip()  # Remove leading '-' and whitespace
            current_entry = LinkEntry(url=url)
            entries.append(current_entry)

        elif indent_level > 0 and content.startswith('-') and current_entry:
            # This is a metadata line for the current entry
            # Format: "- key: value" or "- key: value with more text"
            metadata = content[1:].strip()  # Remove leading '-'

            # Split on first colon
            if ':' in metadata:
                key, value = metadata.split(':', 1)
                key = key.strip()
                value = value.strip()

                # Handle known fields
                if key == 'type':
                    current_entry.type = value
                elif key == 'title':
                    current_entry.title = value
                elif key == 'action':
                    current_entry.action = value
                elif key == 'tags':
                    current_entry.tags = [tag.strip() for tag in re.split(r'[|\s]+', value) if tag.strip()]
                elif key == 'description':
                    current_entry.description = value
                elif key == 'key-quote':
                    current_entry.key_quote = value
                else:
                    # Store unknown fields for extensibility
                    current_entry.custom_fields[key] = value

    return entries


def filter_entries_by_tags(entries: list[LinkEntry], include_tags: list[str] = None,
                           exclude_tags: list[str] = None) -> list[LinkEntry]:
    '''
    Filter link entries by tags.

    Args:
        entries: List of LinkEntry objects
        include_tags: If provided, only include entries with at least one of these tags
        exclude_tags: If provided, exclude entries with any of these tags

    Returns:
        Filtered list of LinkEntry objects
    '''
    filtered = entries

    if include_tags:
        filtered = [e for e in filtered if any(tag in e.tags for tag in include_tags)]

    if exclude_tags:
        filtered = [e for e in filtered if not any(tag in e.tags for tag in exclude_tags)]

    return filtered


def filter_entries_by_action(entries: list[LinkEntry], action: str) -> list[LinkEntry]:
    '''
    Filter link entries by action type.

    Args:
        entries: List of LinkEntry objects
        action: Action type to filter by

    Returns:
        Filtered list of LinkEntry objects
    '''
    return [e for e in entries if e.action == action]
