// SPDX-License-Identifier: GPL-3.0-or-later
// Phase 2.5 — Intrinsic Calibration UI — vanilla JS, no external frameworks.

'use strict';

// ---------------------------------------------------------------------------
// State (per-camera)
// ---------------------------------------------------------------------------
const CAMERA_IDS = ['cam_1', 'cam_2', 'cam_3'];

const state = {};
CAMERA_IDS.forEach(camId => {
  state[camId] = {
    frameCount: 0,
    calState: 'pending',
    autoCapturing: false,
    autoTimer: null,
    // Pose tracking for auto-capture angle diversity heuristic.
    // We can't get the actual pose from the server in this minimal UI,
    // so we track "how many consecutive frames were detected" as a proxy.
    lastAutoCapture: 0,
  };
});

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
function el(id) { return document.getElementById(id); }

function showError(camId, msg) {
  const box = el(`err-${camId}`);
  box.textContent = msg;
  box.style.display = msg ? 'block' : 'none';
}

function showReproj(camId, meanError) {
  const box = el(`reproj-${camId}`);
  if (meanError === null) { box.style.display = 'none'; return; }
  const good = meanError <= 0.5;
  box.className = `reproj-box ${good ? 'good' : 'warn'}`;
  box.style.display = 'block';
  if (good) {
    box.textContent = `Mean reprojection error: ${meanError.toFixed(4)} px — Good! Click Save.`;
  } else {
    box.textContent =
      `Mean reprojection error: ${meanError.toFixed(4)} px — Above 0.5 px. ` +
      `Capture more frames at more varied angles (tilt harder, try near/far).`;
  }
}

function updateCalButton(camId) {
  const s = state[camId];
  el(`btn-cal-${camId}`).disabled = s.frameCount < 10;
  el(`btn-save-${camId}`).disabled = s.calState !== 'calibrated' && s.calState !== 'saved';
}

function updateHint(camId) {
  const s = state[camId];
  const hint = el(`hint-${camId}`);
  if (s.frameCount === 0) {
    hint.textContent = 'Move the chessboard to a new angle, then click Capture.';
  } else if (s.frameCount < 8) {
    hint.textContent = `${s.frameCount} frames captured. Need at least 8 more. Vary the angle — tilt left, tilt right, near, far, rotate.`;
  } else if (s.frameCount < 15) {
    hint.textContent = `${s.frameCount} frames captured. Try to reach 15 for best accuracy. Vary angles more.`;
  } else {
    hint.textContent = `${s.frameCount} frames captured. Click Calibrate when ready.`;
  }
}

function updateStateLabel(camId, calState) {
  const el_state = el(`state-${camId}`);
  el_state.textContent = calState;
  el_state.className = 'cal-state ' + calState;
}

function addThumbnail(camId, frameIndex, b64) {
  const strip = el(`strip-${camId}`);
  const item = document.createElement('div');
  item.className = 'thumb-item';
  item.id = `thumb-${camId}-${frameIndex}`;

  const img = document.createElement('img');
  img.src = `data:image/jpeg;base64,${b64}`;
  img.alt = `Frame ${frameIndex}`;

  const delBtn = document.createElement('button');
  delBtn.className = 'del-btn';
  delBtn.textContent = '×';
  delBtn.title = 'Remove this frame';
  delBtn.onclick = (e) => { e.stopPropagation(); deleteFrame(camId, frameIndex); };

  item.appendChild(img);
  item.appendChild(delBtn);
  strip.appendChild(item);
}

