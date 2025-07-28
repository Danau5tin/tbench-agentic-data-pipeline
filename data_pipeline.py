#!/usr/bin/env python3
"""
Data Pipeline CLI - Domain-specific wrapper for data generation workflow.
Provides agent-friendly commands for managing datapoint generation tasks.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from task_manager.task_manager import TaskManager, TaskStatus

# Add task_manager to path
sys.path.append(str(Path(__file__).parent.parent.parent / "task_manager"))



class DataPipeline:
    """Wrapper for task manager with data generation specific logic."""
    
    def __init__(self):
        self.state_file = Path(__file__).parent / "state" / "generation_state.json"
        self.artifacts_dir = Path(__file__).parent / "artifacts"
        self.tm = TaskManager(self.state_file)
        
        # Ensure artifact directories exist (no longer need draft_dps)
        for subdir in ["seed_dps", "final_dps"]:
            (self.artifacts_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    def get_artifact_path(self, task_id: str, task_type: str) -> Path:
        """Get the artifact path for a given task."""
        type_to_dir = {
            "seed_dp": "seed_dps",
            "final_dp": "final_dps"
        }
        subdir = type_to_dir.get(task_type, "final_dps")
        
        # Draft DPs no longer use artifacts - they're in shared workspace
        if task_type == "draft_dp":
            # Return path to shared workspace draft spec
            return Path("shared_workspace/data_points") / task_id / "draft_spec.md"
        
        # Default to JSON for backward compatibility
        return self.artifacts_dir / subdir / f"{task_id}.json"
    
    def cmd_next(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """Get next available task."""
        # Use a default agent_id based on task type
        agent_id = f"{task_type}_agent" if task_type else "default_agent"
        task_types = [task_type] if task_type else None
        task = self.tm.get_next_task(agent_id, task_types)
        
        if not task:
            return {"status": "no_tasks", "message": "No available tasks"}
        
        # Include artifact path in response
        task["artifact_path"] = str(self.get_artifact_path(task["id"], task["type"]))
        
        return {
            "status": "success",
            "task": task
        }
    
    def cmd_complete(self, task_id: str, status: str, 
                     artifact_file: Optional[str] = None) -> Dict[str, Any]:
        """Complete a task with optional artifact."""
        # Map string status to enum
        status_map = {
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
            "rejected": TaskStatus.CANCELLED
        }
        
        if status not in status_map:
            return {"status": "error", "message": f"Invalid status: {status}"}
        
        # Get task info before completing
        task = self.tm.get_task(task_id)
        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}
        
        # Use the same agent_id that locked the task
        agent_id = task.get("locked_by", "unknown")
        
        # Save artifact if provided
        result_data = {}
        if artifact_file and Path(artifact_file).exists():
            artifact_path = self.get_artifact_path(task_id, task["type"])
            artifact_content = Path(artifact_file).read_text()
            artifact_path.write_text(artifact_content)
            result_data["artifact_saved"] = str(artifact_path)
        
        # Complete the task
        success = self.tm.complete_task(
            task_id=task_id,
            agent_id=agent_id,
            status=status_map[status],
            result_data=result_data
        )
        
        if success:
            return {"status": "success", "message": f"Task {task_id} marked as {status}"}
        else:
            return {"status": "error", "message": "Failed to complete task (wrong agent or not found)"}
    
    def cmd_release(self, task_id: str) -> Dict[str, Any]:
        """Release a task back to pending."""
        # Get task to find who locked it
        task = self.tm.get_task(task_id)
        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}
        
        agent_id = task.get("locked_by", "unknown")
        success = self.tm.release_task(task_id, agent_id)
        
        if success:
            return {"status": "success", "message": f"Task {task_id} released"}
        else:
            return {"status": "error", "message": "Failed to release task"}
    
    def cmd_create_task(self, task_type: str, parent_id: Optional[str], 
                        data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new task."""
        task_id = self.tm.create_task(
            task_type=task_type,
            data=data,
            parent_id=parent_id
        )
        
        return {
            "status": "success",
            "task_id": task_id,
            "message": f"Created task {task_id}"
        }
    
    def cmd_status(self) -> Dict[str, Any]:
        """Get workflow status summary."""
        summary = self.tm.get_status_summary()
        
        # Add completion rates
        if summary["type_counts"]:
            for task_type in summary["type_counts"]:
                total = summary["type_counts"][task_type]
                completed = 0
                
                # Count completed tasks of this type
                state = self.tm._load_state()
                for task in state["tasks"].values():
                    if task["type"] == task_type and task["status"] == "completed":
                        completed += 1
                
                summary[f"{task_type}_completion_rate"] = f"{completed}/{total} ({completed/total*100:.1f}%)"
        
        return summary
    
    def cmd_info(self, task_id: str) -> Dict[str, Any]:
        """Get detailed information about a task."""
        task = self.tm.get_task(task_id)
        
        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}
        
        # Add artifact path
        task["artifact_path"] = str(self.get_artifact_path(task_id, task["type"]))
        
        # Add children info
        children = self.tm.get_task_children(task_id)
        task["children_count"] = len(children)
        task["children_ids"] = [child["id"] for child in children]
        
        return task
    
    def cmd_list(self, task_type: Optional[str] = None, 
                 status: Optional[str] = None) -> Dict[str, Any]:
        """List tasks with optional filters."""
        state = self.tm._load_state()
        tasks = []
        
        for task_id, task in state["tasks"].items():
            # Apply filters
            if task_type and task["type"] != task_type:
                continue
            if status and task["status"] != status:
                continue
            
            tasks.append({
                "id": task_id,
                "type": task["type"],
                "status": task["status"],
                "parent_id": task["parent_id"],
                "locked_by": task["locked_by"],
                "created_at": task["created_at"]
            })
        
        return {
            "count": len(tasks),
            "tasks": tasks
        }
    
    def cmd_get_artifact(self, task_id: str) -> str:
        """Get artifact content for a task."""
        task = self.tm.get_task(task_id)
        
        if not task:
            return f"Error: Task {task_id} not found"
        
        # For draft tasks, read from shared workspace
        if task["type"] == "draft_dp":
            draft_path = Path("shared_workspace/data_points") / task_id / "draft_spec.md"
            if draft_path.exists():
                return draft_path.read_text()
            else:
                return f"Error: No draft specification found at {draft_path}"
        
        artifact_path = self.get_artifact_path(task_id, task["type"])
        
        if artifact_path.exists():
            # Return the raw content as string
            return artifact_path.read_text()
        else:
            # For seed tasks, return the embedded data as JSON string
            if task["type"] == "seed_dp":
                return json.dumps(task["data"], indent=2)
            else:
                return f"Error: No artifact found for task {task_id}"
    
    def cmd_save_artifact(self, task_id: str, file_path: str) -> Dict[str, Any]:
        """Save artifact for a task."""
        task = self.tm.get_task(task_id)
        
        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}
        
        if not Path(file_path).exists():
            return {"status": "error", "message": f"File {file_path} not found"}
        
        artifact_path = self.get_artifact_path(task_id, task["type"])
        content = Path(file_path).read_text()
        
        # Validate JSON
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return {"status": "error", "message": f"Invalid JSON: {e}"}
        
        artifact_path.write_text(content)
        
        return {
            "status": "success",
            "message": f"Artifact saved to {artifact_path}"
        }
    
    def cmd_add_artifact(self, task_id: str, file_path: str) -> Dict[str, Any]:
        """Add artifact file for a task (no longer used for draft_dp)."""
        task = self.tm.get_task(task_id)
        
        if not task:
            return {"status": "error", "message": f"Task {task_id} not found"}
        
        # Draft DPs now use shared workspace directly
        if task["type"] == "draft_dp":
            return {
                "status": "error", 
                "message": "Draft specifications should be created directly in shared_workspace/data_points/{task_id}/draft_spec.md"
            }
        
        if not Path(file_path).exists():
            return {"status": "error", "message": f"File {file_path} not found"}
        
        # Determine artifact path based on file extension
        input_path = Path(file_path)
        artifact_dir = self.artifacts_dir / {
            "seed_dp": "seed_dps",
            "final_dp": "final_dps"
        }.get(task["type"], "final_dps")
        
        # Keep the original file extension
        artifact_path = artifact_dir / f"{task_id}{input_path.suffix}"
        
        # Move file to artifacts directory
        import shutil
        shutil.move(str(input_path), str(artifact_path))
        
        # Update task data with artifact info
        update_data = {"artifact_path": str(artifact_path), "artifact_added": True}
        self.tm.update_task_data(task_id, update_data)
        
        return {
            "status": "success",
            "message": f"Artifact added to {artifact_path}",
            "artifact_path": str(artifact_path)
        }


