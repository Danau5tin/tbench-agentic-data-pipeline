#!/usr/bin/env python3
"""
create_dp.py - Create a new datapoint using shared workspace structure

This version creates files directly in the shared workspace and uses patch_additional_files.py
for syncing additional files to the CSV.

Usage:
    python create_dp.py \
        --task-id draft_001_a \
        --prompt-file /path/to/prompt.md \
        --dockerfile-file /path/to/dockerfile \
        --tests-file /path/to/tests.py \
        --weights-file /path/to/weights.json \
        --difficulty medium
"""

import argparse
import csv
import json
import os
import sys
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional


def ensure_staging_csv(staging_path: Path) -> None:
    """Ensure the staging CSV exists with proper headers."""
    if not staging_path.exists():
        staging_path.parent.mkdir(parents=True, exist_ok=True)
        with open(staging_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'task_id', 'prompt', 'dockerfile', 'test_functions', 
                'test_weights', 'additional_files', 'difficulty', 'created_at', 'updated_at'
            ])
            writer.writeheader()


def task_exists_in_staging(staging_path: Path, task_id: str) -> bool:
    """Check if a task already exists in staging."""
    if not staging_path.exists():
        return False
    
    with open(staging_path, 'r') as f:
        reader = csv.DictReader(f)
        return any(row['task_id'] == task_id for row in reader)


def read_file_content(file_path: Path, file_type: str) -> str:
    """Read and validate file content."""
    if not file_path.exists():
        raise FileNotFoundError(f"{file_type} file not found: {file_path}")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if not content.strip():
            raise ValueError(f"{file_type} file is empty: {file_path}")
            
        return content
    except Exception as e:
        raise RuntimeError(f"Error reading {file_type} file: {e}")


