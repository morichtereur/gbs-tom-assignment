"""Build the interactive page as one self-contained HTML file.

The page is built around one control. The reader moves the coordination cost of
a handoff and the assignment reorganises. The tipping point is the finding, so
it is something the reader arrives at by hand rather than reads in a sentence,
and the range this study is willing to defend is drawn on the control itself.

Every state the page shows is a real solved optimum. The slider indexes the
ladder of pre-solved points rather than interpolating between them, so the page
never shows an assignment the solver did not produce.

Two things are drawn as uncertain because they are uncertain: positions the cost
model does not decide, and positions that do not survive resampling. Both are
hatched rather than filled. Nothing on this page renders a tie as a conclusion.
"""

from __future__ import annotations

import json

from tom.config import DATA, ROOT
from tom.fonts import face_css

# The control only offers prices the model was actually solved at, capped where
# the answer has stopped moving.
CONTROL_MAX = 8.0

# Greyscale chrome. One accent, and it appears only as annotation on a chart —
# never on a button, a border, or a slider. The palette is a lightness ramp, so
# it separates for every kind of colour vision and in print, and the two-series
# chart is direct-labelled on top of that rather than relying on the steps.
CSS = """
:root {
  --sans: 'Archivo', system-ui, -apple-system, sans-serif;
  --serif: 'Source Serif 4', Georgia, serif;
  --mono: 'IBM Plex Mono', ui-monospace, Menlo, monospace;
  --paper: #fbfbfa;
  --panel: #f2f2f0;
  --ink: #16181a;
  --ink-2: #4c5054;
  --ink-3: #7b8085;
  --rule: #d8d8d4;
  --rule-strong: #b4b5b0;
  --fill-1: #33373b;
  --fill-2: #9a9ea2;
  --hatch: #b4b5b0;
  --accent: #146b54;
  --band: rgba(20, 107, 84, 0.10);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #131517;
    --panel: #1b1e21;
    --ink: #eceeef;
    --ink-2: #b0b5b9;
    --ink-3: #838a8f;
    --rule: #2c3033;
    --rule-strong: #454b50;
    --fill-1: #d7dadc;
    --fill-2: #6b7176;
    --hatch: #565c61;
    --accent: #4aa98a;
    --band: rgba(74, 169, 138, 0.14);
  }
}
:root[data-theme="dark"] {
  --paper: #131517; --panel: #1b1e21;
  --ink: #eceeef; --ink-2: #b0b5b9; --ink-3: #838a8f;
  --rule: #2c3033; --rule-strong: #454b50;
  --fill-1: #d7dadc; --fill-2: #6b7176; --hatch: #565c61;
  --accent: #4aa98a; --band: rgba(74, 169, 138, 0.14);
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: var(--sans); font-size: 15px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 860px; margin: 0 auto; padding: 34px 22px 80px; }
/* The measure is set by the column, not by a cap on each block. Capping the
   blocks inside a wider column is what leaves a dead gutter down the right
   and makes every paragraph stop in the middle of the page. */
@media (min-width: 980px) {
  .bleed {
    width: min(1140px, calc(100vw - 48px));
    margin-left: calc((100% - min(1140px, calc(100vw - 48px))) / 2);
  }
}
h1 {
  font-size: clamp(24px, 4vw, 34px); font-weight: 700; letter-spacing: -0.02em;
  margin: 0 0 12px; line-height: 1.15; max-width: 30ch;
}
h2 {
  font-size: 12px; font-family: var(--mono); font-weight: 500;
  letter-spacing: 0.09em; text-transform: uppercase; color: var(--ink-3);
  margin: 0 0 14px;
}
.eyebrow {
  font-family: var(--mono); font-size: 11.5px; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 12px;
}
.standfirst {
  font-family: var(--serif); font-size: 17px; line-height: 1.5;
  color: var(--ink-2); margin: 0 0 4px; text-wrap: pretty;
}
p { text-wrap: pretty; }
header { border-bottom: 1px solid var(--rule-strong); padding-bottom: 24px; }
section { border-top: 1px solid var(--rule); padding: 26px 0 4px; }
section:first-of-type { border-top: 0; }
.caption {
  font-size: 12.5px; line-height: 1.5; color: var(--ink-3);
  border-left: 2px solid var(--rule-strong); padding: 2px 0 2px 11px;
  margin: 14px 0 0;
}
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }

/* --- the control -------------------------------------------------------- */
.control { background: var(--panel); border: 1px solid var(--rule-strong); padding: 20px 20px 16px; }
.control-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px 16px; margin-bottom: 4px; }
.control-head label { font-size: 14px; font-weight: 600; }
.readout { font-family: var(--mono); font-size: 21px; font-weight: 500; letter-spacing: -0.01em; }
.readout small { font-size: 12px; color: var(--ink-3); font-weight: 400; }
.track { position: relative; margin: 34px 0 4px; }
.track-band {
  position: absolute; top: -13px; height: 12px; background: var(--band);
  border-left: 1px solid var(--accent); border-right: 1px solid var(--accent);
  pointer-events: none;
}
.track-band span {
  position: absolute; top: -17px; left: 0; white-space: nowrap;
  font-family: var(--mono); font-size: 10.5px; letter-spacing: 0.04em;
  color: var(--accent);
}
.track-mark { position: absolute; top: -13px; height: 12px; width: 1px; background: var(--ink); pointer-events: none; }
.track-mark span {
  position: absolute; top: -17px; left: 0; transform: translateX(-50%);
  white-space: nowrap; font-family: var(--mono); font-size: 10.5px; color: var(--ink-2);
}
input[type=range] {
  width: 100%; display: block; margin: 0; accent-color: var(--ink);
  height: 26px; background: transparent;
}
input[type=range]:focus-visible { outline: 2px solid var(--ink); outline-offset: 3px; }
.scale { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 11px; color: var(--ink-3); margin-top: 2px; }
.control-note { font-size: 12.5px; color: var(--ink-3); margin: 12px 0 0; }

/* --- summary ------------------------------------------------------------ */
.figures { display: grid; grid-template-columns: repeat(auto-fit, minmax(148px, 1fr));
  gap: 1px; background: var(--rule); border: 1px solid var(--rule);
  margin-top: 18px; }
/* The grid can leave a trailing empty track; fill it so the container's
   rule colour does not read as a sixth, blank figure. */
.figures::after { content: ''; background: var(--paper); }
.figure { background: var(--paper); padding: 12px 14px; }
.figure dt { font-size: 11.5px; color: var(--ink-3); margin: 0 0 5px; }
.figure dd { margin: 0; font-family: var(--mono); font-size: 18px; font-weight: 500; letter-spacing: -0.01em; }
.figure dd small { font-size: 11.5px; color: var(--ink-3); font-weight: 400; display: block; margin-top: 3px; font-family: var(--sans); letter-spacing: 0; }

.split { display: flex; height: 26px; margin-top: 16px; gap: 2px; }
.split div { height: 100%; }
.split .labour { background: var(--fill-1); }
.split .coord { background: var(--fill-2); }
.split-key { display: flex; gap: 20px; margin-top: 8px; font-size: 12px; color: var(--ink-2); flex-wrap: wrap; }
.split-key span { display: inline-flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; display: inline-block; }
.swatch.labour { background: var(--fill-1); }
.swatch.coord { background: var(--fill-2); }

/* --- matrix ------------------------------------------------------------- */
.scroller { overflow-x: auto; margin-top: 16px; border: 1px solid var(--rule); }
table { border-collapse: collapse; font-size: 12.5px; width: 100%; min-width: 860px; }
th, td { text-align: left; padding: 6px 9px; border-bottom: 1px solid var(--rule); }
thead th {
  position: sticky; top: 0; background: var(--paper); z-index: 1;
  white-space: nowrap;
  font-family: var(--mono); font-size: 10.5px; font-weight: 500;
  letter-spacing: 0.05em; text-transform: uppercase; color: var(--ink-3);
  vertical-align: bottom; border-bottom: 1px solid var(--rule-strong);
}
tbody tr:hover { background: var(--panel); }
td.num, th.num { text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }
td.cell { text-align: center; padding: 6px 4px; }
.mark { width: 13px; height: 13px; display: inline-block; background: var(--fill-1); }
.mark.tie {
  background: transparent;
  background-image: repeating-linear-gradient(45deg, var(--hatch) 0 2px, transparent 2px 4px);
  outline: 1px solid var(--hatch); outline-offset: -1px;
}
.act { min-width: 210px; font-weight: 600; }
/* The first column is not a place. It is separated by a rule so it does not
   read as one more option alongside the real ones. */
.undecided-col { border-right: 1px solid var(--rule-strong); }
thead th.undecided-col { color: var(--ink-2); }
.act small { display: block; color: var(--ink-3); font-size: 11px; margin-top: 1px; }
.moved td { background: var(--band); }

/* --- curve -------------------------------------------------------------- */
figure { margin: 16px 0 0; }
svg { display: block; width: 100%; height: auto; }
.axis { stroke: var(--rule-strong); stroke-width: 1; }
.grid { stroke: var(--rule); stroke-width: 1; }
.curve { fill: none; stroke: var(--fill-1); stroke-width: 2; }
.curve-2 { fill: none; stroke: var(--fill-2); stroke-width: 2; stroke-dasharray: 5 3; }
.tick { font-family: var(--mono); font-size: 10px; fill: var(--ink-3); }
.annot { stroke: var(--accent); stroke-width: 1.5; }
/* The reader's own position is a full-height line and will cross these
   labels wherever they sit, so they are drawn with a halo of the page
   colour rather than moved somewhere they collide less often. */
.annot-text, .tick {
  paint-order: stroke fill; stroke: var(--paper); stroke-width: 3px;
  stroke-linejoin: round;
}
.annot-text { font-family: var(--mono); font-size: 10.5px; fill: var(--accent); }
.here { stroke: var(--ink); stroke-width: 1.5; }
.band-fill { fill: var(--band); }
.bar { fill: var(--fill-1); }
.bar-label { font-size: 11.5px; fill: var(--ink-2); }
.bar-value { font-family: var(--mono); font-size: 11px; fill: var(--ink-3); }

/* --- exhibits ----------------------------------------------------------- */
/* Consulting furniture, kept as quiet as the rest of the page: a number, a
   title that states the finding rather than the topic, and a source line. The
   title is the argument; the chart is the evidence for it. */
.exhibit { border-top: 1px solid var(--rule); padding: 26px 0 4px; }
.exhibit-no {
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--ink-3); margin: 0 0 6px;
}
.exhibit-title {
  font-size: clamp(17px, 2.4vw, 20px); font-weight: 700; line-height: 1.28;
  letter-spacing: -0.012em; margin: 0 0 10px; max-width: 46ch;
}
.exhibit-lede { margin: 0 0 4px; color: var(--ink-2); font-size: 14.5px; }
.source {
  font-size: 12px; line-height: 1.55; color: var(--ink-3);
  border-top: 1px solid var(--rule); margin: 14px 0 0; padding: 9px 0 0;
}
/* The labels stay monospaced so the eye finds them; the prose after them does
   not, because a long note set in mono is slower to read than it is worth. */
.source b {
  font-family: var(--mono); font-size: 10.5px; font-weight: 500;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-2);
}

/* The answer, stated before any evidence for it. */
.answer { border: 1px solid var(--ink); padding: 22px 22px 18px; margin: 26px 0 4px; }
.answer h2 { color: var(--ink); margin-bottom: 12px; }
.answer p { font-size: clamp(17px, 2.6vw, 21px); line-height: 1.34; font-weight: 600;
  letter-spacing: -0.015em; margin: 0 0 12px; }
.answer p.qual { font-size: 14.5px; font-weight: 400; color: var(--ink-2);
  letter-spacing: 0; margin-bottom: 0; }
.answer .rule { height: 1px; background: var(--rule-strong); margin: 16px 0; }

/* --- misc --------------------------------------------------------------- */
ul { padding-left: 18px; }
li { margin-bottom: 7px; }
a { color: inherit; text-decoration-color: var(--rule-strong); text-underline-offset: 3px; }
a:focus-visible, button:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
footer { border-top: 1px solid var(--rule-strong); margin-top: 34px; padding-top: 18px; font-size: 12.5px; color: var(--ink-3); }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
@media (max-width: 620px) {
  .wrap { padding: 24px 15px 60px; }
  .readout { font-size: 18px; }
}
"""


