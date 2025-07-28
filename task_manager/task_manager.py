"""
Generic Task Manager - A reusable, workflow-agnostic task coordination system.

This module provides concurrent task management with file-based locking,
parent-child relationships, and automatic timeout handling.
"""

import json
import fcntl
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum


class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskManager:
    """Generic task manager with file-based persistence and locking."""
    
    def __init__(self, state_file: Path, lock_timeout: int = 5, task_timeout_hours: int = 24):
        """
        Initialize the task manager.
        
        Args:
            state_file: Path to the state JSON file
            lock_timeout: Maximum seconds to wait for file lock
            task_timeout_hours: Hours before auto-releasing stale tasks
        """
        self.state_file = Path(state_file)
        self.lock_file = self.state_file.with_suffix('.lock')
        self.lock_timeout = lock_timeout
        self.task_timeout_hours = task_timeout_hours
        
        # Ensure directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize state file if it doesn't exist
        if not self.state_file.exists():
            self._initialize_state()
    
    def _initialize_state(self) -> None:
        """Initialize empty state file."""
        initial_state = {
            "workflow_type": "generic",
            "metadata": {
                "initialized_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat()
            },
            "tasks": {}
        }
        with open(self.state_file, 'w') as f:
            json.dump(initial_state, f, indent=2)
    
    def _acquire_lock(self) -> Any:
        """
        Acquire exclusive file lock.
        
        Returns:
            File handle with lock
            
        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        lock_handle = open(self.lock_file, 'w')
        start_time = time.time()
        
        while True:
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return lock_handle
            except IOError:
                if time.time() - start_time > self.lock_timeout:
                    lock_handle.close()
                    raise TimeoutError(f"Could not acquire lock within {self.lock_timeout} seconds")
                time.sleep(0.01)
    
    def _release_lock(self, lock_handle: Any) -> None:
        """Release file lock."""
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()
    
    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        with open(self.state_file, 'r') as f:
            return json.load(f)
    
    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save state to file atomically."""
        state["metadata"]["last_updated"] = datetime.now().isoformat()
        
        # Write to temporary file first
        temp_file = self.state_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(state, f, indent=2)
        
        # Atomic rename
        temp_file.replace(self.state_file)
    
    def _check_timeouts(self, state: Dict[str, Any]) -> List[str]:
        """
        Check for timed-out tasks and release them.
        
        Args:
            state: Current state dictionary
            
        Returns:
            List of task IDs that were auto-released
        """
        released_tasks = []
        current_time = datetime.now()
        
        for task_id, task in state["tasks"].items():
            if (task["status"] == TaskStatus.IN_PROGRESS.value and 
                task["locked_at"] is not None):
                locked_time = datetime.fromisoformat(task["locked_at"])
                hours_elapsed = (current_time - locked_time).total_seconds() / 3600
                
                if hours_elapsed > self.task_timeout_hours:
                    # Auto-release the task
                    task["status"] = TaskStatus.PENDING.value
                    task["locked_by"] = None
                    task["locked_at"] = None
                    # Clear task_started_at on timeout to allow fresh start
                    if "task_started_at" in task:
                        del task["task_started_at"]
                    released_tasks.append(task_id)
        
        return released_tasks
    
    def create_task(self, task_type: str, data: Dict[str, Any], 
                    parent_id: Optional[str] = None) -> str:
        """
        Create a new task.
        
        Args:
            task_type: Type of the task
            data: Task-specific data
            parent_id: Optional parent task ID
            
        Returns:
            New task ID
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            
            # Generate task ID
            task_id = f"{task_type}_{uuid.uuid4().hex[:8]}"
            
            # Create task
            state["tasks"][task_id] = {
                "type": task_type,
                "status": TaskStatus.PENDING.value,
                "parent_id": parent_id,
                "locked_by": None,
                "locked_at": None,
                "completed_at": None,
                "created_at": datetime.now().isoformat(),
                "data": data
            }
            
            self._save_state(state)
            return task_id
            
        finally:
            self._release_lock(lock_handle)
    
    def get_next_task(self, agent_id: str, task_types: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """
        Get next available task for an agent.
        
        Args:
            agent_id: Unique identifier for the agent
            task_types: Optional list of task types to filter by
            
        Returns:
            Task dictionary with ID, or None if no tasks available
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            
            # Check for timeouts first
            released = self._check_timeouts(state)
            if released:
                self._save_state(state)
            
            # Find next available task
            for task_id, task in state["tasks"].items():
                if task["status"] == TaskStatus.PENDING.value:
                    # Check task type filter
                    if task_types and task["type"] not in task_types:
                        continue
                    
                    # Assign to agent
                    task["status"] = TaskStatus.IN_PROGRESS.value
                    task["locked_by"] = agent_id
                    task["locked_at"] = datetime.now().isoformat()
                    # Add task_started_at for better tracking
                    task["task_started_at"] = datetime.now().isoformat()
                    
                    self._save_state(state)
                    
                    # Return task with ID
                    return {
                        "id": task_id,
                        **task
                    }
            
            return None
            
        finally:
            self._release_lock(lock_handle)
    
    def complete_task(self, task_id: str, agent_id: str, 
                      status: TaskStatus = TaskStatus.COMPLETED,
                      result_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Mark a task as complete.
        
        Args:
            task_id: Task ID to complete
            agent_id: Agent completing the task
            status: Final status
            result_data: Optional result data to merge into task data
            
        Returns:
            True if successful, False if task not found or not locked by agent
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            
            if task_id not in state["tasks"]:
                return False
            
            task = state["tasks"][task_id]
            
            # Verify task is locked by this agent
            if task["locked_by"] != agent_id:
                return False
            
            # Update task
            task["status"] = status.value
            task["completed_at"] = datetime.now().isoformat()
            task["locked_by"] = None
            task["locked_at"] = None
            
            # Merge result data if provided
            if result_data:
                task["data"].update(result_data)
            
            self._save_state(state)
            return True
            
        finally:
            self._release_lock(lock_handle)
    
    def release_task(self, task_id: str, agent_id: str) -> bool:
        """
        Release a task back to pending status.
        
        Args:
            task_id: Task ID to release
            agent_id: Agent releasing the task
            
        Returns:
            True if successful, False if task not found or not locked by agent
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            
            if task_id not in state["tasks"]:
                return False
            
            task = state["tasks"][task_id]
            
            # Verify task is locked by this agent
            if task["locked_by"] != agent_id:
                return False
            
            # Release task
            task["status"] = TaskStatus.PENDING.value
            task["locked_by"] = None
            task["locked_at"] = None
            # Keep task_started_at if it exists (for tracking original start time)
            
            self._save_state(state)
            return True
            
        finally:
            self._release_lock(lock_handle)
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific task by ID.
        
        Args:
            task_id: Task ID to retrieve
            
        Returns:
            Task dictionary or None if not found
        """
        state = self._load_state()
        task = state["tasks"].get(task_id)
        
        if task:
            return {
                "id": task_id,
                **task
            }
        
        return None
    
    def get_task_children(self, parent_id: str) -> List[Dict[str, Any]]:
        """
        Get all child tasks of a parent.
        
        Args:
            parent_id: Parent task ID
            
        Returns:
            List of child task dictionaries
        """
        state = self._load_state()
        children = []
        
        for task_id, task in state["tasks"].items():
            if task["parent_id"] == parent_id:
                children.append({
                    "id": task_id,
                    **task
                })
        
        return children
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics about tasks.
        
        Returns:
            Dictionary with status counts and metadata
        """
        state = self._load_state()
        
        # Count by status
        status_counts = {status.value: 0 for status in TaskStatus}
        
        # Count by type
        type_counts = {}
        
        for task in state["tasks"].values():
            status_counts[task["status"]] += 1
            
            task_type = task["type"]
            if task_type not in type_counts:
                type_counts[task_type] = 0
            type_counts[task_type] += 1
        
        return {
            "total_tasks": len(state["tasks"]),
            "status_counts": status_counts,
            "type_counts": type_counts,
            "metadata": state["metadata"]
        }
    
    def update_workflow_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Update workflow metadata.
        
        Args:
            metadata: Metadata to merge into existing metadata
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            state["metadata"].update(metadata)
            self._save_state(state)
        finally:
            self._release_lock(lock_handle)
    
    def update_task_data(self, task_id: str, data: Dict[str, Any]) -> bool:
        """
        Update task data by merging new data into existing data.
        
        Args:
            task_id: Task ID to update
            data: Data to merge into existing task data
            
        Returns:
            True if successful, False if task not found
        """
        lock_handle = self._acquire_lock()
        try:
            state = self._load_state()
            
            if task_id not in state["tasks"]:
                return False
            
            # Merge new data into existing task data
            state["tasks"][task_id]["data"].update(data)
            state["tasks"][task_id]["updated_at"] = datetime.now().isoformat()
            
            self._save_state(state)
            return True
            
        finally:
            self._release_lock(lock_handle)
