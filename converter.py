# """
# Enhanced Jenkins Declarative Pipeline -> GitHub Actions converter
# Core conversion logic
# """

import re
import yaml
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set

from utils import (
    strip_comments, find_block, sanitize_name, gha_job_id
)
from jenkins_extractors import (
    extract_parameters, extract_global_agent, extract_env_kv,
    split_stages, extract_stage_when_branch, extract_stage_environment,
    extract_steps_commands, extract_stage_post, extract_pipeline_post,
    extract_parallel, extract_stage_agent
)
from action_generator import save_enhanced_composite_actions
from agent_mapper import map_label_to_runs_on


def convert_jenkins_to_gha(jenkins_text: str, output_dir: Path = Path(".")) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Convert Jenkins declarative pipeline to GitHub Actions workflow
    Returns tuple of (workflow_dict, action_paths_metadata)
    """
    text = strip_comments(jenkins_text)

    # pipeline { ... }
    pstart, pend = find_block(text, r"\bpipeline\b")
    if pstart == -1:
        raise ValueError("Not a declarative Jenkins pipeline (no 'pipeline { ... }' found).")
    pipeline_body = text[pstart:pend]

    # Extract pipeline components
    global_agent = extract_global_agent(pipeline_body)
    parameters = extract_parameters(pipeline_body)
    
    # Global environment
    es, ee = find_block(pipeline_body, r"\benvironment\b")
    global_env = extract_env_kv(pipeline_body[es:ee]) if es != -1 else {}

    # Stages
    ss, se = find_block(pipeline_body, r"\bstages\b")
    if ss == -1:
        raise ValueError("No 'stages { ... }' found.")
    stages_list = split_stages(pipeline_body[ss:se])

    # Pipeline-level post
    pipeline_post = extract_pipeline_post(pipeline_body)

    # Determine default runs-on and container from global agent
    default_runs_on: Any = "ubuntu-latest"
    default_container: Optional[Dict[str, Any]] = None
    if global_agent:
        if global_agent["type"] == "any":
            default_runs_on = "ubuntu-latest"
        elif global_agent["type"] == "label":
            default_runs_on = map_label_to_runs_on(global_agent["label"])
        elif global_agent["type"] == "docker":
            default_runs_on = "ubuntu-latest"
            default_container = {"image": global_agent["image"]}
            if "args" in global_agent:
                default_container["options"] = global_agent["args"]

    # Build workflow inputs from parameters
    workflow_inputs = {}
    workflow_env = dict(global_env)
    
    for param_name, param_info in parameters.items():
        if param_info["type"] == "string":
            workflow_inputs[param_name] = {
                "description": param_info["description"] or f"Parameter {param_name}",
                "required": False,
                "default": param_info["default"],
                "type": "string"
            }
        elif param_info["type"] == "boolean":
            workflow_inputs[param_name] = {
                "description": param_info["description"] or f"Parameter {param_name}",
                "required": False,
                "default": param_info["default"],
                "type": "boolean"
            }
        elif param_info["type"] == "choice":
            workflow_inputs[param_name] = {
                "description": param_info["description"] or f"Parameter {param_name}",
                "required": False,
                "default": param_info["default"],
                "type": "choice",
                "options": param_info["options"]
            }

    # Base GHA structure
    gha: Dict[str, Any] = {
        "name": "CI",
        "on": {
            "push": {"branches": ["master", "main"]},
            "pull_request": {},
        }
    }
    
    # Add workflow_dispatch with inputs if parameters exist
    if workflow_inputs:
        gha["on"]["workflow_dispatch"] = {"inputs": workflow_inputs}
    
    # Add global environment
    if workflow_env:
        gha["env"] = workflow_env

    gha["jobs"] = {}

    # Collect stage information for enhanced composite actions
    stages_info = []
    last_job_ids: List[str] = []
    prev_job_id: str = ""

    def compute_job_env(stage_env: Dict[str, str]) -> Dict[str, str]:
        """Return only keys that differ from workflow-level env or are new."""
        if not stage_env:
            return {}
        if not global_env:
            return stage_env
        out: Dict[str, str] = {}
        for k, v in stage_env.items():
            if k not in global_env or str(global_env[k]) != str(v):
                out[k] = v
        return out

    def apply_agent_to_job(job_def: Dict[str, Any], stage_agent: Dict[str, Any]):
        """Apply agent configuration to job definition with proper ordering"""
        if not stage_agent:
            job_def["runs-on"] = default_runs_on
            if default_container:
                job_def["container"] = dict(default_container)
            return
            
        if stage_agent["type"] == "any":
            job_def["runs-on"] = "ubuntu-latest"
        elif stage_agent["type"] == "label":
            job_def["runs-on"] = map_label_to_runs_on(stage_agent["label"])
        elif stage_agent["type"] == "docker":
            job_def["runs-on"] = "ubuntu-latest"
            job_def["container"] = {"image": stage_agent["image"]}
            if "args" in stage_agent:
                job_def["container"]["options"] = stage_agent["args"]

    def create_enhanced_job_steps(action_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create enhanced job steps with better checkout handling"""
        steps = []
        
        # Add checkout only if the action doesn't handle git steps itself
        if not any("git" in str(cred).lower() for cred in action_info.get("credentials", [])):
            steps.append({"uses": "actions/checkout@v4"})
        
        # Add composite action step
        step = {
            "name": f"Run {action_info['name']}",
            "uses": action_info["path"]
        }
        
        # Add inputs for environment variables
        stage_env = action_info.get("env", {})
        if stage_env:
            step["with"] = {k.lower().replace('_', '-'): f"${{{{ env.{k} }}}}" for k in stage_env.keys()}
        
        steps.append(step)
        return steps

    # Process stages with enhanced features
    for stage in stages_list:
        stage_name = stage["name"]
        stage_body = stage["content"]

        # Handle parallel stages
        parallel_substages = extract_parallel(stage_body)
        if parallel_substages:
            upstream = prev_job_id or (last_job_ids[-1] if last_job_ids else None)
            parallel_ids = []
            
            for sub in parallel_substages:
                sub_name = sub["name"]
                sub_body = sub["content"]
                job_id = gha_job_id(sub_name)
                parallel_ids.append(job_id)

                stage_agent = extract_stage_agent(sub_body)
                stage_env_raw = extract_stage_environment(sub_body)
                job_env = compute_job_env(stage_env_raw)
                branch = extract_stage_when_branch(sub_body)
                if_cond = f"github.ref == 'refs/heads/{branch}'" if branch else None
                post_info = extract_stage_post(sub_body)

                # Add to stages info for enhanced composite action generation
                stages_info.append({
                    "name": sub_name,
                    "body": sub_body,  # Include full body for enhanced parsing
                    "env": stage_env_raw,
                    "agent": stage_agent,
                    "post": post_info
                })

                # Create job definition with proper ordering
                job_def: Dict[str, Any] = {}
                apply_agent_to_job(job_def, stage_agent)
                
                if job_env:
                    job_def["env"] = job_env
                if if_cond:
                    job_def["if"] = if_cond
                if upstream:
                    job_def["needs"] = upstream
                
                # Placeholder steps - will be updated after composite actions are created
                job_def["steps"] = [{"uses": "actions/checkout@v4"}]
                
                gha["jobs"][job_id] = job_def

            last_job_ids = parallel_ids
            prev_job_id = ""
            continue

        # Handle sequential stages
        job_id = gha_job_id(stage_name)
        stage_agent = extract_stage_agent(stage_body)
        stage_env_raw = extract_stage_environment(stage_body)
        job_env = compute_job_env(stage_env_raw)
        branch = extract_stage_when_branch(stage_body)
        if_cond = f"github.ref == 'refs/heads/{branch}'" if branch else None
        post_info = extract_stage_post(stage_body)

        # Add to stages info for enhanced composite action generation
        stages_info.append({
            "name": stage_name,
            "body": stage_body,  # Include full body for enhanced parsing
            "env": stage_env_raw,
            "agent": stage_agent,
            "post": post_info
        })

        # Create job definition with proper ordering
        job_def: Dict[str, Any] = {}
        apply_agent_to_job(job_def, stage_agent)
        
        if job_env:
            job_def["env"] = job_env
        if if_cond:
            job_def["if"] = if_cond

        if last_job_ids:
            job_def["needs"] = last_job_ids
            last_job_ids = []
        elif prev_job_id:
            job_def["needs"] = prev_job_id

        # Placeholder steps - will be updated after composite actions are created
        job_def["steps"] = [{"uses": "actions/checkout@v4"}]
        
        gha["jobs"][job_id] = job_def
        prev_job_id = job_id

    # Generate enhanced composite actions
    action_paths = save_enhanced_composite_actions(stages_info, output_dir)
    # print(action_paths)
    # Update job steps to use enhanced composite actions
    job_keys = list(gha["jobs"].keys())
    for i, job_key in enumerate(job_keys):
        if i < len(action_paths):
            action_info = action_paths[i]
            # print(action_info)
            
            # Update job with enhanced features
            job = gha["jobs"][job_key]
            
            # Add approval environment if needed
            if action_info.get("approval_environment"):
                job["environment"] = action_info["approval_environment"]
            
            # Update steps to use enhanced composite action
            job["steps"] = create_enhanced_job_steps(action_info)

    # Pipeline-level post -> final job that depends on all others
    if pipeline_post:
        post_job_steps: List[Dict[str, Any]] = [{"uses": "actions/checkout@v4"}]
        
        for kind in ("always", "success", "failure", "cleanup"):
            if kind in pipeline_post:
                pdata = pipeline_post[kind]
                if "archive" in pdata:
                    post_job_steps.append({
                        "name": f"Upload artifacts ({kind})",
                        "if": f"{kind}()",
                        "uses": "actions/upload-artifact@v4",
                        "with": {"name": f"pipeline-{kind}-artifacts", "path": pdata["archive"]}
                    })
                if "commands" in pdata:
                    post_job_steps.append({
                        "name": f"Pipeline post {kind}",
                        "if": f"{kind}()",
                        "run": "\n".join(pdata["commands"])
                    })
                if "mail_to" in pdata:
                    post_job_steps.append({
                        "name": f"Send notification on {kind}",
                        "if": f"{kind}()",
                        "uses": "dawidd6/action-send-mail@v3",
                        "with": {
                            "server_address": "smtp.gmail.com",
                            "server_port": "587",
                            "username": "${{ secrets.EMAIL_USERNAME }}",
                            "password": "${{ secrets.EMAIL_PASSWORD }}",
                            "subject": f"Pipeline {kind}: ${{{{ github.workflow }}}}",
                            "to": pdata.get("mail_to", ""),
                            "from": "${{ secrets.EMAIL_USERNAME }}",
                            "body": f"Pipeline {kind} for ${{{{ github.repository }}}} - ${{{{ github.sha }}}}"
                        }
                    })
        
        if len(post_job_steps) > 1:
            all_jobs = [k for k in gha["jobs"].keys() if k != "pipeline-post"]
            post_job_def = {
                "name": "Pipeline Post",
                "runs-on": default_runs_on,
                "needs": all_jobs,
                "if": "always()",
                "steps": post_job_steps
            }
            if default_container:
                post_job_def["container"] = dict(default_container)
            gha["jobs"]["pipeline-post"] = post_job_def

    return gha, action_paths