JS = r"""
const D = window.__TOM__;
const fmt0 = n => n.toLocaleString('en-US', {maximumFractionDigits: 0});
const money = n => 'USD ' + fmt0(n);
const priceOf = i => D.ladder[i].price;

const slider = document.getElementById('price');
const readout = document.getElementById('readout');
let previous = null;

function nearestIndex(price) {
  let best = 0;
  D.ladder.forEach((p, i) => {
    if (Math.abs(p.price - price) < Math.abs(D.ladder[best].price - price)) best = i;
  });
  return best;
}

function render(index) {
  const point = D.ladder[index];
  const price = point.price;
  // Undecided is re-read at every stop. An activity can be pinned by cost at
  // one price and merely placed at another, and the page has to say which.
  const loose = new Set(D.undecided[price.toFixed(2)] || []);

  readout.innerHTML = 'USD ' + price.toFixed(2) +
    ' <small>per handoff</small>';

  document.getElementById('f-total').textContent = money(point.total);
  document.getElementById('f-labour').textContent = money(point.labour);
  document.getElementById('f-coord').textContent = money(point.handoff);
  document.getElementById('f-cross').textContent = fmt0(point.crossings);
  document.getElementById('f-units').textContent = point.units;

  const share = point.total > 0 ? point.labour / point.total : 1;
  document.getElementById('bar-labour').style.width = (share * 100).toFixed(2) + '%';
  document.getElementById('bar-coord').style.width = ((1 - share) * 100).toFixed(2) + '%';
  document.getElementById('key-labour').textContent =
    'Wages ' + (share * 100).toFixed(0) + '%';
  document.getElementById('key-coord').textContent =
    'Coordination ' + ((1 - share) * 100).toFixed(0) + '%';

  let decidedCount = 0;
  D.activities.forEach(a => {
    const decided = !loose.has(a.id);
    if (decided) decidedCount++;
    // Where nothing decides the position, the page does not draw one. The unit
    // the solver returned is a tie-break's output, and putting a mark in that
    // column — even a hatched one — is still naming a column.
    const unit = decided ? point.assignment[a.name] : '__none__';
    const row = document.getElementById('row-' + a.id);
    const changed = previous && previous.assignment[a.name] !== unit;
    row.classList.toggle('moved', !!changed);
    [D.not_decided_column].concat(D.units).forEach(u => {
      const cell = document.getElementById('c-' + a.id + '-' + u.id);
      const here = u.key === unit;
      cell.innerHTML = '';
      if (here) {
        const mark = document.createElement('span');
        mark.className = 'mark' + (decided ? '' : ' tie');
        mark.setAttribute('role', 'img');
        mark.setAttribute('aria-label', decided
          ? a.name + ' assigned to ' + u.label
          : a.name + ': the model does not decide where this goes');
        cell.appendChild(mark);
      }
      cell.setAttribute('aria-selected', here ? 'true' : 'false');
    });
  });

  document.getElementById('f-decided').textContent =
    decidedCount + ' of ' + D.activities.length;

  document.getElementById('marker').setAttribute(
    'transform', 'translate(' + xOf(price).toFixed(2) + ',0)');
  previous = point;
}

/* --- the curve: crossing transitions against the price ------------------- */
const W = 720, H = 210, PAD = {t: 14, r: 16, b: 26, l: 54};
const maxPrice = D.ladder[D.ladder.length - 1].price;
const maxCross = Math.max(...D.ladder.map(p => p.crossings));
const xOf = p => PAD.l + (p / maxPrice) * (W - PAD.l - PAD.r);
const yOf = c => PAD.t + (1 - c / maxCross) * (H - PAD.t - PAD.b);

function drawCurve() {
  const svg = document.getElementById('curve');
  const ns = 'http://www.w3.org/2000/svg';
  const add = (tag, attrs, text) => {
    const el = document.createElementNS(ns, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (text !== undefined) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  // The band this study is willing to defend, drawn behind everything.
  add('rect', {
    class: 'band-fill', x: xOf(D.defensible[0]), y: PAD.t,
    width: xOf(D.defensible[1]) - xOf(D.defensible[0]),
    height: H - PAD.t - PAD.b,
  });

  for (let i = 0; i <= 4; i++) {
    const value = (maxCross / 4) * i;
    add('line', {class: 'grid', x1: PAD.l, x2: W - PAD.r, y1: yOf(value), y2: yOf(value)});
    add('text', {class: 'tick', x: PAD.l - 8, y: yOf(value) + 3, 'text-anchor': 'end'},
        fmt0(Math.round(value / 1000)) + 'k');
  }
  add('line', {class: 'axis', x1: PAD.l, x2: W - PAD.r, y1: H - PAD.b, y2: H - PAD.b});
  for (let p = 0; p <= maxPrice; p += 2) {
    add('text', {class: 'tick', x: xOf(p), y: H - PAD.b + 14, 'text-anchor': 'middle'},
        p.toFixed(0));
  }

  // A step line, because the optimum is piecewise constant in the price. A
  // smooth line here would draw assignments that were never solved for.
  let d = '';
  D.ladder.forEach((p, i) => {
    if (i === 0) d += 'M' + xOf(p.price) + ',' + yOf(p.crossings);
    else d += 'H' + xOf(p.price) + 'V' + yOf(p.crossings);
  });
  add('path', {class: 'curve', d: d});

  add('line', {
    class: 'annot', x1: xOf(D.tipping.price), x2: xOf(D.tipping.price),
    y1: PAD.t, y2: H - PAD.b,
  });
  add('text', {
    class: 'annot-text', x: xOf(D.tipping.price) + 5, y: PAD.t + 11,
  }, 'tipping point ' + D.tipping.price.toFixed(2));
  add('text', {
    class: 'annot-text', x: xOf(D.defensible[0]) + 4, y: H - PAD.b - 6,
  }, 'defensible range');

  const marker = add('g', {id: 'marker'});
  const line = document.createElementNS(ns, 'line');
  line.setAttribute('class', 'here');
  line.setAttribute('y1', PAD.t - 6);
  line.setAttribute('y2', H - PAD.b);
  line.setAttribute('x1', 0);
  line.setAttribute('x2', 0);
  marker.appendChild(line);
}

/* --- what each constraint is doing -------------------------------------- */
function drawAblation() {
  const svg = document.getElementById('ablation');
  if (!svg) return;
  const ns = 'http://www.w3.org/2000/svg';
  const rows = D.ablation;
  const LABELS = {
    sod: 'Segregation of duties',
    min_site_size: 'Minimum site size',
    contact_coverage: 'Contact coverage',
    judgment_cap: 'Judgment cap',
  };
  // Room on the right for two value columns. The longest bar plus its own
  // label has to clear the cost column, or they overprint.
  const W = 720, ROW = 34, LEFT = 168, RIGHT = 210, TOP = 22;
  const H = rows.length * ROW + TOP + 10;
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  const max = Math.max(...rows.map(r => r.moved));
  const add = (tag, attrs, text) => {
    const el = document.createElementNS(ns, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (text !== undefined) el.textContent = text;
    svg.appendChild(el);
    return el;
  };

  add('text', {class: 'bar-value', x: LEFT, y: 12}, 'activities moved');
  add('text', {class: 'bar-value', x: W, y: 12, 'text-anchor': 'end'},
      'change in annual cost');

  rows.forEach((r, i) => {
    const y = i * ROW + TOP;
    const width = (r.moved / max) * (W - LEFT - RIGHT);
    add('text', {class: 'bar-label', x: 0, y: y + 14}, LABELS[r.constraint] || r.constraint);
    // Thin mark, anchored to the baseline, with the data end rounded.
    add('rect', {class: 'bar', x: LEFT, y: y + 3, width: Math.max(width, 1),
                 height: 13, rx: 3});
    add('text', {class: 'bar-value', x: LEFT + width + 8, y: y + 14},
        r.moved + ' of ' + D.activities.length);
    add('text', {class: 'bar-value', x: W, y: y + 14, 'text-anchor': 'end'},
        'USD ' + (r.cost_delta / 1000).toFixed(0) + 'k');
  });
  add('line', {class: 'axis', x1: LEFT, x2: LEFT, y1: TOP - 4,
               y2: rows.length * ROW + TOP - 4});
}

drawCurve();
drawAblation();
slider.addEventListener('input', e => render(+e.target.value));
render(+slider.value);
"""


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def _unit_label(key: str, results: dict) -> str:
    if "@" not in key:
        return key.capitalize()
    model, location = key.split("@", 1)
    label = next(
        (l["label"] for l in results["locations"] if l["key"] == location), location
    )
    return f"{label} · {model}"


