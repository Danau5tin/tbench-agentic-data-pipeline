#!/usr/bin/env python3
"""
patch_dp.py - Update specific columns of a datapoint in a CSV file

Usage:
    # Update a single column
    python patch_dp.py \
        --csv-path path/to/datapoints.csv \
        --task-id draft_001_a \
        --column prompt \
        --file drafts/draft_001_a/prompt_v2.md
    
    # Update multiple columns
    python patch_dp.py \
        --csv-path path/to/datapoints.csv \
        --task-id draft_001_a \
        --column tests \
        --file drafts/draft_001_a/tests_v2.py \
        --column weights \
        --file drafts/draft_001_a/weights_v2.json
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any


VALID_COLUMNS = ['prompt', 'dockerfile', 'test_functions', 'test_weights', 'difficulty']


def read_staging_data(staging_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read all data from CSV file."""
    if not staging_path.exists():
        raise FileNotFoundError(f"CSV file not found: {staging_path}")
    
    with open(staging_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    return rows, fieldnames


def find_task_row(rows: List[Dict[str, str]], task_id: str) -> int:
    """Find the row index for a given task ID."""
    for i, row in enumerate(rows):
        if row['task_id'] == task_id:
            return i
    raise ValueError(f"Task '{task_id}' not found in CSV")


def read_file_content(file_path: Path, column: str) -> str:
    """Read and validate file content for a column."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found for column '{column}': {file_path}")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError(f"File is empty for column '{column}': {file_path}")
            
        return content
    except Exception as e:
        raise RuntimeError(f"Error reading file for column '{column}': {e}")


def validate_column_content(column: str, content: str, file_path: Path = None) -> str:
    """Validate content based on column type."""
    if column == 'test_weights':
        # Validate weights JSON
        try:
            weights = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in weights: {e}")
        
        if not isinstance(weights, dict):
            raise ValueError("Weights must be a JSON object")
        
        if not weights:
            raise ValueError("Weights cannot be empty")
        
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:  # Allow small floating point errors
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        
        for test_name, weight in weights.items():
            if not test_name.startswith('test_'):
                raise ValueError(f"Test name must start with 'test_': {test_name}")
            if not isinstance(weight, (int, float)):
                raise ValueError(f"Weight must be numeric: {test_name}={weight}")
            if weight <= 0:
                raise ValueError(f"Weight must be positive: {test_name}={weight}")
        
        # Return as JSON string for CSV storage
        return json.dumps(weights)
    
    
    # For other columns, just return the content
    return content


def patch_datapoint(
    task_id: str,
    updates: List[Tuple[str, Path]],
    staging_path: Path
) -> None:
    """Update specific columns of a datapoint."""
    # Read current data
    rows, fieldnames = read_staging_data(staging_path)
    
    # Find the task row
    row_index = find_task_row(rows, task_id)
    
    # Process updates
    applied_updates = []
    for column, file_path in updates:
        # Normalize column name
        if column == 'tests':
            column = 'test_functions'
        elif column == 'weights':
            column = 'test_weights'
        
        if column == 'additional_files':
            raise ValueError("Column 'additional_files' is no longer supported. Use patch_additional_files.py instead.")
        
        if column not in VALID_COLUMNS:
            raise ValueError(f"Invalid column '{column}'. Valid columns: {', '.join(VALID_COLUMNS)}")
        
        # Read and validate content
        content = read_file_content(file_path, column)
        validated_content = validate_column_content(column, content, file_path)
        
        # Apply update
        rows[row_index][column] = validated_content
        applied_updates.append((column, len(validated_content)))
    
    # Update timestamp
    rows[row_index]['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    # If updating test_weights, validate against test_functions
    if 'test_weights' in [col for col, _ in updates]:
        weights = json.loads(rows[row_index]['test_weights'])
        tests = rows[row_index]['test_functions']
        
        for test_name in weights:
            if f"def {test_name}" not in tests:
                raise ValueError(f"Test function '{test_name}' not found in test_functions")
    
    # Write back to CSV using temporary file for safety
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=staging_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        # Replace original file
        os.replace(temp_path, staging_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    
    # Report success
    print(f"✓ Updated datapoint '{task_id}':")
    for column, size in applied_updates:
        print(f"  - {column}: {size} chars")


def main():
    parser = argparse.ArgumentParser(
        description="Update specific columns of a datapoint in a CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    # Update a single column
    python patch_dp.py \\
        --csv-path path/to/datapoints.csv \\
        --task-id draft_001_a \\
        --column prompt \\
        --file drafts/draft_001_a/prompt_v2.md
    
    # Update multiple columns
    python patch_dp.py \\
        --csv-path path/to/datapoints.csv \\
        --task-id draft_001_a \\
        --column tests \\
        --file drafts/draft_001_a/tests_v2.py \\
        --column weights \\
        --file drafts/draft_001_a/weights_v2.json
    
        
Valid columns: prompt, dockerfile, tests (or test_functions), weights (or test_weights), difficulty

Note: For managing additional files, use patch_additional_files.py instead.
        """
    )
    
    parser.add_argument('--csv-path', required=True, help='Path to the CSV file to update')
    parser.add_argument('--task-id', required=True, help='Task ID to update')
    parser.add_argument('--column', action='append', required=True, 
                        help='Column to update (can be specified multiple times)')
    parser.add_argument('--file', action='append', required=True,
                        help='File path for column (must match --column order)')
    
    args = parser.parse_args()
    
    # Validate matching columns and files
    if len(args.column) != len(args.file):
        parser.error("Number of --column and --file arguments must match")
    
    # Create update list
    updates = [(col, Path(file)) for col, file in zip(args.column, args.file)]
    
    # Use provided CSV path
    staging_path = Path(args.csv_path)
    
    try:
        patch_datapoint(args.task_id, updates, staging_path)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()