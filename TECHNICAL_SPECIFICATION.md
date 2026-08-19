# D.I.A.N.A. (Deterministic Inference • Agent Neuro-symbolics & Architecture) OS Technical Specification

**Authored By:** Kytin LTD Engineering  
**Version:** 1.0  
**Target Audience:** Systems Engineers, Infrastructure Architects, Node Operators

---

## 1. System Architecture & Orchestration Layer

D.I.A.N.A. OS is a deterministic orchestration layer that securely bridges raw local compute with neuro-symbolic reasoning. We explicitly acknowledge our utilization of established open-source frameworks, primarily **Ollama** for managing local LLM pipelines, the **OpenClaw** paradigm for conversational routing, and **Deterministic DSL** for deterministic axiom execution.

The value of the D.I.A.N.A. Immutable Framework lies in its integration: we eliminate dependency hell, environment fragmentation, and driver conflicts. By manifest-locking the orchestration layer, we deliver a unified, out-of-the-box runtime that guarantees deterministic execution.

### Zero-Touch Deployment & Telemetry
- **Systemd Auto-Boot Initialization:** The installation script (`deploy/install.sh`) automatically provisions and configures `systemd` daemon services for the local Ollama LLM endpoint and the OpenClaw orchestration backend. This guarantees zero-touch initialization of the OS immediately upon server boot, minimizing human-in-the-loop dependencies for server restarts.
- **Native Telemetry Dashboard:** The OS includes a unified graphical dashboard (`diana_desktop_launcher.py`) that wraps a headless Streamlit server in a lightweight `pywebview` window. This visualizes active node topologies, real-time memory tensor allocations, inference queue routing, and matrix mesh health without relying on heavy background web servers.

### Universal Domain Routing (Digital vs. Physical)
D.I.A.N.A. OS operates as a Universal Intelligence Framework capable of dynamic embodiment. At boot, the OS executes a deterministic hardware probe via the Domain Router:
*   **Digital Embodiment:** If deployed on standard workstation infrastructure, the OS assumes control via the `VisualActuator`, utilizing pytesseract and VLM screen-buffer parsing for zero-API digital automation.
*   **Physical Embodiment:** If the router detects an RT-PREEMPT Linux kernel and a ROS 2 URDF blueprint, the OS aggressively purges all digital GUI libraries from memory to enforce strict domain isolation. It then binds to the `EmbodiedActuator` to assume control of physical robotic joints. 

### Multimodal & Spatial Parsers
The orchestration layer features pre-configured hooks for offline parsing:
*   **Acoustic Parsing:** Local Whisper (int8) instance for low-latency voice-to-text.
*   **Optic Parsing (2D):** OpenCV and VLM integration for workstation screen-buffer parsing (e.g., Moondream at `http://localhost:11434`).
*   **Spatial Parsing (3D):** VSLAM and LiDAR data fusion for real-time volumetric mapping required for physical drone and humanoid kinematics.

### Vector Data Matrix (Qdrant)
All unstructured data ingestion, multimodal context, and spatial geometries are vectorized and stored securely within the local **Qdrant Matrix Database**. This high-performance, Rust-based vector engine runs bare-metal, enabling lightning-fast similarity searches and geometric grounding without ever transmitting embeddings to the cloud.

### Bare-Metal Hardware Acceleration (CUDA & Tensor Engine)
D.I.A.N.A. OS bypasses generic CPU abstraction layers by binding directly to NVIDIA CUDA kernels and Tensor Core execution engines. The runtime is architecturally optimized across three distinct GPU generations:
* **Blackwell Architecture (FP8/FP4 Precision):** Natively leverages 5th-Gen Tensor Cores and the Transformer Engine on hardware such as the NVIDIA Jetson AGX Thor and RTX 5070 Ti. This enables ultra-fast execution of quantized int8 Whisper and VLM vision pipelines with minimal VRAM overhead.
* **The Blackwell Architecture (NVIDIA RTX 6000 PRO Generation):** Powering your enterprise Queen node, Blackwell features 5th-generation Tensor Cores, a native 2nd-generation Transformer Engine, and over 24,000 CUDA cores. By utilizing native FP4 and FP8 micro-scaling formats, this extreme architectural density allows the Queen node to hold massive temporal ledgers in VRAM while simultaneously orchestrating the 17 Core Pillars across a distributed network with zero compute bottlenecks.
* **Ada Lovelace Architecture:** Leverages 4th-Gen Tensor Cores and high-density CUDA parallel processing on enterprise workstations (e.g., NVIDIA RTX 6000 Ada) to manage high-throughput reasoning workloads and temporal ledger synchronization.
* **Ampere Architecture:** Utilizes 3rd-Gen Tensor Cores on edge embedded systems (e.g., NVIDIA Orin Nano) for low-power, autonomous sensor ingestion and isolated axiom execution.

---

## 2. The Core Geometries (Proprietary Intelligence Engine)