def main():
    parser = argparse.ArgumentParser(description="Data Pipeline CLI for DP generation workflow")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # next command
    next_parser = subparsers.add_parser("next", help="Get next available task")
    next_parser.add_argument("--task-type", help="Filter by task type (seed_dp, draft_dp)")
    
    # complete command
    complete_parser = subparsers.add_parser("complete", help="Complete a task")
    complete_parser.add_argument("task_id", help="Task ID to complete")
    complete_parser.add_argument("--status", required=True, 
                                 choices=["completed", "failed", "rejected"],
                                 help="Completion status")
    complete_parser.add_argument("--artifact", help="Path to artifact file")
    
    # release command
    release_parser = subparsers.add_parser("release", help="Release a task")
    release_parser.add_argument("task_id", help="Task ID to release")
    
    # create-task command
    create_parser = subparsers.add_parser("create-task", help="Create a new task")
    create_parser.add_argument("--type", required=True, help="Task type")
    create_parser.add_argument("--parent", help="Parent task ID")
    create_parser.add_argument("--data", required=True, help="Task data as JSON string")
    
    # status command
    subparsers.add_parser("status", help="Show workflow status")
    
    # info command
    info_parser = subparsers.add_parser("info", help="Get task information")
    info_parser.add_argument("task_id", help="Task ID")
    
    # list command
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--type", help="Filter by task type")
    list_parser.add_argument("--status", help="Filter by status")
    
    # get-artifact command
    get_artifact_parser = subparsers.add_parser("get-artifact", help="Get task artifact")
    get_artifact_parser.add_argument("task_id", help="Task ID")
    
    # save-artifact command
    save_artifact_parser = subparsers.add_parser("save-artifact", help="Save task artifact")
    save_artifact_parser.add_argument("task_id", help="Task ID")
    save_artifact_parser.add_argument("--file", required=True, help="Path to artifact file")
    
    # add-artifact command
    add_artifact_parser = subparsers.add_parser("add-artifact", help="Add artifact file for a task")
    add_artifact_parser.add_argument("--task-id", required=True, help="Task ID")
    add_artifact_parser.add_argument("--file", required=True, help="Path to artifact file")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Initialize pipeline
    pipeline = DataPipeline()
    
    # Execute command
    try:
        if args.command == "next":
            result = pipeline.cmd_next(args.task_type)
        elif args.command == "complete":
            result = pipeline.cmd_complete(args.task_id, args.status, args.artifact)
        elif args.command == "release":
            result = pipeline.cmd_release(args.task_id)
        elif args.command == "create-task":
            data = json.loads(args.data)
            result = pipeline.cmd_create_task(args.type, args.parent, data)
        elif args.command == "status":
            result = pipeline.cmd_status()
        elif args.command == "info":
            result = pipeline.cmd_info(args.task_id)
        elif args.command == "list":
            result = pipeline.cmd_list(args.type, args.status)
        elif args.command == "get-artifact":
            result = pipeline.cmd_get_artifact(args.task_id)
            # Since cmd_get_artifact now returns a string, print it directly
            print(result)
            return
        elif args.command == "save-artifact":
            result = pipeline.cmd_save_artifact(args.task_id, args.file)
        elif args.command == "add-artifact":
            result = pipeline.cmd_add_artifact(args.task_id, args.file)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
        
        # Output result as JSON
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        error_result = {"status": "error", "message": str(e)}
        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
    # pipeline = DataPipeline()
    # print(pipeline.cmd_status())  # Print initial status for debugging