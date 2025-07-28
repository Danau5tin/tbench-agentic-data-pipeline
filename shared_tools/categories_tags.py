"""
categories_tags.py - Shared module for valid categories and tags

This module provides the canonical source of valid categories and tags
used throughout the data generation pipeline.
"""

# Valid categories for datapoints
VALID_CATEGORIES = [
    "data-processing",
    "data-science",
    "debugging",
    "file-operations",
    "games",
    "machine-learning",
    "mathematics",
    "model-training",
    "scientific-computing",
    "security",
    "software-engineering",
    "system-administration"
]

# Valid tags for datapoints
VALID_TAGS = [
    "C", "RL", "algorithm-implementation", "algorithms", "analysis",
    "api", "audio-processing", "automation", "base64", "binary-processing",
    "build-automation", "caching", "cli", "cloud", "coding",
    "compiler-migration", "compression", "data", "data-extraction", "data-processing",
    "data-science", "debugging", "decrypt", "encryption", "file-operations",
    "file-recovery", "forensics", "games", "git", "images",
    "information-retrieval", "interactive", "logic", "long-context", "machine-learning",
    "mathematics", "maze", "model-training", "multiprocessing", "networking",
    "numpy", "optimization", "package-management", "parallel-computing", "pathfinding",
    "pattern-recognition", "performance-optimization", "physics", "python", "pytorch",
    "reinforcement-learning", "scheduling", "scientific-computation", "security", "signal-processing",
    "software-engineering", "software-installation", "string-manipulation", "synchronization", "sys-admin",
    "system", "text-processing", "troubleshooting", "unit-testing", "version-control",
    "web", "web-scraping", "web-server"
]


def validate_category(category: str) -> bool:
    """Check if a category is valid."""
    return category in VALID_CATEGORIES


def validate_tags(tags: str) -> tuple[bool, str]:
    """
    Validate pipe-separated tags string.
    
    Returns:
        (is_valid, error_message)
    """
    if not tags:
        return False, "At least one tag is required"
    
    tag_list = [t.strip() for t in tags.split('|') if t.strip()]
    
    if len(tag_list) == 0:
        return False, "No valid tags provided"
    
    if len(tag_list) > 3:
        return False, f"Too many tags ({len(tag_list)}). Maximum 3 tags allowed."
    
    invalid_tags = [tag for tag in tag_list if tag not in VALID_TAGS]
    if invalid_tags:
        return False, f"Invalid tags: {', '.join(invalid_tags)}"
    
    return True, ""


def get_category_set() -> set[str]:
    """Get categories as a set for fast lookup."""
    return set(VALID_CATEGORIES)


def get_tag_set() -> set[str]:
    """Get tags as a set for fast lookup."""
    return set(VALID_TAGS)