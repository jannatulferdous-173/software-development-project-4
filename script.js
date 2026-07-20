/* ==========================================================
   MindMirror — frontend logic

   NOTE FOR BACKEND INTEGRATION:
   Replace the body of `analyzeText()` with a real API call to
   your NLP service, e.g.:

     async function analyzeText(text) {
       const res = await fetch("/api/analyze", {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ text })
       });
       return res.json(); // { mood, note, message, emotions:{joy,sadness,anxiety,anger,calm} }
     }

   Until then, a small keyword-based scorer runs locally so the
   UI is fully demoable without a backend.
========================================================== */

/* ==========================================================
   Theme (light/dark) — stored in localStorage so it's
   remembered across pages and future visits. Runs immediately
   (not inside a DOMContentLoaded handler) so the page never
   flashes the wrong theme before JS kicks in.
========================================================== */
(function applyStoredTheme(){
  const saved = localStorage.getItem("mindmirror-theme");
  if (saved === "dark"){
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();

function initThemeToggle(){
  const btn = document.getElementById("themeToggle");
  if (!btn) return;

  const setIcon = () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    btn.textContent = isDark ? "☀️" : "🌙";
  };
  setIcon();

  btn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark){
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("mindmirror-theme", "light");
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("mindmirror-theme", "dark");
    }
    setIcon();
  });
}

initThemeToggle();

const journalInput   = document.getElementById("journalInput");
const wordCountEl    = document.getElementById("wordCount");
const analyzeBtn     = document.getElementById("analyzeBtn");
const clearBtn        = document.getElementById("clearBtn");
const emptyState      = document.getElementById("emptyState");
const resultState     = document.getElementById("resultState");
const emotionBarsList = document.getElementById("emotionBars");
const moodWordEl      = document.getElementById("moodWord");
const moodNoteEl      = document.getElementById("moodNote");
const messageEl       = document.getElementById("reflectionMessage");

/* ---------- lightweight placeholder lexicon ---------- */
const LEXICON = {
  joy:     ["happy","good","glad","great","love","excited","grateful","hope","joy","proud"],
  sadness: ["sad","down","cry","lonely","lost","tired","empty","hurt","heavy","numb"],
  anxiety: ["worried","anxious","afraid","panic","nervous","overthink","stress","scared","overwhelmed","racing"],
  anger:   ["angry","annoyed","furious","irritated","frustrated","mad","resentful"],
  calm:    ["calm","peace","relaxed","rest","safe","steady","fine","okay","grounded","settled"]
};

const EMOTION_META = {
  joy:     { label: "Joy",     color: "var(--amber)" },
  sadness: { label: "Sadness", color: "var(--slate)" },
  anxiety: { label: "Anxiety", color: "var(--plum)"  },
  anger:   { label: "Anger",   color: "var(--rust)"   },
  calm:    { label: "Calm",    color: "var(--moss)"  }
};

const MOOD_COPY = {
  joy:     { word: "Bright",   note: "There's a clear thread of positivity in the writing." },
  sadness: { word: "Heavy",    note: "Something seems to be weighing on you." },
  anxiety: { word: "Unsettled",note: "The thoughts seem to be moving pretty fast." },
  anger:   { word: "Charged",  note: "Something seems to be sitting under the surface." },
  calm:    { word: "Steady",   note: "The tone of the writing feels grounded and slow." },
  mixed:   { word: "Mixed",    note: "A few different feelings are showing up together." }
};

