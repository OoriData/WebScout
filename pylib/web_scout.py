#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-present Oori Data <info@oori.dev>
# SPDX-License-Identifier: Apache-2.0
# demo/web_scout/web_scout.py
'''
Web Scout - A tool for monitoring and summarizing web content.

Processes a links file, fetches web content, performs actions (random-remind,
flag-update), and generates reports with Onya knowledge graphs.

Usage:
    python web_scout.py scout --links-file=links.md --output-dir=output --llm-url=http://localhost:8000

    # With specific options
    python web_scout.py scout \\
        --links-file=links.md \\
        --output-dir=output \\
        --llm-url=http://localhost:8000 \\
        --llm-model=gpt-3.5-turbo \\
        --fetcher=simple \\
        --random-remind-count=3 \\
        --focus-tags=ai,tech

See README.md for more information.
'''

import asyncio
import os
from pathlib import Path
import fire
import structlog

from ogbujipt.llm.wrapper import openai_chat_api

from parser import parse_links_file, filter_entries_by_tags
from fetcher import create_fetcher, FetchResult
from actions import ActionProcessor
from onya_builder import build_onya_graph
from report import generate_report


# Setup logging
logger = structlog.get_logger()


class WebScout:
    '''
    Web Scout CLI application.
    '''

    def scout(self,
             links_file: str,
             output_dir: str = './web_scout_output',
             llm_url: str = None,
             llm_model: str = 'gpt-3.5-turbo',
             llm_api_key: str = None,
             fetcher: str = 'simple',
             crawl4ai_url: str = 'http://localhost:11235',
             random_remind_count: int = 3,
             focus_tags: str = None,
             exclude_tags: str = None,
             verbose: bool = False):
        '''
        Run web scout on a links file.

        Args:
            links_file: Path to the links.md file to process
            output_dir: Directory for output files (report, onya graph, cache)
            llm_url: URL of OpenAI-compatible LLM endpoint (e.g., http://localhost:8000)
                    If not provided, checks OPENAI_API_BASE env var
            llm_model: Model name to use (default: gpt-3.5-turbo)
            llm_api_key: API key for LLM (or set OPENAI_API_KEY env var)
            fetcher: Web fetcher to use ('simple', 'crawl4ai', 'fallback')
            crawl4ai_url: URL of Crawl4AI service if using crawl4ai fetcher
            random_remind_count: Number of pages to randomly select for reminders
            focus_tags: Comma-separated tags to focus on (filter to these tags)
            exclude_tags: Comma-separated tags to exclude
            verbose: Enable verbose logging
        '''
        asyncio.run(self._async_scout(
            links_file=links_file,
            output_dir=output_dir,
            llm_url=llm_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            fetcher=fetcher,
            crawl4ai_url=crawl4ai_url,
            random_remind_count=random_remind_count,
            focus_tags=focus_tags,
            exclude_tags=exclude_tags,
            verbose=verbose
        ))

    async def _async_scout(self,
                          links_file: str,
                          output_dir: str,
                          llm_url: str,
                          llm_model: str,
                          llm_api_key: str,
                          fetcher: str,
                          crawl4ai_url: str,
                          random_remind_count: int,
                          focus_tags: str,
                          exclude_tags: str,
                          verbose: bool):
        '''Async implementation of scout command.'''

        # Setup paths
        links_path = Path(links_file)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        cache_dir = output_path / 'cache'
        cache_dir.mkdir(exist_ok=True)

        if verbose:
            logger.info('starting_web_scout',
                       links_file=str(links_path),
                       output_dir=str(output_path))

        # Parse links file
        logger.info('parsing_links_file', path=str(links_path))
        entries = parse_links_file(str(links_path))
        logger.info('parsed_links', count=len(entries))

        # Filter by tags if specified
        if focus_tags or exclude_tags:
            include_list = [t.strip() for t in focus_tags.split(',')] if focus_tags else None
            exclude_list = [t.strip() for t in exclude_tags.split(',')] if exclude_tags else None
            entries = filter_entries_by_tags(entries, include_list, exclude_list)
            logger.info('filtered_by_tags', count=len(entries))

        if not entries:
            logger.warning('no_entries_to_process')
            print('No entries to process. Check your links file and tag filters.')
            return

        # Setup LLM
        llm_url = llm_url or os.environ.get('OPENAI_API_BASE')
        llm_api_key = llm_api_key or os.environ.get('OPENAI_API_KEY')

        if not llm_url:
            logger.error('no_llm_url_provided')
            print('Error: LLM URL not provided. Set --llm-url or OPENAI_API_BASE env var.')
            return

        logger.info('initializing_llm', url=llm_url, model=llm_model)
        llm = openai_chat_api(
            model=llm_model,
            base_url=llm_url,
            api_key=llm_api_key
        )

        # Setup web fetcher
        logger.info('initializing_fetcher', type=fetcher)
        if fetcher == 'crawl4ai':
            web_fetcher = create_fetcher('crawl4ai', base_url=crawl4ai_url)
        elif fetcher == 'fallback':
            web_fetcher = create_fetcher('fallback')
        else:
            web_fetcher = create_fetcher('simple')

        # Fetch all links
        logger.info('fetching_links', count=len(entries))
        print(f'Fetching {len(entries)} links...')

        fetch_results = {}
        entries_with_results = []

        for i, entry in enumerate(entries, 1):
            if verbose:
                print(f'  [{i}/{len(entries)}] Fetching: {entry.url}')
            else:
                print('.', end='', flush=True)

            result = await web_fetcher.fetch(entry.url)
            fetch_results[entry.url] = result
            entries_with_results.append((entry, result))

            if not verbose:
                if i % 50 == 0:
                    print(f' {i}', flush=True)

        if not verbose:
            print()  # Newline after progress dots

        # Count successes
        success_count = sum(1 for r in fetch_results.values() if r.success)
        logger.info('fetch_complete', success=success_count, failed=len(entries) - success_count)
        print(f'Fetched {success_count}/{len(entries)} pages successfully.')

        # Process actions
        logger.info('processing_actions')
        print('Processing actions...')

        action_processor = ActionProcessor(
            llm_wrapper=llm,
            cache_dir=cache_dir,
            random_remind_count=random_remind_count
        )

        action_results = await action_processor.process_all(entries_with_results)

        # Count results
        for action, results in action_results.items():
            count = len(results)
            logger.info('action_processed', action=action, count=count)

        # Generate Onya graph
        logger.info('generating_onya_graph')
        print('Generating Onya knowledge graph...')

        onya_file = output_path / 'web_scout.onya'
        await build_onya_graph(
            entries_with_results=entries_with_results,
            output_file=onya_file,
            llm_wrapper=llm
        )
        logger.info('onya_graph_created', path=str(onya_file))
        print(f'Onya graph saved to: {onya_file}')

        # Generate report
        logger.info('generating_report')
        print('Generating report...')

        report_file = output_path / 'report.txt'
        report = generate_report(
            entries=entries,
            fetch_results=fetch_results,
            action_results=action_results,
            output_file=report_file
        )

        logger.info('report_created', path=str(report_file))
        print(f'Report saved to: {report_file}')
        print()
        print('=' * 80)
        print(report)

        logger.info('web_scout_complete')


def main():
    '''Main entry point.'''
    fire.Fire(WebScout)


if __name__ == '__main__':
    main()
