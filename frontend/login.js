const API_BASE_URL = window.API_BASE_URL || "http://127.0.0.1:8000";

const form = document.getElementById("loginForm");
const staffIdInput = document.getElementById("staffId");
const passwordInput = document.getElementById("password");
const errorMessage = document.getElementById("errorMessage");
const loginButton = document.getElementById("loginButton");

function setError(message) {
  errorMessage.textContent = message;
}

function getDashboardPath(role) {
  if (role === "Admin" || role === "Both") {
    return "admin-dashboard.html";
  }
  return "supervisor-dashboard.html";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setError("");

  const staffId = staffIdInput.value.trim();
  const password = passwordInput.value;

  if (!staffId || !password) {
    setError("Please enter your username/email and password.");
    return;
  }

  loginButton.disabled = true;
  loginButton.textContent = "LOGGING IN...";

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        staff_id: staffId,
        password,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      setError(data.detail || "Invalid username/email or password.");
      return;
    }

    localStorage.setItem("datatrain_token", data.access_token);
    localStorage.setItem("datatrain_user", JSON.stringify(data.user));

    window.location.href = getDashboardPath(data.user.role);
  } catch (error) {
    setError("Unable to connect to the server. Please try again.");
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "LOGIN";
  }
});
