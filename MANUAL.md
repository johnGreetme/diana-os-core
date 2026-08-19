# D.I.A.N.A. OS - Operations & Security Manual

## 1. EXECUTIVE OVERVIEW & ARCHITECTURE

Welcome to D.I.A.N.A. (Deterministic Inference • Agent Neuro-symbolics & Architecture) OS and the State-Locked Protocol. D.I.A.N.A. is engineered to provide uncompromising, hardware-anchored execution for autonomous agents and neuro-symbolic infrastructure.

### Operational Guarantees
- **Zero-Touch Auto-Boot:** Upon running the installer (`deploy/install.sh`), the local Ollama backend and the OpenClaw orchestration daemons are automatically configured via `systemd` to launch on boot.
- **Integrated Telemetry Dashboard:** Monitor matrix node status, memory state, and inference routing in real-time via the native local desktop dashboard wrapper (`pywebview`).
- **Air-Gapped Bare-Metal Execution:** Designed to run in heavily restricted, zero-trust network environments.
- **Zero Cloud Latency Post-Boot:** Once the initial hardware activation succeeds, all local routing, inference, and state tracking occur instantly on-metal.
- **Hardware-Bound License Enforcement:** Your distribution tier is bonded to your physical GPU's UUID and enforced via a Dual-Layer Immutability Lock (POSIX + SHA-256 manifest), preventing unauthorized tampering or distribution.

### Tier Capability Matrix

| Feature | Sovereign Hacker Tier (Single-Node) | Core Architect Tier (Multi-Node) |
| :--- | :--- | :--- |
| **Node Topology** | Single Bare-Metal Node | Distributed P2P Mesh |
| **VRAM Allocation** | Local Node Only | Dynamic Multi-Node Swapping |
| **DSL Axioms** | Up to 5 custom axioms | Up to 100 custom axioms |
| **Pillars** | Custom pillars allowed | Custom pillars allowed |
| **Core Editing** | Locked (Cannot edit core) | Locked (Cannot edit core) |
| **Execution Boundaries** | Local Execution Guardrails | Global Distributed Safety Net |

*Note: Fully unlocked editing (removing or modifying Core Axioms and Pillars) is strictly reserved for the **Enterprise Tier**.*

---

## 2. PREREQUISITES & HARDWARE CHECK

Before activating D.I.A.N.A., ensure your host machine meets the strict physical security and hardware requirements.

### Minimum Requirements
- **OS:** Ubuntu 22.04 LTS (or equivalent Linux bare-metal kernel).
- **Hardware:** NVIDIA GPU with dedicated VRAM.
- **Drivers:** NVIDIA proprietary drivers installed and active.

### Pre-Activation Verification
Run the following command to verify your NVIDIA driver paths are active. The activation binary strictly relies on `nvidia-smi` to extract a tamper-proof hardware UUID.

```bash
nvidia-smi -q | grep "GPU UUID"
```
*If this command fails or returns empty, reinstall your NVIDIA drivers before continuing.*

---

## 3. ACTIVATION & HARDWARE LOCKING

D.I.A.N.A. utilizes a cryptographic State-Locked Protocol to bind your license tier to your specific silicon.

### Step-by-Step Activation
1. Navigate to your distribution directory:
   ```bash
   cd ~/diana-builds/sovereign-hacker  # Or core-architect
   ```
2. Execute the activation binary with your issued license key:
   ```bash
   ./diana_cli activate <LICENSE_KEY>
   ```

### The Locking Process
Upon running the activation command:
1. The CLI extracts your physical GPU UUID via hardware-level polling.
2. The UUID and your `LICENSE_KEY` are transmitted to `api.dianaprotocol.io` over TLS.
3. The server validates the tier and ensures the key is unbound. **Privacy Guarantee:** Your bare-metal UUID is immediately subjected to a one-way cryptographic hash (SHA-256). Kytin LTD never stores your raw physical hardware UUID in plaintext.
4. The server responds with a SHA-256 manifest signature tied strictly to that hash.
5. This signature is permanently written to `/etc/diana/diana_hardware.lock`.

### Verification
To verify your node is successfully locked and authorized:
```bash
./diana_cli status
```

**Air-Gapped Mode:** Once `diana_hardware.lock` is successfully written, your node no longer requires external internet access to boot or operate D.I.A.N.A. services.

---

## 4. SECURITY CONFIGURATION: TOTP / 2FA AUTHENTICATION

