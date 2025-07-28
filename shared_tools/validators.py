#!/usr/bin/env python3
"""
Validators for datapoint validation.
Each validator handles a specific aspect of validation.
"""

import ast
import json
import os
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional


@dataclass
class ValidationResult:
    """Result from a validator."""
    valid: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


class Validator(ABC):
    """Base validator interface."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Name for this validator."""
        pass
    
    @abstractmethod
    def validate(self, task_data: Dict[str, str], context: Dict[str, Any]) -> ValidationResult:
        """Execute validation. Context contains results from previous validators."""
        pass


class DockerfileValidator(Validator):
    """Validates Dockerfile syntax and builds the image."""
    
    @property
    def name(self) -> str:
        return "dockerfile"
    
    def validate(self, task_data: Dict[str, str], context: Dict[str, Any]) -> ValidationResult:
        dockerfile_content = task_data.get('dockerfile', '')
        task_id = task_data.get('task_id', 'unknown')
        
        if not dockerfile_content:
            return ValidationResult(
                valid=False,
                message="No Dockerfile content found"
            )
        
        # Check required dependencies
        dep_valid, dep_message = self._check_required_dependencies(dockerfile_content)
        if not dep_valid:
            return ValidationResult(
                valid=False,
                message=f"Dependencies: {dep_message}"
            )
        
        # Build the Docker image
        valid, result = self._build_dockerfile(dockerfile_content, task_id, task_data)
        if valid:
            # Store image tag in context for other validators
            context['image_tag'] = result
            return ValidationResult(
                valid=True,
                message="Dockerfile builds successfully",
                details={'image_tag': result}
            )
        else:
            return ValidationResult(
                valid=False,
                message=result
            )
    
    def _check_required_dependencies(self, dockerfile_content: str) -> Tuple[bool, str]:
        """Check if Dockerfile includes required terminal-bench dependencies."""
        # Check if it's a standard t-bench image
        if 'ghcr.io/laude-institute/t-bench' in dockerfile_content:
            return True, "Using standard t-bench base image (dependencies pre-installed)"
        
        # For non-standard images, check for required dependencies
        missing_deps = []
        
        if 'tmux' not in dockerfile_content:
            missing_deps.append('tmux')
        
        if 'asciinema' not in dockerfile_content:
            missing_deps.append('asciinema')
        
        if missing_deps:
            return False, f"Missing required dependencies: {', '.join(missing_deps)}"
        
        return True, "All required dependencies found"
    
    def _build_dockerfile(self, dockerfile_content: str, task_id: str, task_data: Dict[str, str]) -> Tuple[bool, str]:
        """Validate Dockerfile by actually building it."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dockerfile_path = os.path.join(temp_dir, 'Dockerfile')
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            # Handle additional files if present
            if 'additional_files' in task_data and task_data['additional_files']:
                try:
                    additional_files = json.loads(task_data['additional_files'])
                    if isinstance(additional_files, dict):
                        for file_path, content in additional_files.items():
                            full_path = os.path.join(temp_dir, file_path)
                            os.makedirs(os.path.dirname(full_path), exist_ok=True)
                            with open(full_path, 'w', encoding='utf-8') as f:
                                f.write(content)
                except json.JSONDecodeError as e:
                    return False, f"Failed to parse additional_files JSON: {e}"
                except Exception as e:
                    return False, f"Failed to write additional files: {e}"
            
            # Generate a unique tag for this validation
            image_tag = f"validation-{task_id}-{os.getpid()}"
            
            try:
                # Build the Docker image
                result = subprocess.run(
                    ['docker', 'build', '--no-cache', '--force-rm', '-t', image_tag, '-f', dockerfile_path, temp_dir],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    return False, f"Dockerfile build failed:\n{result.stderr}"
                
                return True, image_tag
            
            except FileNotFoundError:
                raise Exception("Docker is not installed or not in PATH. Please install Docker to validate Dockerfiles.")
            
            except Exception as e:
                # Try to clean up on any error
                try:
                    subprocess.run(['docker', 'rmi', '-f', image_tag], capture_output=True)
                except Exception:
                    pass
                raise e


class TestSyntaxValidator(Validator):
    """Validates Python test syntax and extracts test function names."""
    
    @property
    def name(self) -> str:
        return "test_syntax"
    
    def validate(self, task_data: Dict[str, str], context: Dict[str, Any]) -> ValidationResult:
        test_content = task_data.get('test_functions', '')
        
        if not test_content:
            return ValidationResult(
                valid=False,
                message="No test functions found"
            )
        
        # Validate syntax
        valid, message, test_names = self._validate_python_syntax(test_content)
        
        if valid:
            # Store test names in context for other validators
            context['test_names'] = test_names
            context['test_content'] = test_content
            
            # Check imports
            import_valid, import_message = self._validate_test_imports(test_content)
            
            return ValidationResult(
                valid=True,
                message=f"{message}. {import_message}",
                details={
                    'test_names': test_names,
                    'expected_tests': len(test_names),
                    'import_check': {'valid': import_valid, 'message': import_message}
                }
            )
        else:
            return ValidationResult(
                valid=False,
                message=message
            )
    
    def _validate_python_syntax(self, code: str, filename: str = "test_functions") -> Tuple[bool, str, List[str]]:
        """Validate Python syntax and attempt compilation. Returns (valid, message, test_function_names)."""
        try:
            # Parse the code as an AST
            tree = ast.parse(code, filename=filename)
            
            # Try to compile it
            compile(tree, filename=filename, mode='exec')
            
            # Check for test functions
            function_names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith('test_'):
                        function_names.append(node.name)
            
            if not function_names:
                return False, "No test functions found (functions should start with 'test_')", []
            
            return True, f"Found {len(function_names)} test functions", function_names
        
        except SyntaxError as e:
            return False, f"Python syntax error at line {e.lineno}: {e.msg}\n{e.text}", []
        
        except Exception as e:
            return False, f"Python compilation error: {str(e)}", []
    
    def _validate_test_imports(self, code: str) -> Tuple[bool, str]:
        """Check if test imports are reasonable."""
        try:
            tree = ast.parse(code)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}" if module else alias.name)
            
            # Common imports that should be available
            problematic_imports = []
            safe_imports = ['os', 'sys', 'subprocess', 'json', 're', 'glob', 
                          'pathlib', 'shutil', 'tempfile', 'ast', 'sqlite3',
                          'urllib', 'urllib.request', 'urllib.parse']
            
            for imp in imports:
                base_module = imp.split('.')[0]
                if base_module not in safe_imports and not base_module.startswith('_'):
                    problematic_imports.append(imp)
            
            if problematic_imports:
                return True, f"Warning: These imports might need to be available in the test environment: {', '.join(problematic_imports)}"
            
            return True, "All imports appear to be standard library modules"
        
        except Exception as e:
            return False, f"Failed to analyze imports: {str(e)}"


class TestWeightsValidator(Validator):
    """Validates test weights configuration."""
    
    @property
    def name(self) -> str:
        return "test_weights"
    
    def validate(self, task_data: Dict[str, str], context: Dict[str, Any]) -> ValidationResult:
        test_weights_str = task_data.get('test_weights', '{}')
        
        # Get test names from context
        test_names = context.get('test_names', [])
        if not test_names:
            return ValidationResult(
                valid=False,
                message="Cannot validate weights - no test names found in context"
            )
        
        # Parse test weights
        try:
            test_weights = json.loads(test_weights_str)
        except json.JSONDecodeError as e:
            return ValidationResult(
                valid=False,
                message=f"Invalid JSON in test_weights: {e}"
            )
        
        # Check if test_weights is empty
        if not test_weights:
            return ValidationResult(
                valid=False,
                message="Test weights not assigned yet (empty JSON object)"
            )
        
        errors = []
        
        # Validate all tests have weights
        missing_weights = [name for name in test_names if name not in test_weights]
        if missing_weights:
            errors.append(f"Missing weights for tests: {', '.join(missing_weights)}")
        
        # Check for extra weights
        extra_weights = [name for name in test_weights if name not in test_names]
        if extra_weights:
            errors.append(f"Weights defined for non-existent tests: {', '.join(extra_weights)}")
        
        # Validate weight values
        for test_name, weight in test_weights.items():
            if not isinstance(weight, (int, float)):
                errors.append(f"Weight for '{test_name}' is not a number: {weight}")
            elif weight < 0:
                errors.append(f"Weight for '{test_name}' is negative: {weight}")
            elif weight > 1:
                errors.append(f"Weight for '{test_name}' is greater than 1: {weight}")
        
        # Check sum equals 1.0
        if all(isinstance(w, (int, float)) for w in test_weights.values()):
            total_weight = sum(test_weights.values())
            if not (0.999 <= total_weight <= 1.001):
                errors.append(f"Weights sum to {total_weight:.6f}, not 1.0")
        
        if errors:
            return ValidationResult(
                valid=False,
                message="; ".join(errors),
                details={'errors': errors}
            )
        else:
            return ValidationResult(
                valid=True,
                message="Test weights are valid"
            )


class ContainerExecutionValidator(Validator):
    """Validates by running tests in the built container."""
    
    @property
    def name(self) -> str:
        return "container_execution"
    
    def validate(self, task_data: Dict[str, str], context: Dict[str, Any]) -> ValidationResult:
        # Check prerequisites
        image_tag = context.get('image_tag')
        if not image_tag:
            return ValidationResult(
                valid=False,
                message="Cannot execute tests - no Docker image available"
            )
        
        test_content = context.get('test_content')
        test_names = context.get('test_names', [])
        if not test_content or not test_names:
            return ValidationResult(
                valid=False,
                message="Cannot execute tests - no test content available"
            )
        
        task_id = task_data.get('task_id', 'unknown')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Parse and create test infrastructure
                test_functions = self._parse_test_functions_json(test_content)
                self._create_test_infrastructure(temp_dir, test_functions)
                
                # Run container with tests
                test_valid, test_message, test_output = self._run_container_with_tests(
                    image_tag, temp_dir, task_id, task_data
                )
                
                if not test_valid:
                    return ValidationResult(
                        valid=False,
                        message=test_message,
                        details={'raw_output': test_output}
                    )
                
                # Parse test results
                test_results = self._parse_test_output(test_output)
                
                # Validate all tests failed
                expected_count = len(test_names)
                failed_count = test_results.get('failed', 0)
                passed_count = test_results.get('passed', 0)
                total_discovered = test_results.get('total_tests', 0)
                
                if failed_count == 0:
                    return ValidationResult(
                        valid=False,
                        message=f"No tests failed - at least one test must fail for validation (discovered {total_discovered} tests)",
                        details={'test_results': test_results, 'raw_output': test_output}
                    )
                elif passed_count > 0:
                    return ValidationResult(
                        valid=False,
                        message=f"Some tests passed ({passed_count} passed, {failed_count} failed) - ALL tests should fail for validation",
                        details={'test_results': test_results, 'raw_output': test_output}
                    )
                elif failed_count != expected_count:
                    return ValidationResult(
                        valid=False,
                        message=f"Test count mismatch: expected {expected_count} tests to fail, but {failed_count} failed (discovered {total_discovered} tests)",
                        details={'test_results': test_results, 'raw_output': test_output}
                    )
                else:
                    return ValidationResult(
                        valid=True,
                        message=f"All {failed_count} tests failed as expected",
                        details={
                            'test_results': test_results,
                            'expected_tests': expected_count,
                            'raw_output': test_output
                        }
                    )
                    
            except Exception as e:
                return ValidationResult(
                    valid=False,
                    message=f"Test execution error: {str(e)}"
                )
    
    def _parse_test_functions_json(self, test_functions_str: str) -> List[Dict[str, str]]:
        """Parse test_functions JSON string into a list of test definitions."""
        try:
            # First try to parse as JSON array
            test_functions = json.loads(test_functions_str)
            if isinstance(test_functions, list):
                return test_functions
            else:
                # If it's not a list, treat it as a single test
                return [{"name": "test_main", "code": test_functions_str}]
        except json.JSONDecodeError:
            # If JSON parsing fails, treat the entire string as Python code
            tests = []
            try:
                tree = ast.parse(test_functions_str)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                        # Get the source code for this function
                        func_code = ast.get_source_segment(test_functions_str, node)
                        if func_code:
                            tests.append({"name": node.name, "code": func_code})
                
                # If no test functions found, use the entire content
                if not tests:
                    tests = [{"name": "test_main", "code": test_functions_str}]
                    
                return tests
            except Exception:
                # Fallback: treat entire content as one test
                return [{"name": "test_main", "code": test_functions_str}]
    
    def _create_test_infrastructure(self, temp_dir: str, test_functions: List[Dict[str, str]]) -> str:
        """Create test files and infrastructure in a temporary directory."""
        # Create tests directory
        tests_dir = os.path.join(temp_dir, "tests")
        os.makedirs(tests_dir, exist_ok=True)
        
        # Check if we're dealing with a single blob of test code or multiple functions
        if len(test_functions) == 1 and 'def test_' in test_functions[0].get('code', ''):
            # This is likely all test functions in one blob - write to single file
            test_code = test_functions[0].get('code', '')
            test_path = os.path.join(tests_dir, "test_outputs.py")
            with open(test_path, 'w') as f:
                f.write(test_code)
        else:
            # Multiple separate test functions - still write to single file for pytest
            all_test_code = ""
            
            # Collect imports first
            imports_seen = set()
            for test in test_functions:
                test_code = test.get('code', '')
                # Extract imports
                lines = test_code.split('\n')
                for line in lines:
                    if line.strip().startswith('import ') or line.strip().startswith('from '):
                        imports_seen.add(line.strip())
            
            # Write all imports at the top
            if imports_seen:
                all_test_code = '\n'.join(sorted(imports_seen)) + '\n\n'
            else:
                # Add default imports if none found
                all_test_code = "import os\nimport sys\n\n"
            
            # Add all test functions
            for test in test_functions:
                test_code = test.get('code', '')
                # Remove imports from individual test code
                lines = test_code.split('\n')
                non_import_lines = [line for line in lines 
                                   if not (line.strip().startswith('import ') or 
                                          line.strip().startswith('from '))]
                all_test_code += '\n'.join(non_import_lines).strip() + '\n\n'
            
            test_path = os.path.join(tests_dir, "test_outputs.py")
            with open(test_path, 'w') as f:
                f.write(all_test_code.strip())
        
        # Create setup-pytest.sh script
        setup_script = """#!/bin/bash

