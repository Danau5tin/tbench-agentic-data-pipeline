#!/usr/bin/env python3
"""
cancel_datapoint.py - Cancel a datapoint that cannot be salvaged after review attempts

Usage:
    python cancel_datapoint.py \
        --review-csv review/datapoints_for_review.csv \
        --task-id draft_001_a \
        --reason "Fundamental issue: task is out of scope for terminal_bench" \
        --category scope
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


# Valid cancellation categories
CANCELLATION_CATEGORIES = [
    'scope',          # Out of scope for terminal_bench
    'unfixable',      # Technical issues that cannot be resolved
    'complexity',     # Fundamentally too complex or too simple
    'quality',        # Irredeemably poor quality after multiple attempts
    'other'           # Other reasons
]


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


def create_cancellation_artifact(
    task_id: str,
    reason: str,
    category: str,
    attempts: int = 0,
    details: Dict[str, any] = None
) -> Dict[str, any]:
    """Create a cancellation artifact with structured feedback."""
    artifact = {
        'task_id': task_id,
        'cancelled_at': datetime.now(timezone.utc).isoformat(),
        'cancelled_by': 'review_agent',
        'category': category,
        'reason': reason,
        'review_attempts': attempts,
        'details': details or {},
        'final_decision': 'cancelled'
    }
    
    return artifact


def cancel_datapoint(
    task_id: str,
    review_csv_path: Path,
    reason: str,
    category: str,
    attempts: int = 0,
    cancellation_dir: Path = None,
    complete_task: bool = True,
    review_task_id: str = None
) -> Path:
    """Cancel a datapoint that cannot be salvaged and update review status.
    
    This should only be used when the datapoint has fundamental issues that
    cannot be fixed through iteration (e.g., out of scope, duplicate).
    
    review_task_id is the review task ID to complete (e.g., review_dp_xxx), if different from task_id.
    
    Returns the path to the cancellation artifact file.
    """
    # Validate category
    if category not in CANCELLATION_CATEGORIES:
        raise ValueError(f"Invalid category '{category}'. Valid categories: {', '.join(CANCELLATION_CATEGORIES)}")
    
    # Read review CSV
    review_rows, review_fieldnames = read_csv_data(review_csv_path)
    
    # Find the datapoint to reject
    review_index, datapoint = find_task_row(review_rows, task_id)
    
    # Check if already processed (using reviewed_at field)
    if datapoint.get('reviewed_at'):
        raise ValueError(f"Task '{task_id}' has already been reviewed at {datapoint['reviewed_at']}")
    
    # Create cancellation artifact
    cancellation_artifact = create_cancellation_artifact(task_id, reason, category, attempts)
    
    # Save cancellation artifact
    if cancellation_dir is None:
        cancellation_dir = review_csv_path.parent / 'cancelled'
    
    cancellation_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = cancellation_dir / f"{task_id}_cancellation.json"
    
    with open(artifact_path, 'w') as f:
        json.dump(cancellation_artifact, f, indent=2)
    
    print(f"✓ Created cancellation artifact: {artifact_path}")
    
    # Update review CSV - only update the reviewed_at field to mark as processed
    review_rows[review_index]['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    
    # Store cancellation details in the artifact instead of the CSV
    # since the CSV doesn't have fields for cancellation details
    
    # Write updated review CSV
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=review_csv_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=review_fieldnames)
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
    print(f"✓ Cancelled datapoint '{task_id}'")
    print(f"  - Category: {category}")
    print(f"  - Reason: {reason}")
    print(f"  - Review attempts: {attempts}")
    print(f"  - Marked as reviewed in: {review_csv_path}")
    
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
                '--status', 'cancelled',
                '--artifact', str(artifact_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✓ Marked task '{task_to_complete}' as cancelled in data pipeline with artifact")
            
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Warning: Failed to complete task in data pipeline: {e.stderr}")
        except Exception as e:
            print(f"⚠️  Warning: Failed to complete task in data pipeline: {str(e)}")
    
    return artifact_path


def main():
    parser = argparse.ArgumentParser(
        description="Cancel a datapoint that cannot be salvaged after review attempts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Example:
    python cancel_datapoint.py \\
        --review-csv agents/dp_builder_workspace/review/datapoints_for_review.csv \\
        --task-id draft_001_a \\
        --reason "Task requires GUI interaction which is out of scope for terminal_bench" \\
        --category scope \\
        --attempts 3

Valid categories: {', '.join(CANCELLATION_CATEGORIES)}
        """
    )
    
    parser.add_argument('--review-csv', required=True, type=Path,
                        help='Path to the review CSV file')
    parser.add_argument('--task-id', required=True, 
                        help='Task ID to reject')
    parser.add_argument('--reason', required=True,
                        help='Detailed reason for cancellation')
    parser.add_argument('--category', required=True, choices=CANCELLATION_CATEGORIES,
                        help='Category of cancellation')
    parser.add_argument('--attempts', type=int, default=0,
                        help='Number of review/iteration attempts made')
    parser.add_argument('--cancellation-dir', type=Path,
                        help='Directory to store cancellation artifacts (defaults to cancelled/ next to review CSV)')
    parser.add_argument('--no-complete-task', action='store_true',
                        help='Do not automatically complete the task in data_pipeline')
    parser.add_argument('--review-task-id',
                        help='Review task ID to complete (e.g., review_dp_xxx), if different from task_id')
    
    args = parser.parse_args()
    
    try:
        artifact_path = cancel_datapoint(
            args.task_id,
            args.review_csv,
            args.reason,
            args.category,
            args.attempts,
            args.cancellation_dir,
            complete_task=not args.no_complete_task,
            review_task_id=args.review_task_id
        )
        
        print(f"\n💡 The DP Builder agent can retrieve this feedback using:")
        print(f"   python data_pipeline.py get-artifact {args.task_id}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()