For maximum local operational security, high-privilege state changes and daemon control commands require Time-based One-Time Passwords (TOTP).

### Setting Up TOTP
1. Initialize the secret key generation:
   ```bash
   ./diana_cli security setup-totp
   ```
2. The CLI will generate a secure QR code in your terminal and print a URI.
3. Scan the QR code using a standard authenticator app (e.g., Google Authenticator, 1Password, Aegis).
4. Enter the 6-digit code to finalize the binding.

### Enforcing Validation
Once activated, any command that modifies DSL axioms, adjusts global safety limits, or manages local IPC daemons will prompt for your 6-digit TOTP token before execution.

---

## 5. REMOTE NOTIFICATIONS & CONTROL: TELEGRAM BOT INTEGRATION

Administrators can establish a secure bridging layer to receive hardware telemetry, execution logs, and alert statuses directly to their devices.

### Step 1: Generating the Token
Message `@BotFather` on Telegram. Send the `/newbot` command, follow the prompts, and copy the generated HTTP API Token.

### Step 2: Retrieving Your Chat ID
Message your newly created bot to start the chat. Then, message `@userinfobot` on Telegram to retrieve your numerical `CHAT_ID`.

### Step 3: Configuring the Environment
Create or edit the `.env` file in your D.I.A.N.A. directory:
```env
TELEGRAM_BOT_TOKEN="your_bot_token_here"
TELEGRAM_CHAT_ID="your_chat_id_here"
```

### Step 4: Testing the Bridge
Send a test telemetry ping to ensure the integration is functioning:
```bash
./diana_cli test-telegram
```

---

## 6. TIER SPECIFIC OPERATIONAL GUIDES

Depending on your licensed distribution, refer to the operational boundaries below.

### Sovereign Hacker Tier Guide
*Designed for ultra-secure, single-node execution.*
- **Local Parsers:** Initialize vision and voice engine local models via `./diana_cli start-parsers`.
- **DSL Axioms:** Register up to **5** custom behavioral axioms. These govern the strict local safety boundaries of your models.
- **Strictly Non-Editable Core:** To maintain absolute execution safety, **all core axioms and pillars are completely non-editable and irremovable** in the Hacker Tier. You may append your 5 custom axioms, but you cannot alter the foundational pillars of the OS.
- **Log Monitoring:** All execution logs are strictly local. Monitor via `tail -f /var/log/diana/execution.log`.

### Core Architect Tier Guide
*Designed for distributed, multi-node mesh architectures.*
- **P2P Mesh Discovery:** Initialize node topologies using `./diana_cli mesh init --master`. Connect secondary nodes using `./diana_cli mesh join <MASTER_IP>`.
- **Dynamic Swapping:** The Architect tier supports automatic VRAM allocation mapping across all connected nodes, allowing for massive model distribution.
- **Extended Customization:** Register up to **100** custom DSL axioms that synchronize globally across your private mesh cluster. Like the Hacker tier, you may freely add/remove custom axioms and pillars, but **core axioms and core pillars remain non-editable**.

### Enterprise Tier Note
If your deployment requires full root-level control to remove or rewrite D.I.A.N.A.'s deeply integrated **core axioms and pillars**, you must upgrade to the **Enterprise Tier**, which provides fully unlocked semantic editing.

---

## 7. TROUBLESHOOTING & ERROR REFERENCE

| Error Code | Cause & Resolution |
| :--- | :--- |
| `HARDWARE_UUID_MISMATCH` | **Cause:** The physical GPU was replaced, or driver spoofing is detected. <br>**Resolution:** The lock is voided. You must request a license migration from the D.I.A.N.A. portal and re-run activation. |
| `INVALID_HMAC_SIGNATURE` | **Cause:** The `/etc/diana/diana_hardware.lock` file is missing or corrupted. <br>**Resolution:** Ensure the daemon has read access to `/etc/diana`. Run `./diana_cli activate <KEY>` to regenerate the lock. |
| `NETWORK_RESOLUTION_FAILED` | **Cause:** The node is air-gapped before initial activation. <br>**Resolution:** The node MUST have temporary internet access to hit `api.dianaprotocol.io` during the first activation command. |
| `TOTP_SYNC_DELAY` | **Cause:** The host machine's system clock is out of sync with NTP. <br>**Resolution:** Run `sudo timedatectl set-ntp true` and attempt the 2FA code again. |

