// PINET board — small progressive-enhancement helpers. Everything here is
// optional: every form still works as a plain POST if JS fails to run, and
// both tab panels stay visible when JS is off.
(function () {
  "use strict";

  // ---- relative timestamps ----
  // The hotspot is offline, so a phone's clock can be minutes off the Pi's.
  // Ages are measured from the server time the page carried, advanced by the
  // time the page has been open. Without JS the absolute time stays.
  var page = document.querySelector("[data-now]");
  var retime = function () {};
  if (page) {
    var serverNow = parseFloat(page.getAttribute("data-now")) || 0;
    var openedAt = Date.now() / 1000;
    retime = function (root) {
      var now = serverNow + (Date.now() / 1000 - openedAt);
      (root || document).querySelectorAll("time[data-ts]").forEach(function (el) {
        if (!el.title) el.title = el.textContent;   // exact time stays on hover
        var age = now - parseFloat(el.getAttribute("data-ts"));
        if (age < 0 || age >= 86400) return;        // older than a day: keep the date
        el.textContent = age < 60 ? "just now"
          : age < 3600 ? Math.floor(age / 60) + " min ago"
          : Math.floor(age / 3600) + " h ago";
      });
    };
    if (serverNow) { retime(); setInterval(retime, 30000); }
  }

  // ---- real tabs (Messages / Files) ----
  // Without JS, CSS leaves both panels visible; adding `tabs-on` to <body>
  // switches on the show-only-active-panel behavior, so this is safe to skip.
  var tabs = document.querySelectorAll(".tab[data-tab]");
  if (tabs.length) {
    document.body.classList.add("tabs-on");
    var panels = document.querySelectorAll(".tab-panel[data-panel]");
    var activate = function (name, focus) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("data-tab") === name;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        // Roving tabindex: Tab reaches the tablist once, arrows move inside it.
        t.tabIndex = on ? 0 : -1;
        if (on && focus) t.focus();
      });
      panels.forEach(function (p) {
        p.classList.toggle("is-active", p.getAttribute("data-panel") === name);
      });
    };
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () {
        activate(t.getAttribute("data-tab"));
        // Keep the tab in the URL so a reload (or the upload redirect) reopens it.
        try { history.replaceState(null, "", "#" + t.getAttribute("data-tab")); } catch (e) {}
      });
      t.addEventListener("keydown", function (e) {
        var step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        var next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1
          : step ? (i + step + tabs.length) % tabs.length : -1;
        if (next < 0) return;
        e.preventDefault();
        activate(tabs[next].getAttribute("data-tab"), true);
      });
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

  // ---- lockout countdown (login page) ----
  var lockBanner = document.querySelector(".banner.error[data-retry]");
  if (lockBanner) {
    var left = parseInt(lockBanner.getAttribute("data-retry"), 10) || 0;
    var msg = lockBanner.querySelector("span");
    var submit = document.querySelector("[data-login-form] button[type=submit]");
    if (submit) submit.disabled = true;
    var tick = setInterval(function () {
      left -= 1;
      if (left > 0) {
        if (msg) msg.textContent = "Too many attempts \u2014 try again in " + left + "s.";
        return;
      }
      clearInterval(tick);
      if (msg) msg.textContent = "You can try again now.";
      lockBanner.classList.remove("error");
      lockBanner.classList.add("success");
      if (submit) submit.disabled = false;
    }, 1000);
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

  // ---- filter the file list by name ----
  var filterInput = document.querySelector("[data-file-filter]");
  if (filterInput) {
    var filterBox = document.querySelector("[data-filter-box]");
    var status = document.querySelector("[data-filter-status]");
    if (filterBox) filterBox.hidden = false;
    filterInput.addEventListener("input", function () {
      var rows = document.querySelectorAll(".file-row");
      var q = filterInput.value.trim().toLowerCase();
      var shown = 0;
      rows.forEach(function (row) {
        var name = row.querySelector(".filename");
        var hit = !q || (name && name.textContent.toLowerCase().indexOf(q) !== -1);
        row.hidden = !hit;
        if (hit) shown++;
      });
      if (!status) return;
      status.textContent = !q ? ""
        : shown ? shown + " of " + rows.length + " files"
        : "No file matches \u201c" + filterInput.value.trim() + "\u201d";
      status.classList.toggle("show", !!q);
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
          // reopen on the Files tab, with the "File shared." confirmation
          window.location.href = "/?ok=upload#files";
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

  // ---- kiosk mode (Pi desktop shortcut opens /login?kiosk=1) ----
  // Remembered in this browser only, so phones never get it; the class keeps
  // the header clear of dsi-kiosk's close button in the top-left corner.
  try {
    if (/[?&]kiosk=1\b/.test(location.search)) localStorage.setItem("pinetKiosk", "1");
    if (localStorage.getItem("pinetKiosk") === "1") document.documentElement.classList.add("kiosk");
  } catch (e) { /* storage disabled: no kiosk spacing, nothing else changes */ }

  // ---- live board: poll for what other devices posted or uploaded ----
  // Cheap on a Pi serving a handful of phones: one small GET every 10s, only
  // while the page is visible, and the server sends nothing but new rows.
  var msgList = document.querySelector("[data-messages]");
  var fileList = document.querySelector("[data-files]");
  if (page && window.fetch && (msgList || fileList)) {
    var seen = function (list) {
      if (list) list.querySelectorAll("[data-seen-row]").forEach(function (r) {
        r.setAttribute("data-seen", "");
      });
    };
    var addRows = function (list, data, emptySel) {
      if (!list || !data.html) return;
      var empty = list.parentNode.querySelector(emptySel);
      if (empty) empty.remove();
      list.insertAdjacentHTML("afterbegin", data.html);
      list.querySelectorAll("[data-seen-row]:not([data-seen])").forEach(function (row) {
        row.classList.add("is-new");
        retime(row);
      });
      seen(list);
      list.setAttribute("data-newest", data.newest);
    };
    var badge = function (tab, n) {
      var el = document.querySelector('.tab[data-tab="' + tab + '"] .count');
      if (el) el.textContent = n;
    };
    var storage = function (st) {
      var pill = document.querySelector("[data-storage]");
      if (!pill || !st) return;
      var text = pill.querySelector("[data-storage-text]");
      var flag = pill.querySelector("[data-storage-flag]");
      var fill = pill.querySelector("[data-storage-fill]");
      if (text) text.textContent = st.storage_text;
      if (flag) flag.hidden = !st.storage_low;
      if (fill) fill.style.width = st.used_pct + "%";
      pill.classList.toggle("is-low", !!st.storage_low);
    };
    var timer = null;
    var poll = function () {
      if (document.hidden) return;
      var url = "/api/state?since=" + (msgList ? msgList.getAttribute("data-newest") : 0) +
        "&since_file=" + (fileList ? fileList.getAttribute("data-newest") : 0);
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          if (r.status === 401) { clearInterval(timer); return null; }  // session ended
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          if (!data) return;
          addRows(msgList, data.messages, ".empty");
          addRows(fileList, data.files, ".empty");
          var filter = document.querySelector("[data-file-filter]");
          if (filter && filter.value.trim()) filter.dispatchEvent(new Event("input"));
          badge("messages", data.messages.total);
          badge("files", data.files.total);
          storage(data.storage);
        })
        .catch(function () { /* offline for a moment: try again next tick */ });
    };
    seen(msgList); seen(fileList);
    timer = setInterval(poll, 10000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) poll();
    });
  }

  // ---- image thumbnails: fall back to the file-type icon if one can't load ----
  document.querySelectorAll("img[data-thumb]").forEach(function (img) {
    var drop = function () { img.remove(); };
    if (img.complete && img.naturalWidth === 0) drop();
    else img.addEventListener("error", drop);
  });
})();