def payload(results: dict) -> dict:
    ladder = [p for p in results["ladder"] if p["price"] <= CONTROL_MAX]
    used = sorted({u for p in ladder for u in p["assignment"].values()})
    forced = results["forced"]["positions"]
    stability = (results.get("stability") or {}).get("activities", {})

    activities = [
        {
            "name": a["name"],
            "id": _slug(a["name"]),
            "fte": a["fte"],
            "events": a["events"],
            "family": a["family"],
            "contact": a["contact"],
            "isco": a["isco"],
            "decided": bool(forced.get(a["name"], {}).get("forced")),
            "cost_of_moving": forced.get(a["name"], {}).get("cost_of_moving"),
            "modal_share": stability.get(a["name"], {}).get("modal_share"),
            "stable": stability.get(a["name"], {}).get("stable"),
        }
        for a in results["activities"]
        if a["owner"] == "buyer"
    ]
    activities.sort(key=lambda a: -a["fte"])

    # Per price: the activities whose position nothing decides. Sent as a list
    # of ids per stop rather than a flag per activity, because it is short and
    # the page only ever asks "is this one undecided right now".
    by_price = results["forced"].get("by_price", {})
    ids = {a["name"]: _slug(a["name"]) for a in results["activities"]}
    undecided = {
        f"{point['price']:.2f}": sorted(
            ids[name]
            for name, row in by_price.get(f"{point['price']:.2f}", {}).items()
            if not row["forced"]
        )
        for point in ladder
    }

    return {
        "ladder": ladder,
        "undecided": undecided,
        "not_decided_column": NOT_DECIDED,
        "units": [
            {"key": key, "id": _slug(key), "label": _unit_label(key, results)}
            for key in used
        ],
        "activities": activities,
        "defensible": results["pre_registered"]["defensible_range"],
        "declared_price": results["pre_registered"]["handoff_price"],
        "tipping": results["tipping_point"],
        "headline": results["headline"],
        "forced": results["forced"],
        "scale": results["scale"],
        "ablation": [
            {"constraint": row["constraint"], "moved": len(row["moved"]),
             "cost_delta": row["cost_delta"]}
            for row in sorted(
                results["ablation"], key=lambda r: -len(r["moved"])
            )
        ],
    }