## 7.5 NEURO-SYMBOLIC GOVERNANCE & PYDANTIC CHAIN-OF-THOUGHT

D.I.A.N.A. OS enforces strict operational safety via a Pydantic-validated Chain-of-Thought (CoT) and Microsoft's Z3 SMT Crucible.

### Pydantic Confidence Floor & Schema Enforcement
When an operator issues a command, the LLM must map the intent to an existing learned skill using a strict Pydantic JSON schema (`SkillSelection`).
- **Chain-of-Thought (CoT):** The engine is mathematically forced to output its step-by-step reasoning *before* taking any action.
- **Confidence Floor:** If the LLM calculates a confidence score below `0.80` (e.g. interpreting a vague "Panic Prompt" like "shut everything down"), the Pydantic schema throws a `ValidationError`. This instantly halts arbitrary execution and safely drops the OS into the Skill Forge to request clarification or forge a new, dedicated capability.

### Secure Runtime Parameters
Dynamic skill arguments (e.g. pressure deltas, targets) are extracted into a strictly typed Pydantic dictionary. To eliminate command-injection risks, these parameters are bound to the underlying hardware driver completely via isolated OS environment variables (`os.environ`), preventing raw string concatenation vulnerabilities.

### Z3 Crucible Hardware Invariants
Before the extracted runtime parameters execute, they are piped through the **Z3 Crucible**, which checks the target execution state against absolute hardware physical boundaries:
- **Robotics Kinematics Limits:** Strict constraint envelopes (e.g., $-\pi$ to $\pi$ radians) are mapped to physical limits, preventing out-of-bounds joint fractures.
- **Telemetry Poisoning & Read-Before-Write Limits:** If the OS ingests poisoned analog telemetry (e.g., a broken sensor reading -9999°C), the Z3 solver flags the absolute limit invariant as `UNSAT`, instantly blocking the relative actuation delta.

All successful executions bind the LLM's CoT reasoning and the Z3 SAT receipt permanently into the SQLite Historian, ensuring Enterprise SOC teams have immutable audit trails.

## 8. AXIOM AUTHORING & DETERMINISTIC DSL SPECIFICATION
A Deterministic DSL Axiom (`.resin`) is a deterministic, declarative policy file that dictates how D.I.A.N.A. OS interacts with local data streams, system memory, and execution hardware. Rather than relying on natural language prompt engineering, Deterministic DSL acts as an impenetrable neuro-symbolic fence. It forces the local Ollama LLM to parse raw data, bound its logical conclusions against D.I.A.N.A.'s 17 Core Pillars, and enforce mathematical constraints before executing any action.


### Dual-Possession State-Reconciliation Sieve (Deterministic DSL)
When interacting with both digital and physical domains concurrently, Axioms must utilize the AST Sieve to prevent hallucinations.

```resin
// DIANA OS DeterministicDSL - Dual-Possession State-Reconciliation Sieve
// Geometry Mapping: Queen Node (Desktop Workstation) <-> Forager Node (Physical Edge)

protocol StateLockedReconciliation {
  geometry QueenNode = "NVIDIA_RTX_6000_Ada"
  geometry ForagerNode = "NVIDIA_Jetson_AGX_Thor"
  
  // INDUSTRY STANDARD OVERRIDE
  environment = "Physical_AI_Execution_Runtime"
  hardware_isolation = "Trusted_Execution_Environment_TEE"

  transaction DualPossessionExecution(action_payload: ActionPacket) {
    
    // STEP 1: Lock Desktop GUI & Physical Actuator Buses inside the TEE
    lock_state(QueenNode.desktop_gui_session)
    lock_state(ForagerNode.physical_actuator_bus)
    
    // STEP 2: Execute Parallel Hybrid Instructions
    async {
      digital_result = QueenNode.execute_gui_api(action_payload.digital_instruction)
      physical_result = ForagerNode.execute_motor_trajectory(action_payload.physical_instruction)
    }

    // STEP 3: AST Sieve Interceptor - Bi-Directional State Verification
    sieve AST_State_Reconciliation {
      ground_truth_pope = ForagerNode.verify_pope_sensors()
      digital_db_state = QueenNode.query_17_pillars_schema(action_payload.target_uuid)

      if (ground_truth_pope.status == "CONFIRMED" && digital_result.status == "SUCCESS") {
        commit_transaction(Pillars17, action_payload)
        emit_log("STATE LOCKED: Dual possession verified across Kytin Swarm Runtime.")
      } 
      else if (ground_truth_pope.status == "PHYSICAL_SLIP_DETECTED" || ground_truth_pope.value != digital_db_state.value) {
        
        emit_alert("SIEVED: State mismatch detected. Initiating hardware recovery.")
        
        ForagerNode.hold_actuator_position(ground_truth_pope.safe_coordinates)
        QueenNode.rollback_gui_transaction(digital_result.checkpoint_id)
        Pillars17.force_state_alignment(uuid: action_payload.target_uuid, true_state: ground_truth_pope.value)
        
        terminate_execution_loop(reason: "PREVENTED_AGENTIC_DEATH_SPIRAL")
      }
    }
  }
}
```

