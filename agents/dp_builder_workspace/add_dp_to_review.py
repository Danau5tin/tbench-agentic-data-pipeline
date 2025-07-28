#!/usr/bin/env python3
"""
add_dp_to_review.py - Safely move a validated datapoint from staging to review dataset

This version includes improvements for:
1. Ensuring consistent columns between staging and review CSVs
2. Only removing from staging after successful addition to review (transaction safety)
3. Properly handling the additional_files column
4. Automatically completing the draft task and creating a review task

Usage:
    python add_dp_to_review.py --task-id draft_001_a
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# Define standard columns for datapoints
STANDARD_COLUMNS = [
    'task_id', 'prompt', 'dockerfile', 'test_functions', 
    'test_weights', 'additional_files', 'difficulty', 'created_at', 'updated_at', 'reviewed_at'
]


def read_staging_data(staging_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read all data from staging CSV."""
    if not staging_path.exists():
        raise FileNotFoundError(f"Staging CSV not found: {staging_path}")
    
    with open(staging_path, 'r') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    return rows, fieldnames


def find_task(rows: List[Dict[str, str]], task_id: str) -> Tuple[Optional[Dict[str, str]], Optional[int]]:
    """Find a task in the rows list, returning the task data and its index."""
    for i, row in enumerate(rows):
        if row['task_id'] == task_id:
            return row, i
    return None, None


def ensure_review_csv(review_path: Path) -> List[str]:
    """Ensure the review CSV exists with proper headers, return existing columns if any."""
    if not review_path.exists():
        review_path.parent.mkdir(parents=True, exist_ok=True)
        with open(review_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=STANDARD_COLUMNS)
            writer.writeheader()
        return STANDARD_COLUMNS
    else:
        # Read existing columns
        with open(review_path, 'r') as f:
            reader = csv.DictReader(f)
            return reader.fieldnames if reader.fieldnames else STANDARD_COLUMNS


def normalize_datapoint(datapoint: Dict[str, str]) -> Dict[str, str]:
    """Ensure datapoint has all standard columns, filling missing ones with empty strings."""
    normalized = {}
    for col in STANDARD_COLUMNS:
        if col == 'reviewed_at':
            # Skip reviewed_at as it will be added when moving to review
            continue
        normalized[col] = datapoint.get(col, '')
    return normalized


