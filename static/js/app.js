// Shared browser code. Plain JavaScript, no build step (docs/tech_stack.md).
// Every page still works without it: forms post normally and the server checks everything.
(function () {
  "use strict";
  document.documentElement.classList.add("js");

  // ---- Dialogs (docs/modals.md, "Shared interaction") ----------------------------------
  // Native <dialog>: showModal() keeps focus inside and Escape closes it. We add: open
  // buttons, close buttons, focus back to the opener, and the unsaved-changes check.
  var openers = new WeakMap();

  function openDialog(dialog, opener) {
    if (!dialog || dialog.open) return;
    if (opener) openers.set(dialog, opener);
    dialog.showModal();
    var first = dialog.querySelector(".field-invalid input, .field-invalid select, input:not([type=hidden]), select, textarea");
    if (first) first.focus();
  }

  function dirtyForm(scope) {
    return scope.querySelector("form[data-guard][data-dirty='1']");
  }

  function closeDialog(dialog) {
    var form = dirtyForm(dialog);
    if (form) {
      confirmDiscard(function () {
        form.reset();
        form.removeAttribute("data-dirty");
        dialog.close();
      });
      return;
    }
    dialog.close();
  }

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-dialog-open]");
    if (opener) {
      event.preventDefault();
      openDialog(document.getElementById(opener.getAttribute("data-dialog-open")), opener);
      return;
    }
    var closer = event.target.closest("[data-dialog-close]");
    if (closer) {
      event.preventDefault();
      closeDialog(closer.closest("dialog"));
    }
  });

  document.querySelectorAll("dialog").forEach(function (dialog) {
    dialog.addEventListener("cancel", function (event) {
      if (dirtyForm(dialog)) {
        event.preventDefault();
        closeDialog(dialog);
      }
    });
    dialog.addEventListener("close", function () {
      var opener = openers.get(dialog);
      if (opener && document.contains(opener)) opener.focus();
    });
  });

  // A dialog with server errors opens again on load, with the typed values kept.
  document.querySelectorAll("dialog[data-open-on-load]").forEach(function (dialog) {
    openDialog(dialog, document.querySelector("[data-dialog-open='" + dialog.id + "']"));
    var form = dialog.querySelector("form[data-guard]");
    if (form) form.setAttribute("data-dirty", "1");
  });

  // ---- Dialog 11: discard unsaved changes ------------------------------------------------
  var discard = document.getElementById("dialog-discard");
  var pendingDiscard = null;

  function confirmDiscard(onDiscard) {
    if (!discard) {
      if (window.confirm("Discard your changes?")) onDiscard();
      return;
    }
    pendingDiscard = onDiscard;
    discard.showModal();
    discard.querySelector("[data-discard-keep]").focus();
  }

  if (discard) {
    discard.querySelector("[data-discard-keep]").addEventListener("click", function () {
      pendingDiscard = null;
      discard.close();
    });
    discard.querySelector("[data-discard-confirm]").addEventListener("click", function () {
      var action = pendingDiscard;
      pendingDiscard = null;
      discard.close();
      if (action) action();
    });
  }

  document.querySelectorAll("form[data-guard]").forEach(function (form) {
    var mark = function () { form.setAttribute("data-dirty", "1"); };
    form.addEventListener("input", mark);
    form.addEventListener("change", mark);
    form.addEventListener("submit", function () { form.removeAttribute("data-dirty"); });
  });

  // Leaving a page with a changed form: the browser's own prompt.
  window.addEventListener("beforeunload", function (event) {
    if (document.querySelector("form[data-guard-page][data-dirty='1']")) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  // Following a link away from a changed editor asks first (dialog 11).
  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (link.target === "_blank" || link.getAttribute("href").charAt(0) === "#") return;
    if (!document.querySelector("form[data-guard-page][data-dirty='1']")) return;
    event.preventDefault();
    confirmDiscard(function () {
      document.querySelectorAll("form[data-guard]").forEach(function (f) { f.removeAttribute("data-dirty"); });
      window.location.href = link.href;
    });
  });

  // Signing out with unsaved work asks first.
  document.querySelectorAll("form[data-signout]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form.dataset.confirmed === "1") return;
      if (document.querySelector("form[data-guard][data-dirty='1']")) {
        event.preventDefault();
        confirmDiscard(function () {
          document.querySelectorAll("form[data-guard]").forEach(function (f) { f.removeAttribute("data-dirty"); });
          form.dataset.confirmed = "1";
          form.submit();
        });
      }
    });
  });

  // ---- Block duplicate clicks while a request is pending --------------------------------
  document.addEventListener("submit", function (event) {
    if (event.defaultPrevented) return;
    var form = event.target;
    var submitter = event.submitter;
    var buttons = form.querySelectorAll("[data-once]");
    if (submitter && submitter.hasAttribute("data-once") && !form.contains(submitter)) {
      buttons = [submitter];
    }
    if (form.dataset.sending === "1") {
      event.preventDefault();
      return;
    }
    form.dataset.sending = "1";
    // Wait a tick so the clicked button's own value is still sent.
    setTimeout(function () {
      Array.prototype.forEach.call(buttons, function (button) {
        button.setAttribute("aria-disabled", "true");
        button.disabled = true;
      });
    }, 0);
  });

  // Close the small-screen menu with Escape or a click outside it.
  var menu = document.querySelector("[data-menu]");
  if (menu) {
    document.addEventListener("click", function (event) {
      if (menu.open && !menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.open) {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
  }

  // ---- Practice: active answering time (pauses while the tab is hidden) -----------------
  // Saved with the answer for evaluation and the retrain (docs/agent.md). Time a question's video
  // plays is measured apart and left out; if the player can't report it, both stay empty (unknown).
  document.querySelectorAll("form[data-timed]").forEach(function (form) {
    var field = form.querySelector("[data-active-seconds]");
    var videoField = form.querySelector("[data-video-seconds]");
    var video = document.querySelector("iframe[data-video]");
    var total = 0;
    var since = document.hidden ? null : performance.now();
    var played = 0;
    var playingSince = null;
    var reliable = !video;
    document.addEventListener("visibilitychange", function () {
      if (document.hidden && since !== null) {
        total += performance.now() - since;
        since = null;
      } else if (!document.hidden && since === null) {
        since = performance.now();
      }
    });
    if (video && videoField) {
      window.onYouTubeIframeAPIReady = function () {
        try {
          new window.YT.Player(video.id, {
            events: {
              onReady: function () { reliable = true; },
              onStateChange: function (event) {
                if (event.data === 1) {
                  if (playingSince === null) playingSince = performance.now();
                } else if (playingSince !== null) {
                  played += performance.now() - playingSince;
                  playingSince = null;
                }
              }
            }
          });
        } catch (error) { reliable = false; }
      };
      var api = document.createElement("script");
      api.src = "https://www.youtube.com/iframe_api";
      api.async = true;
      document.head.appendChild(api);
    }
    form.addEventListener("submit", function () {
      var now = performance.now();
      var active = since === null ? total : total + (now - since);
      var watching = played + (playingSince === null ? 0 : now - playingSince);
      if (!reliable) {
        if (field) field.value = "";
        if (videoField) videoField.value = "";
        return;
      }
      if (field) field.value = (Math.max(0, active - watching) / 1000).toFixed(3);
      if (videoField) videoField.value = (watching / 1000).toFixed(3);
    });
  });

  // ---- Practice results: ask local Qwen to reword the saved feedback once (docs/rag.md) ----
  // The score and the saved text are already on the page; if this fails, they simply stay.
  document.querySelectorAll("[data-generate]").forEach(function (box) {
    var token = document.querySelector("input[name=csrfmiddlewaretoken]");
    var text = box.querySelector("[data-feedback-text]");
    var status = box.querySelector("[data-feedback-status]");
    if (!token || !text) return;
    var body = new FormData();
    body.append("session", box.getAttribute("data-session"));
    status.textContent = "Writing a note for you…";
    fetch(box.getAttribute("data-generate"), {
      method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": token.value, "x-requested-with": "fetch" }
    }).then(function (response) {
      if (!response.ok) throw new Error("failed");
      return response.json();
    }).then(function (data) {
      if (data.generated && data.text) text.textContent = data.text;
      status.textContent = "";
    }).catch(function () { status.textContent = ""; });
  });

  // ---- Pretest / posttest: autosave, answered count, guide to the first missing item ----
  var test = document.querySelector("form[data-assessment]");
  if (test) {
    var items = test.querySelectorAll("[data-item]");
    var answered = test.querySelector("[data-answered]");
    var status = test.querySelector("[data-save-status]");
    var timer = null;
    var saving = false;
    var again = false;

    var countAnswered = function () {
      var n = 0;
      items.forEach(function (item) { if (item.querySelector("input:checked")) n += 1; });
      if (answered) answered.textContent = String(n);
      return n;
    };

    var save = function () {
      if (saving) { again = true; return; }
      saving = true;
      status.textContent = " · Saving…";
      fetch(test.dataset.saveUrl, {
        method: "POST",
        body: new FormData(test),
        headers: { "x-requested-with": "fetch" },
        credentials: "same-origin"
      }).then(function (response) {
        if (response.status === 409) { window.location.reload(); return null; }
        if (!response.ok) throw new Error("save failed");
        return response.json();
      }).then(function (data) {
        if (data) status.textContent = " · Saved " + data.at;
      }).catch(function () {
        status.textContent = " · Not saved yet. Check the connection; your choices stay on this page.";
      }).finally(function () {
        saving = false;
        if (again) { again = false; save(); }
      });
    };

    test.addEventListener("change", function (event) {
      if (event.target.type !== "radio") return;
      var li = event.target.closest(".item");
      if (li) li.classList.remove("item-missing");
      countAnswered();
      clearTimeout(timer);
      timer = setTimeout(save, 500);
    });

    var openButton = test.querySelector("[data-submit-open]");
    var dialog = document.getElementById("dialog-submit-assessment");
    openButton.addEventListener("click", function (event) {
      event.preventDefault();
      var missing = null;
      var missingCount = 0;
      items.forEach(function (item) {
        if (!item.querySelector("input:checked")) {
          missingCount += 1;
          if (!missing) missing = item;
        }
      });
      if (missing) {
        var li = missing.closest(".item");
        li.classList.add("item-missing");
        li.scrollIntoView({ behavior: "smooth", block: "start" });
        missing.querySelector("input").focus({ preventScroll: true });
        status.textContent = " · " + missingCount + (missingCount === 1 ? " question needs" : " questions need") + " an answer first.";
        return;
      }
      openDialog(dialog, openButton);
    });

    countAnswered();
  }
})();
