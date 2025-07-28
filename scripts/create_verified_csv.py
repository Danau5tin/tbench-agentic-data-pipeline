#!/usr/bin/env python3
"""
Step 2 of 2: Create a CSV file containing only verified (completed) datapoints.

This is the second step in a two-step verification workflow:
1. Run validate_all_prod_dps.py first to validate all datapoints
2. Run this script (create_verified_csv.py) to create a CSV with only verified datapoints

This script reads the task manager state file created by validate_all_prod_dps.py
to find which datapoints passed validation, then filters the original CSV to
create a new CSV containing only the verified rows.

Prerequisites:
- validate_all_prod_dps.py must be run first to completion
- The task manager state file must exist with validation results
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from task_manager.task_manager import TaskManager, TaskStatus


def get_completed_task_ids(state_file: Path) -> Set[str]:
    """Extract all completed task IDs from the task manager state."""
    tm = TaskManager(state_file)
    state = tm._load_state()
    
    completed_ids = set()
    for task_id, task in state["tasks"].items():
        if task["status"] == TaskStatus.COMPLETED.value:
            # Extract the original task_id from validation task ID
            if task_id.startswith("validate_"):
                original_id = task["data"]["original_task_id"]
                completed_ids.add(original_id)
    
    return completed_ids


def create_verified_csv(input_csv: Path, output_csv: Path, state_file: Path, dry_run: bool = False):
    """Create a new CSV with only verified/completed tasks."""
    # Get completed task IDs
    completed_ids = get_completed_task_ids(state_file)
    print(f"Found {len(completed_ids)} completed validations")
    
    # Read input CSV and filter
    verified_rows = []
    total_rows = 0
    
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        
        for row in reader:
            total_rows += 1
            task_id = row.get('task_id')
            
            if task_id in completed_ids:
                verified_rows.append(row)
    
    print(f"Total rows in input CSV: {total_rows}")
    print(f"Verified rows to include: {len(verified_rows)}")
    
    if dry_run:
        print("\nDRY RUN - Would write the following verified task IDs:")
        for i, row in enumerate(verified_rows[:10]):
            print(f"  {row['task_id']}")
        if len(verified_rows) > 10:
            print(f"  ... and {len(verified_rows) - 10} more")
        print(f"\nOutput would be written to: {output_csv}")
    else:
        # Write output CSV
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(verified_rows)
        
        print(f"\nWrote {len(verified_rows)} verified rows to {output_csv}")


def main():
    parser = argparse.ArgumentParser(
        description='Create CSV with only verified/completed datapoints'
    )
    parser.add_argument(
        '--input-csv',
        type=str,
        default='data/latest.csv',
        help='Path to input CSV file'
    )
    parser.add_argument(
        '--output-csv',
        type=str,
        default='data/latest_verified.csv',
        help='Path to output CSV file'
    )
    parser.add_argument(
        '--state-file',
        type=str,
        default='state/validate_prod_dps.json',
        help='Path to task manager state file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without creating the file'
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    base_dir = Path(__file__).parent.parent
    input_csv = base_dir / args.input_csv
    output_csv = base_dir / args.output_csv
    state_file = base_dir / args.state_file
    
    # Check input files exist
    if not input_csv.exists():
        print(f"Error: Input CSV not found: {input_csv}")
        sys.exit(1)
    
    if not state_file.exists():
        print(f"Error: State file not found: {state_file}")
        sys.exit(1)
    
    create_verified_csv(input_csv, output_csv, state_file, args.dry_run)


if __name__ == "__main__":
    main()