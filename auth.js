/* ==========================================================
   MindMirror — auth page logic
   ----------------------------------------------------------
   Theme note: the actual toggle button only lives in index.html's
   nav, but this line keeps login/register/age/gender/sleep/
   interests pages in the theme the person last picked, since
   they all load this same script.js.
========================================================== */
(function applyStoredTheme(){
  const saved = localStorage.getItem("mindmirror-theme");
  if (saved === "dark"){
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();

const API_BASE = "http://127.0.0.1:5000";

/* ==========================================================
   Onboarding draft — age.html, gender.html, sleep.html and
   interests.html are separate page loads, so a plain JS variable
   can't survive from one to the next. sessionStorage does (it's
   cleared when the tab closes, which is fine — we don't need it
   after the answers are saved to the backend anyway).
========================================================== */
const ONBOARDING_KEY = "mindmirror-onboarding-draft";

function getOnboardingDraft(){
  try {
    return JSON.parse(sessionStorage.getItem(ONBOARDING_KEY)) || {};
  } catch (err) {
    return {};
  }
}

function saveOnboardingDraft(partial){
  const data = getOnboardingDraft();
  Object.assign(data, partial);
  sessionStorage.setItem(ONBOARDING_KEY, JSON.stringify(data));
}

/* Carries the ?user= name (and any #hash, like #app) from the
   current page's URL onto the Continue button's target link. */
function carryUserParam(continueBtn){
  const params = new URLSearchParams(window.location.search);
  const userName = params.get("user");
  if (!userName) return;

  const nextUrl = new URL(continueBtn.href, window.location.href);
  nextUrl.searchParams.set("user", userName);
  continueBtn.href = nextUrl.pathname + nextUrl.search + nextUrl.hash;
}

/* ==========================================================
   Login / Register (BACKEND CONNECTED)
   ----------------------------------------------------------
   POST /api/login    { email, password }
   POST /api/register { name, email, password }

   `credentials: "include"` sends/stores the session cookie
   Flask uses to remember who's logged in.

   The backend now also returns `onboarded: true/false` — true
   if this user already answered age/gender/sleep/interests
   before. That decides where we send them next:
     onboarded=true  -> straight into the app (index.html#app)
     onboarded=false -> the age/gender/sleep/interests flow
========================================================== */

function showAuthError(noteId, message){
  const note = document.getElementById(noteId);
  if (!note) return;
  note.textContent = message;
  note.hidden = false;
}

function goToNextStep(result){
  const name = encodeURIComponent(result.name);
  if (result.onboarded){
    window.location.href = "index.html?user=" + name + "#app";
  } else {
    window.location.href = "age.html?user=" + name;
  }
}

function handleAuthSubmit(formId, endpoint, noteId){
  const form = document.getElementById(formId);
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const note = document.getElementById(noteId);
    if (note) note.hidden = true; // clear any previous error

    const data = new FormData(form);
    const payload = {
      name: (data.get("name") || "").toString().trim(),
      email: (data.get("email") || "").toString().trim(),
      password: (data.get("password") || "").toString()
    };

    // Register-only client-side check before even calling the backend.
    if (formId === "registerForm"){
      const confirmPassword = (data.get("confirmPassword") || "").toString();
      if (payload.password !== confirmPassword){
        showAuthError(noteId, "Passwords don't match.");
        return;
      }
    }

    try {
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload)
      });

      const result = await res.json();

      if (!res.ok){
        showAuthError(noteId, result.message || "Something went wrong.");
        return;
      }

      goToNextStep(result);
    } catch (err){
      // Usually means the Flask server isn't running.
      showAuthError(noteId, "Couldn't reach the server. Is the backend running?");
    }
  });
}

handleAuthSubmit("loginForm", "/api/login", "loginNote");
handleAuthSubmit("registerForm", "/api/register", "registerNote");

/* ==========================================================
   "Continue with Google" — still fake for now (no real Google
   OAuth wired up, no backend route for it). Always sends the
   person through the onboarding flow since there's no real
   account behind it to check an `onboarded` status for.
========================================================== */