def add_to_review_safely(datapoint: Dict[str, str], review_path: Path) -> None:
    """Add a datapoint to the review CSV with transaction safety."""
    # Normalize the datapoint to ensure all columns are present
    normalized_dp = normalize_datapoint(datapoint)
    
    # Add review timestamp
    normalized_dp['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    
    # Create a temporary file for the new review CSV
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=review_path.parent)
    
    try:
        # If review CSV exists, copy existing content
        if review_path.exists():
            with open(review_path, 'r') as f_in, os.fdopen(temp_fd, 'w', newline='') as f_out:
                reader = csv.DictReader(f_in)
                
                # Ensure we use standard columns for consistency
                writer = csv.DictWriter(f_out, fieldnames=STANDARD_COLUMNS)
                writer.writeheader()
                
                # Copy existing rows, normalizing them
                for row in reader:
                    normalized_row = normalize_datapoint(row)
                    # Preserve existing reviewed_at timestamps
                    if 'reviewed_at' in row:
                        normalized_row['reviewed_at'] = row['reviewed_at']
                    writer.writerow(normalized_row)
                
                # Add the new datapoint
                writer.writerow(normalized_dp)
        else:
            # Create new file with just this datapoint
            with os.fdopen(temp_fd, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=STANDARD_COLUMNS)
                writer.writeheader()
                writer.writerow(normalized_dp)
        
        # Atomically replace the original file
        os.replace(temp_path, review_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def remove_from_staging(rows: List[Dict[str, str]], task_index: int, 
                       fieldnames: List[str], staging_path: Path) -> None:
    """Remove a task from staging CSV by writing all rows except the one at task_index."""
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=staging_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            # Write all rows except the one being removed
            for i, row in enumerate(rows):
                if i != task_index:
                    writer.writerow(row)
        
        # Replace original file
        os.replace(temp_path, staging_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def create_final_artifact(datapoint: Dict[str, str], artifacts_path: Path) -> Path:
    """Create a markdown file in final_dps artifacts directory."""
    artifacts_path.mkdir(parents=True, exist_ok=True)
    
    task_id = datapoint['task_id']
    artifact_path = artifacts_path / f"{task_id}_final.md"
    
    # Parse test weights for display
    try:
        weights = json.loads(datapoint['test_weights'])
        weights_display = "\n".join([f"  - {name}: {weight}" for name, weight in weights.items()])
    except:
        weights_display = datapoint['test_weights']
    
    # Parse additional files for display
    additional_files_display = ""
    if 'additional_files' in datapoint and datapoint['additional_files']:
        try:
            additional_files = json.loads(datapoint['additional_files'])
            if additional_files:
                additional_files_display = "\n\n## Additional Files\n"
                for filename, content in additional_files.items():
                    additional_files_display += f"### {filename}\n```\n{content[:500]}{'...' if len(content) > 500 else ''}\n```\n"
        except:
            pass
    
    content = f"""# Datapoint: {task_id}

## Status
- Created: {datapoint.get('created_at', 'N/A')}
- Updated: {datapoint.get('updated_at', 'N/A')}
- Reviewed: {datapoint.get('reviewed_at', 'N/A')}
- Difficulty: {datapoint.get('difficulty', 'N/A')}

## Prompt
{datapoint['prompt']}

## Dockerfile
```dockerfile
{datapoint['dockerfile']}
```

## Test Functions
```python
{datapoint['test_functions']}
```

## Test Weights
{weights_display}{additional_files_display}

---
*This datapoint has been validated and is ready for final review.*
"""
    
    with open(artifact_path, 'w') as f:
        f.write(content)
    
    return artifact_path


def main():
    parser = argparse.ArgumentParser(
        description="Move a validated datapoint from staging to review dataset",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python add_dp_to_review.py --task-id draft_001_a
    
This will:
1. Add the datapoint to review/datapoints_for_review.csv with a review timestamp
2. Only after successful addition, remove it from staging/datapoints.csv
3. Create a comprehensive artifact in artifacts/final_dps/
4. Complete the draft task (marking it as completed)
5. Create a new review_dp task for the Review Agent
6. Ensure consistent columns across both CSVs
        """
    )
    
    parser.add_argument('--task-id', required=True, help='Task ID to move to review')
    
    args = parser.parse_args()
    
    # Define paths
    base_path = Path(__file__).parent
    staging_path = base_path / 'staging' / 'datapoints.csv'
    review_path = base_path / 'review' / 'datapoints_for_review.csv'
    artifacts_path = base_path / 'artifacts' / 'final_dps'
    
    try:
        # Read staging data
        rows, fieldnames = read_staging_data(staging_path)
        
        # Find the task (but don't remove it yet!)
        datapoint, task_index = find_task(rows, args.task_id)
        if datapoint is None:
            print(f"Error: Task '{args.task_id}' not found in staging", file=sys.stderr)
            sys.exit(1)
        
        # Ensure review CSV exists and get its columns
        review_columns = ensure_review_csv(review_path)
        
        # TRANSACTION SAFETY: First add to review, then remove from staging
        
        # Step 1: Add to review (this might fail)
        add_to_review_safely(datapoint, review_path)
        
        # Step 2: Create artifact (this might fail)
        artifact_path = create_final_artifact(datapoint, artifacts_path)
        
        # Step 3: Only if the above succeeded, remove from staging
        remove_from_staging(rows, task_index, fieldnames, staging_path)
        
        # Step 4: Complete the draft task
        try:
            # Complete the draft task as successful
            complete_cmd = [
                "python", str(base_path.parent.parent / "data_pipeline.py"),
                "complete", args.task_id,
                "--status", "completed"
            ]
            
            complete_result = subprocess.run(complete_cmd, capture_output=True, text=True, check=True)
            task_completed = True
            
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to complete draft task: {e}")
            print(f"Error output: {e.stderr}")
            task_completed = False
        except Exception as e:
            print(f"Warning: Unexpected error completing draft task: {e}")
            task_completed = False
        
        # Step 5: Create a review task for the Review Agent
        try:
            # Prepare task data
            task_data = {
                "review_csv_id": args.task_id,
                "artifact_path": str(artifact_path.relative_to(base_path.parent.parent)),
                "submitted_at": datetime.now().isoformat()
            }
            
            # Create the review task using data_pipeline.py
            cmd = [
                "python", str(base_path.parent.parent / "data_pipeline.py"),
                "create-task",
                "--type", "review_dp",
                "--parent", args.task_id,  # The draft task becomes the parent
                "--data", json.dumps(task_data)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse the result to get the new task ID
            result_data = json.loads(result.stdout)
            review_task_id = result_data.get("task_id", "unknown")
            
            print(f"✓ Moved datapoint '{args.task_id}' to review")
            print(f"  - Added to: review/datapoints_for_review.csv")
            print(f"  - Removed from: staging/datapoints.csv")
            print(f"  - Artifact created: {artifact_path.relative_to(base_path)}")
            print(f"  - Draft task completed: {'Yes' if task_completed else 'Failed'}")
            print(f"  - Review task created: {review_task_id}")
            
        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to create review task: {e}")
            print(f"Error output: {e.stderr}")
            # Still report success for the main operation
            print(f"✓ Moved datapoint '{args.task_id}' to review (but review task creation failed)")
            print(f"  - Added to: review/datapoints_for_review.csv")
            print(f"  - Removed from: staging/datapoints.csv")
            print(f"  - Artifact created: {artifact_path.relative_to(base_path)}")
            print(f"  - Draft task completed: {'Yes' if task_completed else 'Failed'}")
        except Exception as e:
            print(f"Warning: Unexpected error creating review task: {e}")
            # Still report success for the main operation
            print(f"✓ Moved datapoint '{args.task_id}' to review (but review task creation failed)")
            print(f"  - Added to: review/datapoints_for_review.csv")
            print(f"  - Removed from: staging/datapoints.csv")
            print(f"  - Artifact created: {artifact_path.relative_to(base_path)}")
            print(f"  - Draft task completed: {'Yes' if task_completed else 'Failed'}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()