While the orchestration leverages open tools, the foundational reasoning engine is entirely proprietary to Kytin LTD. The system is governed by **17 Core Pillars**:

*   **The 16 Logic Pillars:** Immutable, architectural logic structures that dictate how the orchestration layer parses intent, retains temporal memory, and executes workflows.
*   **The Genesis Axiom (`skill.md`):** The master logic file derived from *Understanding Reality*, which provides the system with its fundamental neuro-symbolic reasoning capabilities.

These geometries serve as the immutable brain of the operating system. They are the fixed boundaries within which the local LLM operates, ensuring the output remains grounded, logical, and safe from unbounded hallucinations.

---

## 3. The Immutable Infrastructure & Hash Verification

To protect the intellectual property of the Core Geometries while allowing enterprise users and auditors absolute transparency, D.I.A.N.A. OS employs a Dual-Layer Immutable Infrastructure model instead of black-box encryption wrappers.

### Layer 1: The Physical File Lock (POSIX Permissions)
During deployment (`install.sh`), standard Linux file permissions strip away "write" access from the core engine while leaving "read" and "execute" access wide open. The `tools/`, `core/`, and `engine/` logic scripts are locked to `chmod 555`, while the JSON schemas and `SKILL.md` documents are locked to `chmod 444`. This allows engineers to read every line of code but physically prevents them from saving edits, while keeping the `skills/` directory writable so the Auto-Skill Generator can continue evolving.

### 2. Build Phase & Manifest Generation
Prior to distribution packaging, the build script `generate_manifest.py` recursively hashes the core components of the OS. It bypasses runtime data stores (like `qdrant_storage/`, `reflections/`, and `ledger/`) and user configuration files (`.env`, `mcp.json`), producing a secure `core_manifest.sha256` integrity ledger.

### 3. Runtime Verification (SHA-256 Integrity Check)
Every time D.I.A.N.A. OS boots up, or before `mediator.py` processes a core logic request, `security.py` checks the current hashes of the deployed files against the signed manifest. If a root-level user bypasses the POSIX locks and alters a file, the SHA-256 hash immediately fractures. The system logs a `[CRITICAL KERNEL PANIC]` and halts all autonomous execution before the compromised code can run.

---

## 4. Physical AI & Kinematic Safety Architecture
Deploying D.I.A.N.A. OS into heavy industrial robotics or high-velocity drones requires hardware-level failsafes. When operating in Physical Embodiment mode, the OS enforces a strict safety triad:

1.  **RT-PREEMPT Kernel Mandate:** Physical deployments require a fully preemptible Linux kernel. This ensures the Linux scheduler prioritizes robotic safety callbacks over heavy Ollama reasoning workloads, mathematically guaranteeing millisecond-accurate execution.
2.  **Kinematic Governor (Control Barrier Functions):** All high-level intents generated by the 17 Core Pillars are routed through a deterministic Kinematic Governor. The OS calculates dynamic feasibility using a Quadratic Program (QP) and Control Barrier Functions (CBF) to enforce safe braking trajectories based on the robot's physical mass, velocity, and URDF limits.
3.  **Hardware Watchdog & Safety Islands:** The software maintains a hardcoded 100Hz heartbeat connection to bare-metal hardware watchdogs (e.g., the Jetson Thor Functional Safety Island). If the temporal ledger locks up or the OS kernel panics, the isolated hardware directly severs physical motor power, ensuring physical environments are never compromised by software-level logic failures.


### Trusted Execution Environment (TEE)
The core logic and state-locking mechanisms are securely isolated within a Trusted Execution Environment (TEE). The TEE is a hardware-isolated CPU/GPU memory enclave that guarantees code integrity and data confidentiality, rendering the logic completely impervious to external operating system or hypervisor tampering.


### Dual-Possession State-Reconciliation Sieve
To solve the latency disparity between digital speeds and physical momentum, the system enforces a Dual-Possession State-Reconciliation Sieve. The workload is strictly mapped:
* **The Queen Node (NVIDIA RTX 6000 Ada):** Manages the heavy spatial reasoning and desktop workstation GUI.
* **The Forager Node (NVIDIA Jetson AGX Thor):** Locks real-time physical actuator control inside its local TEE.

If a physical trajectory (via the Forager) executes concurrently with a digital API call (via the Queen), the AST Interceptor evaluates both return payloads. A deterministic rollback is triggered if the physical Proof of Physical Execution (PoPE) telemetry contradicts the digital software state. Physical bare-metal reality always overrides digital software state, preventing the agentic death spiral.

## 5. Swarm Topology & Distributed Routing

For enterprise and heavy infrastructure scaling, D.I.A.N.A. OS natively supports hierarchical distributed environments.

*   **Queen Nodes:** The primary orchestration hubs. Queen nodes manage the temporal ledger, coordinate complex reasoning tasks via the Core Geometries, and handle user/API ingestion.
*   **Forager Nodes:** Lightweight, edge-compute instances. Forager nodes are dispatched by the Queen to execute isolated logic routines, scrape data, or run parallelized inferencing. 