function countWords(text){
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

journalInput.addEventListener("input", () => {
  wordCountEl.textContent = countWords(journalInput.value);
});

/* ==========================================================
   Quick mood check — a manual, single-select tag above the
   textarea. This is INTENTIONALLY separate from analyzeText()
   below: the NLP analysis only ever looks at the written text,
   never at this selection. It's here so the person can note
   their mood at a glance; wiring it into a backend later would
   mean sending `selectedMood` alongside the journal text.
========================================================== */
let selectedMood = null;

(function initMoodPicker(){
  const picker = document.getElementById("moodPicker");
  if (!picker) return;

  const options = Array.from(picker.querySelectorAll(".mood-option"));
  options.forEach(btn => {
    btn.addEventListener("click", () => {
      const alreadySelected = btn.classList.contains("is-selected");
      options.forEach(b => b.classList.remove("is-selected"));
      if (!alreadySelected){
        btn.classList.add("is-selected");
        selectedMood = btn.dataset.mood;
      } else {
        selectedMood = null;
      }
    });
  });
})();

/* ---------- placeholder analysis ---------- */
function analyzeText(text){
  const lower = text.toLowerCase();
  const scores = {};
  let total = 0;

  for (const [emotion, words] of Object.entries(LEXICON)){
    let hits = 0;
    words.forEach(w => {
      const re = new RegExp(w, "gi");
      const matches = lower.match(re);
      if (matches) hits += matches.length;
    });
    scores[emotion] = hits;
    total += hits;
  }

  // fallback so the UI never shows a totally flat result on neutral text
  if (total === 0){
    scores.calm = 1;
    total = 1;
  }

  const percentages = {};
  for (const emotion in scores){
    percentages[emotion] = Math.round((scores[emotion] / total) * 100);
  }

  const sorted = Object.entries(percentages).sort((a,b) => b[1] - a[1]);
  const [topEmotion, topScore] = sorted[0];
  const second = sorted[1];

  const isMixed = second && (topScore - second[1] <= 8) && topScore < 45;
  const moodKey = isMixed ? "mixed" : topEmotion;

  return {
    emotions: percentages,
    mood: MOOD_COPY[moodKey].word,
    note: MOOD_COPY[moodKey].note,
    message: buildMessage(moodKey, countWords(text))
  };
}

function buildMessage(moodKey, wordCount){
  const length = wordCount < 25
    ? "You said a lot in just a few words."
    : "You wrote quite openly — that's a good habit to keep."

  const byMood = {
    joy:     "This feeling is worth holding onto. It might help to notice what brought it on.",
    sadness: "Writing the hard stuff down takes courage. Sharing it with someone you trust could help too.",
    anxiety: "There's a lot circling in your head. Try picking apart one thought at a time.",
    anger:   "Better out than bottled up. It might help to trace where this feeling started.",
    calm:    "There's a steadiness in this writing. Worth holding onto, as much as you can.",
    mixed:   "It's completely normal for several feelings to show up at once."
  };

  return `${byMood[moodKey]} ${length}`;
}

/* ---------- render ---------- */
function renderResult(result){
  moodWordEl.textContent = result.mood;
  moodNoteEl.textContent = result.note;
  messageEl.textContent = result.message;

  emotionBarsList.innerHTML = "";
  const ordered = Object.entries(result.emotions).sort((a,b) => b[1]-a[1]);

  ordered.forEach(([key, value]) => {
    const meta = EMOTION_META[key];
    const li = document.createElement("li");
    li.className = "emotion-bar";
    li.innerHTML = `
      <div class="emotion-bar__row">
        <span>${meta.label}</span>
        <span class="emotion-bar__value">${value}%</span>
      </div>
      <div class="emotion-bar__track">
        <div class="emotion-bar__fill" style="background:${meta.color}"></div>
        <div class="emotion-bar__reflection" style="background:${meta.color}"></div>
      </div>
    `;
    emotionBarsList.appendChild(li);
    requestAnimationFrame(() => {
      li.querySelector(".emotion-bar__fill").style.width = value + "%";
      li.querySelector(".emotion-bar__reflection").style.width = value + "%";
    });
  });

  emptyState.hidden = true;
  resultState.hidden = false;
}

/* ---------- events ---------- */
analyzeBtn.addEventListener("click", () => {
  const text = journalInput.value.trim();
  if (!text){
    journalInput.focus();
    journalInput.classList.add("shake");
    setTimeout(() => journalInput.classList.remove("shake"), 400);
    return;
  }

  analyzeBtn.classList.add("is-rippling");
  setTimeout(() => analyzeBtn.classList.remove("is-rippling"), 650);

  const result = analyzeText(text);
  renderResult(result);
  recordHistoryEntry(text, result);
});

clearBtn.addEventListener("click", () => {
  journalInput.value = "";
  wordCountEl.textContent = "0";
  emptyState.hidden = false;
  resultState.hidden = true;
  journalInput.focus();
});

/* ==========================================================
   Prompt suggestions — for when someone doesn't know where to
   start. Only fills the textarea if it's empty, so it never
   overwrites something already written.
========================================================== */
const WRITING_PROMPTS = [
  "What's taking up the most space in your head right now?",
  "Describe today in three words, then explain why you picked them.",
  "What's something you didn't say out loud today, but wish you had?",
  "Who or what made you feel most like yourself this week?",
  "What's a small thing that helped today, even a little?",
  "If today had a weather forecast, what would it be?",
  "What are you avoiding thinking about right now?",
  "What's one thing you're looking forward to, even if it's small?"
];

const promptBtn = document.getElementById("promptBtn");
if (promptBtn){
  promptBtn.addEventListener("click", () => {
    const prompt = WRITING_PROMPTS[Math.floor(Math.random() * WRITING_PROMPTS.length)];
    if (!journalInput.value.trim()){
      journalInput.value = prompt + "\n\n";
      journalInput.focus();
      journalInput.setSelectionRange(journalInput.value.length, journalInput.value.length);
      wordCountEl.textContent = countWords(journalInput.value);
    }
  });
}

/* ==========================================================
   Case studies — reads CASE_STUDIES from cases-data.js
   Content lives there; this just builds the accordion cards.
========================================================== */

const MOOD_COLOR = {
  joy: "var(--amber)",
  sadness: "var(--slate)",
  anxiety: "var(--plum)",
  anger: "var(--rust)",
  calm: "var(--moss)",
  mixed: "var(--paper)"
};

function renderCaseStudies(){
  const list = document.getElementById("casesList");
  if (!list || typeof CASE_STUDIES === "undefined") return;

  CASE_STUDIES.forEach((item, i) => {
    const color = MOOD_COLOR[item.mood] || "var(--slate)";
    const itemEl = document.createElement("div");
    itemEl.className = "case-item";
    itemEl.style.setProperty("--case-color", color);

    itemEl.innerHTML = `
      <button class="case-item__header" type="button" aria-expanded="false" data-case-index="${i}">
        <span class="case-item__tag">${item.tag}</span>
        <span class="case-item__title">${item.title}</span>
        <span class="case-item__chevron" aria-hidden="true"></span>
      </button>
      <div class="case-item__body-wrap">
        <div class="case-item__body">
          <p class="case-bubble--situation">${item.situation}</p>
          <div class="case-bubble case-bubble--user">${item.userText}</div>
          <div class="case-bubble case-bubble--reflection">
            <span class="case-bubble__badge">${item.moodLabel}</span>
            ${item.reflection}
          </div>
        </div>
      </div>
    `;

    const header = itemEl.querySelector(".case-item__header");
    header.addEventListener("click", () => {
      const isOpen = itemEl.classList.toggle("is-open");
      header.setAttribute("aria-expanded", String(isOpen));
    });

    list.appendChild(itemEl);
  });
}

renderCaseStudies();

/* ==========================================================
   Onboarding carousel
========================================================== */
function initOnboarding(){
  const track = document.getElementById("onboardingTrack");
  const dotsWrap = document.getElementById("onboardingDots");
  const prevBtn = document.getElementById("prevSlide");
  const nextBtn = document.getElementById("nextSlide");
  if (!track || !dotsWrap) return;

  const slides = Array.from(track.querySelectorAll(".slide"));
  let current = 0;

  slides.forEach((_, i) => {
    const dot = document.createElement("span");
    if (i === 0) dot.classList.add("is-active");
    dot.addEventListener("click", () => goTo(i));
    dotsWrap.appendChild(dot);
  });
  const dots = Array.from(dotsWrap.children);

  function update(index){
    current = index;
    dots.forEach((d, i) => d.classList.toggle("is-active", i === index));
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === slides.length - 1;
  }

  function goTo(index){
    slides[index].scrollIntoView({ behavior: "smooth", inline: "start", block: "nearest" });
  }

  prevBtn.addEventListener("click", () => goTo(Math.max(0, current - 1)));
  nextBtn.addEventListener("click", () => goTo(Math.min(slides.length - 1, current + 1)));

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting && entry.intersectionRatio > 0.6){
        update(slides.indexOf(entry.target));
      }
    });
  }, { root: track, threshold: 0.6 });

  slides.forEach(s => observer.observe(s));
  update(0);
}

