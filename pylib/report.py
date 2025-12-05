'''
Report generator for web scout.

Creates formatted reports from action results.
'''

from pathlib import Path
from datetime import datetime
from collections import defaultdict

from ooriscout.parser import LinkEntry
from ooriscout.actions import ActionResult
from ooriscout.fetcher import FetchResult


class ReportGenerator:
    '''
    Generates formatted reports from web scout results.
    '''

    def __init__(self, output_file: Path = None):
        '''
        Initialize the report generator.

        Args:
            output_file: Path to output report file (optional, defaults to stdout)
        '''
        self.output_file = Path(output_file) if output_file else None

    def generate_report(self,
                       entries: list[LinkEntry],
                       fetch_results: dict[str, FetchResult],
                       action_results: dict[str, list[ActionResult]]) -> str:
        '''
        Generate a formatted report.

        Args:
            entries: List of LinkEntry objects
            fetch_results: Dictionary mapping URLs to FetchResult objects
            action_results: Dictionary mapping action names to lists of ActionResult objects

        Returns:
            Report as a string
        '''
        report_lines = []

        # Header
        report_lines.append('=' * 80)
        report_lines.append('WEB SCOUT REPORT')
        report_lines.append('=' * 80)
        report_lines.append(f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")}')
        report_lines.append('')

        # Summary statistics
        report_lines.extend(self._generate_summary(entries, fetch_results, action_results))
        report_lines.append('')

        # Action results sections
        if 'random-remind' in action_results:
            report_lines.extend(self._generate_random_remind_section(action_results['random-remind']))
            report_lines.append('')

        if 'flag-update' in action_results:
            report_lines.extend(self._generate_flag_update_section(action_results['flag-update']))
            report_lines.append('')

        # Errors section (if any)
        error_results = self._collect_errors(action_results)
        if error_results:
            report_lines.extend(self._generate_errors_section(error_results))
            report_lines.append('')

        # Footer
        report_lines.append('=' * 80)
        report_lines.append('END OF REPORT')
        report_lines.append('=' * 80)

        report = '\n'.join(report_lines)

        # Write to file if specified
        if self.output_file:
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(report)

        return report

    def _generate_summary(self,
                         entries: list[LinkEntry],
                         fetch_results: dict[str, FetchResult],
                         action_results: dict[str, list[ActionResult]]) -> list[str]:
        '''Generate summary statistics section.'''
        lines = ['SUMMARY', '-' * 80]

        # Count entries
        lines.append(f'Total links processed: {len(entries)}')

        # Count by type
        type_counts = defaultdict(int)
        for entry in entries:
            type_counts[entry.type] += 1
        lines.append(f'  - Webpages: {type_counts.get("webpage", 0)}')
        if type_counts.get('rss-feed', 0) > 0:
            lines.append(f'  - RSS Feeds: {type_counts["rss-feed"]}')

        # Count fetch successes/failures
        success_count = sum(1 for r in fetch_results.values() if r.success)
        failure_count = len(fetch_results) - success_count
        lines.append('Fetch results:')
        lines.append(f'  - Successful: {success_count}')
        if failure_count > 0:
            lines.append(f'  - Failed: {failure_count}')

        # Count actions
        action_counts = defaultdict(int)
        for entry in entries:
            action_counts[entry.action] += 1

        lines.append('Actions:')
        for action, count in sorted(action_counts.items()):
            lines.append(f'  - {action}: {count}')

        # Tag cloud
        tag_counts = defaultdict(int)
        for entry in entries:
            for tag in entry.tags:
                tag_counts[tag] += 1

        if tag_counts:
            lines.append('Tags:')
            # Sort by count descending, then alphabetically
            sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
            for tag, count in sorted_tags[:10]:  # Top 10 tags
                lines.append(f'  - {tag}: {count}')

        return lines

    def _generate_random_remind_section(self, results: list[ActionResult]) -> list[str]:
        '''Generate the random-remind section.'''
        lines = ['RANDOM REMINDERS', '-' * 80]

        # Filter to successful results with summaries
        remind_results = [r for r in results if r.status == 'success' and r.summary]

        if not remind_results:
            lines.append('No reminders generated.')
            return lines

        lines.append(f'Selected {len(remind_results)} page(s) for your review:')
        lines.append('')

        for i, result in enumerate(remind_results, 1):
            entry = result.entry
            lines.append(f'{i}. {entry.url}')

            if entry.title:
                lines.append(f'   Title: {entry.title}')

            if entry.tags:
                lines.append(f'   Tags: {", ".join(entry.tags)}')

            if entry.key_quote:
                lines.append(f'   Key Quote: "{entry.key_quote}"')

            lines.append(f'   Reminder: {result.summary}')
            lines.append('')

        return lines

    def _generate_flag_update_section(self, results: list[ActionResult]) -> list[str]:
        '''Generate the flag-update section.'''
        lines = ['UPDATE FLAGS', '-' * 80]

        # Separate into categories
        substantive_updates = [r for r in results if r.status == 'success' and r.summary]
        first_observations = [r for r in results
                             if r.status == 'success' and 'First observation' in (r.message or '')]
        no_changes = [r for r in results
                     if r.status == 'success' and 'No changes' in (r.message or '')]

        # Report substantive updates
        if substantive_updates:
            lines.append('⚠️  SUBSTANTIVE UPDATES DETECTED:')
            lines.append('')
            for result in substantive_updates:
                entry = result.entry
                lines.append(f'• {entry.url}')
                if entry.title:
                    lines.append(f'  Title: {entry.title}')
                lines.append(f'  Changes: {result.summary}')
                lines.append('')
        else:
            lines.append('No substantive updates detected.')
            lines.append('')

        # Report first observations
        if first_observations:
            lines.append('First-time observations (baseline established):')
            for result in first_observations:
                lines.append(f'  • {result.entry.url}')
            lines.append('')

        # Report no changes
        if no_changes:
            lines.append(f'Unchanged pages: {len(no_changes)}')
            lines.append('')

        return lines

    def _collect_errors(self, action_results: dict[str, list[ActionResult]]) -> list[ActionResult]:
        '''Collect all error results.'''
        errors = []
        for results_list in action_results.values():
            errors.extend([r for r in results_list if r.status == 'error'])
        return errors

    def _generate_errors_section(self, error_results: list[ActionResult]) -> list[str]:
        '''Generate the errors section.'''
        lines = ['ERRORS', '-' * 80]

        if not error_results:
            return []

        lines.append(f'Encountered {len(error_results)} error(s):')
        lines.append('')

        for i, result in enumerate(error_results, 1):
            entry = result.entry
            lines.append(f'{i}. {entry.url}')
            lines.append(f'   Action: {result.action}')
            lines.append(f'   Error: {result.message or "Unknown error"}')
            lines.append('')

        return lines


def generate_report(entries: list[LinkEntry],
                   fetch_results: dict[str, FetchResult],
                   action_results: dict[str, list[ActionResult]],
                   output_file: Path = None) -> str:
    '''
    Convenience function to generate a report.

    Args:
        entries: List of LinkEntry objects
        fetch_results: Dictionary mapping URLs to FetchResult objects
        action_results: Dictionary mapping action names to lists of ActionResult objects
        output_file: Optional path to write report to

    Returns:
        Report as a string
    '''
    generator = ReportGenerator(output_file)
    return generator.generate_report(entries, fetch_results, action_results)
