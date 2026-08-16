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

/* ==========================================================
   MindMirror — auth page logic (BACKEND CONNECTED)
   ----------------------------------------------------------
   Login/Register now call the real Flask API:
     POST /api/login    { email, password }
     POST /api/register { name, email, password }

   `credentials: "include"` is required so the browser sends/
   stores the session cookie Flask uses to remember who's
   logged in (current_user() on the backend reads this cookie).

   On success, the backend returns { name, email } and we
   continue the same onboarding flow as before (age.html etc),
   carrying the real name forward.

   On failure (wrong password, duplicate email, etc), the
   backend returns { message: "..." } with a 4xx status — that
   message is shown in the <p id="loginNote">/<p id="registerNote">
   element that already exists in the HTML (just unhidden here).
========================================================== */

const API_BASE = "http://127.0.0.1:5000";

function showAuthError(noteId, message){
  const note = document.getElementById(noteId);
  if (!note) return;
  note.textContent = message;
  note.hidden = false;
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
        credentials: "include", // send/receive the session cookie
        body: JSON.stringify(payload)
      });

      const result = await res.json();

      if (!res.ok){
        // Backend sends e.g. { message: "Incorrect email or password." }
        showAuthError(noteId, result.message || "Something went wrong.");
        return;
      }

      window.location.href = "age.html?user=" + encodeURIComponent(result.name);
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
   OAuth wired up). Leaving as-is; the backend has no route for
   this yet.
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
   age.html + gender.html — short single-select questions shown
   right after login/register, one after another: age.html ->
   gender.html -> index.html. Same pattern as the intent question
   in the onboarding carousel. Nothing is sent to the backend yet
   (no route for saving these answers) — each page just carries
   the ?user= name forward to the next step when Continue is
   pressed.
========================================================== */

function initQuestionPage(optionsId, backId, continueId){
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

  // Carry the ?user= name (if any) forward to the next step.
  const params = new URLSearchParams(window.location.search);
  const userName = params.get("user");
  if (userName){
    const nextUrl = new URL(continueBtn.href, window.location.href);
    nextUrl.searchParams.set("user", userName);
    continueBtn.href = nextUrl.pathname + nextUrl.search;
  }
}

initQuestionPage("ageOptions", "ageBack", "ageContinue");
initQuestionPage("genderOptions", "genderBack", "genderContinue");

/* ==========================================================
   sleep.html — the merged "wake up / bed time" question.
   No pill options here (it's two time pickers), so it just
   needs the back button + carrying ?user= forward to the app.
   The chosen times aren't sent anywhere yet (no backend route
   for them).
========================================================== */

function initSimplePage(backId, continueId){
  const backBtn = document.getElementById(backId);
  const continueBtn = document.getElementById(continueId);
  if (!continueBtn) return;

  if (backBtn){
    backBtn.addEventListener("click", () => window.history.back());
  }

  const params = new URLSearchParams(window.location.search);
  const userName = params.get("user");
  if (userName){
    const nextUrl = new URL(continueBtn.href, window.location.href);
    nextUrl.searchParams.set("user", userName);
    continueBtn.href = nextUrl.pathname + nextUrl.search;
  }
}

initSimplePage("sleepBack", "sleepContinue");

/* ==========================================================
   interests.html — multi-select grid ("choose all that apply").
   Unlike age/gender (single-select), any number of cards can
   be active at once. Selections aren't sent anywhere yet (no
   backend route for them) — Continue just carries ?user=
   forward as usual.
========================================================== */

function initInterestsPage(){
  const grid = document.getElementById("interestsGrid");
  if (!grid) return;

  grid.querySelectorAll(".interest-card").forEach(card => {
    card.addEventListener("click", () => {
      card.classList.toggle("is-selected");
    });
  });

  initSimplePage("interestsBack", "interestsContinue");
}

initInterestsPage();