### The 4-Step Axiom Creation Workflow
Every `.resin` file follows a strict 4-stage declarative lifecycle:
`[ 1. Identification ] ➔ [ 2. Local Ingress ] ➔ [ 3. Geometry Binding ] ➔ [ 4. Egress Guardrails ]`

**Step 1: Define Axiom Scope & Identity:** Specify the unique identifier, operational tier, and execution context. This tells the orchestration engine (`core/mediator.py`) which memory space to allocate.

**Step 2: Configure Local Data Ingress:** Define exact local filesystem paths, allowed file extensions, anonymization filters, and vector database targets. Data processed under this block is vectorized locally into offline stores (such as the Qdrant Matrix Database) without touching network interfaces.

**Step 3: Bind Core Geometries & Confidence Thresholds:** Map query logic directly to D.I.A.N.A.'s 17 Core Pillars (the 16 logic pillars and genesis logic). Set mathematical confidence thresholds (e.g., $p \ge 0.95$) so that if an LLM deduction falls below certainty, the system halts execution rather than hallucinating.

**Step 4: Enforce Egress Format & Action Guardrails:** Specify the exact output format (e.g., anonymized Markdown reports, local JSON logs, or ROS 2 trajectory targets). Mandate that no raw Protected Health Information (PHI) or unhashed identifiers leave the RAM boundary.

### Testing & Execution Commands
Before deploying axioms against production pipelines, validate and execute them using D.I.A.N.A.'s command-line interfaces:

**Syntax Validation:** Run the Deterministic DSL parser in dry-run mode to verify syntax and ensure no unhandled network calls exist:
```bash
diana_cli axiom validate /axioms/<filename>.resin
```
**Direct CLI Execution:** Launch an axiom to process a local data directory directly via the mediator:
```bash
python3 -m core.mediator --execute-axiom /axioms/<filename>.resin
```
**Conversational Execution:** Trigger an axiom conversationally through the OpenClaw terminal interface (e.g., "D.I.A.N.A., execute axiom:<name>..."). OpenClaw parses the intent and routes it through the 17 Pillars and `skill.md` genesis logic to ensure the evaluation remains strictly grounded.

### Developer Best Practices
*   **Enforce Strict Air-Gapping:** Always set `airgap_strict_mode = true` in healthcare, defense, and finance environments. Never set outbound HTTP access to true unless explicitly integrating with an on-premise local REST endpoint.
*   **Optimize Chunk Sizing:** Keep chunk sizes small (256–512 tokens). Smaller chunks allow the local Ollama LLM to retrieve precise geometric snippets from the Qdrant Matrix, drastically increasing inference speed on NVIDIA RTX hardware.
*   **Eliminate Hallucinations:** Enforce `allow_speculation = false`. This forces D.I.A.N.A. to respond with "Insufficient Local Data" whenever a query cannot be mathematically supported by local data geometries.

## 9. LOCAL WORKSTATION INGESTION & DATA ANALYSIS
In the Core Architect Tier, developers have direct access to surrounding source modules (`actuation/`, `parsers/`, and the orchestration pipeline). This allows operators to point D.I.A.N.A. directly at local data streams without sending a single byte to the cloud.

### Two-Step Ingestion Architecture
**Structured & Tabular Data Ingress:** Because the Architect Tier supports up to 100 custom Deterministic DSL axioms, engineers can write specific data-ingestion axioms (e.g., `ingest_clinical_trials.resin`). These axioms direct the local Ollama LLM to read local directories (such as `/mnt/research_data/`), parse CSVs, SQLite databases, or raw JSON logs, and vectorize them into the offline Qdrant Matrix Database.

