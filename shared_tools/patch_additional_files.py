#!/usr/bin/env python3
"""
patch_additional_files.py - Manage additional files in shared workspace

This tool provides granular control over additional files management, working with
a shared workspace approach where both DP Builder and Review agents work on the 
same file structure.

Usage:
    # Sync from shared workspace to CSV (most common operation)
    python patch_additional_files.py --task-id draft_001_a \
        --workspace shared_workspace/data_points/draft_001_a/files/ \
        --csv-path path/to/datapoints.csv \
        --mode sync
    
    # Update/add a single file
    python patch_additional_files.py --task-id draft_001_a \
        --file /tmp/fixed_renv.lock \
        --name renv.lock \
        --csv-path path/to/datapoints.csv
    
    # Remove a file
    python patch_additional_files.py --task-id draft_001_a \
        --mode remove \
        --name old_script.R \
        --csv-path path/to/datapoints.csv
    
    # Replace all files (like old behavior)
    python patch_additional_files.py --task-id draft_001_a \
        --workspace new_files_dir/ \
        --csv-path path/to/datapoints.csv \
        --mode replace
"""

import argparse
import csv
import json
import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional


def read_csv_data(csv_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Read all data from CSV file."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    with open(csv_path, 'r') as f:
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


def get_workspace_path(task_id: str) -> Path:
    """Get the default workspace path for a task."""
    base_path = Path(__file__).parent.parent / 'shared_workspace' / 'data_points' / task_id
    return base_path


def ensure_workspace_exists(workspace_path: Path) -> None:
    """Ensure workspace directory structure exists."""
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    # Create files subdirectory if it doesn't exist
    files_dir = workspace_path / 'files'
    files_dir.mkdir(exist_ok=True)
    
    # Create history directory
    history_dir = workspace_path / '.history'
    history_dir.mkdir(exist_ok=True)


def save_history(workspace_path: Path, operation: str, changes: Dict[str, Any]) -> None:
    """Save operation history for audit trail."""
    history_dir = workspace_path / '.history'
    history_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    history_file = history_dir / f"{timestamp}_{operation}.json"
    
    history_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'operation': operation,
        'changes': changes
    }
    
    with open(history_file, 'w') as f:
        json.dump(history_entry, f, indent=2)


def sync_from_workspace(workspace_path: Path, task_id: str) -> Dict[str, str]:
    """Read all files from workspace and create additional_files JSON."""
    files_dir = workspace_path / 'files'
    if not files_dir.exists():
        return {}
    
    additional_files = {}
    
    for file_path in files_dir.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(files_dir)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    additional_files[str(rel_path)] = f.read()
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")
    
    return additional_files


def update_file_in_workspace(workspace_path: Path, file_name: str, content: str) -> None:
    """Update or create a file in the workspace."""
    files_dir = workspace_path / 'files'
    files_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = files_dir / file_name
    
    # Create parent directories if needed
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


def remove_file_from_workspace(workspace_path: Path, file_name: str) -> bool:
    """Remove a file from the workspace."""
    files_dir = workspace_path / 'files'
    file_path = files_dir / file_name
    
    if file_path.exists():
        file_path.unlink()
        
        # Clean up empty parent directories
        try:
            parent = file_path.parent
            while parent != files_dir and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        except:
            pass
        
        return True
    return False


def replace_all_files_in_workspace(workspace_path: Path, source_dir: Path) -> Dict[str, str]:
    """Replace all files in workspace with files from source directory."""
    files_dir = workspace_path / 'files'
    
    # Remove existing files
    if files_dir.exists():
        shutil.rmtree(files_dir)
    files_dir.mkdir(parents=True)
    
    # Copy new files
    additional_files = {}
    for file_path in source_dir.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(source_dir)
            dest_path = files_dir / rel_path
            
            # Create parent directories
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy file
            shutil.copy2(file_path, dest_path)
            
            # Read content for return
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    additional_files[str(rel_path)] = f.read()
            except Exception as e:
                print(f"Warning: Could not read {file_path}: {e}")
    
    return additional_files


