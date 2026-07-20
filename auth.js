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
   MindMirror — auth page logic
   ----------------------------------------------------------
   There's still no real backend, so this can't check a real
   password or create a real account. What it does instead:
   on submit, it treats the form as "successful" and sends the
   person to age.html (the age-group question) with their name
   in the URL. age.html then forwards that name into index.html,
   which is how index.html knows to show them as a registered
   user for this session.

   WHEN A BACKEND EXISTS, replace the body of handleAuthSubmit()
   with a real call, e.g.:

     const res = await fetch("/api/login", {
       method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({ email, password })
     });
     const data = await res.json();
     if (!res.ok) { showError(data.message); return; }
     window.location.href = "age.html?user=" + encodeURIComponent(data.name);

   and store a real session (cookie / token) instead of a URL param.
========================================================== */

function handleAuthSubmit(formId, nameFieldName){
  const form = document.getElementById(formId);
  if (!form) return;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const data = new FormData(form);
    const rawName = (data.get(nameFieldName) || "").toString().trim();
    // Login form has no "name" field, so fall back to the email's first part.
    const displayName = rawName || (data.get("email") || "").toString().split("@")[0] || "friend";

    window.location.href = "age.html?user=" + encodeURIComponent(displayName);
  });
}

handleAuthSubmit("loginForm", "name");
handleAuthSubmit("registerForm", "name");

/* ==========================================================
   "Continue with Google" — also fake for now, same reason as
   above: there's no backend to run real OAuth against. This
   just sends the person in as a generic "Google user" so the
   button feels complete during design/demo.

   WHEN A BACKEND EXISTS, replace this with real Google OAuth
   (e.g. Google Identity Services), then redirect using the
   name Google returns instead of the hardcoded one below.
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
   in the onboarding carousel. Nothing is sent anywhere yet (no
   backend) — each page just carries the ?user= name forward to
   the next step when Continue is pressed.
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
   The chosen times aren't sent anywhere yet (no backend).
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
   backend) — Continue just carries ?user= forward as usual.
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