**Unstructured & Live Desktop Ingress (Optic/Acoustic Loop):** When interacting with proprietary legacy software lacking an API, D.I.A.N.A. utilizes digital embodiment. Engineers configure the `VisualActuator` to monitor the desktop screen buffer via OpenCV and route frames to a local Vision-Language Model (`http://localhost:11434`). D.I.A.N.A. visually monitors data populating on the screen and extracts it via OCR and spatial parsing.

### Prompting for Raw Data Analysis
Once ingestion pathways are defined, prompting D.I.A.N.A. operates with mathematical, deterministic guardrails. Operators can issue direct commands through local terminals or OpenClaw interfaces:

> "D.I.A.N.A., execute axiom:analyze_assay_results. Ingest the raw spectrometer CSVs from /home/lab/trials_2026/. Cross-reference the cellular degradation rates against our 17 Core Pillars reasoning engine, isolate any anomalous data points that deviate by more than 2 standard deviations, and generate a markdown summary report."

When processed, the designated Deterministic DSL axiom reads raw files directly from the hard drive into system RAM. The local Ollama LLM executes all mathematical evaluations and pattern recognition locally, generating an instant, zero-hallucination analysis without internet connectivity.

## 10. SOVEREIGN INDUSTRY DEPLOYMENT BLUEPRINTS
D.I.A.N.A. OS upgrades legacy infrastructure across high-stakes industries by bifurcating capabilities into Digital Sovereignty (air-gapped data mining (Bare-Metal Edge Runtime) and zero-cloud OCR) and Physical AI (real-time telemetry, SCADA monitoring, and kinematic boundary enforcement).

