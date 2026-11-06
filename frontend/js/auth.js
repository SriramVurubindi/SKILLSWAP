const loginForm = $("loginForm");
const registerForm = $("registerForm");
if (getToken()) window.location.replace("dashboard.html");

const reason = new URLSearchParams(location.search).get("reason");
if (reason === "expired" && $("message")) $("message").textContent = "Your session expired. Please log in again.";

async function submitAuth(form, path, payload, busyText){
  const msg = $("message"), button = form.querySelector("button");
  msg.textContent = busyText; button.disabled = true;
  try {
    const data = await api(path, {method: "POST", body: JSON.stringify(payload())});
    saveLogin(data);
    window.location.href = path === "/register" ? "profile.html?welcome=1" : "dashboard.html";
  } catch (err) { msg.textContent = err.message; button.disabled = false; }
}

if (loginForm) loginForm.addEventListener("submit", e => {
  e.preventDefault();
  submitAuth(loginForm, "/login", () => ({email: $("email").value, password: $("password").value}), "Logging in…");
});
if (registerForm) registerForm.addEventListener("submit", e => {
  e.preventDefault();
  submitAuth(registerForm, "/register", () => ({name: $("name").value, email: $("email").value, password: $("password").value}), "Creating account…");
});
