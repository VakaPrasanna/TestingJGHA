"""
Enhanced composite action generation for GitHub Actions
"""

import re
import yaml
from pathlib import Path
from typing import List, Dict, Any

from utils import sanitize_name
from jenkins_extractors import (
    extract_tools, extract_git_steps, extract_sonarqube_steps, 
    extract_docker_steps, extract_kubectl_steps, extract_input_steps,
    extract_credentials_usage, extract_steps_commands
)


def generate_tool_setup_steps(tools: Dict[str, str]) -> List[Dict[str, Any]]:
    """Generate setup steps for tools"""
    setup_steps = []
    
    # Java/JDK setup
    if "jdk" in tools or "maven" in tools:
        java_version = "8"  # Default
        if "jdk" in tools:
            # Try to extract version from JDK name
            jdk_name = tools["jdk"].lower()
            if "11" in jdk_name:
                java_version = "11"
            elif "17" in jdk_name:
                java_version = "17"
            elif "21" in jdk_name:
                java_version = "21"
        
        setup_steps.append({
            "name": "Set up JDK",
            "uses": "actions/setup-java@v4",
            "with": {
                "java-version": java_version,
                "distribution": "temurin"
            }
        })
    
    # Maven cache
    if "maven" in tools:
        setup_steps.append({
            "name": "Cache Maven packages",
            "uses": "actions/cache@v3",
            "with": {
                "path": "~/.m2",
                "key": "${{ runner.os }}-m2-${{ hashFiles('**/pom.xml') }}"
            }
        })
    
    # Node.js setup
    if "nodejs" in tools:
        node_version = "18"  # Default
        if "nodejs" in tools:
            # Try to extract version
            nodejs_name = tools["nodejs"].lower()
            if "16" in nodejs_name:
                node_version = "16"
            elif "20" in nodejs_name:
                node_version = "20"
        
        setup_steps.append({
            "name": "Set up Node.js",
            "uses": "actions/setup-node@v4",
            "with": {
                "node-version": node_version,
                "cache": "npm"
            }
        })
    
    return setup_steps


