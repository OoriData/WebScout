'''
Core web scout engine for reusable library components.

Provides the main scout processing logic that can be invoked from CLI,
schedulers, or other components.
'''

import os
from pathlib import Path
from typing import TextIO, Union
import structlog

from ogbujipt.llm.wrapper import openai_chat_api

from ooriscout.parser import parse_links_file, filter_entries_by_tags
from ooriscout.fetcher import create_fetcher
from ooriscout.actions import ActionProcessor
from ooriscout.onya_builder import build_onya_graph
from ooriscout.report import generate_report


async def run_scout(
    links_input: Union[str, Path, TextIO],
    output_dir: Union[str, Path] = None,
    llm_url: str = None,
    llm_model: str = 'gpt-3.5-turbo',
    llm_api_key: str = None,
    fetcher: str = 'simple',
    crawl4ai_url: str = 'http://localhost:11235',
    random_remind_count: int = 3,
    focus_tags: str = None,
    exclude_tags: str = None,
    report_output: Union[str, Path, TextIO] = None,
    onya_output: Union[str, Path, TextIO] = None,
    cache_dir: Union[str, Path] = None,
    logger: structlog.BoundLogger = None,
    verbose: bool = False) -> dict:
    '''
    Run web scout processing on a links file.

    This is the core library function that performs all scout operations.
    It can be called from CLI, schedulers, or other components.

    Args:
        links_input: Path to links file (str/Path) or file-like object (TextIO)
        output_dir: Directory for output files (if report_output/onya_output not specified)
        llm_url: URL of OpenAI-compatible LLM endpoint
        llm_model: Model name to use
        llm_api_key: API key for LLM
        fetcher: Web fetcher to use ('simple', 'crawl4ai', 'fallback')
        crawl4ai_url: URL of Crawl4AI service if using crawl4ai fetcher
        random_remind_count: Number of pages to randomly select for reminders
        focus_tags: Comma-separated tags to focus on
        exclude_tags: Comma-separated tags to exclude
        report_output: Path (str/Path) or file-like object (TextIO) for report output.
                       If None, uses output_dir/report.txt
        onya_output: Path (str/Path) or file-like object (TextIO) for Onya graph output.
                     If None, uses output_dir/web_scout.onya
        cache_dir: Directory for caching content. If None, uses output_dir/cache
        logger: Configured structlog logger. If None, uses default structlog.get_logger()
        verbose: Enable verbose logging

    Returns:
        Dictionary with results:
        - entries: List of LinkEntry objects
        - fetch_results: Dict mapping URLs to FetchResult objects
        - action_results: Dict mapping action names to lists of ActionResult objects
        - report: Report string
        - onya_path: Path to created Onya file (if file path was used)
    '''
    # Setup logger
    if logger is None:
        logger = structlog.get_logger()

    # Setup paths and file handles
    links_file_handle = None
    links_path = None
    if isinstance(links_input, (str, Path)):
        links_path = Path(links_input)
    else:
        # Assume it's a file-like object
        links_file_handle = links_input

    # Determine output paths
    if output_dir is None:
        output_dir = Path('./web_scout_output')
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    if cache_dir is None:
        cache_dir = output_dir / 'cache'
    else:
        cache_dir = Path(cache_dir)

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Determine report output
    report_file_handle = None
    report_path = None
    if report_output is None:
        report_path = output_dir / 'report.txt'
    elif isinstance(report_output, (str, Path)):
        report_path = Path(report_output)
    else:
        # Assume it's a file-like object
        report_file_handle = report_output

    # Determine onya output
    onya_file_handle = None
    onya_path = None
    if onya_output is None:
        onya_path = output_dir / 'web_scout.onya'
    elif isinstance(onya_output, (str, Path)):
        onya_path = Path(onya_output)
    else:
        # Assume it's a file-like object
        onya_file_handle = onya_output

    if verbose:
        logger.info('starting_web_scout',
                   links_input=str(links_path) if links_path else 'file-like object',
                   output_dir=str(output_dir))

    # Parse links file
    logger.info('parsing_links_file', 
                path=str(links_path) if links_path else 'file-like object')
    
    if links_file_handle:
        entries = parse_links_file(links_file_handle)
    else:
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
        return {
            'entries': [],
            'fetch_results': {},
            'action_results': {},
            'report': 'No entries to process. Check your links file and tag filters.',
            'onya_path': None
        }

    # Setup LLM
    llm_url = llm_url or os.environ.get('OPENAI_API_BASE')
    llm_api_key = llm_api_key or os.environ.get('OPENAI_API_KEY')

    if not llm_url:
        logger.error('no_llm_url_provided')
        raise ValueError('LLM URL not provided. Set llm_url parameter or OPENAI_API_BASE env var.')

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

    fetch_results = {}
    entries_with_results = []

    for i, entry in enumerate(entries, 1):
        if verbose:
            logger.debug('fetching_entry', index=i, total=len(entries), url=entry.url)

        result = await web_fetcher.fetch(entry.url)
        fetch_results[entry.url] = result
        entries_with_results.append((entry, result))

    # Count successes
    success_count = sum(1 for r in fetch_results.values() if r.success)
    logger.info('fetch_complete', success=success_count, failed=len(entries) - success_count)

    # Process actions
    logger.info('processing_actions')

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

    if onya_file_handle:
        # Write to file-like object
        onya_result = await build_onya_graph(
            entries_with_results=entries_with_results,
            output_file=onya_file_handle,
            llm_wrapper=llm
        )
        onya_path = onya_result  # Could be file-like object
    else:
        onya_result = await build_onya_graph(
            entries_with_results=entries_with_results,
            output_file=onya_path,
            llm_wrapper=llm
        )
        onya_path = onya_result  # Should be Path
    
    logger.info('onya_graph_created', 
                path=str(onya_path) if isinstance(onya_path, Path) else 'file-like object')

    # Generate report
    logger.info('generating_report')

    if report_file_handle:
        # Write to file-like object
        report = generate_report(
            entries=entries,
            fetch_results=fetch_results,
            action_results=action_results,
            output_file=report_file_handle
        )
    else:
        report = generate_report(
            entries=entries,
            fetch_results=fetch_results,
            action_results=action_results,
            output_file=report_path
        )

    logger.info('report_created', 
                path=str(report_path) if report_path else 'file-like object')
    logger.info('web_scout_complete')

    return {
        'entries': entries,
        'fetch_results': fetch_results,
        'action_results': action_results,
        'report': report,
        'onya_path': onya_path
    }
