"""
Jenkins pipeline parsing and feature extraction functions
"""

import re
from typing import List, Dict, Any, Set
from utils import find_block, multiline_to_commands, strip_comments


def extract_tools(stage_body: str) -> Dict[str, str]:
    """Extract tools block from stage"""
    tools = {}
    s, e = find_block(stage_body, r"\btools\b")
    if s == -1:
        return tools
    
    tools_body = stage_body[s:e]
    
    # Maven tools
    m = re.search(r"maven\s+['\"]([^'\"]+)['\"]", tools_body)
    if m:
        tools["maven"] = m.group(1)
    
    # JDK tools
    m = re.search(r"jdk\s+['\"]([^'\"]+)['\"]", tools_body)
    if m:
        tools["jdk"] = m.group(1)
    
    # Node.js tools
    m = re.search(r"nodejs\s+['\"]([^'\"]+)['\"]", tools_body)
    if m:
        tools["nodejs"] = m.group(1)
    
    # Git tools
    m = re.search(r"git\s+['\"]([^'\"]+)['\"]", tools_body)
    if m:
        tools["git"] = m.group(1)
        
    return tools


def extract_git_steps(stage_body: str) -> List[Dict[str, Any]]:
    """Extract git checkout steps"""
    git_steps = []
    
    # git branch: "...", url: "...", credentialsId: "..."
    pattern = r"git\s+(?:branch\s*:\s*['\"]([^'\"]*)['\"](?:\s*,)?)?\s*(?:url\s*:\s*['\"]([^'\"]+)['\"](?:\s*,)?)?\s*(?:credentialsId\s*:\s*['\"]([^'\"]*)['\"])?"
    
    for m in re.finditer(pattern, stage_body):
        branch = m.group(1) or ""
        url = m.group(2) or ""
        credentials_id = m.group(3) or ""
        
        if url:  # Only add if we have a URL
            git_steps.append({
                "branch": branch,
                "url": url,
                "credentialsId": credentials_id
            })
    
    return git_steps


def extract_sonarqube_steps(stage_body: str) -> List[Dict[str, Any]]:
    """Extract SonarQube steps"""
    sonar_steps = []
    
    # withSonarQubeEnv pattern
    pattern = r"withSonarQubeEnv\s*\(\s*(?:credentialsId\s*:\s*['\"]([^'\"]*)['\"])?(?:\s*,)?\s*(?:installationName\s*:\s*['\"]([^'\"]*)['\"])?\s*\)\s*\{([^}]*)\}"
    
    for m in re.finditer(pattern, stage_body, re.DOTALL):
        credentials_id = m.group(1) or ""
        installation_name = m.group(2) or ""
        inner_commands = m.group(3) or ""
        
        # Extract commands from within the block
        commands = []
        for cmd_match in re.finditer(r"sh\s+['\"]([^'\"]+)['\"]", inner_commands):
            commands.append(cmd_match.group(1))
        
        if commands:
            sonar_steps.append({
                "credentialsId": credentials_id,
                "installationName": installation_name,
                "commands": commands
            })
    
    return sonar_steps


def extract_input_steps(stage_body: str) -> List[Dict[str, Any]]:
    """Extract input approval steps"""
    input_steps = []
    
    # input(message: "...", parameters: [...])
    pattern = r"input\s*\(\s*message\s*:\s*['\"]([^'\"]+)['\"](?:\s*,\s*parameters\s*:\s*\[([^\]]*)\])?\s*\)"
    
    for m in re.finditer(pattern, stage_body):
        message = m.group(1)
        parameters_str = m.group(2) or ""
        
        input_steps.append({
            "message": message,
            "parameters": parameters_str
        })
    
    return input_steps


def extract_credentials_usage(stage_body: str) -> Set[str]:
    """Extract credential IDs used in the stage"""
    credentials = set()
    
    # credentialsId: "..."
    for m in re.finditer(r"credentialsId\s*:\s*['\"]([^'\"]+)['\"]", stage_body):
        credentials.add(m.group(1))
    
    # credentials("...")
    for m in re.finditer(r"credentials\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", stage_body):
        credentials.add(m.group(1))
    
    # sshagent ([...])
    for m in re.finditer(r"sshagent\s*\(\s*\[([^\]]+)\]\s*\)", stage_body):
        cred_list = m.group(1)
        for cred in re.findall(r"['\"]?([^'\"]+)['\"]?", cred_list):
            if cred.strip():
                credentials.add(cred.strip())
    
    return credentials


def extract_docker_steps(stage_body: str) -> List[Dict[str, Any]]:
    """Extract Docker-related steps"""
    docker_steps = []
    
    # Docker build
    for m in re.finditer(r"docker\s+build\s+(?:-t\s+)?([^\s]+)(?:\s+(.+))?", stage_body):
        tag = m.group(1).strip()
        context = m.group(2).strip() if m.group(2) else "."
        docker_steps.append({
            "type": "build",
            "tag": tag,
            "context": context
        })
    
    # Docker push
    for m in re.finditer(r"docker\s+push\s+([^\s]+)", stage_body):
        tag = m.group(1).strip()
        docker_steps.append({
            "type": "push",
            "tag": tag
        })
    
    return docker_steps