def convert_git_steps_to_actions(git_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Jenkins git steps to GitHub Actions checkout steps"""
    checkout_steps = []
    
    for git_step in git_steps:
        step = {
            "name": "Checkout code",
            "uses": "actions/checkout@v4"
        }
        
        with_params = {}
        
        if git_step["url"]:
            # Extract repo from URL
            url = git_step["url"]
            if url.startswith("https://github.com/"):
                repo = url.replace("https://github.com/", "").replace(".git", "")
                with_params["repository"] = repo
            elif "/" in url and not url.startswith("http"):
                # Assume it's already in owner/repo format
                with_params["repository"] = url
        
        if git_step["branch"]:
            branch = git_step["branch"]
            # Handle parameter references
            if "${params." in branch:
                param_name = re.search(r"\$\{params\.([^}]+)\}", branch)
                if param_name:
                    with_params["ref"] = f"${{{{ inputs.{param_name.group(1)} }}}}"
            else:
                with_params["ref"] = branch
        
        if git_step["credentialsId"]:
            # Convert credential ID to secret reference
            cred_id = git_step["credentialsId"].upper().replace("-", "_")
            with_params["token"] = f"${{{{ secrets.{cred_id} }}}}"
        
        if with_params:
            step["with"] = with_params
        
        checkout_steps.append(step)
    
    return checkout_steps


def convert_sonarqube_steps(sonar_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert SonarQube steps to GitHub Actions"""
    sonar_actions = []
    
    for sonar_step in sonar_steps:
        # Add SonarQube scan action
        action = {
            "name": "SonarQube Scan",
            "uses": "sonarqube-scan-action@master",
            "env": {
                "SONAR_TOKEN": "${{ secrets.SONAR_TOKEN }}",
                "SONAR_HOST_URL": "${{ secrets.SONAR_HOST_URL }}"
            }
        }
        
        # Extract sonar properties from commands
        with_params = {}
        for cmd in sonar_step["commands"]:
            if "-Dsonar.projectKey=" in cmd:
                key_match = re.search(r"-Dsonar\.projectKey=([^\s]+)", cmd)
                if key_match:
                    with_params["projectKey"] = key_match.group(1)
            
            if "-Dsonar.projectName=" in cmd:
                name_match = re.search(r"-Dsonar\.projectName=([^\s'\"]+)", cmd)
                if name_match:
                    with_params["projectName"] = name_match.group(1).strip("'\"")
        
        if with_params:
            action["with"] = with_params
        
        sonar_actions.append(action)
        
        # Add original commands as fallback
        for cmd in sonar_step["commands"]:
            sonar_actions.append({
                "name": "Run SonarQube analysis",
                "run": cmd,
                "shell": "bash",
                "env": {
                    "SONAR_TOKEN": "${{ secrets.SONAR_TOKEN }}",
                    "SONAR_HOST_URL": "${{ secrets.SONAR_HOST_URL }}"
                }
            })
    
    return sonar_actions


def convert_docker_steps(docker_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert Docker steps to GitHub Actions"""
    docker_actions = []
    
    for docker_step in docker_steps:
        if docker_step["type"] == "build":
            docker_actions.append({
                "name": "Build Docker image",
                "run": f"docker build -t {docker_step['tag']} {docker_step['context']}",
                "shell": "bash"
            })
        elif docker_step["type"] == "push":
            # Add Docker login if not already present
            if not any("docker/login-action" in str(action.get("uses", "")) for action in docker_actions):
                docker_actions.append({
                    "name": "Login to DockerHub",
                    "uses": "docker/login-action@v2",
                    "with": {
                        "username": "${{ secrets.DOCKER_USERNAME }}",
                        "password": "${{ secrets.DOCKER_PASSWORD }}"
                    }
                })
            
            docker_actions.append({
                "name": "Push Docker image",
                "run": f"docker push {docker_step['tag']}",
                "shell": "bash"
            })
    
    return docker_actions


def convert_input_steps_to_environment(input_steps: List[Dict[str, Any]], stage_name: str) -> str:
    """Convert input steps to environment requirement"""
    if input_steps:
        # Return environment name for manual approval
        return f"approval-{sanitize_name(stage_name.lower())}"
    return ""


def generate_enhanced_composite_action(stage_name: str, stage_body: str, stage_env: Dict[str, str], 
                                     stage_agent: Dict[str, Any], post_info: Dict[str, Any]) -> Dict[str, Any]:
    """Generate enhanced composite action with Jenkins feature support"""
    
    # Extract enhanced features
    tools = extract_tools(stage_body)
    git_steps = extract_git_steps(stage_body)
    sonar_steps = extract_sonarqube_steps(stage_body)
    docker_steps = extract_docker_steps(stage_body)
    kubectl_commands = extract_kubectl_steps(stage_body)
    input_steps = extract_input_steps(stage_body)
    credentials = extract_credentials_usage(stage_body)
    basic_commands = extract_steps_commands(stage_body)
    
    action_def = {
        "name": f"{stage_name} Action",
        "description": f"Enhanced composite action for {stage_name} stage",
        "inputs": {},
        "runs": {
            "using": "composite",
            "steps": []
        }
    }
    
    # Add environment variables as inputs
    for env_key, env_val in stage_env.items():
        input_key = env_key.lower().replace('_', '-')
        action_def["inputs"][input_key] = {
            "description": f"Environment variable {env_key}",
            "required": False,
            "default": env_val
        }
    
    steps = []
    
    # Add tool setup steps
    tool_steps = generate_tool_setup_steps(tools)
    steps.extend(tool_steps)
    
    # Add git checkout steps (if any, otherwise regular checkout will be added by job)
    if git_steps:
        git_actions = convert_git_steps_to_actions(git_steps)
        steps.extend(git_actions)
    
    # Add SonarQube steps
    if sonar_steps:
        sonar_actions = convert_sonarqube_steps(sonar_steps)
        steps.extend(sonar_actions)
    
    # Add Docker steps
    if docker_steps:
        docker_actions = convert_docker_steps(docker_steps)
        steps.extend(docker_actions)
    
    # Add basic shell commands (filtered to avoid duplicates with specialized steps)
    filtered_commands = []
    for cmd in basic_commands:
        # Skip commands that are handled by specialized steps
        if not any([
            cmd.startswith("git "),
            "withSonarQubeEnv" in cmd,
            cmd.startswith("docker build"),
            cmd.startswith("docker push"),
            "mvn sonar:sonar" in cmd and sonar_steps  # Only skip if we have sonar steps
        ]):
            filtered_commands.append(cmd)
    
    for i, cmd in enumerate(filtered_commands):
        step = {
            "name": f"Run command {i+1}",
            "run": cmd,
            "shell": "bash"
        }
        if stage_env:
            step["env"] = {k: f"${{{{ inputs.{k.lower().replace('_', '-')} }}}}" for k in stage_env.keys()}
        steps.append(step)
    
    # Add kubectl commands
    for kubectl_cmd in kubectl_commands:
        steps.append({
            "name": "Run kubectl command",
            "run": kubectl_cmd,
            "shell": "bash"
        })
    
    # Add SSH steps if credentials detected
    ssh_credentials = [cred for cred in credentials if 'ssh' in cred.lower()]
    if ssh_credentials:
        for ssh_cred in ssh_credentials:
            steps.append({
                "name": "Execute SSH commands",
                "uses": "appleboy/ssh-action@v0.1.5",
                "with": {
                    "host": "${{ secrets.SSH_HOST }}",
                    "username": "${{ secrets.SSH_USER }}",
                    "key": f"${{{{ secrets.{ssh_cred.upper().replace('-', '_')} }}}}"
                }
            })
    
    # Add post steps
    for kind in ("always", "success", "failure"):
        if kind in post_info:
            pdata = post_info[kind]
            if "archive" in pdata:
                steps.append({
                    "name": f"Upload artifacts ({kind})",
                    "if": f"{kind}()",
                    "uses": "actions/upload-artifact@v4",
                    "with": {
                        "name": f"{sanitize_name(stage_name)}-{kind}-artifacts",
                        "path": pdata["archive"]
                    }
                })
            if "commands" in pdata:
                for cmd in pdata["commands"]:
                    steps.append({
                        "name": f"Post {kind}",
                        "if": f"{kind}()",
                        "run": cmd,
                        "shell": "bash"
                    })
    
    action_def["runs"]["steps"] = steps
    return action_def


def save_enhanced_composite_actions(stages_info: List[Dict[str, Any]], output_dir: Path) -> List[Dict[str, Any]]:
    """Save enhanced composite actions and return metadata"""
    actions_dir = output_dir / ".github" / "actions"
    actions_dir.mkdir(parents=True, exist_ok=True)
    
    action_paths = []
    
    for stage_info in stages_info:
        stage_name = stage_info["name"]
        stage_body = stage_info.get("body", "")
        action_name = sanitize_name(stage_name.lower())
        action_dir = actions_dir / action_name
        action_dir.mkdir(exist_ok=True)
        
        action_def = generate_enhanced_composite_action(
            stage_name,
            stage_body,
            stage_info.get("env", {}),
            stage_info.get("agent", {}),
            stage_info.get("post", {})
        )
        
        action_file = action_dir / "action.yml"
        with action_file.open("w", encoding="utf-8") as f:
            yaml.dump(action_def, f, sort_keys=False, width=1000)
        
        relative_path = f"./.github/actions/{action_name}"
        
        # Extract additional metadata for job creation
        input_steps = extract_input_steps(stage_body)
        approval_env = convert_input_steps_to_environment(input_steps, stage_name)
        credentials = extract_credentials_usage(stage_body)
        
        action_paths.append({
            "name": stage_name,
            "path": relative_path,
            "env": stage_info.get("env", {}),
            "approval_environment": approval_env,
            "credentials": list(credentials),
            "has_docker": bool(extract_docker_steps(stage_body)),
            "has_kubectl": bool(extract_kubectl_steps(stage_body))
        })
    return action_paths
