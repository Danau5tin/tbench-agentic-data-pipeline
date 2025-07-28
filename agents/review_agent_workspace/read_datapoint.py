#!/usr/bin/env python3
"""
Read a datapoint from CSV and format it as markdown.

This tool simplifies reading datapoints for review by extracting all components
from the CSV and formatting them into a readable markdown document.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime


def read_datapoint(csv_path: str, task_id: str) -> dict:
    """Read a specific datapoint from CSV by task_id."""
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['task_id'] == task_id:
                return row
    raise ValueError(f"Task ID '{task_id}' not found in {csv_path}")


def format_datapoint_markdown(datapoint: dict) -> str:
    """Format a datapoint dictionary as markdown."""
    md_lines = []
    
    # Header
    md_lines.append(f"# Datapoint: {datapoint['task_id']}")
    md_lines.append("")
    
    # Status section
    md_lines.append("## Status")
    md_lines.append(f"- Task ID: {datapoint['task_id']}")
    md_lines.append(f"- Difficulty: {datapoint.get('difficulty', 'Not specified')}")
    if 'created_at' in datapoint:
        md_lines.append(f"- Created: {datapoint['created_at']}")
    if 'updated_at' in datapoint:
        md_lines.append(f"- Updated: {datapoint['updated_at']}")
    md_lines.append("")
    
    # Prompt
    md_lines.append("## Prompt")
    md_lines.append(datapoint.get('prompt', 'No prompt provided'))
    md_lines.append("")
    
    # Dockerfile
    md_lines.append("## Dockerfile")
    md_lines.append("```dockerfile")
    md_lines.append(datapoint.get('dockerfile', 'No dockerfile provided'))
    md_lines.append("```")
    md_lines.append("")
    
    # Test Functions
    md_lines.append("## Test Functions")
    md_lines.append("```python")
    md_lines.append(datapoint.get('test_functions', 'No tests provided'))
    md_lines.append("```")
    md_lines.append("")
    
    # Test Weights
    md_lines.append("## Test Weights")
    if 'test_weights' in datapoint and datapoint['test_weights']:
        try:
            weights = json.loads(datapoint['test_weights'])
            for test_name, weight in weights.items():
                md_lines.append(f"- {test_name}: {weight}")
        except json.JSONDecodeError:
            md_lines.append(datapoint['test_weights'])
    else:
        md_lines.append("No weights provided")
    md_lines.append("")
    
    # Additional Files
    if 'additional_files' in datapoint and datapoint['additional_files']:
        md_lines.append("## Additional Files")
        try:
            files = json.loads(datapoint['additional_files'])
            for filename, content in files.items():
                md_lines.append(f"### {filename}")
                # Determine if we need code block based on file extension
                ext = Path(filename).suffix.lower()
                if ext in ['.py', '.r', '.R', '.js', '.sh', '.dockerfile']:
                    lang = {
                        '.py': 'python',
                        '.r': 'r', '.R': 'r',
                        '.js': 'javascript',
                        '.sh': 'bash',
                        '.dockerfile': 'dockerfile'
                    }.get(ext, '')
                    md_lines.append(f"```{lang}")
                elif ext in ['.json', '.yaml', '.yml', '.xml', '.html', '.css']:
                    lang = ext[1:]  # Remove the dot
                    md_lines.append(f"```{lang}")
                else:
                    md_lines.append("```")
                
                # Truncate very long files for display
                if len(content) > 1000:
                    md_lines.append(content[:1000])
                    md_lines.append(f"... [Truncated - {len(content)} total characters]")
                else:
                    md_lines.append(content)
                md_lines.append("```")
                md_lines.append("")
        except json.JSONDecodeError:
            md_lines.append("Error parsing additional files")
            md_lines.append("")
    
    # Validation results if present
    if 'validation_results' in datapoint and datapoint['validation_results']:
        md_lines.append("## Validation Results")
        try:
            results = json.loads(datapoint['validation_results'])
            md_lines.append(f"- Valid: {results.get('valid', 'Unknown')}")
            if 'errors' in results and results['errors']:
                md_lines.append("- Errors:")
                for error in results['errors']:
                    md_lines.append(f"  - {error}")
        except json.JSONDecodeError:
            md_lines.append(datapoint['validation_results'])
        md_lines.append("")
    
    return '\n'.join(md_lines)


def main():
    parser = argparse.ArgumentParser(
        description='Read a datapoint from CSV and format as markdown'
    )
    parser.add_argument(
        '--csv-path',
        required=True,
        help='Path to the CSV file containing datapoints'
    )
    parser.add_argument(
        '--task-id',
        required=True,
        help='Task ID of the datapoint to read'
    )
    parser.add_argument(
        '--output',
        help='Output file path (optional, defaults to stdout)'
    )
    
    args = parser.parse_args()
    
    try:
        # Read the datapoint
        datapoint = read_datapoint(args.csv_path, args.task_id)
        
        # Format as markdown
        markdown = format_datapoint_markdown(datapoint)
        
        # Output
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(markdown)
            print(f"Datapoint written to {args.output}")
        else:
            print(markdown)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()