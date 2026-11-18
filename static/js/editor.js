// The teacher exercise editor (docs/pages.md #5). Plain JavaScript, no build step.
// Without it the editor still works: one blank card per save, position numbers typed by hand,
// and the server checks pictures and YouTube links.
(function () {
  "use strict";
  var form = document.querySelector("form[data-editor]");
  if (!form) return;
  var list = form.querySelector("[data-question-list]");
  var template = form.querySelector("template[data-question-template]");
  var total = form.querySelector("input[name$='-TOTAL_FORMS']");
  var addButton = form.querySelector("[data-add-question]");
  var counter = form.querySelector("[data-question-count]");
  var MAX_BYTES = 2 * 1024 * 1024;

  function cards() { return Array.prototype.slice.call(list.querySelectorAll("[data-question]")); }
  function field(card, suffix) { return card.querySelector("[name$='-" + suffix + "']"); }
  function isRemoved(card) { var box = field(card, "DELETE"); return box && box.checked; }
  function isUsed(card) {
    var source = field(card, "source_id");
    return (source && source.value) || card.hasAttribute("data-touched");
  }

  // Pool order = the cards' order on the page. Untouched blank cards keep an empty position so
  // the server skips them.
  function renumber() {
    var n = 0;
    cards().forEach(function (card) {
      var order = field(card, "ORDER");
      var label = card.querySelector("[data-number]");
      if (isUsed(card) && !isRemoved(card)) {
        n += 1;
        if (order) order.value = String(n);
        if (label) label.textContent = String(n);
      } else {
        if (order && !isUsed(card)) order.value = "";
        if (label) label.textContent = isRemoved(card) ? "(removed)" : "(new)";
      }
      card.classList.toggle("q-edit-removed", isRemoved(card));
    });
    if (counter) counter.textContent = String(n);
  }

  function showFormat(card) {
    var checked = card.querySelector("input[name$='-format']:checked");
    card.setAttribute("data-format", checked ? checked.value : "text");
  }

  function checkFigure(card, input) {
    var note = card.querySelector("[data-figure-check]");
    var preview = card.querySelector("[data-figure-preview]");
    var file = input.files && input.files[0];
    preview.hidden = true;
    if (!file) { note.textContent = ""; return; }
    if (["image/png", "image/jpeg"].indexOf(file.type) === -1) {
      note.textContent = "Use a PNG or JPEG picture.";
      return;
    }
    if (file.size > MAX_BYTES) {
      note.textContent = "This picture is " + (file.size / 1048576).toFixed(1) + " MB. Keep it under 2 MB.";
      return;
    }
    note.textContent = "Looks fine: " + file.name + " (" + Math.round(file.size / 1024) + " KB). It uploads when you save.";
    preview.src = URL.createObjectURL(file);
    preview.hidden = false;
  }

  // The same rules as authoring.parse_youtube, for an instant check; the server decides.
  function parseSeconds(value) {
    value = (value || "").trim().toLowerCase();
    if (/^\d+$/.test(value)) return parseInt(value, 10);
    if (/^\d+(:\d{1,2}){1,2}$/.test(value)) {
      return value.split(":").reduce(function (sum, part) { return sum * 60 + parseInt(part, 10); }, 0);
    }
    var m = value.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/);
    if (m && (m[1] || m[2] || m[3])) return (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0);
    return null;
  }

  function parseYoutube(raw) {
    var url;
    try { url = new URL(/:\/\//.test(raw) ? raw : "https://" + raw); } catch (e) { return null; }
    var host = url.hostname.replace(/^(www|m)\./, "");
    var parts = url.pathname.split("/").filter(Boolean);
    var id = null;
    if (host === "youtu.be") id = parts[0];
    else if (/^(youtube\.com|youtube-nocookie\.com|music\.youtube\.com)$/.test(host)) {
      if (parts[0] === "watch") id = url.searchParams.get("v");
      else if (["embed", "shorts", "live", "v"].indexOf(parts[0]) !== -1) id = parts[1];
    }
    if (!id || !/^[A-Za-z0-9_-]{11}$/.test(id)) return null;
    var t = url.searchParams.get("t") || url.searchParams.get("start");
    if (!t && url.hash.indexOf("#t=") === 0) t = url.hash.slice(3);
    return { id: id, start: t ? parseSeconds(t) : null };
  }

  function checkVideo(card) {
    var input = field(card, "video_url");
    var start = field(card, "video_start");
    var note = card.querySelector("[data-video-check]");
    var thumb = card.querySelector("[data-video-thumb]");
    var raw = input.value.trim();
    thumb.hidden = true;
    if (!raw) { note.textContent = ""; return; }
    var video = parseYoutube(raw);
    if (!video) { note.textContent = "That doesn't look like a YouTube video link."; return; }
    if (video.start !== null && start && !start.value) start.value = String(video.start);
    note.textContent = "Video " + video.id + (start && start.value ? ", starting at " + start.value + " s" : ", from the start") + ".";
    thumb.src = "https://i.ytimg.com/vi/" + video.id + "/mqdefault.jpg";
    thumb.alt = "Thumbnail of the YouTube video " + video.id;
    thumb.hidden = false;
  }

  function wire(card) {
    card.querySelectorAll("[data-move]").forEach(function (button) { button.hidden = false; });
    var position = card.querySelector(".q-order");
    if (position) position.hidden = true;
    showFormat(card);
    var url = field(card, "video_url");
    if (url && url.value) checkVideo(card);
  }

  list.addEventListener("input", function (event) {
    var card = event.target.closest("[data-question]");
    if (!card) return;
    if (!card.hasAttribute("data-touched")) { card.setAttribute("data-touched", ""); renumber(); }
    if (/-video_(url|start)$/.test(event.target.name)) checkVideo(card);
  });

  list.addEventListener("change", function (event) {
    var card = event.target.closest("[data-question]");
    if (!card) return;
    card.setAttribute("data-touched", "");
    if (/-format$/.test(event.target.name)) showFormat(card);
    if (/-figure$/.test(event.target.name)) checkFigure(card, event.target);
    renumber();
  });

  list.addEventListener("click", function (event) {
    var button = event.target.closest("[data-move]");
    if (!button) return;
    var card = button.closest("[data-question]");
    var sibling = button.getAttribute("data-move") === "-1" ? card.previousElementSibling : card.nextElementSibling;
    if (!sibling) return;
    if (button.getAttribute("data-move") === "-1") list.insertBefore(card, sibling);
    else list.insertBefore(sibling, card);
    card.setAttribute("data-touched", "");
    form.setAttribute("data-dirty", "1");
    renumber();
    button.focus();
  });

  if (addButton && template && total) {
    addButton.hidden = false;
    addButton.addEventListener("click", function () {
      var index = parseInt(total.value, 10);
      var holder = document.createElement("ol");
      holder.innerHTML = template.innerHTML.replace(/__prefix__/g, String(index));
      var card = holder.firstElementChild;
      list.appendChild(card);
      total.value = String(index + 1);
      card.setAttribute("data-touched", "");
      wire(card);
      renumber();
      var prompt = field(card, "prompt");
      if (prompt) prompt.focus();
    });
  }

  form.addEventListener("submit", renumber);
  cards().forEach(wire);
  renumber();
})();
