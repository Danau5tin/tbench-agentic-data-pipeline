#!/usr/bin/env python3
"""
Validates a datapoint by running it through a series of validators.
Each validator checks a specific aspect of the datapoint.
"""

import argparse
import csv
import json
import sys
from typing import Dict, Any

# Handle imports for both module and script usage
if __name__ == '__main__':
    # When run as a script
    from validators import (
        DockerfileValidator,
        TestSyntaxValidator,
        TestWeightsValidator,
        ContainerExecutionValidator,
        cleanup_docker_image
    )
else:
    # When imported as a module
    from .validators import (
        DockerfileValidator,
        TestSyntaxValidator,
        TestWeightsValidator,
        ContainerExecutionValidator,
        cleanup_docker_image
    )


def load_datapoint(csv_path: str, task_id: str) -> Dict[str, str]:
    """Load a specific datapoint from the CSV."""
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('task_id') == task_id:
                return row
    
    raise ValueError(f"Task ID '{task_id}' not found in {csv_path}")


def validate_datapoint(task_data: Dict[str, str]) -> Dict[str, Any]:
    """Validate all aspects of a datapoint using the validator pipeline."""
    # Initialize validators
    validators = [
        DockerfileValidator(),
        TestSyntaxValidator(),
        TestWeightsValidator(),
        ContainerExecutionValidator()
    ]
    
    # Run validation pipeline
    context = {}
    results = {
        'task_id': task_data.get('task_id', 'unknown'),
        'overall': True
    }
    
    for validator in validators:
        result = validator.validate(task_data, context)
        results[validator.name] = {
            'valid': result.valid,
            'message': result.message,
            **result.details
        }
        
        # Update overall status
        if not result.valid:
            results['overall'] = False
    
    # Clean up Docker image if one was created
    image_tag = context.get('image_tag')
    if image_tag:
        cleanup_docker_image(image_tag)
    
    return results


def print_validation_results(results: Dict[str, Any], verbose: bool = False):
    """Pretty print validation results."""
    print(f"\n{'='*50}")
    print(f"Task: {results['task_id']}")
    print(f"{'='*50}")
    
    # Dockerfile results
    if 'dockerfile' in results:
        docker_result = results['dockerfile']
        if docker_result['valid']:
            print(f"✅ Dockerfile: {docker_result['message']}")
        else:
            print(f"❌ Dockerfile: {docker_result['message']}")
    
    # Test syntax results
    if 'test_syntax' in results:
        syntax_result = results['test_syntax']
        if syntax_result['valid']:
            print(f"✅ Test Syntax: {syntax_result['message']}")
        else:
            print(f"❌ Test Syntax: {syntax_result['message']}")
    
    # Test weights results
    if 'test_weights' in results:
        weights_result = results['test_weights']
        if weights_result['valid']:
            print(f"✅ Test Weights: {weights_result['message']}")
        else:
            print(f"❌ Test Weights: {weights_result['message']}")
    
    # Container execution results
    if 'container_execution' in results:
        exec_result = results['container_execution']
        if exec_result['valid']:
            print(f"✅ Test Execution: {exec_result['message']}")
        else:
            print(f"❌ Test Execution: {exec_result['message']}")
        
        # Show test output if verbose
        if verbose and 'raw_output' in exec_result:
            print(f"\n--- Test Output ---")
            output_lines = exec_result['raw_output'].split('\n')
            for line in output_lines:
                if line.strip() and any(marker in line for marker in ['FAILED', 'PASSED', '==', 'platform', 'collected']):
                    print(f"{line}")
    
    # Overall result
    print(f"\n{'='*50}")
    if results['overall']:
        print("✅ VALIDATION PASSED")
    else:
        print("❌ VALIDATION FAILED")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Validate a datapoint by building Dockerfile and running tests'
    )
    parser.add_argument(
        '--task-id',
        type=str,
        required=True,
        help='The task ID to validate'
    )
    parser.add_argument(
        '--csv-path',
        type=str,
        required=True,
        help='Path to the CSV file containing datapoints'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON instead of formatted text'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Show detailed test output'
    )
    
    args = parser.parse_args()
    
    try:
        # Load the datapoint
        task_data = load_datapoint(args.csv_path, args.task_id)
        
        # Validate it
        results = validate_datapoint(task_data)
        
        # Output results
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_validation_results(results, args.verbose)
        
        # Exit with appropriate code
        sys.exit(0 if results['overall'] else 1)
    
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()