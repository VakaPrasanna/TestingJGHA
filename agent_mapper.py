"""
Agent label to GitHub Actions runner mapping
"""

from typing import Any


def map_label_to_runs_on(label: str) -> Any:
    """Enhanced label mapping for Jenkins agent labels to GitHub Actions runners"""
    normalized = label.strip().lower()
    
    # GitHub-hosted runners
    if normalized in ("ubuntu", "ubuntu-latest", "linux"):
        return "ubuntu-latest"
    if normalized in ("ubuntu-20.04", "ubuntu-2004"):
        return "ubuntu-20.04"
    if normalized in ("ubuntu-22.04", "ubuntu-2204"):
        return "ubuntu-22.04"
    if normalized in ("windows", "windows-latest", "win"):
        return "windows-latest"
    if normalized in ("windows-2019", "win2019"):
        return "windows-2019"
    if normalized in ("windows-2022", "win2022"):
        return "windows-2022"
    if normalized in ("mac", "macos", "macos-latest", "darwin"):
        return "macos-latest"
    if normalized in ("macos-11", "macos11"):
        return "macos-11"
    if normalized in ("macos-12", "macos12"):
        return "macos-12"
    
    # Docker/container labels
    if "docker" in normalized:
        return "ubuntu-latest"  # Docker needs Linux
    
    # Self-hosted fallback
    return ["self-hosted", label]



