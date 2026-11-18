// Teacher report charts (docs/user_features.md "Teacher": Chart.js with a table equivalent).
// Reads the numbers the server put in #chart-data; every chart has a table under it with the
// same values, so nothing depends on the chart or on color alone.
(function () {
  "use strict";
  var source = document.getElementById("chart-data");
  if (!source || !window.Chart) return;
  var data = JSON.parse(source.textContent);
  var ink = "#3f4750";
  var grid = "#eff2f4";
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = ink;

  function draw(holderId, spec) {
    var holder = document.querySelector("[data-chart='" + holderId + "']");
    if (!holder || !spec || !spec.labels.length) return;
    new Chart(holder.querySelector("canvas"), {
      type: "bar",
      data: {
        labels: spec.labels,
        datasets: spec.series.map(function (series) {
          return {
            label: series.label,
            data: series.values,
            backgroundColor: series.color,
            borderColor: "#ffffff",          // the 2px surface gap between touching marks
            borderWidth: spec.stacked ? { right: 2 } : 0,
            borderRadius: spec.stacked ? 0 : 4,
            borderSkipped: "start",
            maxBarThickness: spec.stacked ? 22 : 12,
            categoryPercentage: 0.8,
            barPercentage: 0.9
          };
        })
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: reduced ? false : { duration: 300 },
        interaction: { mode: "nearest", axis: "y", intersect: false },
        plugins: {
          legend: { position: "top", align: "start", labels: { boxWidth: 12, boxHeight: 12, useBorderRadius: true, borderRadius: 2 } },
          tooltip: {
            callbacks: {
              label: function (context) {
                var value = context.parsed.x;
                if (value === null || value === undefined) return context.dataset.label + ": no data";
                return context.dataset.label + ": " + value + (spec.unit === "%" ? "%" : " " + spec.unit);
              }
            }
          }
        },
        scales: {
          x: {
            stacked: spec.stacked, beginAtZero: true, max: spec.max,
            grid: { color: grid }, border: { display: false },
            ticks: { precision: 0, callback: function (v) { return spec.unit === "%" ? v + "%" : v; } }
          },
          y: { stacked: spec.stacked, grid: { display: false }, border: { color: grid } }
        }
      }
    });
  }

  draw("chart-gaps", data.gaps);
  draw("chart-scores", data.scores);
})();