# Determine which python command to use
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "ERROR: No python interpreter found"
    exit 1
fi

# Install pytest if not available
if ! $PYTHON_CMD -m pytest --version &> /dev/null 2>&1; then
    echo "Installing pytest..."
    # Try pip first
    if command -v pip &> /dev/null; then
        pip install pytest
    elif command -v pip3 &> /dev/null; then
        pip3 install pytest
    # If pip not available, try apt-get
    elif command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3-pytest
    else
        echo "ERROR: Could not install pytest - no package manager found"
        exit 1
    fi
fi
"""
        
        setup_path = os.path.join(tests_dir, "setup-pytest.sh")
        with open(setup_path, 'w') as f:
            f.write(setup_script)
        os.chmod(setup_path, 0o755)
        
        # Create run-pytest.sh script
        run_pytest_script = """#!/bin/bash

# Determine which python command to use
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "ERROR: No python interpreter found"
    exit 1
fi

$PYTHON_CMD -m pytest $TEST_DIR/test_outputs.py -rA
"""
        
        run_pytest_path = os.path.join(tests_dir, "run-pytest.sh")
        with open(run_pytest_path, 'w') as f:
            f.write(run_pytest_script)
        os.chmod(run_pytest_path, 0o755)
        
        # Create main run-tests.sh script
        run_tests_script = """#!/bin/bash

