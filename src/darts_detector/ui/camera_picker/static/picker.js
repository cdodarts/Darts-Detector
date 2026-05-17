// SPDX-License-Identifier: GPL-3.0-or-later
// Darts Detector — Camera Picker — vanilla JS, no frameworks (D-018)

(function () {
  "use strict";

  // Each select[data-preview-target] drives the src of the named <img>.
  // When the user changes the dropdown, we swap the preview src which
  // causes the browser to open a new MJPEG stream for the selected index.
  // The old stream is abandoned (the browser closes the connection), which
  // causes the server-side generator to release the camera handle.

  const selects = document.querySelectorAll(".cam-select[data-preview-target]");

  selects.forEach(function (select) {
    const imgId = select.dataset.previewTarget;
    const img = document.getElementById(imgId);
    if (!img) return;

    select.addEventListener("change", function () {
      const newIndex = select.value;
      // Mark loading state so the user sees the preview is changing.
      img.classList.add("loading");
      // Swap src — browser drops old connection, opens new MJPEG stream.
      img.src = "/preview/" + newIndex;
    });

    // Remove loading class once the first frame arrives.
    img.addEventListener("load", function () {
      img.classList.remove("loading");
    });

    img.addEventListener("error", function () {
      img.classList.remove("loading");
    });
  });

  // Guard: disable Save if no cameras are found.
  const saveBtn = document.getElementById("save-btn");
  const anySelect = document.querySelector(".cam-select");
  if (saveBtn && anySelect && anySelect.options.length === 0) {
    saveBtn.disabled = true;
  }

  // Show a brief spinner on the save button when the form is submitted
  // so the user knows the request is in-flight.
  const form = document.getElementById("picker-form");
  if (form && saveBtn) {
    form.addEventListener("submit", function () {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
    });
  }

})();
