#!/usr/bin/env python3
"""
show_categories_tags.py - Display available categories and tags for datapoint classification

Usage:
    python show_categories_tags.py
"""

import sys
from pathlib import Path

# Add parent directories to path to import shared_tools
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir.parent.parent))

from shared_tools.categories_tags import VALID_CATEGORIES, VALID_TAGS


def show_categories_and_tags():
    """Display all available categories and tags."""
    
    print("Available Categories (choose 1):")
    print("=" * 40)
    for cat in VALID_CATEGORIES:
        print(f"  - {cat}")
    print(f"\nTotal: {len(VALID_CATEGORIES)} categories")
    
    print("\n\nAvailable Tags (choose up to 3):")
    print("=" * 40)
    for i, tag in enumerate(VALID_TAGS):
        print(f"  - {tag}")
        if (i + 1) % 5 == 0:  # Add spacing every 5 tags for readability
            print()
    
    if len(VALID_TAGS) % 5 != 0:  # Add final newline if needed
        print()
    
    print(f"Total: {len(VALID_TAGS)} tags")
    
    print("\n\nGuidelines for selection:")
    print("=" * 40)
    print("1. Category: Choose the single most appropriate category")
    print("2. Tags: Select 1-3 tags that best describe the specific skills/tools")
    print("3. Consider the actual implementation, not just the prompt")
    print("4. Prioritize tags that would help users find similar tasks")


def main():
    """Main entry point."""
    try:
        show_categories_and_tags()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()