NOT_DECIDED = {"key": "__none__", "id": "none", "label": "Not decided"}


def _matrix(data: dict) -> str:
    columns = [NOT_DECIDED] + list(data["units"])
    head = "".join(
        f'<th class="num{" undecided-col" if u is NOT_DECIDED else ""}" scope="col">'
        f'{u["label"].replace(" · ", "<br>")}</th>'
        for u in columns
    )
    rows = []
    for a in data["activities"]:
        cells = "".join(
            f'<td class="cell{" undecided-col" if u is NOT_DECIDED else ""}" '
            f'id="c-{a["id"]}-{u["id"]}"></td>'
            for u in columns
        )
        note = []
        if not a["decided"]:
            note.append("not decided by cost")
        if a["stable"] is False:
            note.append(f'holds in {a["modal_share"]:.0%} of draws')
        detail = f"<small>{' · '.join(note)}</small>" if note else ""
        rows.append(
            f'<tr id="row-{a["id"]}">'
            f'<th scope="row" class="act">{a["name"]}{detail}</th>'
            f'<td class="num">{a["fte"]:.1f}</td>'
            f'<td class="num">{a["events"]:,}</td>'
            f"{cells}</tr>"
        )
    return (
        '<div class="scroller bleed"><table>'
        '<thead><tr><th scope="col">Activity</th>'
        '<th class="num" scope="col">FTE</th>'
        '<th class="num" scope="col">Events</th>'
        f"{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _control(data: dict) -> str:
    ladder = data["ladder"]
    last = len(ladder) - 1
    top = ladder[-1]["price"]
    lo, hi = data["defensible"]
    tipping = data["tipping"]["price"]

    def at(price: float) -> float:
        """Where a price sits on the control, as a percentage of its travel.

        The control indexes the ladder rather than the price, and the ladder is
        dense where the answer moves. So the marks are placed by index too —
        placing them on a linear price scale put the defensible range in the
        wrong half of the track.
        """
        below = [i for i, point in enumerate(ladder) if point["price"] <= price]
        index = below[-1] if below else 0
        if index < last and ladder[index]["price"] < price:
            span = ladder[index + 1]["price"] - ladder[index]["price"]
            index += (price - ladder[index]["price"]) / span if span else 0
        return min(100.0, max(0.0, index / last * 100.0))

    # Index of the price nearest the declared default, so the page opens where
    # the study's own reported optimum sits.
    default = min(
        range(len(ladder)),
        key=lambda i: abs(ladder[i]["price"] - data["declared_price"]),
    )
    return f"""
<div class="control">
  <div class="control-head">
    <label for="price">What one handoff costs</label>
    <span class="readout" id="readout" aria-live="polite"></span>
  </div>
  <div class="track">
    <div class="track-band" style="left:{at(lo):.2f}%;width:{at(hi) - at(lo):.2f}%">
      <span>defensible range</span>
    </div>
    <div class="track-mark" style="left:{at(tipping):.2f}%"><span>{tipping:.2f}</span></div>
    <input type="range" id="price" min="0" max="{last}" step="1" value="{default}"
           aria-label="Coordination cost per handoff, in US dollars"
           aria-describedby="control-note">
  </div>
  <div class="scale"><span>USD 0</span><span>USD {top:.0f}</span></div>
  <p class="control-note" id="control-note">
    Every stop on this control is a price the model was solved at. The page does
    not interpolate between them, so nothing here is an assignment the solver
    did not produce. Arrow keys move one stop.
  </p>
</div>"""


def build_html(results: dict) -> str:
    data = payload(results)
    h = results["headline"]
    f = results["forced"]
    s = results["scale"]
    st = results.get("stability")
    cls = results.get("classifier")
    tip = results["tipping_point"]
    cur = results["pre_registered"]["currency"]
    lo, hi = data["defensible"]
    tr = s["transitions"]

    stability_line = (
        f"{st['summary']['stable']} of {st['summary']['total']} activities hold their "
        f"unit in at least {st['stable_threshold']:.0%} of {st['draws']:,} draws"
        if st else "the resampling run has not been executed"
    )
    classifier_line = (
        f"{cls['overall']['accuracy']:.0%} accurate against the hand-labelled gold set, "
        f"with the ported keyword stage deciding {cls['coverage']['activities']:.0%} of "
        f"names and recalling {cls['stage_1_taxonomy']['recall']['judgment']:.0%} of "
        f"judgment work"
        if cls else "not measured"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>What a handoff costs</title>
<style>{face_css()}{CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">Target operating model · purchase-to-pay · {s['assignable']} activities</p>
  <h1>What a handoff costs decides the operating model</h1>
  <p class="standfirst">
    A target operating model arrives as four columns on a slide — retained,
    captive, provider, automated — with the activities sorted into them by the
    people whose functions are being sorted. What the sorting costs is missing.
    The expensive part is not where an activity sits but how often work crosses
    between columns, and nobody has measured which activities follow each other.
  </p>
</header>

<div class="answer">
  <h2>The answer</h2>
  <p>
    Concentrating purchase-to-pay pays only above {cur} {tip['price']:.2f} per
    handoff. That sits {"inside" if tip['inside_defensible_range'] else "outside"}
    the range this study is willing to defend — near its top edge.
  </p>
  <div class="rule"></div>
  <p class="qual">
    Below that price the model spreads work across cheaper cities and pays for
    the crossings; at it, {tip['activities_moved']} of {s['assignable']}
    activities change unit at once. The case for concentrating this process
    therefore rests on the upper half of what a handoff can defensibly be argued
    to cost, not on the middle of it.
  </p>
  <p class="qual" style="margin-top:10px">
    This is not a target operating model, and the tool below does not name one.
    Cost decides {f['forced']} of the {f['total']} positions. The other
    {f['tie_broken']} are ties, and they are left undecided rather than filled in.
  </p>
</div>

<section class="exhibit">
  <p class="exhibit-no">Exhibit 1 · the control</p>
  <h3 class="exhibit-title">Move the price of a handoff and the operating model
    reorganises</h3>
  <p class="exhibit-lede">
    The one number the slide never states. Drag it and watch the answer change.
  </p>
  {_control(data)}

  <dl class="figures">
    <div class="figure"><dt>Total annual cost</dt><dd id="f-total"></dd></div>
    <div class="figure"><dt>Wages</dt><dd id="f-labour"></dd></div>
    <div class="figure"><dt>Coordination</dt><dd id="f-coord"></dd></div>
    <div class="figure"><dt>Crossing transitions</dt><dd id="f-cross"><small>of {tr['priced']:,} priced</small></dd></div>
    <div class="figure"><dt>Units in use</dt><dd id="f-units"></dd></div>
    <div class="figure"><dt>Positions cost decides</dt><dd id="f-decided"><small>the rest are undecided</small></dd></div>
  </dl>

  <div class="split" role="img" aria-label="Split between wages and coordination cost">
    <div class="labour" id="bar-labour"></div>
    <div class="coord" id="bar-coord"></div>
  </div>
  <div class="split-key">
    <span><i class="swatch labour"></i><span id="key-labour"></span></span>
    <span><i class="swatch coord"></i><span id="key-coord"></span></span>
  </div>

  <p class="source">
    <b>Source:</b> handling volumes from 1,595,923 SAP events over 251,734
    purchase-order line items; wages from the ILOSTAT panel behind
    gbs-location-selection.<br>
    <b>Note:</b> the split is arithmetic, not evidence. Wage cost rests on
    handling times this study authored and resamples; coordination cost rests
    entirely on the number you are holding. At the low end the bar says this
    process is a wage bill and at the high end it says it is a coordination
    problem — and nobody in the room knows which.
  </p>
</section>

<section class="exhibit">
  <p class="exhibit-no">Exhibit 2 · where the answer turns</p>
  <h3 class="exhibit-title">Concentration only pays above {cur} {tip['price']:.2f}
    per handoff, in the top half of the defensible range</h3>
  <p class="exhibit-lede">
    Crossing transitions against the coordination price, at proven optimality
    for every point on the line.
  </p>
  <figure>
    <svg id="curve" viewBox="0 0 720 210" role="img"
         aria-label="Crossing transitions fall in steps as the coordination price rises,
                     with the largest step at the tipping point">
    </svg>
  </figure>
  <p class="source">
    <b>Source:</b> OR-Tools CP-SAT, one exact solve per stop; handoff graph from
    the 11,973 variants of the same log.<br>
    <b>Note:</b> steps rather than a curve, because the optimum is piecewise
    constant in the price — a smooth line would draw assignments that were never
    solved for. The line flattens well before the right-hand edge, and its last
    improvement is worth about 1% of crossings, which is why the turn is measured
    where the assignment reorganises rather than where the line finally bottoms
    out.
  </p>
</section>

<section class="exhibit">
  <p class="exhibit-no">Exhibit 3 · what is decided and what is not</p>
  <h3 class="exhibit-title">Cost decides {f['forced']} of {f['total']} positions;
    the rest are ties and are left blank</h3>
  <p class="exhibit-lede">
    Rows tint when they move. The first column is not a place.
  </p>
  {_matrix(data)}
  <p class="source">
    <b>Source:</b> at every stop on the control, each activity is barred in turn
    from the unit it was given and the model re-solved — {len(data['ladder']) * s['assignable']:,}
    exact probes.<br>
    <b>Note:</b> where the total does not move, several units cost exactly the
    same and nothing decided between them. Those sit under <em>not decided</em>,
    because putting them in a column — even a hatched one — would still be naming
    a column. The count moves as you drag: an activity can be pinned by cost at
    one price and undecided at another.
  </p>
</section>

<section class="exhibit">
  <p class="exhibit-no">Exhibit 4 · what each constraint is doing</p>
  <h3 class="exhibit-title">Contact coverage, not cost, is what keeps this process
    out of the cheapest markets</h3>
  <p class="exhibit-lede">
    Each constraint removed in turn, everything else held. Activities that move,
    and what the answer costs without it.
  </p>
  <figure>
    <svg id="ablation" role="img"
         aria-label="Removing contact coverage moves far more activities than
                     removing any other constraint">
    </svg>
  </figure>
  <p class="source">
    <b>Source:</b> one exact re-solve per constraint at {cur} {results['pre_registered']['handoff_price']:.2f} per handoff.<br>
    <b>Note:</b> the contact requirement is only that somebody can answer a
    supplier inside their working day, and on this process it is worth more than
    the entire labour-arbitrage argument. Read the two columns against each
    other: segregation of duties moves three activities and costs about
    {cur} 409k, so it is the cheapest constraint to state and among the most
    expensive to obey — the count of activities moved is not a proxy for what a
    constraint costs. None of the four is decorative, which is a weaker claim
    than it sounds and worth making anyway; the usual outcome of this test is
    that two of them do nothing.
  </p>
</section>

<section class="exhibit">
  <p class="exhibit-no">Exhibit 5 · what the model is standing on</p>
  <h3 class="exhibit-title">One input is measured; the four that decide the cost
    are declared</h3>
  <ul>
    <li><strong>Measured.</strong> Which activities follow each other, from
      {s['transitions']['total']:,} transitions across 11,973 variants of a real
      SAP log. {tr['self_loops']:,} of those are an activity repeating and never
      cross a unit; {tr['touching_unassignable']:,} touch a vendor or a system
      step and are unavoidable whatever anyone decides. Both are excluded, so
      {tr['priced']:,} transitions are priced.</li>
    <li><strong>Declared.</strong> Handling time per activity, the mapping from
      activity to wage group, the provider margin, and the coordination price
      itself. All four are resampled 10,000 times, and
      {stability_line}.</li>
    <li><strong>Measured, and it failed.</strong> The transactional/judgment
      classifier ported from the sibling study is {classifier_line}. Its error is
      what the resampling runs over, rather than an assumed rate.</li>
    <li><strong>Not separable.</strong> India has no city-level wage in any
      reachable source, so four of its five cities are identical on every input
      the model reads. They are reported as one band, not ranked.</li>
  </ul>
  <p class="source">
    <b>Note:</b> purchase-to-pay only. Nothing here extends to record-to-report
    or order-to-cash, and a narrow model that was checked beats a broad one that
    was asserted. Transition and severance costs, attrition, tax and incentives
    are all absent: the comparison is steady state to steady state.
  </p>
</section>

<footer>
  <p>
    Solver: OR-Tools CP-SAT, solved to proven optimality at every stop on the
    control. No language model anywhere in the assignment decision. Inputs from
    <span class="mono">p2p-process-mining</span> and
    <span class="mono">gbs-location-selection</span>; the segregation-of-duties
    rule from <span class="mono">finance-close-control-agent</span>. Both
    pre-registered metrics, the configuration and the full method are in the
    repository.
  </p>
</footer>

</div>
<script>window.__TOM__ = {json.dumps(data, separators=(",", ":"))};</script>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    results = json.loads((DATA / "results.json").read_text())
    html = build_html(results)
    out = ROOT / "dashboard.html"
    out.write_text(html)
    print(f"wrote {out.name} ({len(html) / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
