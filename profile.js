/* ==========================================================
   MindMirror — profile.js
   ----------------------------------------------------------
   Powers profile.html: fetches GET /api/profile (name, email,
   onboarding answers, full journal history) in one request,
   then renders the profile card, the mood trend chart (reusing
   mood-trend.js, already loaded by profile.html), and the
   history list — all using the profile-* classes already
   defined in style.css.
========================================================== */

/* ---------- theme (light/dark), same behavior as script.js ---------- */
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

const API_BASE = "http://127.0.0.1:5000";

/* ---------- element refs ---------- */
const profileLoading    = document.getElementById("profileLoading");
const profileError      = document.getElementById("profileError");
const profileContent    = document.getElementById("profileContent");

const profileAvatar     = document.getElementById("profileAvatar");
const profileName       = document.getElementById("profileName");
const profileEmail      = document.getElementById("profileEmail");
const profileAge        = document.getElementById("profileAge");
const profileGender     = document.getElementById("profileGender");
const profileWake       = document.getElementById("profileWake");
const profileBed        = document.getElementById("profileBed");
const profileInterests  = document.getElementById("profileInterests");
const profileInterestsEmpty = document.getElementById("profileInterestsEmpty");
const profileEntryCount = document.getElementById("profileEntryCount");
const profileMemberSince = document.getElementById("profileMemberSince");
const profileTrendChart = document.getElementById("profileTrendChart");
const profileHistoryList = document.getElementById("profileHistoryList");
const profileEmptyState  = document.getElementById("profileEmptyState");

/* ---------- small formatting helpers ---------- */

// "07:30" -> "7:30 AM" — the sleep-time inputs on sleep.html save a
// plain 24-hour HH:MM value; this makes it read naturally elsewhere.
function formatTime12hr(value){
  if (!value) return "—";
  const [hStr, mStr] = value.split(":");
  let h = parseInt(hStr, 10);
  const period = h >= 12 ? "PM" : "AM";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${mStr} ${period}`;
}

function formatMemberSince(isoString){
  if (!isoString) return "";
  const d = new Date(isoString);
  return "Since " + d.toLocaleDateString([], { month: "short", year: "numeric" });
}

function formatEntryDate(isoString){
  const d = new Date(isoString);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  const isYesterday = d.toDateString() === yesterday.toDateString();

  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (isToday) return `Today, ${time}`;
  if (isYesterday) return `Yesterday, ${time}`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) + `, ${time}`;
}

/* ---------- render: profile card ---------- */
function renderProfileCard(profile){
  profileAvatar.textContent = (profile.name || "?").trim().charAt(0).toUpperCase();
  profileName.textContent = profile.name || "—";
  profileEmail.textContent = profile.email || "—";

  profileAge.textContent = profile.age_group || "Not set";
  profileGender.textContent = profile.gender || "Not set";
  profileWake.textContent = formatTime12hr(profile.wake_time);
  profileBed.textContent = formatTime12hr(profile.bed_time);

  const interests = profile.interests || [];
  if (interests.length){
    profileInterestsEmpty.hidden = true;
    interests.forEach(name => {
      const span = document.createElement("span");
      span.className = "profile-interest";
      span.textContent = name;
      profileInterests.appendChild(span);
    });
  } else {
    profileInterestsEmpty.hidden = false;
  }

  profileEntryCount.textContent = profile.entry_count || 0;
  profileMemberSince.textContent = formatMemberSince(profile.member_since);
}

/* ---------- render: mood trend chart (last 7 days) ----------
   Reuses renderMoodTrendChart() + MOOD_VALENCE from mood-trend.js
   (already loaded by profile.html). Builds one averaged point per
   of the last 7 calendar days from the entries the backend sent. */
function renderTrend(entries){
  if (!profileTrendChart || typeof renderMoodTrendChart !== "function") return;

  const days = [];
  for (let i = 6; i >= 0; i--){
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    d.setDate(d.getDate() - i);
    days.push(d);
  }

  const dayPoints = days.map(day => {
    const dayEntries = entries.filter(e => new Date(e.created_at).toDateString() === day.toDateString());
    const label = day.toLocaleDateString([], { weekday: "short" });
    if (!dayEntries.length){
      return { label, score: 0, color: "var(--line)", mood: null };
    }
    const scored = dayEntries.map(e => (MOOD_VALENCE[e.mood] || { score: 50 }).score);
    const avgScore = Math.round(scored.reduce((a, b) => a + b, 0) / scored.length);
    const lastMood = dayEntries[0].mood;
    const color = (MOOD_VALENCE[lastMood] || {}).color || "var(--slate)";
    return { label, score: avgScore, color, mood: lastMood };
  });

  renderMoodTrendChart(profileTrendChart, dayPoints);
}

/* ---------- render: history list ---------- */
function renderHistoryList(entries){
  profileHistoryList.innerHTML = "";

  if (!entries.length){
    profileEmptyState.hidden = false;
    profileHistoryList.hidden = true;
    return;
  }

  profileEmptyState.hidden = true;
  profileHistoryList.hidden = false;

  entries.forEach(e => {
    const li = document.createElement("div");
    li.className = "profile-history__item";
    li.innerHTML = `
      <span class="profile-history__mood">${e.mood}</span>
      <div class="profile-history__content">
        <p class="profile-history__text">${e.text}</p>
        <span class="profile-history__date">${formatEntryDate(e.created_at)}</span>
      </div>
    `;
    profileHistoryList.appendChild(li);
  });
}

/* ---------- load ---------- */
async function loadProfile(){
  try {
    const res = await fetch(`${API_BASE}/api/profile`, { credentials: "include" });

    if (!res.ok){
      profileLoading.hidden = true;
      profileError.hidden = false;
      return;
    }

    const profile = await res.json();
    const entries = profile.entries || [];

    renderProfileCard(profile);
    renderTrend(entries);
    renderHistoryList(entries);

    profileLoading.hidden = true;
    profileContent.hidden = false;
  } catch (err){
    // Backend unreachable (e.g. Flask isn't running).
    profileLoading.hidden = true;
    profileError.hidden = false;
  }
}

loadProfile();

/* ---------- logout ---------- */
const profileLogoutBtn = document.getElementById("profileLogout");
if (profileLogoutBtn){
  profileLogoutBtn.addEventListener("click", async () => {
    try {
      await fetch(`${API_BASE}/api/logout`, { method: "POST", credentials: "include" });
    } catch (err){
      // Even if the request fails, still send them back to the
      // homepage — there's nothing else useful to do here.
    }
    window.location.href = "index.html";
  });
}