def patch_additional_files(
    task_id: str,
    mode: str,
    csv_path: Path,
    workspace: Optional[Path] = None,
    file_path: Optional[Path] = None,
    file_name: Optional[str] = None
) -> None:
    """Main function to patch additional files."""
    # Read current CSV data
    rows, fieldnames = read_csv_data(csv_path)
    row_index = find_task_row(rows, task_id)
    
    # Get workspace path
    if workspace:
        workspace_path = workspace
    else:
        workspace_path = get_workspace_path(task_id)
    
    ensure_workspace_exists(workspace_path)
    
    changes = {
        'task_id': task_id,
        'mode': mode,
        'workspace': str(workspace_path)
    }
    
    if mode == 'sync':
        # Sync from workspace to CSV
        additional_files = sync_from_workspace(workspace_path, task_id)
        rows[row_index]['additional_files'] = json.dumps(additional_files)
        changes['files_synced'] = len(additional_files)
        print(f"✓ Synced {len(additional_files)} files from workspace to CSV")
    
    elif mode == 'update':
        # Update/add a single file
        if not file_path or not file_name:
            raise ValueError("--file and --name required for update mode")
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Update in workspace
        update_file_in_workspace(workspace_path, file_name, content)
        
        # Sync to CSV
        additional_files = sync_from_workspace(workspace_path, task_id)
        rows[row_index]['additional_files'] = json.dumps(additional_files)
        
        changes['file_updated'] = file_name
        changes['file_size'] = len(content)
        print(f"✓ Updated file '{file_name}' ({len(content)} chars)")
    
    elif mode == 'remove':
        # Remove a file
        if not file_name:
            raise ValueError("--name required for remove mode")
        
        # Remove from workspace
        removed = remove_file_from_workspace(workspace_path, file_name)
        
        if removed:
            # Sync to CSV
            additional_files = sync_from_workspace(workspace_path, task_id)
            rows[row_index]['additional_files'] = json.dumps(additional_files)
            changes['file_removed'] = file_name
            print(f"✓ Removed file '{file_name}'")
        else:
            print(f"⚠ File '{file_name}' not found in workspace")
            return
    
    elif mode == 'replace':
        # Replace all files
        if not workspace:
            raise ValueError("--workspace required for replace mode")
        
        if not workspace.exists() or not workspace.is_dir():
            raise ValueError(f"Workspace directory not found: {workspace}")
        
        # Replace all files
        additional_files = replace_all_files_in_workspace(workspace_path, workspace)
        rows[row_index]['additional_files'] = json.dumps(additional_files)
        
        changes['files_replaced'] = len(additional_files)
        print(f"✓ Replaced all files ({len(additional_files)} files)")
    
    elif mode == 'append':
        # Only add new files, error if file exists
        if not file_path or not file_name:
            raise ValueError("--file and --name required for append mode")
        
        # Check if file already exists
        target_file = workspace_path / 'files' / file_name
        if target_file.exists():
            raise ValueError(f"File already exists: {file_name}")
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Add to workspace
        update_file_in_workspace(workspace_path, file_name, content)
        
        # Sync to CSV
        additional_files = sync_from_workspace(workspace_path, task_id)
        rows[row_index]['additional_files'] = json.dumps(additional_files)
        
        changes['file_appended'] = file_name
        changes['file_size'] = len(content)
        print(f"✓ Added new file '{file_name}' ({len(content)} chars)")
    
    # Update timestamp
    rows[row_index]['updated_at'] = datetime.now(timezone.utc).isoformat()
    
    # Save history
    save_history(workspace_path.parent, f"patch_additional_files_{mode}", changes)
    
    # Write back to CSV using temporary file for safety
    temp_fd, temp_path = tempfile.mkstemp(suffix='.csv', dir=csv_path.parent)
    try:
        with os.fdopen(temp_fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        # Replace original file
        os.replace(temp_path, csv_path)
        
    except Exception:
        # Clean up temp file on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    
    print(f"✓ Updated datapoint '{task_id}' in {csv_path.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage additional files in shared workspace",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Sync from shared workspace to CSV (most common for agents)
    python patch_additional_files.py --task-id draft_001_a \\
        --csv-path staging/datapoints.csv \\
        --mode sync
    
    # Update/add a single file
    python patch_additional_files.py --task-id draft_001_a \\
        --file /tmp/fixed_renv.lock \\
        --name renv.lock \\
        --csv-path staging/datapoints.csv
    
    # Remove a file
    python patch_additional_files.py --task-id draft_001_a \\
        --mode remove \\
        --name old_script.R \\
        --csv-path staging/datapoints.csv
    
    # Replace all files (like old behavior)
    python patch_additional_files.py --task-id draft_001_a \\
        --workspace new_files_dir/ \\
        --csv-path staging/datapoints.csv \\
        --mode replace
    
    # Add new file (error if exists)
    python patch_additional_files.py --task-id draft_001_a \\
        --file config.yaml \\
        --name config.yaml \\
        --csv-path staging/datapoints.csv \\
        --mode append

Modes:
    update  - Update/add specific files (default)
    append  - Only add new files, error if file exists  
    replace - Replace entire additional_files
    remove  - Remove specific files
    sync    - Sync from shared workspace to CSV
        """
    )
    
    parser.add_argument('--task-id', required=True, help='Task ID to update')
    parser.add_argument('--csv-path', required=True, type=Path, help='Path to the CSV file')
    parser.add_argument('--mode', choices=['update', 'append', 'replace', 'remove', 'sync'], 
                        default='update', help='Operation mode')
    parser.add_argument('--workspace', type=Path, 
                        help='Workspace directory (for sync/replace modes)')
    parser.add_argument('--file', type=Path, 
                        help='File to add/update (for update/append modes)')
    parser.add_argument('--name', 
                        help='File name in workspace (for update/append/remove modes)')
    
    args = parser.parse_args()
    
    try:
        patch_additional_files(
            args.task_id,
            args.mode,
            args.csv_path,
            args.workspace,
            args.file,
            args.name
        )
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()