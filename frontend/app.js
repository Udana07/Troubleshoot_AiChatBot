const API_BASE = document.body.dataset.apiBase || "";

const form = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");
const categorySelect = document.getElementById("category-select");
const statusEl = document.getElementById("status");
const resultsSection = document.getElementById("results");
const stepsList = document.getElementById("steps-list");

function setStatus(message, { error = false, loading = false } = {}) {
  if (!message) {
    statusEl.hidden = true;
    statusEl.textContent = "";
    statusEl.classList.remove("error");
    return;
  }
  statusEl.hidden = false;
  statusEl.textContent = message;
  statusEl.classList.toggle("error", error);
  statusEl.dataset.loading = loading ? "true" : "false";
}

function renderSteps(steps = []) {
  if (!steps.length) {
    resultsSection.hidden = true;
    stepsList.innerHTML = "";
    return;
  }

  stepsList.innerHTML = "";
  steps.forEach((step, idx) => {
    const li = document.createElement("li");
    li.className = "step";
    li.innerHTML = `
      <div class="step-text">
        <strong>Step ${idx + 1}:</strong> ${step.text}
      </div>
      <div class="step-meta">
        <span>ID: ${step.id}</span>
        ${step.error_code ? `<span>Error: ${step.error_code}</span>` : ""}
        ${step.risk ? `<span>Risk: ${step.risk}</span>` : ""}
        ${step.source ? `<span>Source: ${step.source}</span>` : ""}
      </div>
    `;
    stepsList.appendChild(li);
  });

  resultsSection.hidden = false;
}

async function handleSubmit(evt) {
  evt.preventDefault();
  const query = queryInput.value.trim();
  const category = categorySelect.value.trim();

  if (!query) {
    setStatus("Please describe the error first.", { error: true });
    return;
  }

  setStatus("Searching knowledge base...", { loading: true });
  resultsSection.hidden = true;
  stepsList.innerHTML = "";

  try {
    const response = await fetch(`${API_BASE}/troubleshoot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, category: category || null }),
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Request failed");
    }

    if (!data.steps?.length) {
      setStatus("No fix steps found. Try refining the query.", { error: true });
      return;
    }

    setStatus(`Showing top ${data.steps.length} step(s).`);
    renderSteps(data.steps);
  } catch (err) {
    console.error(err);
    setStatus(err.message || "Unexpected error", { error: true });
  }
}

form.addEventListener("submit", handleSubmit);
