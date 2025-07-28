#!/usr/bin/env python3
"""
Step 1 of 2: Validate all production datapoints using task manager for concurrent processing.

This is the first step in a two-step verification workflow:
1. Run this script (validate_all_prod_dps.py) to validate all datapoints
2. Run create_verified_csv.py to create a CSV containing only verified datapoints

This script supports:
- Initializing validation tasks from latest.csv
- Running multiple workers to validate datapoints concurrently
- Monitoring progress and failures
- Resumable execution (can be stopped and restarted)

The validation results are stored in a task manager state file that will be
read by create_verified_csv.py to produce the final verified dataset.
"""

import argparse
import csv
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import multiprocessing

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from task_manager.task_manager import TaskManager, TaskStatus


TIMEOUT_MINUTES = 10

class DatapointValidator:
    """Handles validation of individual datapoints."""
    
    def __init__(self, csv_path: Path, verbose: bool = True):
        self.csv_path = csv_path
        self.verbose = verbose
        self.validate_script = Path(__file__).parent / "validate_datapoint.py"
    
    def validate(self, task_id: str) -> Dict[str, Any]:
        """Run validation for a specific task ID."""
        cmd = [
            sys.executable,
            str(self.validate_script),
            "--task-id", task_id,
            "--csv-path", str(self.csv_path)
        ]
        
        if self.verbose:
            cmd.append("--verbose")
        
        try:
            # Run validation with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout= TIMEOUT_MINUTES * 60,
            )
            
            # Parse output
            if result.returncode == 0:
                return {
                    "status": "success",
                    "stdout": result.stdout,
                    "stderr": result.stderr
                }
            else:
                return {
                    "status": "failed",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "error": f"Validation failed with return code {result.returncode}"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "error": f"Validation timed out after {TIMEOUT_MINUTES} minutes",
                "traceback": "TimeoutExpired"
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e),
                "traceback": traceback.format_exc()
            }


def initialize_tasks(tm: TaskManager, csv_path: Path) -> int:
    """Initialize validation tasks from CSV file."""
    print(f"Loading datapoints from {csv_path}")
    
    # Get existing tasks to avoid duplicates
    existing_tasks = set()
    summary = tm.get_status_summary()
    state = tm._load_state()
    for task_id in state["tasks"]:
        # Extract the original task_id from our validation task ID
        if task_id.startswith("validate_"):
            original_id = task_id.replace("validate_", "", 1)
            existing_tasks.add(original_id)
    
    # Load CSV and create tasks
    new_tasks = 0
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_id = row.get('task_id')
            if not task_id:
                continue
                
            if task_id in existing_tasks:
                continue
            
            # Create validation task
            tm.create_task(
                task_type="validate",
                data={
                    "original_task_id": task_id,
                    "csv_path": str(csv_path),
                    "created_at": datetime.now().isoformat()
                }
            )
            new_tasks += 1
    
    print(f"Created {new_tasks} new validation tasks")
    print(f"Total tasks in queue: {summary['total_tasks'] + new_tasks}")
    return new_tasks


def worker_process(worker_id: str, state_file: Path, csv_path: Path, verbose: bool):
    """Worker process that pulls and processes validation tasks."""
    tm = TaskManager(state_file)
    validator = DatapointValidator(csv_path, verbose)
    
    print(f"[{worker_id}] Starting worker")
    
    while True:
        # Get next task
        task = tm.get_next_task(
            agent_id=worker_id,
            task_types=["validate"]
        )
        
        if not task:
            print(f"[{worker_id}] No more tasks available")
            break
        
        task_id = task["data"]["original_task_id"]
        print(f"[{worker_id}] Validating: {task_id}")
        
        # Double-check we still own this task before running validation
        current_task = tm.get_task(task["id"])
        if not current_task or current_task["locked_by"] != worker_id:
            print(f"[{worker_id}] ⚠️  {task_id} - Task no longer owned by this worker, skipping")
            continue
        
        # Run validation
        result = validator.validate(task_id)
        
        # Update task based on result
        if result["status"] == "success":
            success = tm.complete_task(
                task_id=task["id"],
                agent_id=worker_id,
                status=TaskStatus.COMPLETED,
                result_data={
                    "validation_result": "passed",
                    "completed_at": datetime.now().isoformat()
                }
            )
            if success:
                print(f"[{worker_id}] ✅ {task_id} - Validation passed")
            else:
                print(f"[{worker_id}] ⚠️  {task_id} - Could not complete task (possibly timed out)")
        else:
            # Extract error details
            error_msg = result.get("error", "Unknown error")
            error_trace = result.get("traceback", "")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            
            # Print failure details to stdout
            print(f"\n[{worker_id}] ❌ {task_id} - Validation failed")
            print(f"Error: {error_msg}")
            if error_trace and error_trace != "TimeoutExpired":
                print(f"Traceback:\n{error_trace}")
            if stderr:
                print(f"Stderr:\n{stderr}")
            if verbose and stdout:
                print(f"Stdout:\n{stdout}")
            print("-" * 80)
            
            # Update task with failure details
            success = tm.complete_task(
                task_id=task["id"],
                agent_id=worker_id,
                status=TaskStatus.FAILED,
                result_data={
                    "validation_result": "failed",
                    "error": error_msg,
                    "traceback": error_trace,
                    "stdout": stdout,
                    "stderr": stderr,
                    "completed_at": datetime.now().isoformat()
                }
            )
            if not success:
                print(f"[{worker_id}] ⚠️  {task_id} - Could not mark task as failed (possibly timed out)")
    
    print(f"[{worker_id}] Worker finished")


