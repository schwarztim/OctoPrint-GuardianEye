"""
Background Monitoring Engine for GuardianEye.

Runs a repeating cycle: capture snapshot → AI vision analysis → strike system.
Ported from bambu-lab-mcp/src/print-monitor.ts, adapted for OctoPrint.

Key differences from MCP version:
  - Uses octoprint.util.RepeatedTimer instead of setInterval
  - Uses plugin._printer.cancel_print() instead of mqtt.stopPrint()
  - Gets layer/progress from OctoPrint events instead of MQTT
  - Sends real-time UI updates via plugin._plugin_manager.send_plugin_message()
"""

import os
import time
import base64
import logging
import threading

_logger = logging.getLogger("octoprint.plugins.guardianeye.monitor")


class MonitorState:
    """Mutable state object for the monitoring engine."""

    def __init__(self):
        self.active = False
        self.cycle_count = 0
        self.last_verdict = None
        self.last_snapshot_path = None
        self.consecutive_failures = 0
        self.failure_detected = False
        self.failure_reason = None
        self.emergency_stop_sent = False
        self.layer = None
        self.total_layers = None
        self.progress = 0
        self.errors = []

    def to_dict(self):
        return {
            "active": self.active,
            "cycle_count": self.cycle_count,
            "last_verdict": self.last_verdict.to_dict() if self.last_verdict else None,
            "last_snapshot_path": os.path.basename(self.last_snapshot_path) if self.last_snapshot_path else None,
            "consecutive_failures": self.consecutive_failures,
            "failure_detected": self.failure_detected,
            "failure_reason": self.failure_reason,
            "emergency_stop_sent": self.emergency_stop_sent,
            "layer": self.layer,
            "total_layers": self.total_layers,
            "progress": self.progress,
            "errors": self.errors[-10:],  # Keep last 10 errors
        }

    def reset(self):
        self.__init__()