function checkAllSaved() {
  const allSaved = CAMERA_IDS.every(c => state[c].calState === 'saved');
  el('done-banner').style.display = allSaved ? 'block' : 'none';
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

async function captureFrame(camId) {
  showError(camId, '');
  let resp;
  try {
    resp = await fetch(`/capture/${camId}`, { method: 'POST' });
  } catch (e) {
    showError(camId, `Network error: ${e.message}`);
    return;
  }
  const data = await resp.json();
  if (!resp.ok) { showError(camId, data.error || 'Capture failed.'); return; }

  state[camId].frameCount = data.total_frames;
  el(`count-${camId}`).textContent = `${data.total_frames} frame${data.total_frames !== 1 ? 's' : ''}`;

  addThumbnail(camId, data.frame_index, data.thumbnail_b64);
  updateHint(camId);
  updateCalButton(camId);

  // Invalidate any old calibration result since the frame set changed.
  if (state[camId].calState === 'calibrated') {
    state[camId].calState = 'pending';
    updateStateLabel(camId, 'pending');
    el(`btn-save-${camId}`).disabled = true;
    showReproj(camId, null);
  }
}

async function deleteFrame(camId, frameIndex) {
  showError(camId, '');
  let resp;
  try {
    resp = await fetch(`/capture/${camId}/${frameIndex}`, { method: 'DELETE' });
  } catch (e) { showError(camId, `Network error: ${e.message}`); return; }
  const data = await resp.json();
  if (!resp.ok) { showError(camId, data.error || 'Delete failed.'); return; }

  // Remove thumbnail from DOM.
  const thumbEl = el(`thumb-${camId}-${frameIndex}`);
  if (thumbEl) thumbEl.remove();

  state[camId].frameCount = data.total_frames;
  el(`count-${camId}`).textContent = `${data.total_frames} frame${data.total_frames !== 1 ? 's' : ''}`;
  updateHint(camId);
  updateCalButton(camId);

  // Re-index remaining thumbnails (simple rebuild).
  rebuildThumbnailStrip(camId);
}

async function clearFrames(camId) {
  showError(camId, '');
  let resp;
  try {
    resp = await fetch(`/clear/${camId}`, { method: 'POST' });
  } catch (e) { showError(camId, `Network error: ${e.message}`); return; }
  const data = await resp.json();
  if (!resp.ok) { showError(camId, data.error || 'Clear failed.'); return; }

  state[camId].frameCount = 0;
  state[camId].calState = 'pending';
  el(`count-${camId}`).textContent = '0 frames';
  el(`strip-${camId}`).innerHTML = '';
  updateStateLabel(camId, 'pending');
  showReproj(camId, null);
  updateHint(camId);
  updateCalButton(camId);
}

async function runCalibrate(camId) {
  showError(camId, '');
  showReproj(camId, null);
  el(`btn-cal-${camId}`).disabled = true;
  el(`btn-cal-${camId}`).textContent = 'Calibrating…';

  let resp;
  try {
    resp = await fetch(`/calibrate/${camId}`, { method: 'POST' });
  } catch (e) {
    showError(camId, `Network error: ${e.message}`);
    el(`btn-cal-${camId}`).disabled = false;
    el(`btn-cal-${camId}`).textContent = 'Calibrate';
    return;
  }
  const data = await resp.json();
  el(`btn-cal-${camId}`).textContent = 'Calibrate';
  updateCalButton(camId);

  if (!resp.ok) {
    showError(camId, data.error || 'Calibration failed.');
    return;
  }

  state[camId].calState = 'calibrated';
  updateStateLabel(camId, 'calibrated');
  showReproj(camId, data.mean_reprojection_error);
  el(`btn-save-${camId}`).disabled = false;
}

async function runSave(camId) {
  showError(camId, '');
  el(`btn-save-${camId}`).disabled = true;
  el(`btn-save-${camId}`).textContent = 'Saving…';

  let resp;
  try {
    resp = await fetch(`/save/${camId}`, { method: 'POST' });
  } catch (e) {
    showError(camId, `Network error: ${e.message}`);
    el(`btn-save-${camId}`).disabled = false;
    el(`btn-save-${camId}`).textContent = 'Save';
    return;
  }
  const data = await resp.json();
  el(`btn-save-${camId}`).textContent = 'Save';

  if (!resp.ok) {
    showError(camId, data.error || 'Save failed.');
    el(`btn-save-${camId}`).disabled = false;
    return;
  }

  state[camId].calState = 'saved';
  updateStateLabel(camId, 'saved');
  el(`btn-save-${camId}`).disabled = false;
  checkAllSaved();
}

// ---------------------------------------------------------------------------
// Auto-capture
// ---------------------------------------------------------------------------

function toggleAutoCapture(camId) {
  const s = state[camId];
  const checked = el(`auto-${camId}`).checked;
  if (checked) {
    s.autoCapturing = true;
    s.autoTimer = setInterval(() => {
      if (s.autoCapturing) captureFrame(camId);
    }, 2000);
  } else {
    s.autoCapturing = false;
    if (s.autoTimer) { clearInterval(s.autoTimer); s.autoTimer = null; }
  }
}

// ---------------------------------------------------------------------------
// Thumbnail strip rebuild after deletions
// ---------------------------------------------------------------------------

async function rebuildThumbnailStrip(camId) {
  // Re-fetch status to get accurate count, then rebuild thumbnails.
  let resp;
  try {
    resp = await fetch('/status');
  } catch { return; }
  const statusData = await resp.json();
  const count = statusData[camId]?.frame_count ?? 0;
  state[camId].frameCount = count;
  el(`count-${camId}`).textContent = `${count} frame${count !== 1 ? 's' : ''}`;

  const strip = el(`strip-${camId}`);
  strip.innerHTML = '';
  for (let i = 0; i < count; i++) {
    const item = document.createElement('div');
    item.className = 'thumb-item';
    item.id = `thumb-${camId}-${i}`;
    const img = document.createElement('img');
    img.src = `/thumbnail/${camId}/${i}?t=${Date.now()}`;
    img.alt = `Frame ${i}`;
    const delBtn = document.createElement('button');
    delBtn.className = 'del-btn';
    delBtn.textContent = '×';
    delBtn.onclick = (e) => { e.stopPropagation(); deleteFrame(camId, i); };
    item.appendChild(img);
    item.appendChild(delBtn);
    strip.appendChild(item);
  }
  updateHint(camId);
  updateCalButton(camId);
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

function init() {
  CAMERA_IDS.forEach(camId => {
    // Wire auto-capture toggles.
    el(`auto-${camId}`).addEventListener('change', () => toggleAutoCapture(camId));
  });

  // Poll status every 3 s to keep labels fresh.
  setInterval(async () => {
    let resp;
    try { resp = await fetch('/status'); } catch { return; }
    if (!resp.ok) return;
    const data = await resp.json();
    CAMERA_IDS.forEach(camId => {
      const cam = data[camId];
      if (!cam) return;
      state[camId].calState = cam.calibration_state;
      updateStateLabel(camId, cam.calibration_state);
    });
    checkAllSaved();
  }, 3000);

  // Stop MJPEG streams cleanly on page hide/exit.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      CAMERA_IDS.forEach(camId => {
        const img = el(`preview-${camId}`);
        if (img) img.src = '';
      });
    }
  });
}

document.addEventListener('DOMContentLoaded', init);
