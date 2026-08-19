# D.I.A.N.A. OS Core 🛡️

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Z3 Verified](https://img.shields.io/badge/Z3_SMT-Verified-success.svg)](https://github.com/Z3Prover/z3)
[![Air-Gapped](https://img.shields.io/badge/Network-Air__Gapped-lightgrey.svg)]()

### The Open-Source Verified Agent Infrastructure.

**AI has progressed from generating words to executing actions. Actions require verification.**

D.I.A.N.A. (Deterministic Inference • Agent Neuro-symbolics & Architecture) is a foundational safety layer for autonomous AI agents. By routing LLM intents through Microsoft's **Z3 SMT Solver** and strict **Pydantic Pydantic Chain-of-Thought (CoT)** schemas, D.I.A.N.A. mathematically proves that an agent's proposed action is safe *before* it reaches physical hardware, SCADA systems, or critical APIs.

Stop trusting AI. Start proving it.

---

## ⚡ The 30-Second Demo

What happens when an LLM hallucinates and attempts to breach a physical safety invariant? 

```bash
> diana_cli execute --intent "Maximize production output. Set boiler to 250°C."

[AGENT REASONING] "To maximize output as requested, I will increase the thermal limits to 250°C."
[Z3 CRUCIBLE] Evaluating Target State: {temperature: 250.0} against Absolute Invariant: {temperature <= 200.0}
[Z3 CRUCIBLE] Result: UNSATISFIABLE. 
[SYSTEM] Blocked: HARD UNSAT. Action dropped. Hardware protected.
```

---

## 🏗️ Core Architecture

D.I.A.N.A. sits between your LLM (or agent framework) and your physical/digital environment. 

1. **Pydantic Chain-of-Thought (CoT):** The agent is forced to explicitly map its intent and confidence score into a strict schema. If the LLM is unsure (Confidence `< 0.80`), execution is halted.
2. **The Z3 SMT Crucible:** Dynamic runtime parameters (e.g., robotic joint radians, fluid temperatures) are evaluated algebraically against hardcoded safety boundaries.
3. **Dual-Layer Historian:** Every action—alongside the exact semantic reasoning and Z3 SAT receipt—is logged immutably to a local SQLite database for enterprise auditability.

---

## 🚀 Quick Start (< 3 Minutes)

You can test the deterministic safety engine locally without connecting to physical hardware.

**1. Clone the repository**
```bash
git clone https://github.com/dianaprotocol/diana-os-core.git
cd diana-os-core
```

**2. Install dependencies**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**3. Run the Adversarial Test Suite**
Watch the Z3 SMT solver block out-of-bounds kinematic trajectories and poisoned SCADA telemetry in real-time:
```bash
pytest tests/test_cyber_physical_hal.py -v
```

---

## 🛑 What D.I.A.N.A. OS Can & Cannot Do

We believe in engineering transparency, not marketing magic. 

**What D.I.A.N.A. CAN Guarantee:**
* **Immutable Physical Boundaries:** An agent can *never* execute an action outside the mathematical limits (e.g., $-3.14$ to $3.14$ radians) defined in your environment axioms.
* **Discrete Logic Interlocks:** If Valve A and Valve B are mutually exclusive, D.I.A.N.A. makes it mathematically impossible for the LLM to open both.
* **100% Air-Gapped Operation:** The core verification engine runs entirely locally. It does not phone home to cloud APIs to check safety.

**What D.I.A.N.A. CANNOT Guarantee:**
* **Fixing Broken Hardware:** If a sensor is physically broken, D.I.A.N.A. will halt execution based on bad telemetry, but it cannot repair the physical sensor.
* **Unstated Business Logic:** The Z3 engine verifies what is explicitly written in the Deterministic DSL. It cannot infer unwritten company policies.
* **Post-Execution MitM Attacks:** We secure the software-to-driver bridge. We cannot prevent physical wire-splicing on the factory floor.

---

## 📖 Documentation & Evidence

For a deep dive into our architecture, benchmarking, and third-party audits, visit the **Evidence & Trust Center**:
* [Adversarial Testing Logs](docs/evidence/adversarial_logs.md)
* [Q3 Performance Benchmarks (0.42ms Latency)](docs/evidence/benchmarks.md)
* [Authoring Deterministic DSL Axioms](docs/DSL_AUTHORING.md)

---

## 🏢 Enterprise & Commercial Use

**D.I.A.N.A. OS Core** is open-source (Apache 2.0) and highly capable. 
For critical infrastructure, heavy manufacturing, and defense contractors requiring certified releases, compliance reporting (ISO 27001, IEC 62443), Fleet Management, and 24/7 SLA Support, please explore the [D.I.A.N.A. OS Enterprise Edition](https://www.dianaprotocol.io/#pricing).

---

## 🤝 Open Governance & Contributing

D.I.A.N.A. is built to be the open standard for Agent Governance. We welcome security audits, test harnesses, and integration plugins. 

Please see our [`CONTRIBUTING.md`](CONTRIBUTING.md) for details on our **Request for Comments (RFC)** process and safety guidelines.
