"""
Conversion report generation
"""

import re
from typing import List, Dict, Any


def generate_conversion_report(action_paths: List[Dict[str, Any]], pipeline_text: str) -> str:
    """Generate a detailed conversion report"""
    
    report = ["# Jenkins to GitHub Actions Conversion Report", ""]
    
    # Count features
    total_credentials = set()
    total_git_steps = 0
    total_sonar_steps = 0
    total_docker_steps = 0
    total_approvals = 0
    
    for action_info in action_paths:
        total_credentials.update(action_info.get("credentials", []))
        if action_info.get("has_docker"):
            total_docker_steps += 1
        if action_info.get("approval_environment"):
            total_approvals += 1
    
    # Count git steps and sonar usage in original pipeline
    total_git_steps = len(re.findall(r"\bgit\s+", pipeline_text))
    total_sonar_steps = len(re.findall(r"withSonarQubeEnv", pipeline_text))
    
    report.extend([
        "## Conversion Summary",
        f"- **Stages converted**: {len(action_paths)}",
        f"- **Git steps detected**: {total_git_steps}",
        f"- **SonarQube integrations**: {total_sonar_steps}",
        f"- **Docker operations**: {total_docker_steps}",
        f"- **Approval steps**: {total_approvals}",
        f"- **Credentials detected**: {len(total_credentials)}",
        ""])
   
    
    
    if total_credentials:
        report.extend([
            "## Required GitHub Secrets",
            "Configure these secrets in your repository settings:",
            ""
        ])
        for cred in sorted(total_credentials):
            secret_name = cred.upper().replace("-", "_")
            report.append(f"- `{secret_name}`: {cred} credential")
        report.append("")
    
    if total_sonar_steps > 0:
        report.extend([
            "## SonarQube Setup Required",
            "Add these additional secrets:",
            "- `SONAR_TOKEN`: SonarQube authentication token",
            "- `SONAR_HOST_URL`: SonarQube server URL",
            ""
        ])
    
    if total_docker_steps > 0:
        report.extend([
            "## Docker Setup Required",
            "Add these secrets for Docker operations:",
            "- `DOCKER_USERNAME`: Docker Hub username",
            "- `DOCKER_PASSWORD`: Docker Hub password/token",
            ""
        ])
    
    if total_approvals > 0:
        report.extend([
            "## Manual Approvals",
            "Configure environments in repository settings for approval gates:",
            ""
        ])
        for action_info in action_paths:
            if action_info.get("approval_environment"):
                report.append(f"- `{action_info['approval_environment']}`: For {action_info['name']} stage")
        report.append("")
    
    # Add stage-by-stage breakdown
    if action_paths:
        report.extend([
            "## Stages Breakdown",
            ""
        ])
        for i, action_info in enumerate(action_paths, 1):
            stage_name = action_info.get("name", f"Stage {i}")
            credentials = action_info.get("credentials", [])
            has_docker = action_info.get("has_docker", False)
            has_kubectl = action_info.get("has_kubectl", False)
            approval_env = action_info.get("approval_environment", "")
            
            report.append(f"### {i}. {stage_name}")
            
            features = []
            if credentials:
                features.append(f"Credentials: {', '.join(credentials)}")
            if has_docker:
                features.append("Docker operations")
            if has_kubectl:
                features.append("Kubernetes operations")
            if approval_env:
                features.append(f"Manual approval ({approval_env})")
            
            if features:
                report.append(f"- Features: {' | '.join(features)}")
            else:
                report.append("- Standard shell commands")
            
            report.append("")
    
    report.extend([
        "## Next Steps",
        "1. Review the generated workflow file",
        "2. Configure required secrets in GitHub repository settings",
        "3. Set up environments for manual approvals if needed",
        "4. Test the workflow with a sample commit",
        "5. Adjust any job dependencies or conditions as needed",
        "",
        "## Generated Files Structure",
        "```",
        ".github/",
        "├── workflows/",
        "│   └── ci.yml                 # Main workflow file",
        "└── actions/",
        "    ├── stage-1/",
        "    │   └── action.yml         # Composite action for stage 1",
        "    ├── stage-2/",
        "    │   └── action.yml         # Composite action for stage 2",
        "    └── .../",
        "```",
        "",
        "## Tips for Success",
        "- **Test incrementally**: Start with one stage and gradually enable others",
        "- **Check runner compatibility**: Ensure your chosen runners support required tools",
        "- **Review composite actions**: Each stage becomes a reusable composite action",
        "- **Monitor resource usage**: GitHub Actions has different limits than Jenkins",
        "- **Update dependencies**: Consider updating tool versions for better performance"
    ])
    
    return "\n".join(report)
