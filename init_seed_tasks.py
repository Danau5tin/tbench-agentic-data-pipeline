"""
Initialize seed_dp tasks from eval_tasks directory.
Extracts task information and creates tasks in the task manager.
"""

import sys
from pathlib import Path

from task_manager.task_manager import TaskManager

# Add parent directories to path for imports
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent.parent / "task_manager"))



def read_file(filepath):
    """Read and return file contents."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        return f"Error reading file: {e}"


def clean_content(content, file_type):
    """Remove boilerplate and clean up content based on file type."""
    if content is None:
        return None
    
    # For Dockerfiles, start from "FROM"
    if file_type == "dockerfile":
        from_index = content.find("FROM")
        if from_index != -1:
            content = content[from_index:]
        else:
            # If no FROM found, try to clean manually
            lines = content.split('\n')
            cleaned_lines = []
            for line in lines:
                if "BENCHMARK DATA SHOULD NEVER APPEAR" in line:
                    continue
                if "terminal-bench-canary" in line:
                    continue
                cleaned_lines.append(line)
            content = '\n'.join(cleaned_lines)
    
    # For task.yaml files, start from "instruction:"
    elif file_type == "task_yaml":
        instruction_index = content.find("instruction:")
        if instruction_index != -1:
            content = content[instruction_index:]
    
    # For test files, remove canary lines and template comments
    elif file_type == "test":
        lines = content.split('\n')
        cleaned_lines = []
        skip_template = False
        
        for i, line in enumerate(lines):
            if "BENCHMARK DATA SHOULD NEVER APPEAR" in line:
                continue
            if "terminal-bench-canary" in line:
                continue
            
            # Skip the template comment block
            if "This is a template test file" in line:
                skip_template = True
                continue
            if skip_template and "by the test harness" in line:
                continue
            if skip_template and line.strip() == "":
                skip_template = False
                continue
                
            cleaned_lines.append(line)
        content = '\n'.join(cleaned_lines)
    
    # Remove multiple consecutive blank lines
    while '\n\n\n' in content:
        content = content.replace('\n\n\n', '\n\n')
    
    # Remove leading/trailing whitespace
    content = content.strip()
    
    return content


def extract_task_data(task_dir):
    """Extract task information from a task directory."""
    data = {
        "task_name": task_dir.name,
        "task_yaml": None,
        "dockerfile": None,
        "test_files": {}
    }
    
    # Read and clean task.yaml
    task_yaml_path = task_dir / "task.yaml"
    task_yaml_content = read_file(task_yaml_path)
    data["task_yaml"] = clean_content(task_yaml_content, "task_yaml")
    
    # Read and clean Dockerfile
    dockerfile_path = task_dir / "Dockerfile"
    dockerfile_content = read_file(dockerfile_path)
    data["dockerfile"] = clean_content(dockerfile_content, "dockerfile")
    
    # Read and clean Python test files from tests/ subdirectory
    tests_dir = task_dir / "tests"
    if tests_dir.exists() and tests_dir.is_dir():
        test_files = sorted([f for f in tests_dir.glob("*.py")])
        for test_file in test_files:
            test_content = read_file(test_file)
            cleaned_test_content = clean_content(test_content, "test")
            data["test_files"][test_file.name] = cleaned_test_content
    
    return data


def main():
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python init_seed_tasks.py <tasks_directory>")
        sys.exit(1)
    
    # Initialize task manager
    state_file = Path(__file__).parent / "state" / "generation_state.json"
    tm = TaskManager(state_file)
    
    # Update workflow metadata
    tm.update_workflow_metadata({
        "workflow_type": "dp_generation",
        "initialization_method": "eval_tasks_directory"
    })
    
    # Path to eval_tasks directory from command line argument
    eval_tasks_dir = Path(sys.argv[1])
    
    if not eval_tasks_dir.exists():
        print(f"Error: tasks directory not found at {eval_tasks_dir}")
        sys.exit(1)
    
    # Get all task directories
    task_dirs = [d for d in eval_tasks_dir.iterdir() if d.is_dir()]
    task_dirs.sort()  # Sort for consistent ordering
    
    print(f"Found {len(task_dirs)} tasks in eval_tasks directory")
    
    # Create seed_dp tasks
    created_count = 0
    for task_dir in task_dirs:
        try:
            # Extract task data
            task_data = extract_task_data(task_dir)
            
            # Create task
            task_id = tm.create_task(
                task_type="seed_dp",
                data=task_data
            )
            
            print(f"Created task {task_id} for {task_dir.name}")
            created_count += 1
            
        except Exception as e:
            print(f"Error processing {task_dir.name}: {e}")
    
    print(f"\nInitialization complete: created {created_count} seed_dp tasks")
    
    # Show status
    summary = tm.get_status_summary()
    print(f"\nTask summary:")
    print(f"  Total tasks: {summary['total_tasks']}")
    print(f"  By status: {summary['status_counts']}")
    print(f"  By type: {summary['type_counts']}")


if __name__ == "__main__":
    main()