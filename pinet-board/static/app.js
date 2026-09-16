// PINET board — small progressive-enhancement helpers. Everything here is
// optional: every form still works as a plain POST if JS fails to run, and
// both tab panels stay visible when JS is off.
(function () {
  "use strict";

  // ---- real tabs (Messages / Files) ----
  // Without JS, CSS leaves both panels visible; adding `tabs-on` to <body>
  // switches on the show-only-active-panel behavior, so this is safe to skip.
  var tabs = document.querySelectorAll(".tab[data-tab]");
  if (tabs.length) {
    document.body.classList.add("tabs-on");
    var panels = document.querySelectorAll(".tab-panel[data-panel]");
    var activate = function (name) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("data-tab") === name;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.forEach(function (p) {
        p.classList.toggle("is-active", p.getAttribute("data-panel") === name);
      });
    };
    tabs.forEach(function (t) {
      t.addEventListener("click", function () { activate(t.getAttribute("data-tab")); });
    });
    // Let the URL hash pick the opening tab (used after an upload reload).
    if (location.hash === "#files") activate("files");
    else if (location.hash === "#messages") activate("messages");
  }

  // ---- password show/hide (login page) ----
  var toggle = document.querySelector("[data-toggle-password]");
  if (toggle) {
    var pwInput = document.getElementById(toggle.getAttribute("data-toggle-password"));
    toggle.addEventListener("click", function () {
      var showing = pwInput.type === "text";
      pwInput.type = showing ? "password" : "text";
      toggle.setAttribute("aria-label", showing ? "Show password" : "Hide password");
      toggle.classList.toggle("is-showing", !showing);
    });
  }

  // ---- login submit loading state ----
  var loginForm = document.querySelector("[data-login-form]");
  if (loginForm) {
    loginForm.addEventListener("submit", function () {
      var btn = loginForm.querySelector("button");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span> Checking&hellip;';
      }
    });
  }

  // ---- message character counter ----
  var msgBox = document.querySelector("[data-char-count]");
  if (msgBox) {
    var counter = document.getElementById(msgBox.getAttribute("data-char-count"));
    var max = parseInt(msgBox.getAttribute("maxlength"), 10) || 2000;
    var update = function () {
      var len = msgBox.value.length;
      counter.textContent = len + " / " + max;
      counter.classList.toggle("near-limit", len > max * 0.9);
      counter.classList.toggle("at-limit", len >= max);
    };
    msgBox.addEventListener("input", function () {
      msgBox.setCustomValidity("");
      update();
    });
    update();
  }

  // ---- block whitespace-only posts, which "required" alone lets through
  // (the server then strips them to nothing and silently no-ops) ----
  var postForm = document.querySelector("[data-post-form]");
  if (postForm) {
    postForm.addEventListener("submit", function (e) {
      var body = postForm.querySelector("textarea[name=body]");
      if (body && body.value.trim().length === 0) {
        e.preventDefault();
        body.setCustomValidity("Write something before posting.");
        body.reportValidity();
      }
    });
  }

  // ---- drag & drop + chosen-file preview for the upload form ----
  var dropzone = document.querySelector("[data-dropzone]");
  if (dropzone) {
    var fileInput = dropzone.querySelector("input[type=file]");
    var chosen = document.querySelector("[data-file-chosen]");
    var chosenName = chosen ? chosen.querySelector("[data-file-name]") : null;

    var showChosen = function (file) {
      if (!chosen || !chosenName) return;
      if (file) {
        chosenName.textContent = file.name + " (" + formatBytes(file.size) + ")";
        chosen.classList.add("show");
      } else {
        chosen.classList.remove("show");
      }
    };

    dropzone.addEventListener("click", function () { fileInput.click(); });
    dropzone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", function () {
      showChosen(fileInput.files[0]);
    });
    ["dragenter", "dragover"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.add("drag");
      });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.remove("drag");
      });
    });
    dropzone.addEventListener("drop", function (e) {
      var files = e.dataTransfer.files;
      if (files && files.length) {
        fileInput.files = files;
        showChosen(files[0]);
      }
    });
  }

  function formatBytes(bytes) {
    if (bytes >= 1073741824) return (bytes / 1073741824).toFixed(1) + "GB";
    if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + "MB";
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + "KB";
    return bytes + "B";
  }

  // ---- upload with a real progress bar (falls back to a plain POST if
  // XHR construction fails for any reason) ----
  var uploadForm = document.querySelector("[data-upload-form]");
  if (uploadForm) {
    uploadForm.addEventListener("submit", function (e) {
      var input = uploadForm.querySelector("input[type=file]");
      if (!input || !input.files || !input.files.length) return; // let native validation handle it

      e.preventDefault();
      var progressWrap = document.querySelector("[data-progress]");
      var fill = progressWrap ? progressWrap.querySelector(".progress-fill") : null;
      var pct = progressWrap ? progressWrap.querySelector("[data-progress-pct]") : null;
      var submitBtn = uploadForm.querySelector("button");
      var errorSlot = document.querySelector("[data-upload-error]");

      if (errorSlot) errorSlot.innerHTML = "";
      if (submitBtn) submitBtn.disabled = true;
      if (progressWrap) progressWrap.classList.add("show");

      var xhr = new XMLHttpRequest();
      xhr.open("POST", uploadForm.action, true);
      xhr.upload.addEventListener("progress", function (evt) {
        if (!evt.lengthComputable) return;
        var percent = Math.round((evt.loaded / evt.total) * 100);
        if (fill) fill.style.width = percent + "%";
        if (pct) pct.textContent = percent + "%";
      });
      xhr.addEventListener("load", function () {
        if (xhr.status >= 200 && xhr.status < 400) {
          // reopen on the Files tab so the just-uploaded file is in view
          window.location.hash = "files";
          window.location.reload();
        } else {
          if (submitBtn) submitBtn.disabled = false;
          if (progressWrap) progressWrap.classList.remove("show");
          if (errorSlot) {
            errorSlot.innerHTML = '<div class="banner error">' +
              (xhr.status === 413
                ? "That file is too large, or there isn't enough free space on the Pi right now."
                : "Upload failed &mdash; please try again.") +
              "</div>";
          }
        }
      });
      xhr.addEventListener("error", function () {
        if (submitBtn) submitBtn.disabled = false;
        if (progressWrap) progressWrap.classList.remove("show");
        // Network-level failure: the request never reached the Pi. On phones
        // this is almost always the Wi-Fi sign-in popup (cut off while the
        // file picker was open) and/or mobile data carrying the request.
        if (errorSlot) errorSlot.innerHTML = '<div class="banner error">Upload failed &mdash; your phone lost its connection to PINET. Open 10.10.10.1 in your browser (not the sign-in popup), turn off mobile data, and try again.</div>';
      });

      var formData = new FormData(uploadForm);
      xhr.send(formData);
    });
  }
  // ---- confirm destructive actions (admin file delete) ----
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });
})();
