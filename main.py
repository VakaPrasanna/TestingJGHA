#!/usr/bin/env python3
"""
Enhanced Jenkins Declarative Pipeline -> GitHub Actions converter
Main entry point for the conversion tool
"""

import sys
from pathlib import Path
from converter import convert_jenkins_to_gha
from report_generator import generate_conversion_report


def main():
    if len(sys.argv) < 2:
        print("Enhanced Jenkins to GitHub Actions Converter")
        print("Usage: python main.py <path/to/Jenkinsfile> [output_directory]")
        print("  output_directory: Where to create .github/workflows/ci.yml and .github/actions/")
        sys.exit(1)

    in_path = Path(sys.argv[1])
    if not in_path.exists():
        print(f"File not found: {in_path}")
        sys.exit(1)

    output_dir = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    workflow_path = output_dir / ".github" / "workflows" / "ci.yml"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    
    report_path = output_dir / "CONVERSION_REPORT.md"

    try:
        jenkins_text = in_path.read_text(encoding="utf-8")
        print(f"Converting {in_path} to GitHub Actions...")
        
        gha, action_paths = convert_jenkins_to_gha(jenkins_text, output_dir)
        
        # Save workflow file
        import yaml
        with workflow_path.open("w", encoding="utf-8") as f:
            yaml.dump(gha, f, sort_keys=False, width=1000)
        
        print(f" Main workflow saved to: {workflow_path}")
        print(f" Composite actions saved to: {output_dir / '.github' / 'actions'}")
        
        # Generate and save conversion report
        report = generate_conversion_report(action_paths, jenkins_text)
        with report_path.open("w", encoding="utf-8") as f:
            f.write(report)
        
        print(f" Conversion report saved to: {report_path}")
        print("\n Generated files:")
        print(f"  - {workflow_path.relative_to(output_dir)}")
        print(f"  - {report_path.relative_to(output_dir)}")
        
        # List generated composite actions
        actions_dir = output_dir / ".github" / "actions"
        if actions_dir.exists():
            for action_dir in actions_dir.iterdir():
                if action_dir.is_dir():
                    action_file = action_dir / "action.yml"
                    if action_file.exists():
                        print(f"  - {action_file.relative_to(output_dir)}")
        
        print("\n Conversion completed! Check the CONVERSION_REPORT.md for next steps.")
        
    except Exception as e:
        print(f" Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