function handleGoogleButton(buttonId){
  const btn = document.getElementById(buttonId);
  if (!btn) return;

  btn.addEventListener("click", () => {
    window.location.href = "age.html?user=" + encodeURIComponent("Google user");
  });
}

handleGoogleButton("googleLoginBtn");
handleGoogleButton("googleRegisterBtn");

/* ==========================================================
   age.html + gender.html — single-select questions. On Continue,
   the selected option is saved into the onboarding draft
   (sessionStorage) before moving to the next page — it isn't
   sent to the backend yet, that happens all at once at the end
   of interests.html.
========================================================== */

function initQuestionPage(optionsId, backId, continueId, fieldKey){
  const optionsWrap = document.getElementById(optionsId);
  const backBtn = document.getElementById(backId);
  const continueBtn = document.getElementById(continueId);
  if (!optionsWrap || !continueBtn) return;

  const options = Array.from(optionsWrap.querySelectorAll(".intent-option"));
  options.forEach(btn => {
    btn.addEventListener("click", () => {
      options.forEach(b => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");
    });
  });

  if (backBtn){
    backBtn.addEventListener("click", () => window.history.back());
  }

  continueBtn.addEventListener("click", () => {
    const selected = options.find(b => b.classList.contains("is-selected"));
    if (selected){
      saveOnboardingDraft({ [fieldKey]: selected.textContent.trim() });
    }
  });

  carryUserParam(continueBtn);
}

initQuestionPage("ageOptions", "ageBack", "ageContinue", "ageGroup");
initQuestionPage("genderOptions", "genderBack", "genderContinue", "gender");

/* ==========================================================
   sleep.html — two time pickers instead of pill options. Same
   idea: save the chosen times into the draft on Continue.
========================================================== */

function initSleepPage(backId, continueId, wakeId, bedId){
  const backBtn = document.getElementById(backId);
  const continueBtn = document.getElementById(continueId);
  const wakeInput = document.getElementById(wakeId);
  const bedInput = document.getElementById(bedId);
  if (!continueBtn) return;

  if (backBtn){
    backBtn.addEventListener("click", () => window.history.back());
  }

  continueBtn.addEventListener("click", () => {
    saveOnboardingDraft({
      wakeTime: wakeInput ? wakeInput.value : null,
      bedTime: bedInput ? bedInput.value : null
    });
  });

  carryUserParam(continueBtn);
}

initSleepPage("sleepBack", "sleepContinue", "wakeTime", "bedTime");

/* ==========================================================
   interests.html — multi-select grid, and the LAST onboarding
   step. On Continue: gather the selected interests, merge them
   into the draft built up on the previous pages, POST the whole
   thing to /api/onboarding (this is where it actually gets
   saved to the database), then navigate to the app.

   preventDefault() + a manual redirect afterward is needed here
   (unlike the earlier steps) because we have to wait for the
   save to finish before it's safe to leave the page.
========================================================== */

function initInterestsPage(){
  const grid = document.getElementById("interestsGrid");
  const backBtn = document.getElementById("interestsBack");
  const continueBtn = document.getElementById("interestsContinue");
  if (!grid || !continueBtn) return;

  const cards = Array.from(grid.querySelectorAll(".interest-card"));
  cards.forEach(card => {
    card.addEventListener("click", () => {
      card.classList.toggle("is-selected");
    });
  });

  if (backBtn){
    backBtn.addEventListener("click", () => window.history.back());
  }

  carryUserParam(continueBtn);

  continueBtn.addEventListener("click", async (e) => {
    e.preventDefault();

    const interests = cards
      .filter(c => c.classList.contains("is-selected"))
      .map(c => c.querySelector(".interest-card__label").textContent.trim());

    const draft = getOnboardingDraft();
    draft.interests = interests;

    try {
      await fetch(`${API_BASE}/api/onboarding`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(draft)
      });
      sessionStorage.removeItem(ONBOARDING_KEY);
    } catch (err){
      // Backend unreachable — still let them into the app rather
      // than getting stuck; the answers just won't be saved.
    }

    window.location.href = continueBtn.href;
  });
}

initInterestsPage();