def extract_kubectl_steps(stage_body: str) -> List[str]:
    """Extract kubectl commands"""
    kubectl_commands = []
    
    for m in re.finditer(r"kubectl\s+([^\n\"']+)", stage_body):
        kubectl_commands.append(f"kubectl {m.group(1).strip()}")
    
    return kubectl_commands


def extract_parameters(pipeline_body: str) -> Dict[str, Any]:
    """Extract pipeline parameters with enhanced support"""
    params = {}
    s, e = find_block(pipeline_body, r"\bparameters\b")
    if s == -1:
        return params
    
    param_body = pipeline_body[s:e]
    
    # string parameters
    for m in re.finditer(r"string\s*\(\s*name\s*:\s*['\"]([^'\"]+)['\"](?:,\s*defaultValue\s*:\s*['\"]([^'\"]*)['\"])?(?:,\s*description\s*:\s*['\"]([^'\"]*)['\"])?", param_body):
        name = m.group(1)
        default = m.group(2) or ""
        description = m.group(3) or ""
        params[name] = {
            "type": "string",
            "default": default,
            "description": description
        }
    
    # boolean parameters
    for m in re.finditer(r"booleanParam\s*\(\s*name\s*:\s*['\"]([^'\"]+)['\"](?:,\s*defaultValue\s*:\s*(true|false))?(?:,\s*description\s*:\s*['\"]([^'\"]*)['\"])?", param_body):
        name = m.group(1)
        default = m.group(2) or "false"
        description = m.group(3) or ""
        params[name] = {
            "type": "boolean",
            "default": default.lower() == "true",
            "description": description
        }
    
    # choice parameters
    for m in re.finditer(r"choice\s*\(\s*name\s*:\s*['\"]([^'\"]+)['\"](?:,\s*choices\s*:\s*\[([^\]]+)\])?(?:,\s*description\s*:\s*['\"]([^'\"]*)['\"])?", param_body):
        name = m.group(1)
        choices_str = m.group(2) or ""
        description = m.group(3) or ""
        choices = [c.strip().strip('\'"') for c in choices_str.split(',') if c.strip()]
        params[name] = {
            "type": "choice",
            "options": choices,
            "default": choices[0] if choices else "",
            "description": description
        }
    
    return params


def extract_global_agent(pipeline_body: str) -> Dict[str, Any]:
    """Enhanced agent extraction with better parsing"""
    s, e = find_block(pipeline_body, r"\bagent\b")
    if s == -1:
        return {}
    agent_body = pipeline_body[s:e]
    
    # agent any
    if re.search(r"\bany\b", agent_body):
        return {"type": "any"}
    
    # agent { node { label '...' } }
    ns, ne = find_block(agent_body, r"\bnode\b")
    if ns != -1:
        node_body = agent_body[ns:ne]
        m = re.search(r"label\s+['\"]([^'\"]+)['\"]", node_body)
        if m:
            return {"type": "label", "label": m.group(1).strip()}
    
    # agent { label '...' }
    m = re.search(r"label\s+['\"]([^'\"]+)['\"]", agent_body)
    if m:
        return {"type": "label", "label": m.group(1).strip()}
    
    # agent { docker { ... } }
    ds, de = find_block(agent_body, r"\bdocker\b")
    if ds != -1:
        docker_body = agent_body[ds:de]
        img = re.search(r"image\s+['\"]([^'\"]+)['\"]", docker_body)
        args = re.search(r"args\s+['\"]([^'\"]+)['\"]", docker_body)
        reuse_node = re.search(r"reuseNode\s+(true|false)", docker_body)
        
        if img:
            out = {"type": "docker", "image": img.group(1).strip()}
            if args:
                out["args"] = args.group(1).strip()
            if reuse_node:
                out["reuseNode"] = reuse_node.group(1) == "true"
            return out
    
    return {}


def extract_stage_agent(stage_body: str) -> Dict[str, Any]:
    """Enhanced stage agent extraction"""
    s, e = find_block(stage_body, r"\bagent\b")
    if s == -1:
        return {}
    body = stage_body[s:e]
    
    if re.search(r"\bany\b", body):
        return {"type": "any"}
    
    # Handle node { label } syntax
    ns, ne = find_block(body, r"\bnode\b")
    if ns != -1:
        node_body = body[ns:ne]
        m = re.search(r"label\s+['\"]([^'\"]+)['\"]", node_body)
        if m:
            return {"type": "label", "label": m.group(1).strip()}
    
    m = re.search(r"label\s+['\"]([^'\"]+)['\"]", body)
    if m:
        return {"type": "label", "label": m.group(1).strip()}
    
    ds, de = find_block(body, r"\bdocker\b")
    if ds != -1:
        dbody = body[ds:de]
        img = re.search(r"image\s+['\"]([^'\"]+)['\"]", dbody)
        args = re.search(r"args\s+['\"]([^'\"]+)['\"]", dbody)
        reuse_node = re.search(r"reuseNode\s+(true|false)", dbody)
        
        if img:
            out = {"type": "docker", "image": img.group(1).strip()}
            if args:
                out["args"] = args.group(1).strip()
            if reuse_node:
                out["reuseNode"] = reuse_node.group(1) == "true"
            return out
    
    return {}