def validate_weights(weights_content: str) -> Dict[str, float]:
    """Validate test weights JSON."""
    try:
        weights = json.loads(weights_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in weights file: {e}")
    
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
    
    return weights


def get_workspace_path(task_id: str) -> Path:
    """Get the workspace path for a task."""
    # Go up from dp_builder_workspace to data_generation_pipeline
    base_path = Path(__file__).parent.parent.parent / 'shared_workspace' / 'data_points' / task_id
    return base_path


def create_workspace_structure(workspace_path: Path) -> None:
    """Create the workspace directory structure."""
    workspace_path.mkdir(parents=True, exist_ok=True)
    (workspace_path / 'files').mkdir(exist_ok=True)
    (workspace_path / '.history').mkdir(exist_ok=True)


def copy_file_to_workspace(source_file: Path, workspace_path: Path, target_name: str) -> None:
    """Copy a file to the workspace."""
    target_path = workspace_path / target_name
    
    # If source and target are the same file, skip copying
    if source_file.resolve() == target_path.resolve():
        return
    
    shutil.copy2(source_file, target_path)


def copy_additional_files(source_dir: Path, workspace_path: Path) -> int:
    """Copy additional files to workspace files directory."""
    files_dir = workspace_path / 'files'
    files_dir.mkdir(exist_ok=True)
    
    # If source and target are the same directory, just count files
    if source_dir.resolve() == files_dir.resolve():
        file_count = sum(1 for _ in files_dir.rglob('*') if _.is_file())
        return file_count
    
    file_count = 0
    for file_path in source_dir.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(source_dir)
            target_path = files_dir / rel_path
            
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Skip if source and target are the same
            if file_path.resolve() != target_path.resolve():
                shutil.copy2(file_path, target_path)
            file_count += 1
    
    return file_count


def create_datapoint(
    task_id: str,
    prompt_file: Path,
    dockerfile_file: Path,
    tests_file: Path,
    weights_file: Path,
    staging_path: Path,
    difficulty: str,
    additional_files_dir: Optional[Path] = None
) -> None:
    """Create a new datapoint using shared workspace structure."""
    # Read and validate all files first
    prompt = read_file_content(prompt_file, "Prompt")
    dockerfile = read_file_content(dockerfile_file, "Dockerfile")
    tests = read_file_content(tests_file, "Tests")
    weights_json = read_file_content(weights_file, "Weights")
    
    # Validate weights
    weights = validate_weights(weights_json)
    
    # Validate tests contain the functions referenced in weights
    for test_name in weights:
        if f"def {test_name}" not in tests:
            raise ValueError(f"Test function '{test_name}' not found in tests file")
    
    # Create workspace structure
    workspace_path = get_workspace_path(task_id)
    create_workspace_structure(workspace_path)
    
    print(f"✓ Workspace at: {workspace_path}")
    
    # Copy files to workspace (or skip if already there)
    copy_file_to_workspace(prompt_file, workspace_path, 'prompt.md')
    copy_file_to_workspace(dockerfile_file, workspace_path, 'dockerfile')
    copy_file_to_workspace(tests_file, workspace_path, 'tests.py')
    copy_file_to_workspace(weights_file, workspace_path, 'weights.json')
    
    # Copy additional files if provided
    additional_file_count = 0
    if additional_files_dir and additional_files_dir.exists():
        additional_file_count = copy_additional_files(additional_files_dir, workspace_path)
        if additional_files_dir.resolve() == (workspace_path / 'files').resolve():
            print(f"✓ Found {additional_file_count} additional files in workspace")
        else:
            print(f"✓ Copied {additional_file_count} additional files to workspace")
    
    # Create initial CSV entry (without additional_files content)
    timestamp = datetime.now(timezone.utc).isoformat()
    datapoint = {
        'task_id': task_id,
        'prompt': prompt,
        'dockerfile': dockerfile,
        'test_functions': tests,
        'test_weights': json.dumps(weights),
        'additional_files': '',  # Will be synced later
        'difficulty': difficulty,
        'created_at': timestamp,
        'updated_at': timestamp
    }
    
    # Append to staging CSV
    with open(staging_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=datapoint.keys())
        writer.writerow(datapoint)
    
    print(f"✓ Created datapoint '{task_id}' in staging CSV")
    print(f"  - Prompt: {len(prompt)} chars")
    print(f"  - Dockerfile: {len(dockerfile)} chars")
    print(f"  - Tests: {len(tests)} chars")
    print(f"  - Weights: {len(weights)} test functions")
    
    # If there are additional files, sync them using patch_additional_files.py
    if additional_file_count > 0:
        patch_tool_path = Path(__file__).parent.parent.parent / 'shared_tools' / 'patch_additional_files.py'
        
        try:
            result = subprocess.run([
                sys.executable,
                str(patch_tool_path),
                '--task-id', task_id,
                '--csv-path', str(staging_path),
                '--mode', 'sync'
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"✓ Synced additional files to CSV")
            else:
                print(f"Warning: Failed to sync additional files: {result.stderr}")
        except Exception as e:
            print(f"Warning: Could not sync additional files: {e}")
    
    print(f"\n✓ Workspace created at: {workspace_path}")
    print("  You can now edit files directly in the workspace")
    print("  Use patch_additional_files.py --mode sync to update CSV after changes")


def main():
    parser = argparse.ArgumentParser(
        description="Create a new datapoint using shared workspace structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python create_dp.py \\
        --task-id draft_001_a \\
        --prompt-file /path/to/prompt.md \\
        --dockerfile-file /path/to/dockerfile \\
        --tests-file /path/to/tests.py \\
        --weights-file /path/to/weights.json \\
        --difficulty medium
        
    # With additional files:
    python create_dp.py \\
        --task-id draft_001_a \\
        --prompt-file /path/to/prompt.md \\
        --dockerfile-file /path/to/dockerfile \\
        --tests-file /path/to/tests.py \\
        --weights-file /path/to/weights.json \\
        --additional-files-dir /path/to/files/ \\
        --difficulty hard

This will:
1. Create a workspace at shared_workspace/data_points/{task_id}/
2. Copy all files to the workspace
3. Create an entry in the staging CSV
4. Sync additional files to CSV using patch_additional_files.py
        """
    )
    
    parser.add_argument('--task-id', required=True, help='Task ID for the datapoint')
    parser.add_argument('--prompt-file', required=True, type=Path, help='Path to prompt file')
    parser.add_argument('--dockerfile-file', required=True, type=Path, help='Path to Dockerfile')
    parser.add_argument('--tests-file', required=True, type=Path, help='Path to test functions file')
    parser.add_argument('--weights-file', required=True, type=Path, help='Path to test weights JSON file')
    parser.add_argument('--additional-files-dir', type=Path, help='Directory containing additional files to include')
    parser.add_argument('--difficulty', required=True, choices=['easy', 'medium', 'hard', 'extremely_hard'], 
                       help='Difficulty level of the datapoint')
    
    args = parser.parse_args()
    
    # Define staging CSV path
    staging_path = Path(__file__).parent / 'staging' / 'datapoints.csv'
    
    try:
        # Ensure staging CSV exists
        ensure_staging_csv(staging_path)
        
        # Check if task already exists
        if task_exists_in_staging(staging_path, args.task_id):
            print(f"Error: Task '{args.task_id}' already exists in staging", file=sys.stderr)
            print("Use patch_dp.py to update existing datapoints", file=sys.stderr)
            sys.exit(1)
        
        # Create the datapoint
        create_datapoint(
            args.task_id,
            args.prompt_file,
            args.dockerfile_file,
            args.tests_file,
            args.weights_file,
            staging_path,
            args.difficulty,
            args.additional_files_dir
        )
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()