export TEST_DIR=/tests/tests

# Setup and run pytest
source $TEST_DIR/setup-pytest.sh
bash $TEST_DIR/run-pytest.sh
"""
        
        run_tests_path = os.path.join(temp_dir, "run-tests.sh")
        with open(run_tests_path, 'w') as f:
            f.write(run_tests_script)
        os.chmod(run_tests_path, 0o755)
        
        return tests_dir
    
    def _run_container_with_tests(self, image_tag: str, temp_dir: str, task_id: str, task_data: Dict[str, str]) -> Tuple[bool, str, str]:
        """Run a container, copy tests and additional files, execute tests, and return results."""
        container_name = f"test-validation-{task_id}-{os.getpid()}"
        
        # Handle additional files if present
        if 'additional_files' in task_data and task_data['additional_files']:
            try:
                additional_files = json.loads(task_data['additional_files'])
                if isinstance(additional_files, dict):
                    for file_path, content in additional_files.items():
                        full_path = os.path.join(temp_dir, file_path)
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(content)
            except json.JSONDecodeError as e:
                return False, f"Failed to parse additional_files JSON: {e}", ""
            except Exception as e:
                return False, f"Failed to write additional files: {e}", ""
        
        try:
            # Start the container
            start_result = subprocess.run(
                ['docker', 'run', '-d', '--name', container_name, image_tag, 'sleep', 'infinity'],
                capture_output=True,
                text=True
            )
            
            if start_result.returncode != 0:
                return False, f"Failed to start container: {start_result.stderr}", ""
            
            # Check if tmux is available
            tmux_check = subprocess.run(
                ['docker', 'exec', container_name, 'which', 'tmux'],
                capture_output=True,
                text=True
            )
            
            if tmux_check.returncode != 0:
                return False, "tmux is not installed in the container. Terminal-Bench requires tmux.", ""
            
            # Check if asciinema is available
            asciinema_check = subprocess.run(
                ['docker', 'exec', container_name, 'which', 'asciinema'],
                capture_output=True,
                text=True
            )
            
            if asciinema_check.returncode != 0:
                return False, "asciinema is not installed in the container. Terminal-Bench requires asciinema.", ""
            
            # Copy test files to container
            copy_result = subprocess.run(
                ['docker', 'cp', temp_dir + '/.', f"{container_name}:/tests"],
                capture_output=True,
                text=True
            )
            
            if copy_result.returncode != 0:
                return False, f"Failed to copy tests: {copy_result.stderr}", ""
            
            # Execute tests
            exec_result = subprocess.run(
                ['docker', 'exec', container_name, 'bash', '/tests/run-tests.sh'],
                capture_output=True,
                text=True
            )
            
            test_output = exec_result.stdout + "\n" + exec_result.stderr
            
            # Return test output regardless of exit code
            return True, "Tests executed", test_output
                
        finally:
            # Always clean up the container
            subprocess.run(['docker', 'stop', container_name], capture_output=True)
            subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True)
    
    def _parse_test_output(self, test_output: str) -> Dict[str, Any]:
        """Parse test output to extract test results."""
        results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'errors': 0,
            'test_details': []
        }
        
        # Check for test collection
        collection_match = re.search(r'collected (\d+) items?', test_output)
        if collection_match:
            results['total_tests'] = int(collection_match.group(1))

        if results['total_tests'] == 0:
            print("No tests collected - cannot parse results")
            print("Full output:\n", test_output)
            return results
        
        # Look for short test summary info section
        summary_pattern = r'=+\s*short test summary info\s*=+'
        summary_match = re.search(summary_pattern, test_output, re.IGNORECASE)
        
        if summary_match:
            # Extract everything after the summary header
            summary_start = summary_match.end()
            summary_section = test_output[summary_start:]
            
            # Find the end of the summary section
            end_match = re.search(r'\n=+', summary_section)
            if end_match:
                summary_section = summary_section[:end_match.start()]
            
            # Parse each line in the summary section
            for line in summary_section.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Parse lines like "FAILED test_outputs.py::test_name - AssertionError: ..."
                parts = line.split(' ', 1)
                if len(parts) >= 2:
                    status = parts[0].strip(':')
                    if status in ['FAILED', 'PASSED', 'ERROR', 'SKIPPED', 'XFAIL', 'XPASS']:
                        # Extract test name from path
                        test_path = parts[1].split(' - ')[0] if ' - ' in parts[1] else parts[1]
                        if '::' in test_path:
                            test_name = test_path.split('::')[-1]
                            results['test_details'].append({
                                'name': test_name,
                                'status': status
                            })
                            
                            # Update counters
                            if status == 'FAILED':
                                results['failed'] += 1
                            elif status == 'PASSED':
                                results['passed'] += 1
                            elif status == 'ERROR':
                                results['errors'] += 1
        else:
            # Fallback: look for summary line
            failed_match = re.search(r'(\d+)\s+failed', test_output)
            passed_match = re.search(r'(\d+)\s+passed', test_output)
            error_match = re.search(r'(\d+)\s+error', test_output)
            
            if failed_match:
                results['failed'] = int(failed_match.group(1))
            if passed_match:
                results['passed'] = int(passed_match.group(1))
            if error_match:
                results['errors'] = int(error_match.group(1))
        
        # If we collected tests but have no detailed results, assume all failed
        if results['total_tests'] > 0 and (results['passed'] + results['failed'] + results['errors']) == 0:
            results['failed'] = results['total_tests']
        
        # Calculate total from results if not found via collection
        if results['total_tests'] == 0:
            results['total_tests'] = results['passed'] + results['failed'] + results['errors']
        
        return results


# Cleanup function to be used after validation
def cleanup_docker_image(image_tag: Optional[str]):
    """Clean up Docker image if it was created."""
    if image_tag:
        try:
            subprocess.run(['docker', 'rmi', '-f', image_tag], capture_output=True)
        except Exception:
            pass