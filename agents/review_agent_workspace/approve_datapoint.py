#!/usr/bin/env python3
"""
approve_datapoint.py - Approve a reviewed datapoint and add it to production dataset

Usage:
    python approve_datapoint.py \
        --review-csv review/datapoints_for_review.csv \
        --task-id draft_001_a \
        --latest-csv /path/to/latest.csv
"""

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directories to path to import shared_tools
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent.parent))

from shared_tools.categories_tags import (
    validate_category, 
    validate_tags,
    get_category_set,
    VALID_CATEGORIES
)


def read_csv_data(csv_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read all data from CSV file."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    return rows, fieldnames


def find_task_row(rows: List[Dict[str, str]], task_id: str) -> Tuple[int, Dict[str, str]]:
    """Find the row index and data for a given task ID."""
    for i, row in enumerate(rows):
        if row['task_id'] == task_id:
            return i, row
    raise ValueError(f"Task '{task_id}' not found in CSV")


def backup_file(file_path: Path, backup_dir: Path) -> Path:
    """Create a timestamped backup of a file using dataset_YYYYMMDD_HHMMSS format."""
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    backup_name = f"dataset_{timestamp}.csv"
    backup_path = backup_dir / backup_name
    
    shutil.copy2(file_path, backup_path)
    return backup_path


def approve_datapoint(
    task_id: str,
    review_csv_path: Path,
    latest_csv_path: Path,
    category: str,
    tags: str,
    backup_dir: Path = None,
    complete_task: bool = True,
    review_task_id: str = None
) -> None:
    """Approve a datapoint and add it to the production dataset.
    
    If backup_dir is not provided, defaults to archive/ directory next to latest.csv.
    If complete_task is True, automatically marks the task as completed in data_pipeline.
    review_task_id is the review task ID to complete (e.g., review_dp_xxx), if different from task_id.
    """
    # Validate category
    if not validate_category(category):
        raise ValueError(f"Invalid category '{category}'. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}")
    
    # Validate tags
    is_valid, error_msg = validate_tags(tags)
    if not is_valid:
        raise ValueError(f"Invalid tags: {error_msg}")
    
    # Read review CSV
    review_rows, review_fieldnames = read_csv_data(review_csv_path)
    
    # Find the datapoint to approve
    review_index, datapoint = find_task_row(review_rows, task_id)
    
    # No need to check if already reviewed - just check if it exists in production
    
    # Read production CSV or create new structure
    if latest_csv_path.exists():
        prod_rows, prod_fieldnames = read_csv_data(latest_csv_path)
        
        # Check for duplicates
        for row in prod_rows:
            if row['task_id'] == task_id:
                raise ValueError(f"Task '{task_id}' already exists in production dataset")
    else:
        # Create new production CSV with required fields
        prod_rows = []
        prod_fieldnames = [
            'task_id', 'difficulty', 'title', 'use_case_category', 'prompt', 
            'category', 'tags', 'dockerfile', 'test_functions', 'test_weights',
            'additional_files', 'created_at', 'updated_at'
        ]
    
    # Prepare the approved datapoint
    approved_datapoint = {
        'task_id': datapoint['task_id'],
        'difficulty': datapoint.get('difficulty', 'medium'),
        'title': datapoint['task_id'],  # Use task_id as title
        'use_case_category': category,  # Use the category as use_case_category
        'prompt': datapoint['prompt'],
        'category': category,
        'tags': tags,
        'dockerfile': datapoint['dockerfile'],
        'test_functions': datapoint['test_functions'],
        'test_weights': datapoint['test_weights'],
        'additional_files': datapoint.get('additional_files', '{}'),
        'created_at': datapoint.get('created_at', datetime.now(timezone.utc).isoformat()),
        'updated_at': datapoint.get('updated_at', datetime.now(timezone.utc).isoformat())
    }
    
    # Set default backup directory if not provided
    if backup_dir is None and latest_csv_path.exists():
        backup_dir = latest_csv_path.parent / 'archive'
    
    # Create backup directory if it doesn't exist
    if backup_dir:
        backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Backup existing production CSV
    if backup_dir and latest_csv_path.exists():
        backup_path = backup_file(latest_csv_path, backup_dir)
        print(f"✓ Created backup: {backup_path}")
    
    # Add to production dataset
    prod_rows.append(approved_datapoint)
    
    # Write updated production CSV atomically
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=latest_csv_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=prod_fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(prod_rows)
        
        # Replace original file
        os.replace(temp_path, latest_csv_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    
    # Update review CSV to mark as reviewed
    review_rows[review_index]['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    
    # Write updated review CSV
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=review_csv_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=review_fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(review_rows)
        
        # Replace original file
        os.replace(temp_path, review_csv_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    
    # Report success
    print(f"✓ Approved datapoint '{task_id}'")
    print(f"  - Added to production: {latest_csv_path}")
    print(f"  - Updated review status: {review_csv_path}")
    print(f"  - Total production datapoints: {len(prod_rows)}")
    
    # Complete the task in data_pipeline if requested
    if complete_task:
        try:
            # Get the path to data_pipeline.py relative to this script
            script_dir = Path(__file__).parent
            data_pipeline_path = script_dir.parent.parent / 'data_pipeline.py'
            
            # Use review_task_id if provided, otherwise use task_id
            task_to_complete = review_task_id if review_task_id else task_id
            
            cmd = [
                'python', str(data_pipeline_path),
                'complete', task_to_complete,
                '--status', 'completed'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✓ Marked task '{task_to_complete}' as completed in data pipeline")
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Warning: Failed to complete task in data pipeline: {e.stderr}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to complete task in data pipeline: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description="Approve a reviewed datapoint and add it to production dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python approve_datapoint.py \\
        --review-csv agents/dp_builder_workspace/review/datapoints_for_review.csv \\
        --task-id draft_001_a \\
        --latest-csv ../datasets/v1/versioned_datasets/latest.csv \\
        --category software-engineering \\
        --tags "python|debugging|cli"
    
    # Backup will be automatically created in ../datasets/v1/versioned_datasets/archive/
        """
    )
    
    parser.add_argument('--review-csv', required=True, type=Path,
                        help='Path to the review CSV file')
    parser.add_argument('--task-id', required=True, 
                        help='Task ID to approve')
    parser.add_argument('--latest-csv', type=Path,
                        default=Path('/Users/danaustin/Documents/Projects/terminal_bench_training/workings/ds/datasets/v1/versioned_datasets/latest.csv'),
                        help='Path to the production latest.csv file (default: /Users/danaustin/Documents/Projects/terminal_bench_training/workings/ds/datasets/v1/versioned_datasets/latest.csv)')
    parser.add_argument('--category', required=True,
                        help='Category for the datapoint (e.g., software-engineering)')
    parser.add_argument('--tags', required=True,
                        help='Pipe-separated tags for the datapoint (e.g., python|debugging|cli)')
    parser.add_argument('--backup-dir', type=Path,
                        help='Directory to store backups (defaults to archive/ next to latest.csv)')
    parser.add_argument('--no-complete-task', action='store_true',
                        help='Do not automatically complete the task in data_pipeline')
    parser.add_argument('--review-task-id',
                        help='Review task ID to complete (e.g., review_dp_xxx), if different from task_id')
    
    args = parser.parse_args()
    
    try:
        approve_datapoint(
            args.task_id,
            args.review_csv,
            args.latest_csv,
            args.category,
            args.tags,
            args.backup_dir,
            complete_task=not args.no_complete_task,
            review_task_id=args.review_task_id
        )
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()