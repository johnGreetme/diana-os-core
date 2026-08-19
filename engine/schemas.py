"""DIANA OS - Universal Pydantic Domain Action Schemas.

Defines validated structured output schemas for SCADA/Modbus, ROS 2 Robotics,
and Digital Workstation GUI automation.
"""

from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, field_validator

class SCADAModbusAction(BaseModel):
    """
    Structured action schema for industrial SCADA and Modbus fieldbus operations.
    Enforces relative operational deltas to prevent destructive hardware zeroing.
    """
    valid_intent: bool = Field(
        default=True,
        description="Set to True ONLY if the prompt is an actionable, unambiguous industrial control intent."
    )
    pressure_delta: int = Field(
        default=0,
        description="Relative change in pressure (units). Positive to increase, negative to decrease. 0 = no change."
    )
    toggle_valve_a: bool = Field(
        default=False,
        description="Set to True to toggle Valve A state (Coil 0). False = no change."
    )
    toggle_valve_b: bool = Field(
        default=False,
        description="Set to True to toggle Valve B state (Coil 1). False = no change."
    )
    register_deltas: Dict[int, int] = Field(
        default_factory=dict,
        description="Arbitrary holding register relative deltas mapped by address {addr: delta_value}."
    )
    coil_toggles: Dict[int, bool] = Field(
        default_factory=dict,
        description="Arbitrary coil toggles mapped by address {addr: True_to_toggle}."
    )
    reasoning: str = Field(
        default="",
        description="Engineering justification for the proposed operational delta."
    )

class ROS2JointAction(BaseModel):
    """
    Structured action schema for physical robotics trajectory and joint actuation.
    """
    valid_intent: bool = Field(
        default=True,
        description="Set to True if the robotics trajectory command is safe and well-formed."
    )
    joint_name: str = Field(
        default="joint_1",
        description="Target joint identifier from the URDF blueprint."
    )
    position_delta_rad: float = Field(
        default=0.0,
        description="Relative angular displacement delta in radians."
    )
    velocity_delta: float = Field(
        default=0.0,
        description="Relative velocity change in rad/s."
    )
    max_effort_nm: float = Field(
        default=50.0,
        description="Maximum permissible torque/effort bound in Newton-meters."
    )
    reasoning: str = Field(
        default="",
        description="Kinematic justification for the proposed joint trajectory."
    )

class DigitalGUIAction(BaseModel):
    """
    Structured action schema for desktop workstation GUI automation via OCR.
    """
    action_type: str = Field(
        default="click",
        description="Type of GUI action: 'click', 'double_click', 'type', 'press', 'scroll', 'inspect'."
    )
    target_text: str = Field(
        default="",
        description="On-screen text label to locate via OCR and actuate upon."
    )
    text_payload: str = Field(
        default="",
        description="Text string to type into active input element."
    )
    key: str = Field(
        default="",
        description="Special keyboard key to press (e.g. 'enter', 'tab', 'escape')."
    )
    scroll_clicks: int = Field(
        default=0,
        description="Mouse wheel clicks (positive for up, negative for down)."
    )

class SkillSelection(BaseModel):
    """
    Strict schema for autonomous skill selection via the Hot-Loader.
    Forces the Deductive Engine to explicitly state its reasoning before execution.
    """
    selected_skill_id: str = Field(
        ...,
        description="The exact skill slug to invoke from the Available Learned Skills list."
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        description="Step-by-step chain of thought mapping the user intent to this specific skill."
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence between 0.0 and 1.0 that this skill resolves the deficit."
    )
    runtime_parameters: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict,
        description="Key-value arguments mapped to the skill's execution payload."
    )

    @field_validator("confidence_score")
    @classmethod
    def enforce_confidence_floor(cls, v: float) -> float:
        if v < 0.80:
            raise ValueError(f"Confidence score {v:.2f} below minimum operational threshold (0.80). Trigger SkillForge instead.")
        return v

class SkillForgeRequest(BaseModel):
    """
    Strict schema for triggering the LLM Skill Forge.
    Forces the Deductive Engine to define the exact capability deficit.
    """
    capability_description: str = Field(
        ...,
        min_length=15,
        description="Specific, actionable description of the missing capability to be forged."
    )
    reasoning: str = Field(
        ...,
        min_length=20,
        description="Justification for why no existing skill matches and why a new one is required."
    )
    target_slug: str = Field(
        ...,
        pattern=r"^[a-z0-9-]+$",
        description="Proposed URL-safe slug for the new skill (e.g. 'check-modbus-health')."
    )

    @field_validator("target_slug")
    @classmethod
    def validate_non_meta(cls, v: str) -> str:
        prohibited = ["forge", "skill-loader", "z3-crucible", "the-skill"]
        if any(p in v for p in prohibited):
            raise ValueError(f"Target slug '{v}' attempts to forge core OS infrastructure. Prohibited.")
            
        # Anti-Recursion Duplicate Sieve
        import os, json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        registry_path = os.path.join(base_dir, "ledger", "skills_registry.json")
        if os.path.exists(registry_path):
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    reg = json.load(f)
                    if v in reg.get("skills", {}):
                        raise ValueError(f"Target slug '{v}' already exists in active registry. Do not forge a duplicate.")
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
        return v

def get_schema_for_domain(domain: str):
    """Dynamically routes and returns the appropriate Pydantic schema based on active domain."""
    domain_clean = (domain or "").lower().strip()
    if domain_clean in ["scada", "modbus", "openplc"]:
        return SCADAModbusAction
    elif domain_clean in ["robotics", "embodied", "ros2"]:
        return ROS2JointAction
    else:
        return DigitalGUIAction
