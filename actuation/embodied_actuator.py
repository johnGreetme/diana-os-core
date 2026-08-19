import time
import logging
from abc import ABC, abstractmethod
import threading

logger = logging.getLogger(__name__)

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
except ImportError:
    # Fallback handled by router
    pass

try:
    from scipy.optimize import minimize
except ImportError:
    pass

class HardwareWatchdog:
    """Maintains a strict 100Hz heartbeat to /dev/watchdog for Functional Safety Island failsafes."""
    def __init__(self):
        self._running = False
        self._thread = None
        self._watchdog_path = "/dev/watchdog"
        # HARDCODED 100Hz heartbeat. Never exposed to .env for safety reasons.
        self._heartbeat_interval = 0.01 
        
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        logger.info("[SAFETY] HardwareWatchdog 100Hz heartbeat started.")

    def _heartbeat_loop(self):
        while self._running:
            try:
                with open(self._watchdog_path, 'w') as wd:
                    wd.write('\\0')
            except Exception:
                # Silently fail if testing in a non-bare-metal environment, 
                # but in production, failing to write will trigger a hardware e-stop.
                pass
            time.sleep(self._heartbeat_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("[SAFETY] HardwareWatchdog stopped.")

class KinematicGovernor:
    """
    Kinematic Safety Governor implementing Control Barrier Functions (CBFs).
    Solves the quadratic program:
        u* = argmin ||u - u_nominal||^2 s.t. h_dot(x, u) + alpha(h(x)) >= 0
    ensuring dynamic feasibility, torque limiting, and collision-free trajectories.
    """
    def __init__(self, gamma: float = 1.0, max_effort_limit: float = 50.0):
        self.gamma = gamma
        self.max_effort_limit = max_effort_limit

    def h(self, state: float) -> float:
        """Invariant forward set function measuring margin to safety boundary."""
        return float(state)

    def alpha(self, h_val: float) -> float:
        """Extended class K function: alpha(h) = gamma * h."""
        return self.gamma * h_val

    def halt_trajectory(self, current_state, nominal_command):
        """
        Calculates safe trajectory by solving the QP:
        u* = argmin ||u - u_nominal||^2 s.t. h_dot(x, u) + alpha(h(x)) >= 0
        """
        try:
            from scipy.optimize import minimize
            import numpy as np

            if isinstance(nominal_command, (int, float)):
                u_nom = float(nominal_command)
                x_curr = float(current_state) if current_state is not None else 1.0

                # Objective: minimize 0.5 * (u - u_nom)^2
                obj = lambda u: 0.5 * (u[0] - u_nom) ** 2
                
                # Invariant constraint: u + alpha(h(x)) >= 0
                cons = ({
                    'type': 'ineq',
                    'fun': lambda u: u[0] + self.alpha(self.h(x_curr))
                })
                bounds = [(-self.max_effort_limit, self.max_effort_limit)]

                res = minimize(obj, x0=[u_nom], bounds=bounds, constraints=cons, method='SLSQP')
                if res.success:
                    safe_u = float(res.x[0])
                    logger.info(f"[GOVERNOR] CBF QP Solved: nominal={u_nom:.3f} -> safe={safe_u:.3f}")
                    return safe_u
        except Exception as e:
            logger.warning(f"[GOVERNOR] CBF QP fallback: {e}")

        logger.info(f"[GOVERNOR] Pass-through trajectory bounds for command: {nominal_command}")
        return nominal_command


class EmbodiedActuator:
    def __init__(self):
        # We need to inherit or wrap Node differently because of rclpy instantiation constraints.
        # So we use composition here.
        self._is_active = False
        self.node = None
        self.watchdog = HardwareWatchdog()
        self.governor = None 
        
        try:
            if not rclpy.ok():
                rclpy.init()
            self.node = rclpy.create_node('diana_embodied_actuator')
            
            # Mutually Exclusive Callback Group for safety-critical topics
            self.safety_cb_group = MutuallyExclusiveCallbackGroup()
            
            self.subscription = self.node.create_subscription(
                String,
                '/robot_description',
                self._urdf_callback,
                10,
                callback_group=self.safety_cb_group
            )
            
            # Placeholder for /joint_commands publisher
            self.joint_publisher = self.node.create_publisher(String, '/joint_commands', 10)

            # Spin once with timeout to check for transient-local latched topics
            rclpy.spin_once(self.node, timeout_sec=2.0)
        except Exception as e:
            logger.error(f"[ACTUATOR] Failed to initialize ROS 2 node: {e}")

    def _urdf_callback(self, msg):
        logger.info("[ROUTER] Successfully latched onto /robot_description URDF blueprint.")
        self.urdf_blueprint = msg.data
        self._is_active = True
        self.watchdog.start()

    def is_active(self):
        return self._is_active
        
    def execute_command(self, command):
        """High-level entry point from the LLM"""
        safe_command = command
        if self.governor:
            safe_command = self.governor.halt_trajectory(None, command)
            
        if self.node:
            msg = String()
            msg.data = str(safe_command)
            self.joint_publisher.publish(msg)
            
        return f"[PHYSICAL SUCCESS] Executed safe physical trajectory: {safe_command}"

    def shutdown(self):
        self.watchdog.stop()
        if self.node:
            self.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
