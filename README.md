Web Scout demo

A tool that uses OgbujiPT to monitor and summarize web content. It processes a links file (e.g., `links.md`) based on configurable rules, fetching content from each URL and generating reports with LLM-powered summaries and insights.

# Features

- **Flexible link format**: Simple markdown-based format for managing monitored links
- **Multiple, selectable actions**:
  - `random-remind`: Randomly selects pages for periodic review with AI-generated reminders
  - `flag-update`: Tracks content changes and flags substantive updates
- **Pluggable web fetchers**: Protocol-based design supporting multiple web scraping backends
- **Knowledge Graphs**: Generates [Onya](https://github.com/OoriData/Onya) graphs from links and their content
- **Content caching**: Stores markdown versions for update tracking
- **Tag-based filtering**: Optional focus on specific content categories

# Links File Format

The links file uses a simple markdown list format, in which each top-level
list item is a target link and the sib-list items within are the fields that
govern how that link is processed.

```markdown
- https://example.com/
  - tags: tech | ai
  - action: random-remind
  - description: Optional description
  - key-quote: "Notable quote from the page"

- https://another-site.com/index.rss
  - type: rss-feed
  - action: flag-update
  - tags: news
```

## Supported Fields

- **URL** (required): The outer list item
- **type**: `webpage` (default) or `rss-feed`
- **title**: Override the page's title
- **action**: `random-remind` (default) or `flag-update`
- **tags**: Space or pipe-separated tags for filtering
- **description**: Custom description
- **key-quote**: Notable quote to highlight

# Installation

1. Install OgbujiPT with required dependencies:

```bash
uv pip install -U "ogbujipt[mega]"
```

or to avoid installing a few dependencies you may not need:

```bash
uv pip install -U ogbujipt cssutils selectolax fire
```

2. (Optional) For JavaScript-heavy sites, set up [Crawl4AI](https://github.com/unclecode/crawl4ai):

```bash
docker run -p 11235:11235 unclecode/crawl4ai:basic
```

Or you can be more detailed, e.g.

```bash
docker pull unclecode/crawl4ai:latest
docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest
```

The dashboard should be at http://localhost:11235/dashboard

# Usage

Basic usage with a local LLM endpoint:

```bash
python web_scout.py scout \
  --links-file=links.md \
  --output-dir=./output \
  --llm-url=http://localhost:8000 \
  --llm-model=llama-3.2-3b-instruct
```

Note: for this config you'll need to install a local LLM server, such as our sister project [Toolio](https://github.com/OoriData/Toolio). Or you can use the better-known [Ollama](https://ollama.com/) or [LM Studio](https://lmstudio.ai/).


## Command-Line Options

- `--links-file`: Path to the links file (required)
- `--output-dir`: Directory for output files (default: ./web_scout_output)
- `--llm-url`: OpenAI-compatible LLM endpoint URL (or set OPENAI_API_BASE env var)
- `--llm-model`: Model name (default: gpt-3.5-turbo)
- `--llm-api-key`: API key (or set OPENAI_API_KEY env var)
- `--fetcher`: Web fetcher to use: `simple`, `crawl4ai`, or `fallback` (default: simple)
- `--crawl4ai-url`: Crawl4AI service URL (default: http://localhost:11235)
- `--random-remind-count`: Number of pages to randomly select (default: 3)
- `--focus-tags`: Comma-separated tags to focus on
- `--exclude-tags`: Comma-separated tags to exclude
- `--verbose`: Enable verbose logging

## Examples

Focus on AI-related links only:

```bash
python web_scout.py scout \
  --links-file=links.md \
  --focus-tags=ai,tech \
  --output-dir=./output \
  --llm-url=http://localhost:8000
```

Use Crawl4AI for JavaScript-heavy sites:

```bash
python web_scout.py scout \
  --links-file=links.md \
  --fetcher=crawl4ai \
  --output-dir=./output \
  --llm-url=http://localhost:8000
```

Use fallback fetcher (tries simple first, falls back to Crawl4AI):

```bash
python web_scout.py scout \
  --links-file=links.md \
  --fetcher=fallback \
  --output-dir=./output \
  --llm-url=http://localhost:8000
```

# Output

Web Scout generates three main outputs in the specified output directory:

1. **report.txt**: Human-readable report with:
   - Summary statistics
   - Random reminders with AI-generated summaries
   - Update flags for changed content
   - Error reports

2. **web_scout.onya**: Onya knowledge graph containing:
   - Nodes for each monitored page
   - Metadata (tags, actions, status)
   - AI-generated summaries

3. **cache/**: Directory containing:
   - Cached markdown content for each page
   - Used for tracking changes in flag-update mode

# Architecture

## Web Fetcher Protocol

The tool uses a pluggable protocol for web fetching, making it easy to swap different backends:

- **SimpleHttpFetcher**: Uses httpx + OgbujiPT HTML processing (fast, works for most sites)
- **Crawl4AIFetcher**: Uses Crawl4AI for JavaScript-heavy sites (requires docker service)
- **FallbackFetcher**: Tries simple first, falls back to Crawl4AI on failure

New fetchers can be added by implementing the `WebFetcher` protocol.

## Actions

Actions are processed by dedicated handlers:

- **RandomRemindHandler**: Randomly selects entries and generates reminder summaries
- **FlagUpdateHandler**: Compares cached content with current content, uses LLM to detect substantive changes

# Testing

Run the included tests to verify basic functionality:

```bash
# Test the parser
python test_parser.py

# Test the web fetcher
python test_fetcher.py
```

# Notes

- The `simple` fetcher works well for most static HTML sites
- Use `crawl4ai` or `fallback` for sites requiring JavaScript execution
- The `flag-update` action builds up a cache over time - first run establishes baselines
- LLM costs scale with the number of links and content length
- Substantive changes are determined by LLM judgment, tuned to ignore minor formatting changes

Web Scout started out as an OgbujiPT demo. It uses `ogbujipt.llm.wrapper` for LLM interactions, `ogbujipt.text.html` for HTML processing, `ogbujipt.store.kgraph` concepts for Onya graphs, and standard OgbujiPT patterns such as async, httpx and structlog.
