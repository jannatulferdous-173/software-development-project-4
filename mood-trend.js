/* ==========================================================
   MindMirror — mood-trend.js
   ----------------------------------------------------------
   Small, dependency-free SVG chart for "how has your mood
   looked this week" — used in two places:

   1. index.html — built from the person's REAL journalHistory
      (see script.js, buildWeeklyTrendFromHistory()).
   2. trend.html — the onboarding page shown right after
      interests.html, before the person has written anything.
      It shows SAMPLE_WEEK_DATA just so the feature is visible
      during a demo/presentation; swap it for real data once
      a backend exists.

   Each day needs: { label, score (0-100 valence), color, mood }
   "color" is a CSS var string, e.g. "var(--amber)".
========================================================== */

const MOOD_VALENCE = {
  Bright:     { score: 85, color: "var(--amber)" },
  Steady:     { score: 65, color: "var(--moss)"  },
  Mixed:      { score: 50, color: "var(--slate)" },
  Unsettled:  { score: 35, color: "var(--plum)"  },
  Charged:    { score: 30, color: "var(--rust)"  },
  Heavy:      { score: 20, color: "var(--slate)" }
};

// Demo data for trend.html (no real entries exist yet at that point
// in onboarding). Numbers are illustrative, not tied to any user.
const SAMPLE_WEEK_DATA = [
  { label: "Mon", mood: "Steady",    score: 62 },
  { label: "Tue", mood: "Unsettled", score: 38 },
  { label: "Wed", mood: "Heavy",     score: 24 },
  { label: "Thu", mood: "Mixed",     score: 48 },
  { label: "Fri", mood: "Bright",    score: 74 },
  { label: "Sat", mood: "Bright",    score: 82 },
  { label: "Sun", mood: "Steady",    score: 68 }
].map(d => ({ ...d, color: (MOOD_VALENCE[d.mood] || {}).color || "var(--slate)" }));

/**
 * Renders a bar + line trend chart into `containerEl` (a <div>).
 * `days` — array of up to 7 { label, score, color, mood } objects,
 * oldest first.
 */
function renderMoodTrendChart(containerEl, days){
  if (!containerEl || !days || !days.length) return;

  const W = 700, H = 200;
  const padL = 30, padR = 20, padT = 20, padB = 30;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;
  const stepX = chartW / Math.max(days.length - 1, 1);
  const barW = Math.min(34, (chartW / days.length) * 0.5);

  const points = days.map((d, i) => {
    const x = padL + i * stepX;
    const y = padT + chartH - (Math.max(0, Math.min(100, d.score)) / 100) * chartH;
    return { x, y, d };
  });

  const linePath = points.map((p, i) => (i === 0 ? "M" : "L") + p.x + "," + p.y).join(" ");

  const bars = points.map(p => {
    const barH = (padT + chartH) - p.y;
    return `<rect class="trend-bar" x="${p.x - barW / 2}" y="${p.y}" width="${barW}" height="${Math.max(barH, 2)}"
              rx="4" fill="${p.d.color}" opacity="0.35"></rect>`;
  }).join("");

  const dots = points.map(p =>
    `<circle cx="${p.x}" cy="${p.y}" r="4.5" fill="${p.d.color}"></circle>`
  ).join("");

  const labels = points.map(p =>
    `<text x="${p.x}" y="${H - 8}" text-anchor="middle">${p.d.label}</text>`
  ).join("");

  const gridLines = [0, 50, 100].map(v => {
    const y = padT + chartH - (v / 100) * chartH;
    return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
              stroke="var(--line)" stroke-width="1" stroke-dasharray="3,4"></line>`;
  }).join("");

  containerEl.innerHTML = `
    <svg class="trend-chart" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img"
         aria-label="Weekly mood trend chart">
      ${gridLines}
      ${bars}
      <path d="${linePath}" fill="none" stroke="var(--amber)" stroke-width="2.5"
            stroke-linecap="round" stroke-linejoin="round"></path>
      ${dots}
      ${labels}
    </svg>
  `;
}

/**
 * Given a list of entry dates (Date objects, one per journal entry,
 * newest first or in any order), returns the current streak: the
 * number of consecutive calendar days — counting back from today —
 * that have at least one entry. Returns 0 if today has no entry
 * (streak "resets" until they write again).
 */
function calculateStreak(entryDates){
  if (!entryDates || !entryDates.length) return 0;

  const daySet = new Set(
    entryDates.map(d => {
      const dt = new Date(d);
      return `${dt.getFullYear()}-${dt.getMonth()}-${dt.getDate()}`;
    })
  );

  let streak = 0;
  let cursor = new Date();
  const todayKey = `${cursor.getFullYear()}-${cursor.getMonth()}-${cursor.getDate()}`;
  if (!daySet.has(todayKey)) {
    cursor.setDate(cursor.getDate() - 1);
  }

  while (true) {
    const key = `${cursor.getFullYear()}-${cursor.getMonth()}-${cursor.getDate()}`;
    if (daySet.has(key)) {
      streak += 1;
      cursor.setDate(cursor.getDate() - 1);
    } else {
      break;
    }
  }
  return streak;
}