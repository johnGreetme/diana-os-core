"""DIANA OS - Tools Wrapper for SymPy Compiler (Deprecated).
"""
import sys
import os

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from z3_crucible import *

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DIANA OS Tools Verification Gate")
    parser.add_argument("--verify-skill", type=str, dest="verify_skill",
                        help="Path to draft SKILL.md for formal verification")
    args = parser.parse_args()

    if args.verify_skill:
        verification_result = verify_skill_file(args.verify_skill)
        print(json.dumps(verification_result, indent=2))
    else:
        major = "Accepting reality as having no possibilities means there is a reason for everything."
        minor = "When there is reason, there is purpose, which is the reason to understand."
        conclusion = "Therefore, accepting reality as having no possibilities establishes the purpose to understand."
        print(json.dumps(compile_syllogistic_geometry(major, minor, conclusion), indent=2))