initOnboarding();

/* ==========================================================
   Intent question ("What brings you here?") — single-select
   toggle. No backend yet, so the choice isn't saved anywhere;
   it's just a visual selection before the person hits Continue.
========================================================== */
function initIntentOptions(){
  const optionsWrap = document.getElementById("intentOptions");
  if (!optionsWrap) return;

  const options = Array.from(optionsWrap.querySelectorAll(".intent-option"));
  options.forEach(btn => {
    btn.addEventListener("click", () => {
      options.forEach(b => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
    });
  });
}

initIntentOptions();

/* ==========================================================
   Guest vs. registered user state
   ----------------------------------------------------------
   No backend yet, so "logged in" just means the URL has a
   ?user=name param (set by auth.js after the login/register
   form is submitted). History is kept in a plain in-memory
   array — it resets on refresh. Once there's a backend, swap
   this for a real session + a fetch() to load/save entries.
========================================================== */

const params = new URLSearchParams(window.location.search);
const userName = params.get("user");
const currentUser = userName ? { name: userName } : null;

function daysAgo(n, hour, minute){
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(hour, minute, 0, 0);
  return d;
}

const journalHistory = [
  {
    fullText: "Felt a bit lighter today after finishing that report. Small win, but it counts.",
    snippet: "Felt a bit lighter today after finishing that report.",
    mood: "Bright",
    moodKey: "joy",
    moodColor: "var(--amber)",
    date: daysAgo(0, 9, 14)
  },
  {
    fullText: "Couldn't stop thinking about the exam tomorrow, chest felt tight the whole evening.",
    snippet: "Couldn't stop thinking about the exam tomorrow, chest felt tight.",
    mood: "Unsettled",
    moodKey: "anxiety",
    moodColor: "var(--plum)",
    date: daysAgo(1, 23, 2)
  },
  {
    fullText: "Quiet day. Made tea, read a bit, didn't talk to anyone and that felt okay for once.",
    snippet: "Quiet day. Made tea, read a bit, didn't talk to anyone.",
    mood: "Steady",
    moodKey: "calm",
    moodColor: "var(--moss)",
    date: daysAgo(2, 20, 40)
  },
  {
    fullText: "Argued with my brother again over something small. Still feel annoyed about it.",
    snippet: "Argued with my brother again over something small.",
    mood: "Charged",
    moodKey: "anger",
    moodColor: "var(--rust)",
    date: daysAgo(3, 18, 5)
  },
  {
    fullText: "Missed my friend a lot today. Called them and just talked for an hour, felt lonely before that.",
    snippet: "Missed my friend a lot today. Called them and just talked.",
    mood: "Heavy",
    moodKey: "sadness",
    moodColor: "var(--slate)",
    date: daysAgo(4, 21, 30)
  }
];

const navGreeting  = document.getElementById("navGreeting");
const navAuthLink  = document.getElementById("navAuthLink");
const historySection = document.getElementById("historySection");
const historyList     = document.getElementById("historyList");
const historyEmpty    = document.getElementById("historyEmpty");

function applyUserState(){
  if (!currentUser) return;

  if (navGreeting){
    navGreeting.textContent = `Hi, ${currentUser.name}`;
    navGreeting.hidden = false;
  }
  if (navAuthLink){
    navAuthLink.textContent = "Log out";
    navAuthLink.href = "index.html";
    navAuthLink.classList.remove("nav__link--cta");
    navAuthLink.classList.add("nav__link--logout");
  }
  if (historySection) historySection.hidden = false;
  renderHistory();
}

function recordHistoryEntry(text, result){
  if (!currentUser || !historyList) return;

  const topEmotionKey = Object.keys(result.emotions)
    .sort((a, b) => result.emotions[b] - result.emotions[a])[0];

  // MOOD_COPY maps keys ("joy","sadness",...,"mixed") to display words
  // ("Bright","Heavy",...,"Mixed"); reverse that to store the key, not
  // just the word, so charting/export logic has something consistent
  // to work with regardless of which word is shown.
  const moodKey = Object.keys(MOOD_COPY).find(key => MOOD_COPY[key].word === result.mood) || topEmotionKey;

  journalHistory.unshift({
    fullText: text,
    snippet: text.length > 60 ? text.slice(0, 60) + "…" : text,
    mood: result.mood,
    moodKey: moodKey,
    moodColor: (EMOTION_META[topEmotionKey] && EMOTION_META[topEmotionKey].color) || "var(--slate)",
    date: new Date()
  });

  renderHistory();
}

function formatEntryTime(date){
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();

  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (isToday) return time;
  if (isYesterday) return `Yesterday, ${time}`;
  return date.toLocaleDateString([], { month: "short", day: "numeric" }) + `, ${time}`;
}

function renderHistory(){
  if (!historyList) return;
  if (historyEmpty) historyEmpty.hidden = journalHistory.length > 0;

  historyList.querySelectorAll(".history__item").forEach(el => el.remove());

  journalHistory.forEach((entry, i) => {
    const li = document.createElement("li");
    li.className = "history__item";
    li.style.setProperty("--h-color", entry.moodColor);
    li.innerHTML = `
      <span class="history__item__mood">${entry.mood}</span>
      <span class="history__item__snippet">${entry.snippet}</span>
      <span class="history__item__time">${formatEntryTime(entry.date)}</span>
      <button type="button" class="history__item__download" data-entry-index="${i}" aria-label="Download this entry" title="Download">⬇</button>
    `;
    li.querySelector(".history__item__download").addEventListener("click", () => downloadEntry(entry));
    historyList.appendChild(li);
  });

  renderStreak();
  renderMoodChart();
  renderWordCloud();
}

/* ==========================================================
   Export/Download — turns one history entry into a plain .txt
   file the browser downloads. No backend needed: build a Blob
   in memory and trigger a download via a throwaway <a> link.
========================================================== */
function downloadEntry(entry){
  const dateLabel = entry.date.toLocaleString([], {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit"
  });

  const content =
`MindMirror journal entry
${dateLabel}
Mood: ${entry.mood}

${entry.fullText}
`;

  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mindmirror-entry-${entry.date.toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/* ==========================================================
   Streak counter — counts consecutive calendar days (going
   backward from today) that have at least one journal entry.
   Purely derived from journalHistory, no separate tracking.
========================================================== */

const streakBadge = document.getElementById("streakBadge");
const streakCountEl = document.getElementById("streakCount");

function calculateStreak(){
  if (journalHistory.length === 0) return 0;

  const entryDays = new Set(
    journalHistory.map(entry => entry.date.toDateString())
  );

  let streak = 0;
  const cursor = new Date();
  cursor.setHours(0, 0, 0, 0);

  while (entryDays.has(cursor.toDateString())){
    streak++;
    cursor.setDate(cursor.getDate() - 1);
  }

  return streak;
}

function renderStreak(){
  if (!streakBadge || !streakCountEl) return;
  const streak = calculateStreak();
  streakBadge.hidden = streak === 0;
  streakCountEl.textContent = streak;
}

/* ==========================================================
   Mood trend chart — a small hand-built SVG line chart of the
   last 7 days (no chart library). Each mood word maps to a
   rough valence number so multiple moods can sit on one axis:
   very negative (sadness) to very positive (joy).
========================================================== */
const MOOD_VALENCE = { joy: 2, calm: 1, mixed: 0, anxiety: -1, anger: -1.5, sadness: -2 };

function renderMoodChart(){
  const svg = document.getElementById("moodChartSvg");
  const axis = document.getElementById("moodChartAxis");
  if (!svg || !axis) return;

  const days = [];
  for (let i = 6; i >= 0; i--){
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - i);
    days.push(d);
  }

  const width = 700, height = 180, marginX = 40, marginTop = 20, marginBottom = 30;
  const usableHeight = height - marginTop - marginBottom;
  const stepX = (width - marginX * 2) / 6;
  const valenceToY = v => marginTop + (1 - (v + 2) / 4) * usableHeight;

  const points = [];
  days.forEach((day, i) => {
    const dayEntries = journalHistory.filter(e => e.date.toDateString() === day.toDateString());
    if (dayEntries.length === 0) return;
    const avgValence = dayEntries.reduce((sum, e) => sum + (MOOD_VALENCE[e.moodKey] ?? 0), 0) / dayEntries.length;
    points.push({ x: marginX + stepX * i, y: valenceToY(avgValence), color: dayEntries[0].moodColor });
  });

  const neutralY = valenceToY(0);
  let svgContent = `<line x1="${marginX}" y1="${neutralY}" x2="${width - marginX}" y2="${neutralY}" stroke="rgba(var(--ink-rgb),.15)" stroke-dasharray="4 4" />`;

  if (points.length > 1){
    const linePoints = points.map(p => `${p.x},${p.y}`).join(" ");
    svgContent += `<polyline points="${linePoints}" fill="none" stroke="rgb(var(--ink-rgb))" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" opacity="0.35" />`;
  }
  points.forEach(p => {
    svgContent += `<circle cx="${p.x}" cy="${p.y}" r="6" fill="${p.color}" stroke="var(--paper)" stroke-width="2" />`;
  });

  svg.innerHTML = svgContent;
  axis.innerHTML = days.map(d => `<span>${d.toLocaleDateString([], { weekday: "short" })}</span>`).join("");
}

/* ==========================================================
   Word cloud — most-used words across all saved entries, sized
   by frequency. A small stopword list filters out filler words
   so what's left actually says something about the writing.
========================================================== */
const STOPWORDS = new Set([
  "the","a","an","and","or","but","is","are","was","were","am","be","been","being",
  "to","of","in","on","at","for","with","about","today","felt","feel","feeling",
  "that","this","its","just","still","not","no","so","very","really","much",
  "more","than","then","there","here","what","who","which","when","where","why",
  "how","again","also","if","because","as","by","from","up","down","out","over",
  "under","after","before","while","all","some","can","could","would","should",
  "will","did","do","does","have","has","had","dont","didnt","couldnt","wasnt",
  "werent","thats","and","one","get","got","like"
]);

function renderWordCloud(){
  const wrap = document.getElementById("wordCloudWords");
  if (!wrap) return;

  const counts = {};
  journalHistory.forEach(entry => {
    const words = entry.fullText.toLowerCase().match(/[a-z']+/g) || [];
    words.forEach(w => {
      if (w.length < 3 || STOPWORDS.has(w)) return;
      counts[w] = (counts[w] || 0) + 1;
    });
  });

  const top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
  if (top.length === 0){
    wrap.innerHTML = `<span class="word-cloud__empty">Not enough writing yet to spot patterns.</span>`;
    return;
  }

  const maxCount = top[0][1];
  wrap.innerHTML = top.map(([word, count]) => {
    const size = (0.85 + (count / maxCount) * 1.15).toFixed(2);
    return `<span class="word-cloud__word" style="font-size:${size}rem">${word}</span>`;
  }).join(" ");
}

/* ==========================================================
   Breathing exercise — a simple guided in/hold/out cycle.
   The circle's scale transition is CSS-driven (4s ease-in-out)
   so this JS only needs to toggle a class and swap the label
   text in step with it.
========================================================== */
(function initBreathing(){
  const circle = document.getElementById("breathingCircle");
  const text = document.getElementById("breathingText");
  const toggleBtn = document.getElementById("breathingToggle");
  if (!circle || !text || !toggleBtn) return;

  const PHASES = [
    { label: "Breathe in", duration: 4000, className: "is-inhale" },
    { label: "Hold",       duration: 4000, className: "is-hold" },
    { label: "Breathe out", duration: 4000, className: "is-exhale" }
  ];
  let phaseIndex = 0;
  let timer = null;

  function runPhase(){
    const phase = PHASES[phaseIndex];
    text.textContent = phase.label;
    circle.className = "breathing__circle " + phase.className;
    phaseIndex = (phaseIndex + 1) % PHASES.length;
    timer = setTimeout(runPhase, phase.duration);
  }

  function start(){
    phaseIndex = 0;
    runPhase();
    toggleBtn.textContent = "Stop";
  }

  function stop(){
    clearTimeout(timer);
    timer = null;
    circle.className = "breathing__circle";
    text.textContent = "Start";
    toggleBtn.textContent = "Begin";
  }

  toggleBtn.addEventListener("click", () => {
    if (timer) stop(); else start();
  });
})();

applyUserState();