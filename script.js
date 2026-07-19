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

const journalHistory = [];

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
}

function recordHistoryEntry(text, result){
  if (!currentUser || !historyList) return;

  const topEmotionKey = Object.keys(result.emotions)
    .sort((a, b) => result.emotions[b] - result.emotions[a])[0];

  journalHistory.unshift({
    snippet: text.length > 60 ? text.slice(0, 60) + "…" : text,
    mood: result.mood,
    moodColor: (EMOTION_META[topEmotionKey] && EMOTION_META[topEmotionKey].color) || "var(--slate)",
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  });

  renderHistory();
}

function renderHistory(){
  if (!historyList) return;
  if (historyEmpty) historyEmpty.hidden = journalHistory.length > 0;

  historyList.querySelectorAll(".history__item").forEach(el => el.remove());

  journalHistory.forEach(entry => {
    const li = document.createElement("li");
    li.className = "history__item";
    li.style.setProperty("--h-color", entry.moodColor);
    li.innerHTML = `
      <span class="history__item__mood">${entry.mood}</span>
      <span class="history__item__snippet">${entry.snippet}</span>
      <span class="history__item__time">${entry.time}</span>
    `;
    historyList.appendChild(li);
  });
}

applyUserState();

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
