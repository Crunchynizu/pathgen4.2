// Lesson interactives, ported from PathGen 3.0's lesson.js. Presentation only: nothing here is
// saved, scored or used by BKT. Without JavaScript the plain text inside each widget stays.
(function () {
  "use strict";
  var page = document.querySelector("[data-lesson-page]");
  if (!page) return;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var MINUS = "−";

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function button(className, text) {
    var node = el("button", className, text);
    node.type = "button";
    return node;
  }
  function num(n) {
    var span = el("span", n < 0 ? "num num-neg" : n > 0 ? "num num-pos" : "num num-zero");
    span.textContent = n < 0 ? MINUS + Math.abs(n) : String(n);
    return span;
  }
  function say(target) {
    var parts = Array.prototype.slice.call(arguments, 1);
    target.replaceChildren.apply(target, parts.map(function (part) {
      return typeof part === "number" ? num(part) : document.createTextNode(part);
    }));
  }

  // ---- Spot the mistake: "X is wrong. Why." becomes a quick yes/no check ----
  page.querySelectorAll("[data-spot-mistake]").forEach(function (card) {
    var textNode = card.querySelector("[data-mistake-text]");
    var match = textNode && textNode.textContent.trim().match(/^(.+?) is wrong\.\s*([\s\S]*)$/);
    if (!match) return;
    var claim = match[1], why = match[2];
    var label = card.querySelector(".lw-mistake-label");
    if (label) label.textContent = "Spot the mistake";
    var claimLine = el("p", "lw-claim", "“" + claim + "”");
    var ask = el("p", "lw-ask", "Is this right?");
    var row = el("div", "lw-guess");
    var yes = button("btn btn-secondary", "It's right");
    var no = button("btn btn-secondary", "It's wrong");
    row.append(yes, no);
    var verdict = el("p", "lw-verdict");
    verdict.setAttribute("role", "status");
    var explain = el("p", "lw-why", "It's wrong. " + why);
    verdict.hidden = true;
    explain.hidden = true;
    textNode.replaceWith(claimLine, ask, row, verdict, explain);
    function answer(saidWrong) {
      yes.disabled = true;
      no.disabled = true;
      card.dataset.result = saidWrong ? "good" : "oops";
      verdict.textContent = saidWrong ? "Good eye! You spotted it." : "Careful! This one is a trap.";
      verdict.hidden = false;
      explain.hidden = false;
    }
    yes.addEventListener("click", function () { answer(false); });
    no.addEventListener("click", function () { answer(true); });
  });

  // ---- Step-by-step reveal (worked examples, order of operations) ----
  page.querySelectorAll("[data-reveal-group]").forEach(function (group) {
    var items = Array.prototype.slice.call(group.querySelectorAll("[data-reveal-item]"));
    if (items.length < 2) return;
    var label = group.dataset.revealLabel || "Show step";
    var finalLabel = group.dataset.revealFinal;
    var shown = 0;
    items.forEach(function (item) { item.hidden = true; });
    var bar = el("div", "lw-reveal-bar");
    var next = button("btn btn-primary btn-small", "");
    var all = button("lw-link-btn", "Show all");
    bar.append(next, all);
    group.append(bar);
    function sync() {
      var upcoming = items[shown];
      next.textContent = upcoming && upcoming.hasAttribute("data-reveal-answer") && finalLabel ? finalLabel : label + " " + (shown + 1);
      if (shown >= items.length) bar.remove();
    }
    function revealOne() {
      var item = items[shown];
      item.hidden = false;
      item.classList.add("is-revealed");
      shown += 1;
      sync();
      item.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "nearest" });
    }
    next.addEventListener("click", revealOne);
    all.addEventListener("click", function () { while (shown < items.length) revealOne(); });
    sync();
  });

  // ---- Interactive figures ----
  var widgets = {
    numberline: function (figure, stage) {
      var opposites = figure.dataset.mode === "opposites";
      var value = Number(figure.dataset.start || 0);
      var MIN = -8, MAX = 8;
      var track = el("div", "lw-nl-track");
      var ticks = [];
      for (var n = MIN; n <= MAX; n += 1) {
        (function (n) {
          var tick = button("lw-tick");
          tick.dataset.n = String(n);
          tick.dataset.sign = n < 0 ? "neg" : n > 0 ? "pos" : "zero";
          tick.setAttribute("aria-label", "Choose " + (n < 0 ? "negative " + Math.abs(n) : n));
          tick.append(el("span", "lw-tick-dot"), el("span", "lw-tick-label", n < 0 ? MINUS + -n : String(n)));
          tick.addEventListener("click", function () { set(n); });
          ticks.push(tick);
          track.append(tick);
        })(n);
      }
      var arrows = el("div", "lw-nl-arrows");
      arrows.append(el("span", "", "← less"), el("span", "", "greater →"));
      var controls = el("div", "lw-controls");
      var less = button("btn btn-secondary btn-small", "← Left");
      var more = button("btn btn-secondary btn-small", "Right →");
      controls.append(less, more);
      var readout = el("p", "lw-readout");
      readout.setAttribute("aria-live", "polite");
      less.addEventListener("click", function () { set(value - 1); });
      more.addEventListener("click", function () { set(value + 1); });
      var wrap = el("div", "lw-nl");
      wrap.append(track, arrows);
      stage.replaceChildren(wrap, controls, readout);
      function set(next) {
        value = Math.max(MIN, Math.min(MAX, next));
        ticks.forEach(function (tick) {
          var t = Number(tick.dataset.n);
          tick.classList.toggle("is-picked", t === value);
          tick.classList.toggle("is-mirror", opposites && value !== 0 && t === -value);
          tick.classList.toggle("is-greater", !opposites && t > value);
          tick.setAttribute("aria-pressed", String(t === value));
        });
        less.disabled = value === MIN;
        more.disabled = value === MAX;
        if (opposites) {
          if (value === 0) say(readout, 0, " is its own opposite, and |", 0, "| = ", 0, ".");
          else say(readout, value, " and ", -value, " are opposites. Each is ", Math.abs(value), " steps from 0, so both have absolute value ", Math.abs(value), ".");
        } else if (value < 0) {
          say(readout, value, " is ", -value, " steps left of 0. Every number to its right is greater.");
        } else if (value > 0) {
          say(readout, value, " is ", value, " steps right of 0. It is greater than 0 and every negative number.");
        } else {
          say(readout, "0 is in the middle. It is neither positive nor negative.");
        }
      }
      set(value);
    },

    chips: function (figure, stage) {
      var negatives = Number(figure.dataset.negatives || 5);
      var positives = Number(figure.dataset.positives || 3);
      var MAX = 8;
      var counters = el("div", "lw-chip-counters");
      var expr = el("p", "lw-expr");
      var board = el("div", "lw-chip-board");
      var pairBtn = button("btn btn-primary", "Make zero pairs");
      var readout = el("p", "lw-readout");
      readout.setAttribute("aria-live", "polite");
      function counter(label, sign, get, setValue) {
        var box = el("div", "lw-counter");
        box.dataset.sign = sign;
        var minus = button("btn btn-secondary btn-small", "−");
        minus.setAttribute("aria-label", "Fewer " + label);
        var plus = button("btn btn-secondary btn-small", "+");
        plus.setAttribute("aria-label", "More " + label);
        var value = el("strong", "lw-counter-value");
        minus.addEventListener("click", function () { setValue(Math.max(0, get() - 1)); draw(); });
        plus.addEventListener("click", function () { setValue(Math.min(MAX, get() + 1)); draw(); });
        box.append(el("span", "lw-counter-name", label), minus, value, plus);
        return { box: box, value: value, minus: minus, plus: plus };
      }
      var neg = counter("negative chips", "neg", function () { return negatives; }, function (v) { negatives = v; });
      var pos = counter("positive chips", "pos", function () { return positives; }, function (v) { positives = v; });
      counters.append(neg.box, pos.box);
      stage.replaceChildren(counters, expr, board, pairBtn, readout);
      function row(count, sign) {
        var line = el("div", "lw-chip-row");
        line.dataset.sign = sign;
        for (var i = 0; i < count; i += 1) line.append(el("span", "lw-chip", sign === "neg" ? MINUS : "+"));
        return line;
      }
      function draw() {
        neg.value.textContent = String(negatives);
        pos.value.textContent = String(positives);
        neg.minus.disabled = negatives === 0;
        neg.plus.disabled = negatives === MAX;
        pos.minus.disabled = positives === 0;
        pos.plus.disabled = positives === MAX;
        say(expr, -negatives, " + ", positives, " = ?");
        board.replaceChildren(row(negatives, "neg"), row(positives, "pos"));
        pairBtn.disabled = false;
        say(readout, "A negative chip and a positive chip together make zero. Tap the button to pair them.");
      }
      pairBtn.addEventListener("click", function () {
        var pairs = Math.min(negatives, positives);
        var rows = board.children;
        for (var i = 0; i < pairs; i += 1) {
          rows[0].children[i].classList.add("is-cancelled");
          rows[1].children[i].classList.add("is-cancelled");
        }
        pairBtn.disabled = true;
        var result = positives - negatives;
        if (pairs === 0) say(readout, "No zero pairs: all the chips have the same sign. The sum is ", result, ".");
        else if (result === 0) say(readout, pairs + " pairs make zero and nothing is left, so the sum is ", 0, ".");
        else say(readout, pairs + (pairs === 1 ? " pair makes" : " pairs make") + " zero. " + Math.abs(result) + " " + (result < 0 ? "negative" : "positive") + (Math.abs(result) === 1 ? " chip is" : " chips are") + " left, so ", -negatives, " + ", positives, " = ", result, ".");
        say(expr, -negatives, " + ", positives, " = ", result);
      });
      draw();
    },

    signs: function (figure, stage) {
      var cells = Array.prototype.slice.call(stage.querySelectorAll("[data-sign-cell]"));
      var readout = el("p", "lw-readout", "Tap a box to see the sign of the answer.");
      readout.setAttribute("aria-live", "polite");
      cells.forEach(function (cell) {
        var text = cell.textContent.trim();
        var reveal = button("lw-sign-btn", "?");
        reveal.setAttribute("aria-label", "Show: " + cell.dataset.label);
        cell.dataset.text = text;
        cell.replaceChildren(reveal);
        reveal.addEventListener("click", function () {
          cell.textContent = text;
          cell.classList.add("is-revealed");
          readout.textContent = cell.dataset.label + ": " + text;
        });
      });
      stage.append(readout);
    },

    thermometer: function (figure, stage) {
      var start = Number(figure.dataset.start || 0);
      var change = Number(figure.dataset.change || 0);
      var MIN = -10, MAX = 10, temp = start, timer = null;
      var scale = el("div", "lw-thermo-scale");
      for (var t = MAX; t >= MIN; t -= 2) scale.append(el("span", "lw-thermo-mark", (t < 0 ? MINUS + -t : String(t)) + "°"));
      var tube = el("div", "lw-thermo-tube");
      var fill = el("span", "lw-thermo-fill");
      tube.append(fill);
      var panel = el("div", "lw-thermo-panel");
      var big = el("p", "lw-thermo-now");
      big.setAttribute("aria-live", "polite");
      var go = button("btn btn-primary", (change >= 0 ? "Rise by " : "Fall by ") + Math.abs(change) + "°");
      var again = button("btn btn-secondary", "Start again");
      again.hidden = true;
      var readout = el("p", "lw-readout");
      readout.setAttribute("aria-live", "polite");
      panel.append(big, go, again, readout);
      var wrap = el("div", "lw-thermo");
      wrap.append(scale, tube, panel);
      stage.replaceChildren(wrap);
      function paint() {
        fill.style.height = ((temp - MIN) / (MAX - MIN)) * 100 + "%";
        fill.dataset.below = String(temp < 0);
        say(big, temp, " °C");
      }
      function reset() {
        if (timer) window.clearInterval(timer);
        temp = start;
        paint();
        go.hidden = false;
        again.hidden = true;
        say(readout, "It is ", start, " °C. What happens after a change of ", change, " degrees?");
      }
      go.addEventListener("click", function () {
        go.hidden = true;
        var target = start + change;
        var step = change >= 0 ? 1 : -1;
        function finish() {
          again.hidden = false;
          say(readout, start, " + (", change, ") = ", target, ". The new temperature is ", target, " °C.");
        }
        if (reduceMotion.matches) { temp = target; paint(); finish(); return; }
        timer = window.setInterval(function () {
          temp += step;
          paint();
          if (temp === target) { window.clearInterval(timer); finish(); }
        }, 180);
      });
      again.addEventListener("click", reset);
      reset();
    }
  };

  page.querySelectorAll("[data-widget]").forEach(function (figure) {
    var build = widgets[figure.dataset.widget];
    var stage = figure.querySelector("[data-widget-stage]");
    if (!build || !stage) return;
    try {
      build(figure, stage);
      figure.classList.add("is-live");
    } catch (error) { /* keep the plain-text fallback */ }
  });
})();
