# Task Manager - Generic Concurrent Task Coordination

A reusable Python module for managing concurrent task processing with file-based persistence, atomic locking, and automatic timeout handling.

## Features

- **Concurrent Access**: File-based locking ensures multiple agents can safely access tasks
- **Parent-Child Relationships**: Support for hierarchical task dependencies
- **Auto-Recovery**: Automatic release of stale tasks after timeout (configurable, default 24 hours)
- **Status Tracking**: Tasks progress through states: pending → in_progress → completed/failed/cancelled
- **Workflow Agnostic**: No domain-specific logic, suitable for any task-based workflow
- **Multiple Workflows**: Single instance can manage multiple independent workflows via different state files

## Installation

Simply import the module:

```python
from task_manager import TaskManager, TaskStatus
```

## Basic Usage

### Initialize Task Manager

```python
from pathlib import Path
from task_manager import TaskManager

# Each workflow gets its own state file
tm = TaskManager(
    state_file=Path("states/my_workflow.json"),
    lock_timeout=5,        # seconds to wait for lock
    task_timeout_hours=24  # hours before auto-releasing tasks
)
```

### Create Tasks

```python
# Create a root task
task_id = tm.create_task(
    task_type="analyze",
    data={"file": "data.csv", "params": {"threshold": 0.8}}
)

# Create a child task
child_id = tm.create_task(
    task_type="validate", 
    data={"validation_type": "schema"},
    parent_id=task_id
)
```

### Get and Process Tasks

```python
# Agent requests next available task
task = tm.get_next_task(
    agent_id="worker-001",
    task_types=["analyze", "validate"]  # optional filter
)

if task:
    print(f"Processing task {task['id']} of type {task['type']}")
    # Do work...
    
    # Complete the task
    success = tm.complete_task(
        task_id=task["id"],
        agent_id="worker-001",
        status=TaskStatus.COMPLETED,
        result_data={"output": "results.json"}  # optional
    )
```

### Query Tasks

```python
# Get specific task
task = tm.get_task("analyze_12345678")

# Get all children of a task
children = tm.get_task_children("analyze_12345678")

# Get status summary
summary = tm.get_status_summary()
print(f"Total tasks: {summary['total_tasks']}")
print(f"By status: {summary['status_counts']}")
print(f"By type: {summary['type_counts']}")
```

## Task Structure

Each task contains:

```python
{
    "id": "task_type_12345678",         # Auto-generated
    "type": "task_type",                # User-defined type
    "status": "pending",                # Status enum value
    "parent_id": null,                  # Parent task ID or null
    "locked_by": null,                  # Agent ID when in_progress
    "locked_at": null,                  # ISO timestamp when locked
    "created_at": "2024-01-01T10:00:00",  # ISO timestamp
    "completed_at": null,               # ISO timestamp when done
    "data": {                           # User-defined data
        "custom": "fields"
    }
}
```

## Multiple Workflows

Support different workflows by using different state files:

```python
# Data processing workflow
data_tm = TaskManager(Path("states/data_processing.json"))

# Code review workflow  
review_tm = TaskManager(Path("states/code_review.json"))

# Testing workflow
test_tm = TaskManager(Path("states/test_execution.json"))
```

## Advanced Usage

### Release Task

If an agent can't complete a task:

```python
tm.release_task(task_id="analyze_12345678", agent_id="worker-001")
```

### Update Workflow Metadata

```python
tm.update_workflow_metadata({
    "version": "2.0",
    "environment": "production",
    "started_by": "scheduler"
})
```

### Handle Failures

```python
try:
    # Process task...
    if error_occurred:
        tm.complete_task(
            task_id=task["id"],
            agent_id="worker-001", 
            status=TaskStatus.FAILED,
            result_data={"error": str(error)}
        )
except Exception as e:
    # Release task for retry
    tm.release_task(task["id"], "worker-001")
    raise
```

## State File Structure

The state file is a JSON file with the following structure:

```json
{
    "workflow_type": "generic",
    "metadata": {
        "initialized_at": "2024-01-01T10:00:00",
        "last_updated": "2024-01-01T12:00:00",
        "custom_field": "custom_value"
    },
    "tasks": {
        "task_id": {
            "type": "task_type",
            "status": "pending",
            "parent_id": null,
            "locked_by": null,
            "locked_at": null,
            "created_at": "2024-01-01T10:00:00",
            "completed_at": null,
            "data": {}
        }
    }
}
```

## Thread Safety

The task manager uses file locking (`fcntl`) to ensure thread/process safety:
- Multiple agents can request tasks concurrently
- Task assignment is atomic
- State updates are atomic via temp file + rename

## Best Practices

1. **Task Granularity**: Keep tasks small enough to complete within timeout
2. **Idempotency**: Design task processing to be safely retryable
3. **Data Storage**: Store large artifacts outside the state file
4. **Error Handling**: Use appropriate status (failed/cancelled) for different scenarios
5. **Agent IDs**: Use unique, persistent agent identifiers

## Limitations

- **Scale**: File-based storage suitable for thousands, not millions of tasks
- **Performance**: File I/O for each operation (no caching)
- **Distribution**: Single-machine only (no network coordination)
- **Features**: No scheduling, priorities, or automatic retries (implement in wrapper)

## Example: Multi-Stage Pipeline

```python
# Stage 1: Create initial tasks
for item in dataset:
    tm.create_task("extract", {"source": item})

# Stage 2: Workers process extraction
while True:
    task = tm.get_next_task("extractor-1", ["extract"])
    if not task:
        break
    
    # Process and create transform tasks
    result = extract_data(task["data"])
    tm.create_task("transform", {"data": result}, parent_id=task["id"])
    tm.complete_task(task["id"], "extractor-1")

# Stage 3: Different workers do transformation
while True:
    task = tm.get_next_task("transformer-1", ["transform"])
    if not task:
        break
    
    result = transform_data(task["data"])
    tm.complete_task(task["id"], "transformer-1", 
                    result_data={"output": result})
```