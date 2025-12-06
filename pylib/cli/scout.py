#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025-present Oori Data <info@oori.dev>
# SPDX-License-Identifier: Apache-2.0
# ooriscout.cli.scout
'''
Web Scout - A tool for monitoring and summarizing web content.

Processes a links file, fetches web content, performs actions (random-remind,
flag-update), and generates reports with Onya knowledge graphs.

Usage:

webscout --links-file=demo/links.md --output-dir=output --llm-url=http://localhost:8000

Other option examples include:

--llm-model=llama-3.2-3b-instruct
--fetcher=fallback
--random-remind-count=3
--focus-tags=ai,tech

See README.md for more information.
'''

import asyncio
import fire
import structlog

from ooriscout.main import run_scout


# Setup logging
logger = structlog.get_logger()


def scout(links_file: str,
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
    asyncio.run(_async_scout(
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


async def _async_scout(links_file: str,
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
    '''Async implementation of scout command - thin wrapper around library function.'''
    from pathlib import Path
    
    # Setup paths
    output_path = Path(output_dir)
    report_file = output_path / 'report.txt'
    onya_file = output_path / 'web_scout.onya'

    try:
        # Call the core library function
        results = await run_scout(
            links_input=links_file,
            output_dir=output_dir,
            llm_url=llm_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            fetcher=fetcher,
            crawl4ai_url=crawl4ai_url,
            random_remind_count=random_remind_count,
            focus_tags=focus_tags,
            exclude_tags=exclude_tags,
            report_output=report_file,
            onya_output=onya_file,
            logger=logger,
            verbose=verbose
        )

        # Handle empty results
        if not results['entries']:
            print('No entries to process. Check your links file and tag filters.')
            return

        # Print CLI-friendly output
        success_count = sum(1 for r in results['fetch_results'].values() if r.success)
        print(f'Fetched {success_count}/{len(results["entries"])} pages successfully.')
        print('Processing actions...')
        
        for action, action_results in results['action_results'].items():
            count = len(action_results)
            print(f'  Processed {count} {action} action(s)')

        print('Generating Onya knowledge graph...')
        onya_path = results['onya_path']
        if isinstance(onya_path, Path):
            print(f'Onya graph saved to: {onya_path}')
        else:
            print('Onya graph written to provided output.')

        print('Generating report...')
        print(f'Report saved to: {report_file}')
        print()
        print('=' * 80)
        print(results['report'])

    except ValueError as e:
        # Handle validation errors (e.g., missing LLM URL)
        logger.error('scout_error', error=str(e))
        print(f'Error: {e}')
        return


def main():
    '''Main entry point.'''
    fire.Fire(scout)


if __name__ == '__main__':
    main()
