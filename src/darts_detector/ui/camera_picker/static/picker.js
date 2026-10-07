// SPDX-License-Identifier: GPL-3.0-or-later
// Darts Detector — Camera Picker — vanilla JS, no frameworks (D-018)

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Phase 1: camera preview selects
  // -------------------------------------------------------------------------

  const selects = document.querySelectorAll(".cam-select[data-preview-target]");

  selects.forEach(function (select) {
    const imgId = select.dataset.previewTarget;
    const img = document.getElementById(imgId);
    if (!img) return;

    select.addEventListener("change", function () {
      const newIndex = select.value;
      img.classList.add("loading");
      img.src = "/preview/" + newIndex;
    });

    img.addEventListener("load", function () {
      img.classList.remove("loading");
    });

    img.addEventListener("error", function () {
      img.classList.remove("loading");
    });
  });

  // Guard: disable probe button if no cameras are found.
  const probeBtn = document.getElementById("probe-btn");
  const anySelect = document.querySelector(".cam-select");
  if (probeBtn && anySelect && anySelect.options.length === 0) {
    probeBtn.disabled = true;
  }

  // -------------------------------------------------------------------------
  // Phase 2: mode probing state
  // -------------------------------------------------------------------------

  // Populated when probe completes. List of {width, height, fps, label}.
  var _allModes = [];

  // Current selection.
  var _selectedWidth = 1280;
  var _selectedHeight = 720;
  var _selectedFps = 30;

  // Camera slot indices (set when startProbe() is called).
  var _cam1Idx = -1;
  var _cam2Idx = -1;
  var _cam3Idx = -1;

  var _pollIntervalId = null;

  // -------------------------------------------------------------------------
  // startProbe() — called when user clicks "Select Mode"
  // -------------------------------------------------------------------------

  // -------------------------------------------------------------------------
  // Poll-error tracking for consecutive failure detection (item F)
  // -------------------------------------------------------------------------
  var _pollErrorCount = 0;
  var _POLL_MAX_ERRORS = 3;

  window.startProbe = function () {
    var cam1 = document.getElementById("cam_1");
    var cam2 = document.getElementById("cam_2");
    var cam3 = document.getElementById("cam_3");

    if (!cam1 || !cam2 || !cam3) return;

    _cam1Idx = parseInt(cam1.value, 10);
    _cam2Idx = parseInt(cam2.value, 10);
    _cam3Idx = parseInt(cam3.value, 10);

    // CRITICAL: Stop the preview MJPEG streams before probing or DSHOW will
    // deadlock.  Clearing src aborts the HTTP connection on the client side so
    // the server-side async generators receive GeneratorExit and call
    // cap.release().  We also remove the src attribute so the browser does not
    // try to reload the stream automatically.
    document.querySelectorAll(".cam-select[data-preview-target]").forEach(function (sel) {
      var imgId = sel.dataset.previewTarget;
      var img = document.getElementById(imgId);
      if (img) {
        img.src = "";
        img.removeAttribute("src");
      }
    });

    // Show camera summary in step 2.
    var summary = document.getElementById("selected-cameras-summary");
    if (summary) {
      summary.innerHTML =
        "<p class=\"selected-cam-item\">Camera 1: <strong>" + cam1.options[cam1.selectedIndex].text + "</strong></p>" +
        "<p class=\"selected-cam-item\">Camera 2: <strong>" + cam2.options[cam2.selectedIndex].text + "</strong></p>" +
        "<p class=\"selected-cam-item\">Camera 3: <strong>" + cam3.options[cam3.selectedIndex].text + "</strong></p>";
    }

    // Transition to step 2.
    var stepAssign = document.getElementById("step-assign");
    var stepMode = document.getElementById("step-mode");
    if (stepAssign) stepAssign.style.display = "none";
    if (stepMode) stepMode.style.display = "";

    // Reset progress UI.
    _setProgress(0, 60); // 20 probes × 3 cameras
    _pollErrorCount = 0;
    var modeDropdowns = document.getElementById("mode-dropdowns");
    var saveForm = document.getElementById("save-form");
    if (modeDropdowns) modeDropdowns.style.display = "none";
    if (saveForm) saveForm.style.display = "none";

    // Give server-side generators 700ms to receive GeneratorExit and release
    // the cv2.VideoCapture handles before we POST /start_probe.  Without this
    // delay DSHOW may still hold the device open when the probe thread tries
    // to open the same index.
    setTimeout(function () {
      var formData = new FormData();
      formData.append("cam_1", _cam1Idx);
      formData.append("cam_2", _cam2Idx);
      formData.append("cam_3", _cam3Idx);

      fetch("/start_probe", { method: "POST", body: formData })
        .then(function () {
          _pollIntervalId = setInterval(_pollProbeStatus, 500);
        })
        .catch(function (err) {
          _setStatusText("Error starting probe: " + err);
        });
    }, 700);
  };

  // -------------------------------------------------------------------------
  // Polling
  // -------------------------------------------------------------------------

  function _pollProbeStatus() {
    fetch("/probe_status")
      .then(function (r) {
        if (!r.ok) {
          // 5xx or unexpected status — treat as a poll failure.
          _pollErrorCount += 1;
          if (_pollErrorCount >= _POLL_MAX_ERRORS) {
            clearInterval(_pollIntervalId);
            _showProbeStoppedMessage();
          } else {
            _setStatusText("Probe server error (HTTP " + r.status + ") — retry " + _pollErrorCount + "/" + _POLL_MAX_ERRORS);
          }
          return null;
        }
        _pollErrorCount = 0; // reset on success
        return r.json();
      })
      .then(function (data) {
        if (!data) return; // error path already handled above
        var totalProbed = data.cameras.reduce(function (acc, c) { return acc + c.probed; }, 0);
        var totalTotal = data.cameras.reduce(function (acc, c) { return acc + c.total; }, 0);
        _setProgress(totalProbed, totalTotal);

        // Build per-camera label.
        var currentCam = data.cameras.find(function (c) { return !c.done; });
        if (currentCam) {
          _setStatusText("Reading supported modes from cameras...");
        } else {
          _setStatusText("Modes detected. Computing intersection...");
        }

        if (data.all_done) {
          clearInterval(_pollIntervalId);
          _loadIntersection();
        }
      })
      .catch(function (err) {
        _pollErrorCount += 1;
        if (_pollErrorCount >= _POLL_MAX_ERRORS) {
          clearInterval(_pollIntervalId);
          _showProbeStoppedMessage();
        } else {
          _setStatusText("Poll error: " + err + " (retry " + _pollErrorCount + "/" + _POLL_MAX_ERRORS + ")");
        }
      });
  }

  function _showProbeStoppedMessage() {
    var statusEl = document.getElementById("probe-status-text");
    if (statusEl) {
      statusEl.textContent = "Probe stopped responding. Restart the picker and try again.";
    }
    // Insert a Restart button if not already present.
    var progressSection = document.getElementById("probe-progress-section");
    if (progressSection && !document.getElementById("probe-restart-btn")) {
      var btn = document.createElement("button");
      btn.id = "probe-restart-btn";
      btn.type = "button";
      btn.className = "btn btn--secondary";
      btn.style.marginTop = "12px";
      btn.textContent = "Restart";
      btn.onclick = function () { window.location.reload(); };
      progressSection.appendChild(btn);
    }
  }

  function _loadIntersection() {
    fetch("/intersection")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.ready) {
          _setStatusText("Waiting for intersection data...");
          setTimeout(_loadIntersection, 500);
          return;
        }

        _allModes = data.modes;
        _selectedWidth = data.default_width;
        _selectedHeight = data.default_height;
        _selectedFps = data.default_fps;

        _populateResolutionDropdown();
        _updateFpsDropdown();
        _updateBandwidthAdvisory();
        _updateFpsAdvisory();

        var progressSection = document.getElementById("probe-progress-section");
        if (progressSection) progressSection.style.display = "none";

        var modeDropdowns = document.getElementById("mode-dropdowns");
        if (modeDropdowns) modeDropdowns.style.display = "";

        var saveForm = document.getElementById("save-form");
        if (saveForm) {
          saveForm.style.display = "";
          _updateHiddenFields();
          var saveBtn = document.getElementById("save-btn");
          if (saveBtn) saveBtn.disabled = false;
        }
      })
      .catch(function (err) {
        _setStatusText("Error loading modes: " + err);
      });
  }

  // -------------------------------------------------------------------------
  // Resolution dropdown
  // -------------------------------------------------------------------------

  function _populateResolutionDropdown() {
    var sel = document.getElementById("resolution-select");
    if (!sel) return;

    // Unique resolutions, sorted (best first — _allModes is already sorted by width desc).
    var seen = {};
    var resOptions = [];
    _allModes.forEach(function (m) {
      var key = m.width + "x" + m.height;
      if (!seen[key]) {
        seen[key] = true;
        resOptions.push({ width: m.width, height: m.height, key: key });
      }
    });

    sel.innerHTML = "";
    resOptions.forEach(function (r) {
      var opt = document.createElement("option");
      opt.value = r.key;
      opt.textContent = r.width + "×" + r.height;
      if (r.width === _selectedWidth && r.height === _selectedHeight) {
        opt.selected = true;
      }
      sel.appendChild(opt);
    });
  }

  window.onResolutionChange = function () {
    var sel = document.getElementById("resolution-select");
    if (!sel) return;
    var parts = sel.value.split("x");
    _selectedWidth = parseInt(parts[0], 10);
    _selectedHeight = parseInt(parts[1], 10);
    _updateFpsDropdown();
    _updateBandwidthAdvisory();
    _updateFpsAdvisory();
    _updateHiddenFields();
  };

  // -------------------------------------------------------------------------
  // FPS dropdown (filtered by selected resolution)
  // -------------------------------------------------------------------------

  function _updateFpsDropdown() {
    var sel = document.getElementById("fps-select");
    if (!sel) return;

    // FPS values available at the current resolution (all cameras must support them).
    var fpsValues = _allModes
      .filter(function (m) { return m.width === _selectedWidth && m.height === _selectedHeight; })
      .map(function (m) { return m.fps; })
      .filter(function (fps, idx, arr) { return arr.indexOf(fps) === idx; }) // unique
      .sort(function (a, b) { return b - a; }); // desc

    sel.innerHTML = "";
    fpsValues.forEach(function (fps) {
      var opt = document.createElement("option");
      opt.value = fps;
      opt.textContent = fps + " fps";
      if (fps === _selectedFps) opt.selected = true;
      sel.appendChild(opt);
    });

    // If the previously selected FPS is not available at the new resolution, pick the best.
    if (fpsValues.length > 0 && fpsValues.indexOf(_selectedFps) === -1) {
      _selectedFps = fpsValues[0];
    }
    if (sel.value) {
      _selectedFps = parseInt(sel.value, 10);
    }
  }

  window.onFpsChange = function () {
    var sel = document.getElementById("fps-select");
    if (!sel) return;
    _selectedFps = parseInt(sel.value, 10);
    _updateBandwidthAdvisory();
    _updateFpsAdvisory();
    _updateHiddenFields();
  };

  // -------------------------------------------------------------------------
  // FPS accuracy advisory (D-019 canonical menu: 60, 30, 25, 20, 15)
  // Sub-25 fps is permitted but shows a plain-language accuracy warning.
  // -------------------------------------------------------------------------

  function _updateFpsAdvisory() {
    var el = document.getElementById("fps-advisory");
    if (!el) return;
    if (_selectedFps < 25) {
      el.style.display = "";
      el.textContent = "Below 25 fps. Detection accuracy may be reduced — a thrown dart"
        + " only spans 2–4 frames in flight. Use 30 fps or higher if your hardware"
        + " supports it.";
    } else {
      el.style.display = "none";
      el.textContent = "";
    }
  }

  // -------------------------------------------------------------------------
  // Bandwidth advisory
  // -------------------------------------------------------------------------

  function _updateBandwidthAdvisory() {
    var el = document.getElementById("bandwidth-advisory");
    if (!el) return;

    fetch("/bandwidth_advisory?width=" + _selectedWidth + "&height=" + _selectedHeight + "&fps=" + _selectedFps + "&num_cameras=3")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.severity === "ok" || !data.message) {
          el.style.display = "none";
          el.textContent = "";
        } else {
          el.style.display = "";
          el.textContent = data.message;
          el.className = "bandwidth-advisory bandwidth-advisory--" + data.severity;
        }
      })
      .catch(function () {
        el.style.display = "none";
      });
  }

  // -------------------------------------------------------------------------
  // Hidden fields sync
  // -------------------------------------------------------------------------

  function _updateHiddenFields() {
    var f = function (id, val) {
      var el = document.getElementById(id);
      if (el) el.value = val;
    };
    f("hidden-cam-1", _cam1Idx);
    f("hidden-cam-2", _cam2Idx);
    f("hidden-cam-3", _cam3Idx);
    f("hidden-width", _selectedWidth);
    f("hidden-height", _selectedHeight);
    f("hidden-fps", _selectedFps);
  }

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function _setProgress(probed, total) {
    var pct = total > 0 ? Math.round((probed / total) * 100) : 0;
    var fill = document.getElementById("progress-bar-fill");
    if (fill) fill.style.width = pct + "%";
  }

  function _setStatusText(msg) {
    var el = document.getElementById("probe-status-text");
    if (el) el.textContent = msg;
  }

  // Show a brief spinner on the save button when the form is submitted.
  var form = document.getElementById("save-form");
  var saveBtn = document.getElementById("save-btn");
  if (form && saveBtn) {
    form.addEventListener("submit", function () {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
    });
  }

})();
