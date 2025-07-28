#!/usr/bin/env python3
"""
Returns task creation parameters for the idea generation agent.
This is a simple CLI tool that returns the number of tasks to create (n)
and the brainstorming multiplier.
"""

def main():
    n_tasks = 5
    multiplier = 4
    
    print(f"Task specs to create (n): {n_tasks}")
    print(f"Brainstorming multiplier: {multiplier}x")

if __name__ == "__main__":
    main()
