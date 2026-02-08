"""
GuardianEye — AI-powered print failure detection for OctoPrint.

Supports 6 AI vision providers (OpenAI, Azure, Anthropic, Grok, Gemini, Ollama).
Captures webcam snapshots, runs AI analysis, and implements a configurable
strike system to detect spaghetti, detachment, and other failures.

License: AGPLv3
"""

import os
import logging
import flask

import octoprint.plugin

from .vision_providers import create_vision_provider
from .monitor import PrintMonitor
from .history import VerdictHistory, SessionHistory
from .cost_tracker import CostTracker
from .notifications import send_failure_notifications

_logger = logging.getLogger("octoprint.plugins.guardianeye")


class GuardianEyePlugin(
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.BlueprintPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.ProgressPlugin,
):
    # ── Lifecycle ──────────────────────────────────────────────

    def on_after_startup(self):
        data_folder = self.get_plugin_data_folder()
        os.makedirs(data_folder, exist_ok=True)
        os.makedirs(os.path.join(data_folder, "snapshots"), exist_ok=True)

        self._verdict_history = VerdictHistory(data_folder)
        self._session_history = SessionHistory(data_folder)
        self._cost_tracker = CostTracker()
        self._monitor = PrintMonitor(self)
        self._vision_provider = None

        _logger.info("GuardianEye started. Data folder: %s", data_folder)

    def on_shutdown(self):
        if hasattr(self, "_monitor") and self._monitor.state.active:
            self._monitor.stop()
            if hasattr(self, "_session_history"):
                self._session_history.end_session(
                    emergency_stop=self._monitor.state.emergency_stop_sent
                )

    # ── Settings ───────────────────────────────────────────────

    def get_settings_defaults(self):
        return {
            "enabled": True,
            "auto_start": True,
            # Provider — unified endpoint/api_key/model for all providers
            "provider": "openai",
            "endpoint": "",
            "api_key": "",
            "model": "gpt-4o-mini",
            # Azure-specific extras
            "azure_deployment": "gpt-4o-mini",
            "azure_api_version": "2025-01-01-preview",
            # Monitoring
            "interval_seconds": 60,
            "min_layer_for_vision": 2,
            "fail_strikes": 3,
            "layer_height": 0.2,
            # Snapshot
            "snapshot_url": "",
            "snapshot_retention": 20,
            "delete_after_analysis": True,
            # Prompt
            "custom_prompt": "",
            # Notifications
            "notifications": {
                "octoprint_popup": True,
                "webhook_enabled": False,
                "webhook_url": "",
                "discord_enabled": False,
                "discord_webhook_url": "",
                "telegram_enabled": False,
                "telegram_bot_token": "",
                "telegram_chat_id": "",
            },
            # Advanced
            "cost_tracking": True,
        }

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        # Invalidate cached provider so it's re-created with new settings
        self._vision_provider = None

    # ── Templates ──────────────────────────────────────────────

    def get_template_configs(self):
        return [
            {"type": "sidebar", "name": "GuardianEye", "template": "guardianeye_sidebar.jinja2",
             "icon": "eye", "custom_bindings": True, "data_bind": "visible: loginState.hasPermission(access.permissions.STATUS)"},
            {"type": "settings", "name": "GuardianEye", "template": "guardianeye_settings.jinja2",
             "custom_bindings": True},
            {"type": "tab", "name": "GuardianEye", "template": "guardianeye_tab.jinja2",
             "custom_bindings": True},
            {"type": "navbar", "name": "GuardianEye", "template": "guardianeye_navbar.jinja2",
             "custom_bindings": True, "classes": ["dropdown"]},
        ]

    # ── Assets ─────────────────────────────────────────────────

    def get_assets(self):
        return {
            "js": ["js/guardianeye.js"],
            "css": ["css/guardianeye.css"],
        }

    # ── API Commands ───────────────────────────────────────────

    def get_api_commands(self):
        return {
            "test_provider": [],
            "manual_check": [],
            "start_monitoring": [],
            "stop_monitoring": [],
            "clear_history": [],
            "mark_false_positive": ["entry_id"],
            "get_statistics": [],
        }

    def on_api_command(self, command, data):
        if command == "test_provider":
            return self._api_test_provider()
        elif command == "manual_check":
            return self._api_manual_check()
        elif command == "start_monitoring":
            return self._api_start_monitoring()
        elif command == "stop_monitoring":
            return self._api_stop_monitoring()
        elif command == "clear_history":
            return self._api_clear_history()
        elif command == "mark_false_positive":
            return self._api_mark_false_positive(data)
        elif command == "get_statistics":
            return self._api_get_statistics()

    def on_api_get(self, request):
        """Handle GET requests — return current state + recent history."""
        return flask.jsonify({
            "state": self._monitor.get_state() if hasattr(self, "_monitor") else {},
            "history": self._verdict_history.get_entries(50) if hasattr(self, "_verdict_history") else [],
            "statistics": self._verdict_history.get_statistics() if hasattr(self, "_verdict_history") else {},
            "cost": self._cost_tracker.to_dict() if hasattr(self, "_cost_tracker") else {},
        })

    def _api_test_provider(self):
        try:
            provider = self.get_vision_provider(force_new=True)
            success, message = provider.test_connection()
            return flask.jsonify({"success": success, "message": message})
        except Exception as e:
            return flask.jsonify({"success": False, "message": str(e)})

    def _api_manual_check(self):
        if not hasattr(self, "_monitor"):
            return flask.jsonify({"error": "Plugin not initialized"})
        if not self._monitor.state.active:
            # Start temporarily for one cycle
            self._monitor.state.active = True
            self._monitor._run_cycle()
            self._monitor.state.active = False
        else:
            self._monitor._run_cycle()
        return flask.jsonify({"state": self._monitor.get_state()})

    def _api_start_monitoring(self):
        if hasattr(self, "_monitor"):
            self._session_history.start_session()
            self._cost_tracker.reset_session()
            self._monitor.start()
        return flask.jsonify({"state": self._monitor.get_state()})

    def _api_stop_monitoring(self):
        if hasattr(self, "_monitor"):
            state = self._monitor.stop()
            self._session_history.end_session()
            return flask.jsonify({"state": state})
        return flask.jsonify({"state": {}})

    def _api_clear_history(self):
        if hasattr(self, "_verdict_history"):
            self._verdict_history.clear()
        return flask.jsonify({"success": True})

    def _api_mark_false_positive(self, data):
        entry_id = data.get("entry_id", "")
        if hasattr(self, "_verdict_history"):
            found = self._verdict_history.mark_false_positive(entry_id)
            return flask.jsonify({"success": found})
        return flask.jsonify({"success": False})

    def _api_get_statistics(self):
        stats = self._verdict_history.get_statistics() if hasattr(self, "_verdict_history") else {}
        cost = self._cost_tracker.to_dict() if hasattr(self, "_cost_tracker") else {}
        return flask.jsonify({"statistics": stats, "cost": cost})

    # ── Blueprint (serve snapshots) ────────────────────────────

    @octoprint.plugin.BlueprintPlugin.route("/snapshot/<filename>", methods=["GET"])
    def serve_snapshot(self, filename):
        snapshot_dir = os.path.join(self.get_plugin_data_folder(), "snapshots")
        return flask.send_from_directory(snapshot_dir, filename)

    def is_blueprint_csrf_protected(self):
        return True

    # ── Events ─────────────────────────────────────────────────

    def on_event(self, event, payload):
        if not self._settings.get_boolean(["enabled"]):
            return

        if event == "PrintStarted":
            if self._settings.get_boolean(["auto_start"]):
                filename = payload.get("name", "unknown")
                _logger.info("Print started: %s — auto-starting monitor", filename)
                self._session_history.start_session(filename)
                self._cost_tracker.reset_session()
                self._monitor.start()

        elif event in ("PrintDone", "PrintCancelled", "PrintFailed"):
            if hasattr(self, "_monitor") and self._monitor.state.active:
                emergency = event == "PrintFailed" or self._monitor.state.emergency_stop_sent
                self._monitor.stop()
                session = self._session_history.end_session(emergency_stop=emergency)
                if session:
                    _logger.info(
                        "Print session ended: score=%s, cycles=%d, cost=$%.4f",
                        session.get("print_score"), session.get("cycles", 0), session.get("total_cost", 0),
                    )

        elif event == "ZChange":
            if hasattr(self, "_monitor") and self._monitor.state.active:
                z = payload.get("new", 0)
                layer_height = self._settings.get_float(["layer_height"]) or 0.2
                estimated_layer = max(1, int(z / layer_height))
                self._monitor.set_layer(estimated_layer)

    # ── Progress ───────────────────────────────────────────────

    def on_print_progress(self, storage, path, progress):
        if hasattr(self, "_monitor") and self._monitor.state.active:
            self._monitor.set_progress(progress)

    # ── Helper Methods ─────────────────────────────────────────

    def get_vision_provider(self, force_new=False):
        """Get or create the vision provider instance."""
        if self._vision_provider is None or force_new:
            settings_data = {
                "provider": self._settings.get(["provider"]),
                "endpoint": self._settings.get(["endpoint"]),
                "api_key": self._settings.get(["api_key"]),
                "model": self._settings.get(["model"]),
                "azure_deployment": self._settings.get(["azure_deployment"]),
                "azure_api_version": self._settings.get(["azure_api_version"]),
            }
            self._vision_provider = create_vision_provider(settings_data)
        return self._vision_provider

    def record_verdict(self, verdict, cycle, layer, progress):
        """Record a verdict in history and cost tracker."""
        verdict_dict = verdict.to_dict()
        if hasattr(self, "_monitor") and self._monitor.state.last_snapshot_path:
            verdict_dict["snapshot"] = os.path.basename(self._monitor.state.last_snapshot_path)

        self._verdict_history.add(verdict_dict, cycle, layer, progress)
        self._cost_tracker.record(verdict.cost)
        self._session_history.record_verdict(verdict.failed, verdict.cost)

    def send_failure_notifications(self, reason):
        """Send notifications on failure detection."""
        settings_data = self._settings.get_all_data()
        snapshot_path = None
        if hasattr(self, "_monitor") and self._monitor.state.last_snapshot_path:
            snapshot_path = self._monitor.state.last_snapshot_path
        send_failure_notifications(settings_data, reason, snapshot_path)

    # ── Software Update ────────────────────────────────────────

    def get_update_information(self):
        return {
            "guardianeye": {
                "displayName": "GuardianEye",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "schwarztim",
                "repo": "OctoPrint-GuardianEye",
                "current": self._plugin_version,
                "pip": "https://github.com/schwarztim/OctoPrint-GuardianEye/archive/{target_version}.zip",
            }
        }


__plugin_name__ = "GuardianEye"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = GuardianEyePlugin()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
}
