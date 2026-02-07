$(function () {
  function GuardianEyeViewModel(parameters) {
    var self = this;
    self.loginState = parameters[0];
    self.settings = parameters[1];
    self.printerState = parameters[2];

    // === State observables ===
    self.monitorActive = ko.observable(false);
    self.cycleCount = ko.observable(0);
    self.consecutiveFailures = ko.observable(0);
    self.failureDetected = ko.observable(false);
    self.failureReason = ko.observable("");
    self.layer = ko.observable(null);
    self.totalLayers = ko.observable(null);
    self.progress = ko.observable(0);
    self.lastSnapshotPath = ko.observable(null);
    self.errors = ko.observableArray([]);

    // Last verdict
    self.lastVerdictFailed = ko.observable(false);
    self.lastVerdictReason = ko.observable("");
    self.lastVerdictProvider = ko.observable("");
    self.lastVerdictModel = ko.observable("");
    self.lastVerdictLatency = ko.observable(0);
    self.lastVerdictCost = ko.observable(0);

    // Cost
    self.sessionCost = ko.observable(0);
    self.sessionCalls = ko.observable(0);

    // History
    self.historyEntries = ko.observableArray([]);
    self.statistics = ko.observable({});

    // Test connection
    self.testResult = ko.observable("");
    self.testSuccess = ko.observable(null);
    self.testRunning = ko.observable(false);

    // === Computed ===
    self.statusText = ko.computed(function () {
      if (self.failureDetected()) return "FAILURE DETECTED";
      if (self.monitorActive()) return "Monitoring";
      return "Idle";
    });

    self.statusClass = ko.computed(function () {
      if (self.failureDetected()) return "guardianeye-status-failure";
      if (self.monitorActive()) return "guardianeye-status-active";
      return "guardianeye-status-idle";
    });

    self.navbarIconClass = ko.computed(function () {
      if (self.failureDetected()) return "guardianeye-navbar-failure";
      if (self.monitorActive()) return "guardianeye-navbar-active";
      return "guardianeye-navbar-idle";
    });

    self.failStrikes = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s ? s.fail_strikes() : 3;
    });

    self.strikeDisplay = ko.computed(function () {
      var current = self.consecutiveFailures();
      var max = self.failStrikes();
      var dots = [];
      for (var i = 0; i < max; i++) {
        dots.push(i < current ? "strike-active" : "strike-inactive");
      }
      return dots;
    });

    self.snapshotUrl = ko.computed(function () {
      var path = self.lastSnapshotPath();
      if (!path) return null;
      return BASEURL + "plugin/guardianeye/snapshot/" + path;
    });

    self.printScore = ko.computed(function () {
      var stats = self.statistics();
      if (!stats || !stats.total) return "--";
      var ok = stats.ok || 0;
      return Math.round((ok / stats.total) * 100) + "%";
    });

    self.formattedSessionCost = ko.computed(function () {
      return "$" + self.sessionCost().toFixed(4);
    });

    // Provider visibility for settings
    self.isProviderOpenAI = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "openai";
    });
    self.isProviderAzure = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "azure_openai";
    });
    self.isProviderAnthropic = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "anthropic";
    });
    self.isProviderXAI = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "xai";
    });
    self.isProviderGemini = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "gemini";
    });
    self.isProviderOllama = ko.computed(function () {
      var s = self.settings.settings
        ? self.settings.settings.plugins.guardianeye
        : null;
      return s && s.provider() === "ollama";
    });
    self.showApiKey = ko.computed(function () {
      return !self.isProviderOllama();
    });

    // === Plugin message handler (real-time updates) ===
    self.onDataUpdaterPluginMessage = function (plugin, data) {
      if (plugin !== "guardianeye") return;

      if (data.type === "state_update" && data.state) {
        var s = data.state;
        self.monitorActive(s.active || false);
        self.cycleCount(s.cycle_count || 0);
        self.consecutiveFailures(s.consecutive_failures || 0);
        self.failureDetected(s.failure_detected || false);
        self.failureReason(s.failure_reason || "");
        self.layer(s.layer);
        self.totalLayers(s.total_layers);
        self.progress(s.progress || 0);
        self.lastSnapshotPath(s.last_snapshot_path || null);
        self.errors(s.errors || []);

        if (s.last_verdict) {
          var v = s.last_verdict;
          self.lastVerdictFailed(v.failed || false);
          self.lastVerdictReason(v.reason || "");
          self.lastVerdictProvider(v.provider || "");
          self.lastVerdictModel(v.model || "");
          self.lastVerdictLatency(v.latency_ms || 0);
          self.lastVerdictCost(v.cost || 0);
        }
      }
    };

    // === API calls ===
    self.testConnection = function () {
      self.testRunning(true);
      self.testResult("");
      self.testSuccess(null);
      OctoPrint.simpleApiCommand("guardianeye", "test_provider")
        .done(function (data) {
          self.testResult(data.message || "Unknown result");
          self.testSuccess(data.success || false);
        })
        .fail(function () {
          self.testResult("Request failed");
          self.testSuccess(false);
        })
        .always(function () {
          self.testRunning(false);
        });
    };

    self.manualCheck = function () {
      OctoPrint.simpleApiCommand("guardianeye", "manual_check");
    };

    self.startMonitoring = function () {
      OctoPrint.simpleApiCommand("guardianeye", "start_monitoring");
    };

    self.stopMonitoring = function () {
      OctoPrint.simpleApiCommand("guardianeye", "stop_monitoring");
    };

    self.clearHistory = function () {
      if (confirm("Clear all verdict history?")) {
        OctoPrint.simpleApiCommand("guardianeye", "clear_history").done(
          function () {
            self.historyEntries([]);
            self.statistics({});
          },
        );
      }
    };

    self.markFalsePositive = function (entry) {
      OctoPrint.simpleApiCommand("guardianeye", "mark_false_positive", {
        entry_id: entry.id,
      }).done(function () {
        entry.false_positive = true;
        self.loadHistory();
      });
    };

    self.loadHistory = function () {
      OctoPrint.simpleApiGet("guardianeye").done(function (data) {
        self.historyEntries(data.history || []);
        self.statistics(data.statistics || {});
        if (data.cost) {
          self.sessionCost(data.cost.session_cost || 0);
          self.sessionCalls(data.cost.session_calls || 0);
        }
      });
    };

    // === Initialization ===
    self.onBeforeBinding = function () {
      // Initial state load
      self.loadHistory();
    };

    self.onTabChange = function (current, previous) {
      if (current === "#tab_plugin_guardianeye") {
        self.loadHistory();
      }
    };
  }

  OCTOPRINT_VIEWMODELS.push({
    construct: GuardianEyeViewModel,
    dependencies: [
      "loginStateViewModel",
      "settingsViewModel",
      "printerStateViewModel",
    ],
    elements: [
      "#sidebar_plugin_guardianeye",
      "#settings_plugin_guardianeye",
      "#tab_plugin_guardianeye",
      "#navbar_plugin_guardianeye",
    ],
  });
});