class PrintMonitor:
    """
    Background AI vision monitoring engine.

    Captures webcam snapshots on a configurable interval, runs AI vision
    analysis, and implements a strike system for failure detection.
    """

    def __init__(self, plugin):
        """
        Args:
            plugin: The GuardianEyePlugin instance (provides settings, printer, etc.)
        """
        self._plugin = plugin
        self.state = MonitorState()
        self._timer = None
        self._snapshot_count = 0
        self._lock = threading.Lock()

    def start(self):
        """Start the monitoring loop."""
        if self.state.active:
            return

        from octoprint.util import RepeatedTimer

        self.state.reset()
        self.state.active = True
        self._snapshot_count = 0

        settings = self._plugin._settings
        interval = max(10, settings.get_int(["interval_seconds"]))
        min_layer = settings.get_int(["min_layer_for_vision"])
        strikes = settings.get_int(["fail_strikes"])

        provider = self._plugin.get_vision_provider()
        _logger.info(
            "Monitor started: %ds interval, vision after layer %d, %d strikes, provider: %s/%s",
            interval, min_layer, strikes, provider.name, provider.model,
        )

        # Run first cycle immediately, then on interval
        self._run_cycle()
        self._timer = RepeatedTimer(interval, self._run_cycle, run_first=False)
        self._timer.start()
        self._send_state_update()

    def stop(self):
        """Stop the monitoring loop and return final state."""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

        self.state.active = False
        _logger.info("Monitor stopped after %d cycles", self.state.cycle_count)
        self._send_state_update()
        return self.state.to_dict()

    def get_state(self):
        return self.state.to_dict()

    def set_layer(self, layer):
        self.state.layer = layer

    def set_total_layers(self, total_layers):
        self.state.total_layers = total_layers

    def set_progress(self, progress):
        self.state.progress = progress

    def _run_cycle(self):
        """Execute one monitoring cycle (thread-safe)."""
        with self._lock:
            self._monitor_cycle()

    def _monitor_cycle(self):
        if not self.state.active:
            return

        self.state.cycle_count += 1
        cycle_num = self.state.cycle_count

        try:
            from .snapshot import capture_snapshot, cleanup_old_snapshots, get_snapshot_url
            from .prompt_builder import build_vision_prompt
            from .cost_tracker import estimate_cost

            settings = self._plugin._settings

            # 1. Get current print state
            layer = self.state.layer
            total_layers = self.state.total_layers
            progress = self.state.progress

            # 2. Capture snapshot
            snapshot_url = get_snapshot_url(
                settings.get_all_data(),
                self._plugin._settings,
            )
            snapshot_dir = self._plugin.get_plugin_data_folder()
            snapshot_dir = os.path.join(snapshot_dir, "snapshots")

            ts = time.strftime("%Y%m%d-%H%M%S")
            self._snapshot_count += 1
            snapshot_path = os.path.join(snapshot_dir, f"monitor_{ts}_{self._snapshot_count}.jpg")

            try:
                saved_path = capture_snapshot(snapshot_url, snapshot_path)
                self.state.last_snapshot_path = saved_path
            except Exception as e:
                msg = f"Cycle {cycle_num}: snapshot failed: {e}"
                self.state.errors.append(msg)
                _logger.warning(msg)
                self._send_state_update()
                return  # Skip vision if snapshot fails — don't stop the print

            _logger.info(
                "Cycle %d: %s | %s%% | Layer %s/%s",
                cycle_num, os.path.basename(saved_path), progress, layer, total_layers,
            )

            # 3. Clean up old snapshots
            retention = settings.get_int(["snapshot_retention"]) or 100
            cleanup_old_snapshots(snapshot_dir, retention)

            # 4. Check min_layer threshold
            min_layer = settings.get_int(["min_layer_for_vision"]) or 2
            if layer is not None and layer < min_layer:
                _logger.info("Cycle %d: skipping vision (layer %s < %d)", cycle_num, layer, min_layer)
                self._send_state_update()
                return

            # 5. AI Vision analysis
            try:
                with open(saved_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("ascii")

                custom_prompt = settings.get(["custom_prompt"])
                prompt = build_vision_prompt(layer, total_layers, progress, custom_prompt)

                provider = self._plugin.get_vision_provider()
                verdict = provider.analyze(image_b64, prompt)

                # Cost tracking
                if settings.get_boolean(["cost_tracking"]):
                    verdict.cost = estimate_cost(provider.name, provider.model)

                self.state.last_verdict = verdict

                # Record in history
                self._plugin.record_verdict(verdict, cycle_num, layer, progress)

                if verdict.failed:
                    self.state.consecutive_failures += 1
                    strikes = self.state.consecutive_failures
                    needed = settings.get_int(["fail_strikes"]) or 3

                    if strikes >= needed:
                        self._handle_failure(
                            f"Vision: {verdict.reason} ({strikes}/{needed} consecutive strikes)"
                        )
                        return

                    _logger.warning(
                        "Cycle %d: STRIKE %d/%d — %s (%dms)",
                        cycle_num, strikes, needed, verdict.reason, verdict.latency_ms,
                    )
                else:
                    if self.state.consecutive_failures > 0:
                        _logger.info(
                            "Cycle %d: Vision OK — strike counter reset (was %d)",
                            cycle_num, self.state.consecutive_failures,
                        )
                    self.state.consecutive_failures = 0
                    _logger.info(
                        "Cycle %d: Vision OK (%dms) — %s",
                        cycle_num, verdict.latency_ms, verdict.reason[:80],
                    )

            except Exception as e:
                # Vision API errors are non-fatal
                msg = f"Cycle {cycle_num}: vision error: {e}"
                self.state.errors.append(msg)
                _logger.warning(msg)

        except Exception as e:
            msg = f"Cycle {cycle_num}: unexpected error: {e}"
            self.state.errors.append(msg)
            _logger.error(msg)

        self._send_state_update()

    def _handle_failure(self, reason):
        """Handle confirmed failure: emergency stop + notify."""
        self.state.failure_detected = True
        self.state.failure_reason = reason
        _logger.error("FAILURE DETECTED: %s", reason)

        # Emergency stop
        try:
            self._plugin._printer.cancel_print()
            self.state.emergency_stop_sent = True
            _logger.error("Emergency stop sent — print cancelled")
        except Exception as e:
            _logger.error("Failed to cancel print: %s", e)

        # Send notifications
        try:
            self._plugin.send_failure_notifications(reason)
        except Exception as e:
            _logger.error("Failed to send notifications: %s", e)

        self.stop()

    def _send_state_update(self):
        """Push state to the frontend via OctoPrint's plugin message system."""
        try:
            self._plugin._plugin_manager.send_plugin_message(
                self._plugin._identifier,
                {"type": "state_update", "state": self.state.to_dict()},
            )
        except Exception:
            pass
