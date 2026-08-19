"""DIANA OS - Built-In Virtual SCADA Plant Simulator.

Spawns a local Modbus TCP server simulating a pressurized industrial vessel with
dynamic physical feedback (inlet/outlet valves, pressure buildup, vent dissipation).
Allows out-of-the-box evaluation of D.I.A.N.A.'s Read-Before-Write loop and Z3 Crucible.
"""

import sys
import os
import time
import threading
import argparse
import logging

try:
    from pymodbus.server import StartTcpServer
    from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext
except ImportError:
    StartTcpServer = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SimulatedSCADAPlant")

class VirtualPlantEngine:
    """Simulates physical vessel dynamics on top of Modbus datastore."""

    def __init__(self, port: int = 5020):
        self.port = port
        self.running = False
        
        # Initial State: Pressure = 35, Valve A = False, Valve B = False
        self.block = ModbusSequentialDataBlock(0, [35] + [0] * 31)
        self.coil_block = ModbusSequentialDataBlock(0, [0, 0] + [0] * 30)
        
        self.store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 32),
            co=self.coil_block,
            hr=self.block,
            ir=ModbusSequentialDataBlock(0, [0] * 32)
        )
        self.context = ModbusServerContext(slaves=self.store, single=True)

    def _physics_loop(self):
        """Simulates physical vessel reaction to valve states."""
        while self.running:
            try:
                coils = self.store.getValues(1, 0, count=2) # 1 = Coils
                valve_a = bool(coils[0]) # Inlet
                valve_b = bool(coils[1]) # Outlet

                current_pressure = self.store.getValues(3, 0, count=1)[0] # 3 = Holding Regs

                # Physical Dynamics:
                if valve_a and not valve_b:
                    # Inflow charging
                    new_pressure = min(current_pressure + 2, 100)
                elif valve_b and not valve_a:
                    # Outflow venting
                    new_pressure = max(current_pressure - 3, 0)
                else:
                    new_pressure = current_pressure

                self.store.setValues(3, 0, [new_pressure])
                
                state_str = f"Pressure: {new_pressure:02d} | Valve A (Inlet): {'OPEN' if valve_a else 'CLOSED'} | Valve B (Outlet): {'OPEN' if valve_b else 'CLOSED'}"
                if new_pressure >= 90:
                    state_str += " ⚠️ [BURST HAZARD]"
                print(f"\r[PLANT TELEMETRY] {state_str}   ", end="", flush=True)

            except Exception as e:
                logger.error(f"Physics error: {e}")
            time.sleep(1.0)

    def start(self):
        if StartTcpServer is None:
            print("ERROR: pymodbus is required. Install via `pip install pymodbus`.")
            sys.exit(1)

        print("=" * 65)
        print(f" D.I.A.N.A. OS // VIRTUAL SCADA PLANT SIMULATOR")
        print(f" Listening on Modbus TCP: 127.0.0.1:{self.port}")
        print(f" Initial State -> Pressure: 35 | Valve A: CLOSED | Valve B: CLOSED")
        print(" Press Ctrl+C to terminate.")
        print("=" * 65)

        self.running = True
        physics_thread = threading.Thread(target=self._physics_loop, daemon=True)
        physics_thread.start()

        try:
            StartTcpServer(context=self.context, address=("127.0.0.1", self.port))
        except KeyboardInterrupt:
            print("\nShutting down virtual plant simulator.")
        finally:
            self.running = False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DIANA OS Built-In Virtual SCADA Plant Simulator")
    parser.add_argument("--port", type=int, default=5020, help="Modbus TCP port (default: 5020)")
    args = parser.parse_args()

    plant = VirtualPlantEngine(port=args.port)
    plant.start()