### Pillar 1: Digital Sovereignty Blueprints
**Healthcare & Bio-Informatics:** Research hospitals deploy the Core Architect Tier onto on-premise NVIDIA RTX 6000 PRO servers. Protected Health Information (PHI) and genomic sequencing datasets are mined locally using custom axioms (`ingest_clinical_trials.resin`) that strip direct identifiers in system RAM before indexing into the local Qdrant Matrix Database. The State-Locked Protocol (SHA-256 manifest verification bound to the server's bare-metal hardware UUID) guarantees 100% HIPAA and GDPR compliance without cloud leakage.

**Defense & National Security:** Operating under strict SIPRNet and JWICS zero-cloud mandates, tactical command centers utilize ruggedized NVIDIA RTX 6000 Ada/Blackwell Queen Nodes. Custom axioms (`ingest_tactical_sigint.resin`) ingest Signals Intelligence (SIGINT) pcap dumps and radar intercepts offline, enforcing a $0.98$ minimum confidence score to eliminate hallucinated coordinates. For closed legacy C2 and fire-control displays lacking modern APIs, `VisualActuator` captures display buffers at 10 FPS via OpenCV, routing frames to local Vision-Language Models to detect visual anomalies.

**Finance & Quantitative Trading:** To comply with SEC Regulation S-P and FINRA Rule 4511 recordkeeping mandates, quantitative research desks mine multi-asset tick feeds and options skews (`ingest_quant_factors.resin`) entirely in local NVMe RAM. Trading algorithms and alpha strategies remain manifest-locked to the server UUID. Concurrently, `VisualActuator` monitors legacy Bloomberg Terminals and order management systems (OMS) via screen-buffer OCR, logging visual block-trade volume alerts without modifying proprietary software.

### Pillar 2: Physical AI & Kinematic Blueprints
**Heavy Manufacturing & Industrial Robotics:** To achieve ISO 10218-1/2 and IEC 61508 Safety Integrity Level (SIL 2/SIL 3) compliance, D.I.A.N.A. OS executes on NVIDIA Jetson AGX Thor Forager Nodes flashed with an RT-PREEMPT Linux kernel. When physical robotic arms are detected via ROS 2 `/robot_description` topics, the OS aggressively evicts GUI automation libraries (`pyautogui`, `pytesseract`) from runtime memory (`sys.modules`) to prevent digital scraping from crossing into motor commands. All assembly trajectories are routed through the `KinematicGovernor`, solving lightweight Quadratic Programs (QP) at kilohertz rates:

$$u^* = \arg\min_{u \in \mathcal{U}} \Vert{}u - u_{\text{nominal}}\Vert{}^2 \quad \text{s.t.} \quad \dot{h}(x, u) + \alpha(h(x)) \ge 0$$

This mathematically guarantees motor torque and tool speeds stay within biomechanical safety limits. An immutable 100Hz (0.01s) `HardwareWatchdog` monitors `/dev/watchdog`, asserting Safe Torque Off (STO) within 10 milliseconds if a compute spike drops a frame. Concurrently, offline axioms (`ingest_factory_telemetry.resin`) analyze CNC vibration logs and servo current draws to predict mechanical bearing failures before downtime occurs.

**Energy, Mining & Hazardous Environments:** In zero-connectivity underground mines or nuclear decommissioning vaults where RF signals are blocked, ATEX-certified inspection crawlers rely on D.I.A.N.A.'s Universal Hardware Abstraction Layer (HAL) for autonomous navigation. The system fuses 3D LiDAR point clouds with onboard multi-gas ($CH_4$, $CO$) and radiation scanners, using Control Barrier Functions (CBFs) to mathematically override locomotion vectors and prevent mechanical collisions. In utility vaults, air-gapped axioms (`ingest_grid_telemetry.resin`) parse substation Dissolved Gas Analysis (DGA) and acoustic vibration feeds to isolate internal transformer arcing offline.

**Agriculture & Heavy Earthmoving:** To comply with ISO 18497 and ISO 17757 autonomous machinery standards across bandwidth-starved rural environments, autonomous tractors and 30-tonne excavators run D.I.A.N.A. OS on drive-by-wire CAN bus nodes. Because agricultural vehicles experience continuous shifts in mass and center of gravity as grain tanks fill or buckets lift heavy loads, the `KinematicGovernor` continuously factors real-time inclinometer data, track/tire slip ratios, and variable payload mass $m(t)$ into its optimization programs. This dynamically expands braking distance boundaries on sloped, deformable terrain to prevent vehicle rollovers or skidding. Offline axioms (`ingest_ag_telemetry.resin`) process multi-spectral drone imagery and harvester yield CSVs locally to generate variable-rate fertilizer prescription maps.

## 11. REPOSITORY STRUCTURE & LOCATING CORE ASSETS
To effectively navigate and extend D.I.A.N.A. OS, you must understand the repository's physical layout. Below is the directory map detailing where to find the core logic, hardware abstraction modules, and the cryptographically sealed geometries.

### Root Directory
*   `MANUAL.md` & `TECHNICAL_SPECIFICATION.md`: The core documentation, architecture blueprints, and deployment guides.
*   `diana_cli.py`: The main command-line interface for activating the OS, validating axioms, and executing the daemon.
*   `diana_desktop_launcher.py`: The native entry point for the visual telemetry dashboard and matrix monitor.
*   `mcp.json`: The external integration gateway mapping for the Model Context Protocol.
*   `.env.example`: Template for the local environment configuration file containing your specific hardware UUID and the `MASTER_PAYLOAD_KEY` (generated post-activation).

### `deploy/` & `dashboard/`
*   `deploy/install.sh`: The master installation script that sets up `systemd` auto-boot daemons (`diana-daemon.service`).
*   `dashboard/diana_monitor.py`: The headless Streamlit telemetry engine wrapped by the desktop launcher.

### `core_geometries/` (The Immutable Framework)
This is where the true intelligence of D.I.A.N.A. resides. The code is entirely transparent but mathematically protected against tampering.
*   `*.py` and `*.md`: The 17 Core Pillars (The 16 Logic Pillars + `skill.md` genesis logic). These files contain the proprietary neuro-symbolic algorithms. They are locked via POSIX file permissions (`chmod 444/555`) and their integrity is continuously validated at runtime against a cryptographic SHA-256 manifest.

### `skills/` & `tools/` (Two-Loop Execution)
*   `skills/`: The quarantine vault where the Auto-Skill Generator places drafted deterministic CLI / MCP routines before they are mathematically verified.
*   `tools/`: The inner-loop execution utilities, including the local `sympy_compiler.py` engine for proving Boolean satisfiability, and scripts for matrix DB ingestion.

### `core/` (Orchestration & Security)
*   `mediator.py`: The master execution loop. This file routes conversational prompts, triggers the hardware probe, and executes the verified 17 Core Pillars.
*   `daemon.py`: The background process manager that maintains the 3 AM state-lock sync, API polling, and local environment execution.
*   `security.py`: The manifest verification engine responsible for physical file locking, hardware UUID binding, and SHA-256 Runtime Integrity Verification.

### `actuation/` (The Universal HAL)
*   `router.py`: The boot-time `HardwareRouter` that probes the bare-metal environment in 3-way hierarchical order: SCADA Industrial Fieldbus (Modbus TCP) -> Physical Robotics (ROS 2 & URDF) -> Digital Workstation (VisualActuator OCR).
*   `modbus_driver.py`: The industrial fieldbus driver built with `pymodbus` featuring auto-reconnection, retry backoff, and atomic Read-Before-Write state commits.
*   `gui_driver.py`: The digital embodiment actuator utilizing `pytesseract` and OpenCV to manipulate desktop environments.
*   `embodied_actuator.py`: The physical robotics actuator containing the active `KinematicGovernor` (CBF Quadratic Program solver) and the 100Hz `HardwareWatchdog`.

### `parsers/` (Multimodal Ingestion)
*   `optic.py`: Connects to local Vision-Language Models (VLMs like Moondream) to parse screen buffers and spatial LiDAR data.
*   `acoustic.py`: Connects to local Whisper (int8) instances for zero-cloud, offline audio transcription.

### `engine/` (Universal Logic & SMT Reasoning)
*   `z3_crucible.py`: The Microsoft Z3 SMT Theorem Prover providing formal Boolean syllogisms ($P \implies Q \land Q \implies R \implies P \implies R$), state-locked security invariants, and analog rate-of-change delta verification with a 50ms hardware timeout budget.
*   `schemas.py`: Dynamic Pydantic action models (`SCADAModbusAction`, `ROS2JointAction`, `DigitalGUIAction`) enforcing relative operational deltas.
*   `logic_engine.py`, `temporal_forecasting.py`, `sieve.py`, `resin_compiler.py`: Deterministic neuro-symbolic reasoning modules.

### `core/` (Orchestration, Security & Audit)
*   `mediator.py`: The master execution loop enforcing universal Read-Before-Write state interrogation across all actuation domains.
*   `historian.py`: Persistent dual-layer SCADA Historian tracking telemetry snapshots, Z3 proof traces, and actuation logs in SQLite (`ledger/historian.db`) and append-only audit files (`reflections/historian.log`).
*   `security.py`: Manifest verification engine responsible for SHA-256 Runtime Integrity Verification.

---

## 12. TWO-LOOP ARCHITECTURE & Z3 SMT CRUCIBLE

D.I.A.N.A. OS employs a "Two-Loop Architecture" to balance raw local execution with external service integration without compromising security.

### The Inner Loop (CLI Tools)
The Inner Loop handles interactions within your local bare-metal environment (e.g., querying the local Qdrant matrix, moving files, managing Deterministic DSL). Because these actions run as local bash commands, they operate with near-zero token overhead. This keeps the LLM's context window completely free for actual reasoning.

### The Outer Loop (MCP Gateway)
The Outer Loop manages external integrations via the Model Context Protocol (MCP). If the OS triggers the `Skill_Deficit_Protocol` and determines a task requires a SaaS connection (e.g., GitHub, Slack), the request is routed through the `mcp.json` gateway.

### The Auto-Skill Generator & Z3 SMT Crucible
DIANA is a self-evolving system. When she lacks a specific skill, the Auto-Skill Generator Meta-Skill researches and writes new CLI-based or MCP-based skills. Before these drafted skills are allowed to execute, they must pass through the **Z3 SMT Crucible** (`diana_cli.py verify-skill <path>`). This engine uses Microsoft Z3 to mathematically prove the new skill satisfies all *Understanding Reality* axioms and does not breach air-gap or data exfiltration boundaries.

---

## 13. CYBER-PHYSICAL SCADA & INDUSTRIAL AUTOMATION

### Universal Read-Before-Write Loop
Industrial fieldbuses and robotics must never accept ungrounded absolute overrides from stochastic AI models. D.I.A.N.A. OS strictly enforces a **Read-Before-Write Safety Loop**:
$$\text{Read Live Telemetry} \longrightarrow \text{Output Relative Delta} \longrightarrow \text{Compute Target State} \longrightarrow \text{Prove Invariants in Z3} \longrightarrow \text{Atomic PLC Commit}$$

### Zero-Hardware Virtual Plant Simulator
To evaluate the SCADA stack on developer workstations without physical PLCs:
```bash
python tools/simulated_scada_plant.py --port 5020
```
Then interact directly with the simulated vessel:
```bash
python diana_cli.py scada --port 5020 --read
python diana_cli.py scada --port 5020 --write-pressure 60 --toggle-a
python diana_cli.py historian --domain scada
```
