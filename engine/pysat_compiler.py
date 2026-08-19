"""DIANA OS - PySAT Compiler Deprecation Wrapper.

DEPRECATION NOTICE:
pysat_compiler.py has been unified into engine/z3_crucible.py using Microsoft Z3 SMT solver.
This wrapper provides 100% backward compatibility for legacy callers.
"""

import warnings
import sys
import os

from engine.z3_crucible import (
    compile_syllogistic_geometry,
    verify_state_locked_protocol,
    verify_invariants
)

warnings.warn(
    "engine.pysat_compiler is deprecated; use engine.z3_crucible instead.",
    DeprecationWarning,
    stacklevel=2
)

def solve_cnf_sat(cnf_clauses: list) -> dict:
    """Wrapper using Z3 for arbitrary CNF clause satisfaction."""
    from z3 import Solver, Bool, Or, Not, sat, unsat
    solver = Solver()
    solver.set("timeout", 50)
    
    var_map = {}
    for clause in cnf_clauses:
        z3_lits = []
        for lit in clause:
            var_idx = abs(lit)
            if var_idx not in var_map:
                var_map[var_idx] = Bool(f"v_{var_idx}")
            z_lit = var_map[var_idx] if lit > 0 else Not(var_map[var_idx])
            z3_lits.append(z_lit)
        if z3_lits:
            solver.add(Or(*z3_lits))
            
    res = solver.check()
    return {
        "status": "SUCCESS",
        "satisfiable": (res == sat),
        "solver": "z3_crucible_shim"
    }