def extract_env_kv(env_body: str) -> Dict[str, str]:
    """Extract environment key-value pairs from environment block"""
    env: Dict[str, str] = {}
    for line in env_body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1]
            env[key] = val
    return env


def split_stages(stages_body: str) -> List[Dict[str, Any]]:
    """Split stages block into individual stages"""
    res = []
    i = 0
    while True:
        m = re.search(r"stage\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\{", stages_body[i:])
        if not m:
            break
        name = m.group(1)
        abs_start = i + m.start()
        block_start = abs_start + m.end() - m.start() - 1
        depth = 0
        j = block_start + 1
        content_start = j
        while j < len(stages_body):
            if stages_body[j] == '{':
                depth += 1
            elif stages_body[j] == '}':
                if depth == 0:
                    res.append({"name": name, "content": stages_body[content_start:j]})
                    i = j + 1
                    break
                depth -= 1
            j += 1
        else:
            break
    return res


def extract_stage_when_branch(stage_body: str) -> str:
    """Extract branch condition from when block"""
    s, e = find_block(stage_body, r"\bwhen\b")
    if s == -1:
        return ""
    when_body = stage_body[s:e]
    m = re.search(r"branch\s+['\"]([^'\"]+)['\"]", when_body)
    return m.group(1) if m else ""


def extract_stage_environment(stage_body: str) -> Dict[str, str]:
    """Extract environment variables from stage"""
    s, e = find_block(stage_body, r"\benvironment\b")
    if s == -1:
        return {}
    return extract_env_kv(stage_body[s:e])


def extract_steps_commands(stage_body: str) -> List[str]:
    """Extract shell commands from steps block"""
    cmds: List[str] = []
    s, e = find_block(stage_body, r"\bsteps\b")
    search_zone = stage_body[s:e] if s != -1 else stage_body
    zone = strip_comments(search_zone)

    for m in re.finditer(r"sh\s+([\"']{3})([\s\S]*?)\1", zone):
        inner = m.group(2)
        cmds.extend(multiline_to_commands(inner))
    for m in re.finditer(r"sh\s+['\"]([^'\"]+)['\"]", zone):
        cmds.append(m.group(1).strip())
    for m in re.finditer(r"\becho\s+['\"]([^'\"]+)['\"]", zone):
        cmds.append(f"echo {m.group(1).strip()}")

    return cmds


def _extract_post_body(body: str) -> Dict[str, Any]:
    """Extract post block content"""
    out: Dict[str, Any] = {}
    ps, pe = find_block(body, r"\bpost\b")
    if ps == -1:
        return out
    post_body = body[ps:pe]

    def _collect(kind: str) -> Dict[str, Any]:
        ks, ke = find_block(post_body, rf"\b{kind}\b")
        if ks == -1:
            return {}
        kbody = post_body[ks:ke]
        data: Dict[str, Any] = {}
        # archiveArtifacts (common)
        m = re.search(r"archiveArtifacts\s*\(\s*artifacts\s*:\s*['\"]([^'\"]+)['\"]", kbody)
        if m:
            data["archive"] = m.group(1).strip()
        # capture shell/echo inside post
        cmds = []
        for mm in re.finditer(r"sh\s+['\"]([^'\"]+)['\"]", kbody):
            cmds.append(mm.group(1).strip())
        for mm in re.finditer(r"sh\s+([\"']{3})([\s\S]*?)\1", kbody):
            cmds.extend(multiline_to_commands(mm.group(2)))
        for mm in re.finditer(r"\becho\s+['\"]([^'\"]+)['\"]", kbody):
            cmds.append(f"echo {mm.group(1).strip()}")
        if cmds:
            data["commands"] = cmds
        # mail to (placeholder)
        m = re.search(r"mail\s+to\s*:\s*['\"]([^'\"]+)['\"]", kbody)
        if m:
            data["mail_to"] = m.group(1).strip()
        return data

    for kind in ("always", "success", "failure", "cleanup"):
        kdata = _collect(kind)
        if kdata:
            out[kind] = kdata
    return out


def extract_stage_post(stage_body: str) -> Dict[str, Any]:
    """Extract post block from stage"""
    return _extract_post_body(stage_body)


def extract_pipeline_post(pipeline_body: str) -> Dict[str, Any]:
    """Extract post block from pipeline"""
    return _extract_post_body(pipeline_body)


def extract_parallel(stage_body: str) -> List[Dict[str, Any]]:
    """Extract parallel stages from stage body"""
    ps, pe = find_block(stage_body, r"\bparallel\b")
    if ps == -1:
        return []
    par_body = stage_body[ps:pe]
    return split_stages(par_body)



