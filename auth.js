/* ==========================================================
   MindMirror — auth.js
========================================================== */

const API_BASE = "http://127.0.0.1:5000";

const ONBOARDING_KEY = "mindmirror-onboarding-draft";

/* ==========================================================
   THEME
========================================================== */

(function applyStoredTheme() {
  const saved = localStorage.getItem("mindmirror-theme");

  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();


/* ==========================================================
   ONBOARDING DRAFT
========================================================== */

function getOnboardingDraft() {
  try {
    return JSON.parse(
      sessionStorage.getItem(ONBOARDING_KEY)
    ) || {};
  } catch (error) {
    return {};
  }
}


function saveOnboardingDraft(partialData) {

  const currentData = getOnboardingDraft();

  Object.assign(currentData, partialData);

  sessionStorage.setItem(
    ONBOARDING_KEY,
    JSON.stringify(currentData)
  );
}


/* ==========================================================
   USER PARAMETER
========================================================== */

function carryUserParam(button) {

  if (!button) return;

  const params = new URLSearchParams(
    window.location.search
  );

  const user = params.get("user");

  if (!user) return;

  const nextURL = new URL(
    button.href,
    window.location.href
  );

  nextURL.searchParams.set("user", user);

  button.href =
    nextURL.pathname +
    nextURL.search +
    nextURL.hash;
}


/* ==========================================================
   GOOGLE LOGIN
========================================================== */

const GOOGLE_CLIENT_ID =
  "273728656708-4airnra74qebgsnp6oknuedo72qq85hd.apps.googleusercontent.com";


function initGoogleSignIn() {

  if (
    !window.google ||
    !window.google.accounts
  ) {
    return;
  }

  const loginButton =
    document.getElementById("googleLoginBtn");

  const registerButton =
    document.getElementById("googleRegisterBtn");


  if (!loginButton && !registerButton) {
    return;
  }


  google.accounts.id.initialize({

    client_id: GOOGLE_CLIENT_ID,

    callback: handleGoogleCredentialResponse

  });


  if (loginButton) {

    google.accounts.id.renderButton(
      loginButton,
      {
        theme: "outline",
        size: "large",
        width: 320,
        text: "continue_with"
      }
    );

  }


  if (registerButton) {

    google.accounts.id.renderButton(
      registerButton,
      {
        theme: "outline",
        size: "large",
        width: 320,
        text: "continue_with"
      }
    );

  }

}


async function handleGoogleCredentialResponse(response) {

  try {

    const res = await fetch(
      `${API_BASE}/api/auth/google`,
      {
        method: "POST",

        headers: {
          "Content-Type": "application/json"
        },

        credentials: "include",

        body: JSON.stringify({
          credential: response.credential
        })
      }
    );


    const data = await res.json();


    if (!res.ok) {

      alert(
        data.message ||
        "Google login failed."
      );

      return;
    }


    goToNextStep(data);


  } catch (error) {

    console.error(error);

    alert(
      "Could not reach the server."
    );

  }

}


/* Wait for Google script */

function waitForGoogleAndInit() {

  if (
    window.google &&
    window.google.accounts
  ) {

    initGoogleSignIn();

  } else {

    setTimeout(
      waitForGoogleAndInit,
      100
    );

  }

}


/* ==========================================================
   AUTH ERROR
========================================================== */

function showAuthError(
  noteId,
  message
) {

  const note =
    document.getElementById(noteId);

  if (!note) return;

  note.textContent = message;

  note.hidden = false;
}


/* ==========================================================
   AFTER LOGIN / REGISTER
========================================================== */

function goToNextStep(result) {

  const name =
    encodeURIComponent(
      result.name || ""
    );


  if (result.onboarded) {

    window.location.href =
      "index.html?user=" +
      name +
      "#app";

  } else {

    window.location.href =
      "age.html?user=" +
      name;

  }

}


/* ==========================================================
   LOGIN / REGISTER FORM
========================================================== */

function handleAuthSubmit(
  formId,
  endpoint,
  noteId
) {

  const form =
    document.getElementById(formId);

  if (!form) return;


  form.addEventListener(
    "submit",
    async function (event) {

      event.preventDefault();


      const note =
        document.getElementById(noteId);

      if (note) {
        note.hidden = true;
      }


      const formData =
        new FormData(form);


      const payload = {

        name:
          (formData.get("name") || "")
            .toString()
            .trim(),

        email:
          (formData.get("email") || "")
            .toString()
            .trim(),

        password:
          (formData.get("password") || "")
            .toString()

      };


      /* Register password confirmation */

      if (formId === "registerForm") {

        const confirmPassword =
          (
            formData.get(
              "confirmPassword"
            ) || ""
          ).toString();


        if (
          payload.password !==
          confirmPassword
        ) {

          showAuthError(
            noteId,
            "Passwords don't match."
          );

          return;
        }

      }


      try {

        const res =
          await fetch(
            `${API_BASE}${endpoint}`,
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              credentials: "include",

              body:
                JSON.stringify(payload)
            }
          );


        const result =
          await res.json();


        if (!res.ok) {

          showAuthError(
            noteId,
            result.message ||
              "Something went wrong."
          );

          return;
        }


        goToNextStep(result);


      } catch (error) {

        console.error(error);

        showAuthError(
          noteId,
          "Couldn't reach the server. Is the backend running?"
        );

      }

    }
  );

}


/* Initialize login */

handleAuthSubmit(
  "loginForm",
  "/api/login",
  "loginNote"
);


/* Initialize register */

handleAuthSubmit(
  "registerForm",
  "/api/register",
  "registerNote"
);


/* ==========================================================
   AGE + GENDER
========================================================== */

function initQuestionPage(
  optionsId,
  backId,
  continueId,
  fieldKey
) {

  const optionsWrap =
    document.getElementById(optionsId);

  const backButton =
    document.getElementById(backId);

  const continueButton =
    document.getElementById(continueId);


  if (
    !optionsWrap ||
    !continueButton
  ) {
    return;
  }


  const options =
    Array.from(
      optionsWrap.querySelectorAll(
        ".intent-option"
      )
    );


  /* Select option */

  options.forEach(
    function (button) {

      button.addEventListener(
        "click",
        function () {

          options.forEach(
            function (item) {

              item.classList.remove(
                "is-selected"
              );

            }
          );


          button.classList.add(
            "is-selected"
          );

        }
      );

    }
  );


  /* Back */

  if (backButton) {

    backButton.addEventListener(
      "click",
      function () {

        window.history.back();

      }
    );

  }


  /* Continue */

  continueButton.addEventListener(
    "click",
    function () {

      const selected =
        options.find(
          function (button) {

            return button.classList.contains(
              "is-selected"
            );

          }
        );


      if (selected) {

        saveOnboardingDraft({

          [fieldKey]:
            selected.textContent.trim()

        });

      }

    }
  );


  carryUserParam(
    continueButton
  );

}


/* AGE */

initQuestionPage(
  "ageOptions",
  "ageBack",
  "ageContinue",
  "ageGroup"
);


/* GENDER */

initQuestionPage(
  "genderOptions",
  "genderBack",
  "genderContinue",
  "gender"
);


/* ==========================================================
   SLEEP
========================================================== */

function initSleepPage() {

  const backButton =
    document.getElementById(
      "sleepBack"
    );

  const continueButton =
    document.getElementById(
      "sleepContinue"
    );

  const wakeInput =
    document.getElementById(
      "wakeTime"
    );

  const bedInput =
    document.getElementById(
      "bedTime"
    );


  if (!continueButton) {
    return;
  }


  /* Back */

  if (backButton) {

    backButton.addEventListener(
      "click",
      function () {

        window.history.back();

      }
    );

  }


  /* Save sleep data */

  continueButton.addEventListener(
    "click",
    function () {

      saveOnboardingDraft({

        wakeTime:
          wakeInput
            ? wakeInput.value
            : null,

        bedTime:
          bedInput
            ? bedInput.value
            : null

      });

    }
  );


  carryUserParam(
    continueButton
  );

}


initSleepPage();


/* ==========================================================
   INTERESTS
========================================================== */

function initInterestsPage() {

  const grid =
    document.getElementById(
      "interestsGrid"
    );

  const backButton =
    document.getElementById(
      "interestsBack"
    );

  const continueButton =
    document.getElementById(
      "interestsContinue"
    );


  if (
    !grid ||
    !continueButton
  ) {
    return;
  }


  const cards =
    Array.from(
      grid.querySelectorAll(
        ".interest-card"
      )
    );


  /* Select / unselect interests */

  cards.forEach(
    function (card) {

      card.addEventListener(
        "click",
        function () {

          card.classList.toggle(
            "is-selected"
          );

        }
      );

    }
  );


  /* Back */

  if (backButton) {

    backButton.addEventListener(
      "click",
      function () {

        window.history.back();

      }
    );

  }


  carryUserParam(
    continueButton
  );


  /* Final onboarding save */

  continueButton.addEventListener(
    "click",
    async function (event) {

      event.preventDefault();


      const interests =
        cards
          .filter(
            function (card) {

              return card.classList.contains(
                "is-selected"
              );

            }
          )
          .map(
            function (card) {

              const label =
                card.querySelector(
                  ".interest-card__label"
                );

              return label
                ? label.textContent.trim()
                : "";

            }
          )
          .filter(Boolean);


      const draft =
        getOnboardingDraft();


      draft.interests =
        interests;


      try {

        const res =
          await fetch(
            `${API_BASE}/api/onboarding`,
            {
              method: "POST",

              headers: {
                "Content-Type":
                  "application/json"
              },

              credentials: "include",

              body:
                JSON.stringify(draft)
            }
          );


        if (!res.ok) {

          console.warn(
            "Onboarding save failed:",
            await res.text()
          );

        } else {

          /* Successfully saved */

          sessionStorage.removeItem(
            ONBOARDING_KEY
          );

        }


      } catch (error) {

        console.error(
          "Could not save onboarding:",
          error
        );

      }


      /* Go to app */

      window.location.href =
        continueButton.href;

    }
  );

}


initInterestsPage();


/* ==========================================================
   PROFILE NAVIGATION
========================================================== */

async function initProfileNavLink() {

  const profileLink =
    document.getElementById(
      "navProfileLink"
    );


  if (!profileLink) {
    return;
  }


  try {

    const res =
      await fetch(
        `${API_BASE}/api/profile`,
        {
          method: "GET",

          credentials: "include"
        }
      );


    if (res.ok) {

      profileLink.hidden = false;

    } else {

      profileLink.hidden = true;

    }


  } catch (error) {

    profileLink.hidden = true;

  }

}


document.addEventListener(
  "DOMContentLoaded",
  function () {

    waitForGoogleAndInit();

    initProfileNavLink();

  }
);