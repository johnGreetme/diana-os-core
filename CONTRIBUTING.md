# Contributing to D.I.A.N.A. OS Core

First, thank you for your interest in contributing. D.I.A.N.A. OS is designed to be the definitive **Verified Agent Infrastructure**, and achieving that requires rigorous, open collaboration from security engineers, roboticists, and the AI community.

Our philosophy is simple: **Proof over Promises.** 
Every new feature, constraint, or capability must be mathematically verifiable and auditable.

## 🧭 The Golden Rules of Contribution

1. **Safety First:** The Z3 SMT Crucible is the heart of D.I.A.N.A. Any PR that attempts to bypass, weaken, or obfuscate the `verify_invariants` flow will be instantly rejected.
2. **Deterministic Over Probabilistic:** Do not introduce stochastic (random) logic into the execution pathway. If an outcome cannot be predicted 100% of the time given the same state, it does not belong in the Core.
3. **No Cloud-Dependent Failsafes:** Safety checks must be capable of running entirely air-gapped on bare-metal hardware.

---

## 🛠️ How to Contribute

### 1. Submitting New Cyber-Physical Invariants (Z3 Rules)
If you are adding a new safety boundary (e.g., Drone Altitude Limits, OpenPLC safety interlocks) to `engine/z3_crucible.py`, your PR **must** include:
* The algebraic `solver.add()` logic.
* A corresponding test in `tests/test_cyber_physical_hal.py` that intentionally violates your new rule to prove that it results in a `HARD UNSAT` rejection.

### 2. The RFC Process (Architecture Changes)
For major changes (e.g., adding a new backend solver, changing the Pydantic CoT schema, or modifying the Dual-Layer Historian), we use a **Request for Comments (RFC)** process. 
1. Open an Issue with the tag `[RFC]`.
2. Clearly define the Problem, the Proposed Solution, and the Safety Implications.
3. Allow 7 days for the core maintainers and community to review the mathematical implications before submitting a PR.

### 3. Reporting Vulnerabilities (Responsible Disclosure)
If you find a way to bypass the Z3 Crucible, hallucinate past the Pydantic schema, or inject unsafe runtime parameters:
* **DO NOT open a public GitHub issue.** 
* Email the technical details directly to `support@dianaprotocol.io`.
* We take safety-critical disclosures extremely seriously and will coordinate a patched release with you.

---

## 💻 Local Development Setup

To run the codebase and test suite locally:

```bash
# 1. Fork and Clone your repository
git clone https://github.com/YOUR_USERNAME/diana-os-core.git
cd diana-os-core

# 2. Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 3. Install Requirements
pip install -r requirements.txt

# 4. Run the full Cyber-Physical Test Suite
# Ensure all 27+ tests pass before opening a PR
pytest tests/test_cyber_physical_hal.py -v
```

## 📜 Code of Conduct
D.I.A.N.A. is built for critical infrastructure, and our community reflects the professionalism of that sector. Be respectful, be rigorous, and let the math speak for itself.
