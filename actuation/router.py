"""DIANA OS - Universal Hardware Abstraction Layer (HAL) Router.

Probes the host and network environment to deterministically bind to:
1. SCADA Industrial Fieldbus Domain (Modbus TCP)
2. Physical Robotics Domain (ROS 2 & URDF Kinematics)
3. Digital Workstation Domain (PyAutoGUI & Tesseract OCR)
"""

import sys
import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)

class HardwareRouter:
    """Universal Domain Router that probes and binds to the active cyber-physical runtime."""

    def __init__(self):
        self.active_domain = "digital"
        self.is_embodied = False
        self.is_scada = False
        self.actuator: Any = None
        self.modbus_driver: Optional[Any] = None
        self._probe_hardware()

    def _probe_hardware(self):
        """Probes environment in strict hierarchical order: SCADA -> Robotics -> Digital."""
        logger.info("[ROUTER] Initiating Universal HAL Hardware Probe...")

        # 1. SCADA Domain Probe (Modbus TCP / OpenPLC)
        if self._probe_scada():
            return

        # 2. Physical Robotics Domain Probe (ROS 2 / URDF)
        if self._probe_robotics():
            return

        # 3. Digital Workstation Domain Fallback
        self._fallback_to_digital()

    def _probe_scada(self) -> bool:
        """Probes for active Modbus TCP server / Industrial PLC."""
        modbus_host = os.environ.get("MODBUS_HOST") or os.environ.get("PLC_HOST")
        domain_env = os.environ.get("DIANA_DOMAIN", "").lower()

        if modbus_host or domain_env == "scada":
            logger.info(f"[ROUTER] SCADA environment detected. Initializing ModbusDriver...")
            try:
                from actuation.modbus_driver import ModbusDriver
                driver = ModbusDriver()
                if driver.connect():
                    self.modbus_driver = driver
                    self.actuator = driver
                    self.active_domain = "scada"
                    self.is_scada = True
                    logger.info("[ROUTER] SCADA domain active (Modbus TCP connected).")
                    return True
                else:
                    logger.info("[ROUTER] Modbus server unreachable at configured address. Checking next domain.")
            except Exception as e:
                logger.warning(f"[ROUTER] Modbus probe failed: {e}")
        return False

    def _probe_robotics(self) -> bool:
        """Probes for ROS 2 real-time environment and /robot_description URDF."""
        if "ROS_DISTRO" not in os.environ:
            return False

        logger.info("[ROUTER] Probing for physical robotics embodiment (ROS 2 & URDF)...")
        try:
            import rclpy
            from actuation.embodied_actuator import EmbodiedActuator

            temp_actuator = EmbodiedActuator()
            if temp_actuator.is_active():
                self.actuator = temp_actuator
                self.is_embodied = True
                self.active_domain = "robotics"
                self._purge_digital_namespace()
                logger.info("[ROUTER] Robotics domain active (ROS 2 / URDF latched).")
                return True
            else:
                logger.info("[ROUTER] /robot_description not found. Falling back.")
                temp_actuator.shutdown()
        except ImportError:
            logger.info("[ROUTER] ROS 2 (rclpy) not found in Python environment.")
        except Exception as e:
            logger.error(f"[ROUTER] Robotics probe failed: {e}")
        return False

    def _purge_digital_namespace(self):
        """Purges desktop GUI libraries from memory to enforce physical domain isolation."""
        logger.info("[ROUTER] Physical domain confirmed. Purging digital namespace (pyautogui, pytesseract).")
        modules_to_purge = ['pyautogui', 'pytesseract', 'PIL.Image', 'PIL']
        for mod in modules_to_purge:
            if mod in sys.modules:
                del sys.modules[mod]

    def _fallback_to_digital(self):
        """Initializes the VisualActuator for desktop automation."""
        try:
            from actuation.gui_driver import VisualActuator
            self.actuator = VisualActuator()
        except ImportError as e:
            logger.info(f"[ROUTER] VisualActuator optional dependencies not present: {e}. Running in headless mode.")
            self.actuator = None
        self.active_domain = "digital"
        logger.info("[ROUTER] Bound to Digital Workstation Domain.")

    def get_actuator(self) -> Any:
        return self.actuator

    def get_domain(self) -> str:
        return self.active_domain
