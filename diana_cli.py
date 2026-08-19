#!/usr/bin/env python3
"""DIANA OS - Master Command-Line Interface (CLI).

Universal management interface for node activation, integrity verification,
Z3 SMT skill validation, SCADA fieldbus inspection, Historian queries,
Auditable Skill Registry filing, LLM Skill Forge, and Genesis verification.
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.license_manager import LicenseManager
from engine.z3_crucible import verify_skill_file
from core.security import verify_kernel_integrity
from core.historian import historian
from core.skill_registry import skill_registry
from core.skill_loader import skill_loader
from actuation.router import HardwareRouter
from actuation.modbus_driver import ModbusDriver

def load_env():
    """Loads .env configuration file if present."""
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v.strip('"').strip("'")

def cmd_activate(args):
    """Activates the node and establishes cryptographic hardware lock."""
    load_env()
    manager = LicenseManager(tier="hacker")
    manager.activate(args.license_key)

def cmd_status(args):
    """Prints comprehensive cyber-physical node status and integrity health."""
    load_env()
    print("=" * 65)
    print(" D.I.A.N.A. OS // SYSTEM STATUS & INTEGRITY REPORT")
    print("=" * 65)

    # 1. Hardware Silicon Binding
    manager = LicenseManager(tier="hacker")
    gpu_uuid = manager._get_hardware_uuid()
    print(f"[*] Silicon Target (Hardware UUID): {gpu_uuid or 'UNBOUND / CPU FALLBACK'}")

    # 2. Kernel Integrity Check
    manifest_path = os.path.join(BASE_DIR, "core_manifest.sha256")
    if os.path.exists(manifest_path):
        is_intact, report = verify_kernel_integrity(BASE_DIR, manifest_path)
        status_str = "SEALED & INTACT [PASS]" if is_intact else "INTEGRITY BREACH [PANIC]"
        print(f"[*] Layer 2 Immutability Manifest: {status_str}")
        print(f"    Details: {report}")
    else:
        print("[!] Layer 2 Immutability Manifest: MANIFEST NOT GENERATED")

    # 3. Genesis Integrity Check
    genesis_ok, genesis_report = skill_registry.verify_genesis_integrity()
    genesis_badge = "INTACT [PASS]" if genesis_ok else "BREACH DETECTED [PANIC]"
    print(f"[*] Genesis Axiom Integrity: {genesis_badge}")
    print(f"    Details: {genesis_report}")

    # 4. Skill Registry Summary
    active_skills = skill_registry.list_skills(status_filter="active")
    deprecated_skills = skill_registry.list_skills(status_filter="deprecated")
    revoked_skills = skill_registry.list_skills(status_filter="revoked")
    print(f"[*] Skill Registry: {len(active_skills)} active, {len(deprecated_skills)} deprecated, {len(revoked_skills)} revoked")

    # 5. Skill Hot-Loader Status
    loaded_ids = skill_loader.get_loaded_skill_ids()
    print(f"[*] Skill Hot-Loader: {len(loaded_ids)} skill(s) in active memory cache")

    # 6. Universal Domain Probe
    router = HardwareRouter()
    domain = router.get_domain()
    print(f"[*] Active Hardware Domain: {domain.upper()}")
    if domain == "scada":
        state = router.modbus_driver.read_live_state()
        print(f"    Modbus Host: {router.modbus_driver.host}:{router.modbus_driver.port}")
        print(f"    Live Telemetry -> Pressure: {state.get('pressure')}, Valve A: {state.get('valve_a')}, Valve B: {state.get('valve_b')}")
    elif domain == "robotics":
        print("    Robotics Middleware: ROS 2 / URDF Active")
    else:
        print("    Digital Driver: VisualActuator (OCR & PyAutoGUI)")

    print("=" * 65)

def cmd_verify_skill(args):
    """Evaluates candidate skill against the Microsoft Z3 SMT Crucible."""
    print(f"[*] Submitting skill to Z3 Crucible: {args.skill_path}")
    result = verify_skill_file(args.skill_path)
    print(json.dumps(result, indent=2))
    if not result.get("mathematically_valid"):
        sys.exit(1)

def cmd_graduate_skill(args):
    """Proves and graduates a draft skill into the auditable skill filing system."""
    print(f"[*] Submitting draft skill to Z3 Crucible: {args.draft_path}")
    proof_result = verify_skill_file(args.draft_path)
    if not proof_result.get("mathematically_valid"):
        print("[!] Z3 CRUCIBLE REJECTION: Candidate skill breached invariants.")
        print(json.dumps(proof_result, indent=2))
        sys.exit(1)

    print("[*] Z3 SMT Proof SATISFIED. Registering skill in auditable filing system...")
    success, msg = skill_registry.graduate_skill(
        draft_path=args.draft_path,
        z3_proof_result=proof_result,
        author=args.author or "auto-skill-generator"
    )
    if success:
        skill_loader.invalidate_cache()
        print(f"[SUCCESS] {msg}")
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)

def cmd_skills(args):
    """Lists or audits all registered, graduated skills."""
    if args.info:
        rec = skill_registry.get_skill_audit(args.info)
        if rec:
            print("=" * 65)
            print(f" SKILL AUDIT RECEIPT: {args.info} (v{rec.get('version')})")
            print("=" * 65)
            print(json.dumps(rec, indent=2))
        else:
            print(f"Skill '{args.info}' not found in registry.")
    else:
        skills = skill_registry.list_skills(status_filter=args.status)
        filter_label = f" [{args.status.upper()}]" if args.status else ""
        print("=" * 75)
        print(f" D.I.A.N.A. OS // AUDITABLE SKILL REGISTRY ({len(skills)} skills{filter_label})")
        print("=" * 75)
        if not skills:
            print("No skills found matching criteria.")
            return
        for s in skills:
            status_badge = s.get("status", "active").upper()
            print(f"[{status_badge}] {s['skill_id']} (v{s.get('version', 1)}) | SHA-256: {s.get('sha256_hash', '')[:16]}... | Author: {s.get('author')}")
            print(f"    Graduated: {s.get('graduated_at')} | Forged by: {s.get('forged_by', 'manual')}")
            if s.get("revocation_reason"):
                print(f"    Revoked: {s.get('revoked_at')} | Reason: {s.get('revocation_reason')}")
            if s.get("successor"):
                print(f"    Deprecated → Successor: {s.get('successor')}")
            print(f"    Genesis Preserved: {s.get('the_skill_txt_intact')}")
            print("-" * 75)

def cmd_revoke_skill(args):
    """Revokes a graduated skill with mandatory reason string."""
    print(f"[*] Revoking skill '{args.skill_id}'...")
    success, msg = skill_registry.revoke_skill(args.skill_id, args.reason)
    if success:
        skill_loader.invalidate_cache()
        print(f"[SUCCESS] {msg}")
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)

def cmd_skill_diff(args):
    """Shows unified diff between current and previous version of a graduated skill."""
    diff = skill_registry.diff_skill_versions(args.skill_id)
    if diff:
        print(diff)
    else:
        print(f"No version history available for skill '{args.skill_id}'.")

def cmd_genesis_check(args):
    """Runs standalone genesis integrity verification against core_manifest.sha256."""
    print("=" * 65)
    print(" D.I.A.N.A. OS // GENESIS AXIOM INTEGRITY VERIFICATION")
    print("=" * 65)
    intact, report = skill_registry.verify_genesis_integrity()
    badge = "INTACT [PASS]" if intact else "BREACH DETECTED [PANIC]"
    print(f"[*] Genesis Status: {badge}")
    print(f"    {report}")
    print("=" * 65)
    if not intact:
        sys.exit(1)

def cmd_forge(args):
    """Triggers the full LLM Skill Forge cycle from the terminal."""
    load_env()
    from core.skill_forge import skill_forge

    description = args.description
    print("=" * 65)
    print(" D.I.A.N.A. OS // LLM SKILL FORGE")
    print("=" * 65)
    print(f"[*] Forge Target: \"{description}\"")
    print(f"[*] Budget Ceiling: {skill_forge.MAX_LLM_CALLS} LLM calls")
    print(f"[*] Z3 Strike Limit: {skill_forge.MAX_Z3_RETRIES}")
    print(f"[*] Cloud Bridge: {'ENABLED' if skill_forge._is_cloud_bridge_enabled() else 'DISABLED (local-only)'}")
    print("-" * 65)

    result = skill_forge.forge_full_cycle(description)

    print("-" * 65)
    if result["success"]:
        print(f"[SUCCESS] {result['message']}")
        print(f"    Skill ID: {result['skill_id']}")
        print(f"    LLM Calls Used: {result['llm_calls_used']}/{skill_forge.MAX_LLM_CALLS}")
        print(f"    Z3 Attempts: {result['z3_attempts']}")
        print(f"    Forged By: {result['forged_by']}")
    else:
        print(f"[FAILED] {result['message']}")
        print(f"    LLM Calls Used: {result['llm_calls_used']}/{skill_forge.MAX_LLM_CALLS}")
        if result.get("last_z3_report"):
            print(f"    Last Z3 Report: {result['last_z3_report']}")
    print("=" * 65)

def cmd_historian(args):
    """Queries the persistent SCADA Historian database."""
    records = historian.query_history(domain=args.domain, limit=args.limit)
    print("=" * 75)
    print(f" D.I.A.N.A. OS // HISTORIAN AUDIT LOG ({len(records)} recent records)")
    print("=" * 75)
    if not records:
        print("No evaluation records found.")
        return

    for idx, r in enumerate(records, 1):
        status_badge = "SAT [SAFE]" if r["is_safe"] else "UNSAT [BLOCKED]"
        print(f"[{idx}] {r['timestamp']} | Domain: {r['domain'].upper()} | {status_badge}")
        print(f"    Action: {json.dumps(r['action'])}")
        if r.get("report"):
            print(f"    Report: {r['report']}")
        print("-" * 75)

def cmd_scada(args):
    """Direct operator inspection and testing tool for Modbus fieldbus."""
    driver = ModbusDriver(host=args.host, port=args.port)
    if args.write_pressure is not None or args.toggle_a or args.toggle_b:
        curr = driver.read_live_state()
        p = curr.get("pressure", 0) if args.write_pressure is None else args.write_pressure
        va = curr.get("valve_a", False) ^ args.toggle_a
        vb = curr.get("valve_b", False) ^ args.toggle_b

        print(f"[*] Committing Target State -> Pressure: {p}, Valve A: {va}, Valve B: {vb}")
        succ, msg = driver.write_target_state(coils={0: va, 1: vb}, registers={0: p})
        print(f"[{'SUCCESS' if succ else 'ERROR'}] {msg}")
    else:
        print(f"[*] Reading live Modbus telemetry from {driver.host}:{driver.port}...")
        state = driver.read_live_state()
        print(json.dumps(state, indent=2))

def cmd_test(args):
    """Runs the built-in Cyber-Physical HAL and Z3 Crucible test suite."""
    import unittest
    test_path = os.path.join(BASE_DIR, "tests")
    suite = unittest.defaultTestLoader.discover(test_path, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="D.I.A.N.A. OS Master Command-Line Interface")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # activate
    p_act = subparsers.add_parser("activate", help="Activate node license and establish hardware lock")
    p_act.add_argument("license_key", help="Issued license key string")
    p_act.set_defaults(func=cmd_activate)

    # status
    p_stat = subparsers.add_parser("status", help="Display node hardware binding, domain, and integrity status")
    p_stat.set_defaults(func=cmd_status)

    # verify-skill
    p_ver = subparsers.add_parser("verify-skill", help="Prove candidate skill safety in Z3 Crucible")
    p_ver.add_argument("skill_path", help="Path to draft SKILL.md")
    p_ver.set_defaults(func=cmd_verify_skill)

    # graduate-skill
    p_grad = subparsers.add_parser("graduate-skill", help="Prove draft skill in Z3 Crucible and register in Auditable Filing System")
    p_grad.add_argument("draft_path", help="Path to draft SKILL.md")
    p_grad.add_argument("--author", default="auto-skill-generator", help="Author tag")
    p_grad.set_defaults(func=cmd_graduate_skill)

    # skills
    p_skl = subparsers.add_parser("skills", help="List or inspect audited, graduated skills")
    p_skl.add_argument("--info", default=None, help="Skill ID to inspect audit receipt")
    p_skl.add_argument("--status", default=None, choices=["active", "deprecated", "revoked"], help="Filter by lifecycle status")
    p_skl.set_defaults(func=cmd_skills)

    # revoke-skill
    p_rev = subparsers.add_parser("revoke-skill", help="Revoke a graduated skill with mandatory reason")
    p_rev.add_argument("skill_id", help="Skill ID to revoke")
    p_rev.add_argument("--reason", required=True, help="Mandatory revocation reason for audit trail")
    p_rev.set_defaults(func=cmd_revoke_skill)

    # skill-diff
    p_dif = subparsers.add_parser("skill-diff", help="Show unified diff between current and previous skill version")
    p_dif.add_argument("skill_id", help="Skill ID to diff")
    p_dif.set_defaults(func=cmd_skill_diff)

    # genesis-check
    p_gen = subparsers.add_parser("genesis-check", help="Verify genesis axiom integrity against Layer 2 manifest")
    p_gen.set_defaults(func=cmd_genesis_check)

    # forge
    p_frg = subparsers.add_parser("forge", help="Trigger full LLM Skill Forge cycle (deficit→research→draft→Z3→graduate)")
    p_frg.add_argument("description", help="Description of the capability to forge")
    p_frg.set_defaults(func=cmd_forge)

    # historian
    p_hist = subparsers.add_parser("historian", help="Query the persistent SCADA Historian audit log")
    p_hist.add_argument("--domain", choices=["scada", "robotics", "gui", "mcp", "system"], default=None, help="Filter by domain")
    p_hist.add_argument("--limit", type=int, default=20, help="Number of records to fetch")
    p_hist.set_defaults(func=cmd_historian)

    # scada
    p_scd = subparsers.add_parser("scada", help="Inspect or test live Modbus fieldbus registers")
    p_scd.add_argument("--host", default=None, help="Modbus TCP host")
    p_scd.add_argument("--port", type=int, default=None, help="Modbus TCP port")
    p_scd.add_argument("--read", action="store_true", help="Read live Modbus telemetry (default action)")
    p_scd.add_argument("--write-pressure", type=int, default=None, help="Directly write target pressure register")
    p_scd.add_argument("--toggle-a", action="store_true", help="Toggle Valve A (Coil 0)")
    p_scd.add_argument("--toggle-b", action="store_true", help="Toggle Valve B (Coil 1)")
    p_scd.set_defaults(func=cmd_scada)

    # test
    p_tst = subparsers.add_parser("test", help="Execute built-in verification unit test suite")
    p_tst.set_defaults(func=cmd_test)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == "__main__":
    main()
