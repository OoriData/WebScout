#!/usr/bin/env python3
'''
Quick test of the fetcher functionality.
'''

import asyncio
from fetcher import SimpleHttpFetcher


async def test_fetcher():
    '''Test fetching a simple web page.'''
    print('Testing SimpleHttpFetcher...')

    fetcher = SimpleHttpFetcher()

    # Test with a simple page
    url = 'https://example.com'
    print(f'\nFetching: {url}')

    result = await fetcher.fetch(url)

    print(f'\nSuccess: {result.success}')
    if result.success:
        print(f'Title: {result.title}')
        print(f'Markdown length: {len(result.markdown)} characters')
        print(f'\nFirst 300 characters of markdown:')
        print('-' * 80)
        print(result.markdown[:300])
        print('-' * 80)
        print('\n✓ Fetcher test completed successfully!')
    else:
        print(f'Error: {result.error}')
        print('\n✗ Fetcher test failed!')


if __name__ == '__main__':
    asyncio.run(test_fetcher())