The routing between Queen and Forager nodes operates over secured local network protocols, maintaining the strict air-gapped guarantees of the overarching OS.

### Hardware Reference Profiles

**Enterprise Reference Architecture:**
* **Queen Node (Core Orchestration):** NVIDIA RTX 6000 PRO Generation (*Blackwell Architecture — 5th-Gen Tensor Cores, 2nd-Gen Transformer Engine*).
* **Forager Node (Edge Execution):** NVIDIA Jetson AGX Thor (*Blackwell Architecture — 5th-Gen Tensor Cores, Transformer Engine*).

**Developer / Dev-Kit Architecture:**
* **Queen Node:** NVIDIA RTX 5070 Ti (*Blackwell Architecture — FP8/FP4 Native Acceleration*).
* **Forager Node:** NVIDIA Orin Nano Dev Kit (*Ampere Architecture — 1024 CUDA Cores, 32 Tensor Cores*).

---

## 6. Tier Technical Boundaries

D.I.A.N.A. OS is distributed in two distinct tier bundles to accommodate different operational security (OPSEC) and development requirements.

| Feature / Capability | Sovereign Hacker Tier | Core Architect Tier |
| :--- | :--- | :--- |
| **Target Audience** | Security Researchers, Single-Node Operators | Systems Engineers, Swarm Deployers |
| **Distribution Format** | Transparent Pure Python Archive (.tar.gz) | Editable Source Modules & Framework |
| **Execution Scope** | Single-Node Execution | Multi-Node Swarm Deployments (Queen/Forager) |
| **Custom Deterministic DSL Axioms** | Support for up to **5** custom axioms | Support for up to **100** custom axioms |
| **Core Geometries** | Immutable via SHA-256 | Immutable via SHA-256 |
| **Code Auditing** | Read-only architecture manifests | Full access to surrounding module source code |
| **Tooling** | Standard `diana_cli` | `diana_cli_advanced`, Clawhub packaging scripts |

### Sovereign Hacker Bundle (`diana-os-hacker-v1.0.tar.gz`)
Optimized for lightweight execution and frictionless cross-architecture deployment. Pure Python (`.py`) distribution natively runs on x86_64 or ARM64 architectures (e.g., Jetson AGX Thor) without relying on heavily bound binary extensions. Transparency allows end-users to audit all logic routing locally.

### Core Architect Bundle (`diana-os-architect-v1.0.tar.gz`)
The developer-grade framework. It strips away the pre-compiled guardrails on the surrounding framework, allowing heavy-hitters to actively tailor the code, optimize the software for specific hardware, and rewrite routing logic. Includes advanced templates for deploying Queen/Forager network topologies.

---

## 7. The Two-Loop Architecture & Neuro-Symbolic Governance

To handle enterprise workloads safely, D.I.A.N.A. OS leverages a self-evolving Two-Loop Architecture governed by Microsoft's Z3 SMT Solver and strict Pydantic parsing.

### 1. Structured Chain-of-Thought (Pydantic Enforcement)
The engine does not rely on raw XML tags for critical decisions. The mediator layer intercepts skill selection and forces the Deductive Engine through strict Pydantic schemas (`SkillSelection`, `SkillForgeRequest`). 
- **Confidence Floor:** The runtime actively blocks any skill invocation where the LLM's confidence falls below `0.80`, safely halting ambiguous "Panic Prompts" and triggering a targeted Forge cycle instead of guessing.
- **Typed Parameter Extraction:** Dynamic arguments required for CLI or SCADA execution are extracted into a strictly typed `runtime_parameters` dictionary. To neutralize command-injection risks, these parameters are bound to the execution layer exclusively via isolated OS environment variables, not raw string concatenation.

### 2. The Outer Loop (MCP Gateway)
For external SaaS communication, the OS leverages the Model Context Protocol (MCP). The routing interceptor parses `<mcp_request>` tags and forwards validated payloads to external endpoints configured in `mcp.json`.

### 3. Z3 SMT Crucible Enforcement & Historian Binding
Both local CLI executions and physical embodied actions (ROS 2 / Modbus) are protected by the **Z3 Crucible** (`engine/z3_crucible.py`). 
When the LLM targets a state transition, the Z3 compiler evaluates the typed parameters against dynamic cyber-physical limits.
- **Robotics Kinematics Limits:** Strict radian bounds ($-\pi$ to $\pi$) prevent hallucinated out-of-bounds joint trajectories.
- **Telemetry Poisoning Shields:** Read-Before-Write bounds strictly block target state deltas if the current analog telemetry registers as physically impossible (e.g., NaN or $-9999$ degrees).

Every successful Z3 SAT receipt is permanently bound to the LLM's semantic Chain-of-Thought rationale and logged into a dual-layer, immutable SQLite Historian. Enterprise auditors can trace physical hardware actuations directly back to the original neuro-symbolic mapping that justified the action.
