#!/usr/bin/env python3
"""
Returns refinement guidelines for selecting the best ideas from brainstormed list.
This tool provides criteria and guidance for the idea agent to refine their
brainstormed ideas down to the final n selections.
"""

REFINEMENT_GUIDELINES = """# Idea Refinement Guidelines

## Selection Criteria

When refining your brainstormed ideas down to the final n selections, evaluate each idea against these criteria:

### 1. Training Value (Weight: 40%)
- **Unique Learning Opportunity**: Does this task teach something distinct from other selected tasks?
- **Skill Coverage**: Does it exercise the core capabilities identified in the seed DP analysis?
- **Generalization Potential**: Will solving this help with similar real-world problems?
- **Edge Case Exposure**: Does it reveal important edge cases or failure modes?

### 2. Technical Diversity (Weight: 30%)
- **Stack Variety**: Are you selecting tasks across different tech stacks?
- **Problem Type Distribution**: Mix of debugging, building, refactoring, configuration?
- **Complexity Levels**: Good distribution across medium/hard/extremely hard?
- **Domain Coverage**: Different industries and use cases represented?

### 3. Feasibility (Weight: 20%)
- **Docker Build Time**: Can the environment be set up in <5 minutes?
- **Clear Success Criteria**: Is it obvious when the task is complete?
- **Reasonable Scope**: Can it be completed in <50 agent turns?
- **Deterministic Outcomes**: Will the solution be consistently verifiable?

### 4. Realism (Weight: 10%)
- **Real-World Scenario**: Is this something developers actually encounter?
- **Practical Constraints**: Are the constraints realistic (not artificial)?
- **Business Context**: Does the scenario make sense in a professional setting?

## Selection Process

1. **Score Each Idea**: Rate each brainstormed idea on the criteria above (1-5 scale)
2. **Check Distribution**: Ensure your final selection has:
   - At least 2 different difficulty levels
   - Multiple tech stacks or variations
   - Different problem types (not all debugging, not all building)
   
3. **Avoid Clustering**: Don't select multiple ideas that are too similar:
   - Same tech stack + same problem type = too similar
   - Minor variations of the same task = too similar
   
4. **Prioritize Learning Value**: When in doubt, choose the task that:
   - Tests the core capability in the most different context
   - Exposes the model to new patterns or approaches
   - Has clear but challenging success criteria

## Red Flags to Avoid

- **Incremental Variations**: "Do the same thing but with logging" ❌
- **Surface-Level Changes**: "Same bug but different variable names" ❌
- **Overly Complex Setups**: "Install 15 services that take 20 mins" ❌
- **Ambiguous Success**: "Make it 'better' or 'more efficient'" ❌
- **Artificial Constraints**: "Fix this but you can't use common tools" ❌

## Final Checklist

Before finalizing your n selections:
- [ ] Each task tests the core capabilities from the seed DP
- [ ] No two tasks are too similar (different contexts/approaches)
- [ ] Difficulty levels are well distributed
- [ ] All tasks have clear, verifiable success criteria
- [ ] Each task can realistically be completed in <50 turns
- [ ] The set as a whole provides diverse training value
"""

def main():
    print(REFINEMENT_GUIDELINES)

if __name__ == "__main__":
    main()