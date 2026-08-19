"""DIANA OS - SymPy Compiler Deprecation Wrapper.

DEPRECATION NOTICE:
sympy_compiler.py has been unified into engine/z3_crucible.py using Microsoft Z3 SMT solver.
This wrapper provides 100% backward compatibility for legacy imports and CLI flags.
"""

import warnings
import sys
import os

# Redirect to z3_crucible
from engine.z3_crucible import (
    compile_syllogistic_geometry,
    load_major_premise_axioms,
    verify_state_locked_protocol,
    verify_skill_file,
    verify_invariants
)

warnings.warn(
    "engine.sympy_compiler is deprecated; use engine.z3_crucible instead.",
    DeprecationWarning,
    stacklevel=2
)

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DIANA OS SymPy Compiler (Deprecated -> Redirecting to Z3 Crucible)")
    parser.add_argument("--verify-skill", type=str, dest="verify_skill",
                        help="Path to draft SKILL.md for verification")
    args = parser.parse_args()

    if args.verify_skill:
        verification_result = verify_skill_file(args.verify_skill)
        print(json.dumps(verification_result, indent=2))
    else:
        major = "Accepting reality as having no possibilities means there is a reason for everything."
        minor = "When there is reason, there is purpose, which is the reason to understand."
        conclusion = "Therefore, accepting reality as having no possibilities establishes the purpose to understand."
        result = compile_syllogistic_geometry(major, minor, conclusion)
        print(json.dumps(result, indent=2))
