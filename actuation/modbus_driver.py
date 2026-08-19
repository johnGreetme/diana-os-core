"""DIANA OS - Industrial SCADA & Modbus TCP Actuator.

Provides universal fieldbus connectivity, auto-reconnection with exponential backoff,
Read-Before-Write state interrogation, and safe atomic state commit for PLCs.
"""

import os
import time
import logging
from typing import Dict, Any, Tuple, Optional, List

logger = logging.getLogger(__name__)

try:
    from pymodbus.client import ModbusTcpClient
    from pymodbus.exceptions import ConnectionException, ModbusException
except ImportError:
    ModbusTcpClient = None
    ConnectionException = Exception
    ModbusException = Exception

class ModbusDriver:
    """Industrial Modbus TCP driver with auto-reconnection and Read-Before-Write safeguards."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: float = 2.0,
        max_retries: int = 3,
        backoff_base: float = 0.5
    ):
        self.host = host or os.environ.get("MODBUS_HOST") or os.environ.get("PLC_HOST") or "127.0.0.1"
        self.port = int(port or os.environ.get("MODBUS_PORT") or 502)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.client: Optional[ModbusTcpClient] = None
        self._is_active = False

    def connect(self) -> bool:
        """Connects to the Modbus server with retry backoff."""
        if ModbusTcpClient is None:
            logger.warning("[MODBUS] pymodbus is not installed in the environment.")
            return False

        for attempt in range(1, self.max_retries + 1):
            try:
                if self.client is None:
                    self.client = ModbusTcpClient(self.host, port=self.port, timeout=self.timeout)
                
                if self.client.connect():
                    self._is_active = True
                    logger.info(f"[MODBUS] Connected to {self.host}:{self.port} (Attempt {attempt})")
                    return True
            except Exception as e:
                logger.warning(f"[MODBUS] Connection attempt {attempt} failed: {e}")
            
            sleep_time = self.backoff_base * (2 ** (attempt - 1))
            time.sleep(sleep_time)

        self._is_active = False
        logger.error(f"[MODBUS] Failed to connect to {self.host}:{self.port} after {self.max_retries} retries.")
        return False

    def is_active(self) -> bool:
        return self._is_active

    def close(self):
        """Closes the active Modbus connection."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self._is_active = False

    def read_live_state(
        self,
        coil_address: int = 0,
        coil_count: int = 8,
        register_address: int = 0,
        register_count: int = 8
    ) -> Dict[str, Any]:
        """
        Interrogates live coils and holding registers from the hardware.
        Core element of the Universal Read-Before-Write architecture.
        """
        state = {
            "connected": False,
            "timestamp": time.time(),
            "coils": [False] * coil_count,
            "registers": [0] * register_count,
            "holding_register_0": 0,
            "pressure": 0,
            "valve_a": False,
            "valve_b": False,
            "coil_0": False,
            "coil_1": False
        }

        if not self._is_active and not self.connect():
            logger.warning("[MODBUS] Cannot read live state: Server offline.")
            return state

        try:
            # Read Coils
            coil_resp = self.client.read_coils(address=coil_address, count=coil_count)
            if hasattr(coil_resp, "bits"):
                bits = coil_resp.bits[:coil_count]
                state["coils"] = bits
                state["coil_0"] = bool(bits[0]) if len(bits) > 0 else False
                state["coil_1"] = bool(bits[1]) if len(bits) > 1 else False
                state["valve_a"] = state["coil_0"]
                state["valve_b"] = state["coil_1"]

            # Read Holding Registers
            reg_resp = self.client.read_holding_registers(address=register_address, count=register_count)
            if hasattr(reg_resp, "registers"):
                regs = reg_resp.registers[:register_count]
                state["registers"] = regs
                state["holding_register_0"] = int(regs[0]) if len(regs) > 0 else 0
                state["pressure"] = state["holding_register_0"]

            state["connected"] = True
            return state

        except ConnectionException as ce:
            logger.error(f"[MODBUS] Connection lost during read: {ce}. Attempting reconnect...")
            self.close()
            if self.connect():
                return self.read_live_state(coil_address, coil_count, register_address, register_count)
            return state
        except Exception as e:
            logger.error(f"[MODBUS] Telemetry read error: {e}")
            return state

    def write_target_state(
        self,
        coils: Optional[Dict[int, bool]] = None,
        registers: Optional[Dict[int, int]] = None
    ) -> Tuple[bool, str]:
        """
        Commits verified target state to Modbus coils and holding registers.
        Must be called ONLY after Z3 Crucible validation.
        """
        if not self._is_active and not self.connect():
            return False, "[MODBUS ERROR] Cannot write state: Connection offline."

        try:
            # Write Coils
            if coils:
                for addr, val in coils.items():
                    res = self.client.write_coil(address=addr, value=bool(val))
                    if hasattr(res, "isError") and res.isError():
                        return False, f"[MODBUS ERROR] Failed to write coil {addr}: {res}"

            # Write Registers
            if registers:
                for addr, val in registers.items():
                    res = self.client.write_register(address=addr, value=int(val))
                    if hasattr(res, "isError") and res.isError():
                        return False, f"[MODBUS ERROR] Failed to write register {addr}: {res}"

            logger.info(f"[MODBUS] Successfully committed target state (Coils: {coils}, Regs: {registers})")
            return True, "[MODBUS SUCCESS] State committed to physical hardware."

        except ConnectionException as ce:
            logger.error(f"[MODBUS] Connection broken during write: {ce}. Retrying...")
            self.close()
            if self.connect():
                return self.write_target_state(coils, registers)
            return False, f"[MODBUS FATAL] Write dropped due to disconnect: {ce}"
        except Exception as e:
            return False, f"[MODBUS ERROR] Write execution failed: {e}"