def monitor_progress(tm: TaskManager):
    """Display current progress and statistics."""
    summary = tm.get_status_summary()
    
    print("\n" + "="*60)
    print("Validation Progress")
    print("="*60)
    print(f"Total tasks: {summary['total_tasks']}")
    print(f"Status breakdown:")
    for status, count in summary['status_counts'].items():
        if count > 0:
            print(f"  {status}: {count}")
    
    # Show failed tasks
    state = tm._load_state()
    failed_tasks = []
    for task_id, task in state["tasks"].items():
        if task["status"] == TaskStatus.FAILED.value:
            failed_tasks.append({
                "task_id": task["data"]["original_task_id"],
                "error": task["data"].get("error", "Unknown error"),
                "stderr": task["data"].get("stderr", ""),
                "stdout": task["data"].get("stdout", ""),
                "traceback": task["data"].get("traceback", "")
            })
    
    if failed_tasks:
        # Group errors by type
        error_groups = {}
        for task in failed_tasks:
            error_type = task["error"]
            if error_type not in error_groups:
                error_groups[error_type] = []
            error_groups[error_type].append(task)
        
        # Display summary
        print(f"\nFailed tasks ({len(failed_tasks)}):")
        for task in failed_tasks[:10]:  # Show first 10
            print(f"  - {task['task_id']}: {task['error']}")
        if len(failed_tasks) > 10:
            print(f"  ... and {len(failed_tasks) - 10} more")
        
        # Display grouped errors
        print("\n" + "="*60)
        print("Error Groups")
        print("="*60)
        for error_type, tasks in sorted(error_groups.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"\n{error_type} ({len(tasks)} tasks):")
            for task in tasks[:5]:  # Show first 5 of each type
                print(f"  - {task['task_id']}")
            if len(tasks) > 5:
                print(f"  ... and {len(tasks) - 5} more")
        
        # Display all individual errors with details
        print("\n" + "="*60)
        print("All Failed Tasks (Detailed)")
        print("="*60)
        for i, task in enumerate(failed_tasks, 1):
            print(f"\n[{i}] Task: {task['task_id']}")
            print(f"    Error: {task['error']}")
            if task.get('traceback') and task['traceback'] not in ['', 'TimeoutExpired']:
                print(f"    Traceback:")
                for line in task['traceback'].strip().split('\n'):
                    print(f"      {line}")
            if task.get('stderr'):
                print(f"    Stderr:")
                for line in task['stderr'].strip().split('\n')[:10]:  # First 10 lines
                    print(f"      {line}")
                if len(task['stderr'].strip().split('\n')) > 10:
                    print(f"      ... ({len(task['stderr'].strip().split('\n')) - 10} more lines)")
    
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description='Validate all production datapoints using task manager'
    )
    parser.add_argument(
        '--mode',
        choices=['init', 'worker', 'monitor'],
        default='worker',
        help='Mode of operation: init (create tasks), worker (process tasks), monitor (show progress)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of worker processes (default: 4)'
    )
    parser.add_argument(
        '--csv-path',
        type=str,
        default='data/latest.csv',
        help='Path to CSV file (default: data/latest.csv)'
    )
    parser.add_argument(
        '--state-file',
        type=str,
        default='state/validate_prod_dps.json',
        help='Path to task manager state file'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed validation output'
    )
    
    args = parser.parse_args()
    
    # Resolve paths
    base_dir = Path(__file__).parent.parent
    csv_path = base_dir / args.csv_path
    state_file = base_dir / args.state_file
    
    # Ensure state directory exists
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Initialize task manager
    tm = TaskManager(state_file, task_timeout_hours=24)
    
    if args.mode == 'init':
        # Initialize tasks from CSV
        initialize_tasks(tm, csv_path)
        
    elif args.mode == 'monitor':
        # Show current progress
        monitor_progress(tm)
        
    elif args.mode == 'worker':
        # First check if we need to initialize
        summary = tm.get_status_summary()
        if summary['total_tasks'] == 0:
            print("No tasks found, initializing from CSV...")
            initialize_tasks(tm, csv_path)
        
        # Start worker processes
        if args.workers == 1:
            # Single process mode
            worker_process("worker-001", state_file, csv_path, args.verbose)
        else:
            # Multi-process mode
            processes = []
            for i in range(args.workers):
                worker_id = f"worker-{i+1:03d}"
                p = multiprocessing.Process(
                    target=worker_process,
                    args=(worker_id, state_file, csv_path, args.verbose)
                )
                p.start()
                processes.append(p)
            
            # Wait for all workers to complete
            for p in processes:
                p.join()
        
        # Show final summary
        monitor_progress(tm)


if __name__ == "__main__":
    main()