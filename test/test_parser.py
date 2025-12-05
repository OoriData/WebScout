#!/usr/bin/env python3
'''
Quick test of the parser functionality.
'''

from webscout.parser import parse_links_file, filter_entries_by_tags


def test_parser():
    '''Test parsing the links.md file.'''
    print('Testing parser...')

    # Parse the example links file
    entries = parse_links_file('links.md')

    print(f'\nParsed {len(entries)} entries:')
    print('=' * 80)

    for entry in entries:
        print(f'\nURL: {entry.url}')
        print(f'  Type: {entry.type}')
        print(f'  Action: {entry.action}')
        print(f'  Tags: {entry.tags}')
        if entry.title:
            print(f'  Title: {entry.title}')
        if entry.description:
            print(f'  Description: {entry.description}')
        if entry.key_quote:
            print(f'  Key Quote: {entry.key_quote[:80]}...')

    # Test filtering
    print('\n' + '=' * 80)
    print('Testing tag filtering:')

    ai_entries = filter_entries_by_tags(entries, include_tags=['ai'])
    print(f'\nEntries with "ai" tag: {len(ai_entries)}')
    for entry in ai_entries:
        print(f'  - {entry.url}')

    tool_entries = filter_entries_by_tags(entries, include_tags=['tool'])
    print(f'\nEntries with "tool" tag: {len(tool_entries)}')
    for entry in tool_entries:
        print(f'  - {entry.url}')

    # Test action filtering
    from webscout.parser import filter_entries_by_action

    remind_entries = filter_entries_by_action(entries, 'random-remind')
    print(f'\nEntries with "random-remind" action: {len(remind_entries)}')

    update_entries = filter_entries_by_action(entries, 'flag-update')
    print(f'\nEntries with "flag-update" action: {len(update_entries)}')

    print('\n✓ Parser test completed successfully!')


if __name__ == '__main__':
    test_parser()
