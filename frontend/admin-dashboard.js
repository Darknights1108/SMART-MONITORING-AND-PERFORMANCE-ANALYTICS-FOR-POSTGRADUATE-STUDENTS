const API_BASE_URL = window.API_BASE_URL || "http://127.0.0.1:8000";

const token = localStorage.getItem("datatrain_token");
const user = JSON.parse(localStorage.getItem("datatrain_user") || "null");

const datasetSelect = document.getElementById("datasetSelect");
const chartModeSelect = document.getElementById("chartModeSelect");
const refreshButton = document.getElementById("refreshButton");
const logoutButton = document.getElementById("logoutButton");
const statusMessage = document.getElementById("statusMessage");
const chartTitle = document.getElementById("chartTitle");
const chartMeta = document.getElementById("chartMeta");
const rowCount = document.getElementById("rowCount");
const tableOnlyNotice = document.getElementById("tableOnlyNotice");
const canvas = document.getElementById("chartCanvas");
const ctx = canvas.getContext("2d");

const chartTableHead = document.getElementById("chartTableHead");
const chartTableBody = document.getElementById("chartTableBody");
const recordsTableHead = document.getElementById("recordsTableHead");
const recordsTableBody = document.getElementById("recordsTableBody");

let currentChartRows = [];

if (!token) {
  window.location.href = "index.html";
}

if (user) {
  document.getElementById("userPill").textContent = `${user.name || user.staff_id} (${user.role})`;
}

function setStatus(message) {
  statusMessage.textContent = message;
}

async function apiGet(path) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem("datatrain_token");
    localStorage.removeItem("datatrain_user");
    window.location.href = "index.html";
    return null;
  }

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

function normalizeChartData(chartData) {
  if (chartData.data) {
    return chartData.data.map((item) => ({
      label: item.name,
      value: Number(item.value) || 0,
    }));
  }

  if (chartData.series) {
    return chartData.categories.map((category, index) => {
      const row = { label: category };
      chartData.series.forEach((series) => {
        row[series.name] = Number(series.data[index]) || 0;
      });
      return row;
    });
  }

  return (chartData.categories || []).map((category, index) => ({
    label: category,
    value: Number(chartData.values[index]) || 0,
  }));
}

function getNumericKeys(rows) {
  if (!rows.length) {
    return [];
  }
  return Object.keys(rows[0]).filter((key) => key !== "label");
}

function drawChart(rows, mode, title) {
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  tableOnlyNotice.classList.toggle("hidden", mode !== "table");

  if (!rows.length || mode === "table") {
    if (!rows.length) {
      drawEmptyState("No data available");
    }
    return;
  }

  if (mode === "pie") {
    drawPie(rows);
  } else if (mode === "line") {
    drawLine(rows);
  } else {
    drawBar(rows, title);
  }
}

function drawEmptyState(message) {
  ctx.fillStyle = "#687586";
  ctx.font = "700 22px Arial";
  ctx.textAlign = "center";
  ctx.fillText(message, canvas.width / 2, canvas.height / 2);
}

function chartColors(index) {
  const palette = ["#116dca", "#16845b", "#c43d32", "#b87911", "#7057c7", "#18808a", "#c45a1b"];
  return palette[index % palette.length];
}

function drawAxes(left, top, right, bottom, maxValue) {
  ctx.strokeStyle = "#d7dde5";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, bottom);
  ctx.lineTo(right, bottom);
  ctx.stroke();

  ctx.fillStyle = "#687586";
  ctx.font = "12px Arial";
  ctx.textAlign = "right";
  for (let i = 0; i <= 4; i += 1) {
    const value = Math.round((maxValue / 4) * i);
    const y = bottom - ((bottom - top) * i) / 4;
    ctx.fillText(String(value), left - 10, y + 4);
    ctx.strokeStyle = "#edf1f5";
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  }
}

function drawBar(rows) {
  const keys = getNumericKeys(rows);
  const left = 64;
  const top = 28;
  const right = canvas.width - 24;
  const bottom = canvas.height - 78;
  const maxValue = Math.max(1, ...rows.flatMap((row) => keys.map((key) => row[key])));
  const groupWidth = (right - left) / rows.length;
  const barWidth = Math.max(8, Math.min(46, (groupWidth - 14) / keys.length));

  drawAxes(left, top, right, bottom, maxValue);

  rows.forEach((row, rowIndex) => {
    keys.forEach((key, keyIndex) => {
      const value = row[key];
      const x = left + rowIndex * groupWidth + 8 + keyIndex * barWidth;
      const barHeight = ((bottom - top) * value) / maxValue;
      ctx.fillStyle = chartColors(keyIndex);
      ctx.fillRect(x, bottom - barHeight, barWidth - 2, barHeight);
    });

    ctx.save();
    ctx.translate(left + rowIndex * groupWidth + groupWidth / 2, bottom + 12);
    ctx.rotate(-0.55);
    ctx.fillStyle = "#334256";
    ctx.font = "12px Arial";
    ctx.textAlign = "right";
    ctx.fillText(String(row.label).slice(0, 28), 0, 0);
    ctx.restore();
  });

  drawLegend(keys, left, canvas.height - 28);
}

function drawLine(rows) {
  const key = getNumericKeys(rows)[0];
  const left = 64;
  const top = 28;
  const right = canvas.width - 24;
  const bottom = canvas.height - 78;
  const maxValue = Math.max(1, ...rows.map((row) => row[key]));

  drawAxes(left, top, right, bottom, maxValue);

  ctx.strokeStyle = chartColors(0);
  ctx.lineWidth = 3;
  ctx.beginPath();

  rows.forEach((row, index) => {
    const x = left + ((right - left) * index) / Math.max(1, rows.length - 1);
    const y = bottom - ((bottom - top) * row[key]) / maxValue;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  rows.forEach((row, index) => {
    const x = left + ((right - left) * index) / Math.max(1, rows.length - 1);
    const y = bottom - ((bottom - top) * row[key]) / maxValue;
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = chartColors(0);
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.save();
    ctx.translate(x, bottom + 12);
    ctx.rotate(-0.55);
    ctx.fillStyle = "#334256";
    ctx.font = "12px Arial";
    ctx.textAlign = "right";
    ctx.fillText(String(row.label).slice(0, 24), 0, 0);
    ctx.restore();
  });
}

function drawPie(rows) {
  const key = getNumericKeys(rows)[0];
  const total = rows.reduce((sum, row) => sum + row[key], 0);
  if (!total) {
    drawEmptyState("No values to chart");
    return;
  }

  const centerX = canvas.width * 0.38;
  const centerY = canvas.height * 0.48;
  const radius = Math.min(canvas.width, canvas.height) * 0.28;
  let start = -Math.PI / 2;

  rows.forEach((row, index) => {
    const slice = (row[key] / total) * Math.PI * 2;
    ctx.fillStyle = chartColors(index);
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, radius, start, start + slice);
    ctx.closePath();
    ctx.fill();
    start += slice;
  });

  const legendX = canvas.width * 0.68;
  let legendY = canvas.height * 0.28;
  ctx.font = "14px Arial";
  rows.forEach((row, index) => {
    ctx.fillStyle = chartColors(index);
    ctx.fillRect(legendX, legendY - 11, 13, 13);
    ctx.fillStyle = "#334256";
    ctx.textAlign = "left";
    const percent = Math.round((row[key] / total) * 100);
    ctx.fillText(`${row.label}: ${row[key]} (${percent}%)`, legendX + 22, legendY);
    legendY += 25;
  });
}

function drawLegend(keys, x, y) {
  ctx.font = "13px Arial";
  ctx.textAlign = "left";
  let offset = 0;
  keys.forEach((key, index) => {
    ctx.fillStyle = chartColors(index);
    ctx.fillRect(x + offset, y - 11, 13, 13);
    ctx.fillStyle = "#334256";
    ctx.fillText(key, x + offset + 20, y);
    offset += Math.min(190, key.length * 8 + 42);
  });
}

function renderDataTable(rows, headEl, bodyEl) {
  headEl.innerHTML = "";
  bodyEl.innerHTML = "";

  if (!rows.length) {
    bodyEl.innerHTML = `<tr><td>No data available</td></tr>`;
    return;
  }

  const columns = Object.keys(rows[0]);
  headEl.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  bodyEl.innerHTML = rows.map((row) => (
    `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`
  )).join("");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function resolveMode(chartType, selectedMode) {
  if (selectedMode !== "auto") {
    return selectedMode;
  }
  if (chartType === "pie") {
    return "pie";
  }
  if (chartType === "line") {
    return "line";
  }
  return "bar";
}

async function loadSummary() {
  const summary = await apiGet("/api/dashboard/summary");
  if (!summary) {
    return;
  }

  document.getElementById("totalStudents").textContent = summary.total_students ?? 0;
  document.getElementById("overdueStudents").textContent = summary.overdue_students ?? 0;
  document.getElementById("upcomingSeven").textContent = summary.upcoming_7_days ?? 0;
  document.getElementById("ppmRisk").textContent = summary.ppm_at_risk ?? 0;
}

async function loadChart() {
  const dataset = datasetSelect.value;
  setStatus("Loading chart data from SQL...");
  const chartData = await apiGet(`/api/dashboard/charts/${dataset}`);
  if (!chartData) {
    return;
  }

  currentChartRows = normalizeChartData(chartData);
  chartTitle.textContent = chartData.title || "Chart";
  chartMeta.textContent = `${chartData.type || "dataset"} from /api/dashboard/charts/${dataset}`;
  rowCount.textContent = `${currentChartRows.length} rows`;

  renderDataTable(currentChartRows, chartTableHead, chartTableBody);
  drawChart(currentChartRows, resolveMode(chartData.type, chartModeSelect.value), chartData.title);
  setStatus("Dashboard data loaded.");
}

async function loadRecords(tabName) {
  const endpoints = {
    deadlines: "/api/dashboard/upcoming-deadlines?days=30",
    overdue: "/api/dashboard/overdue",
    emails: "/api/dashboard/email-log?limit=50",
  };

  const rows = await apiGet(endpoints[tabName]);
  renderDataTable(rows || [], recordsTableHead, recordsTableBody);
}

async function refreshDashboard() {
  refreshButton.disabled = true;
  try {
    await Promise.all([loadSummary(), loadChart()]);
  } catch (error) {
    setStatus(error.message || "Unable to load dashboard data.");
  } finally {
    refreshButton.disabled = false;
  }
}

datasetSelect.addEventListener("change", loadChart);
chartModeSelect.addEventListener("change", () => loadChart());
refreshButton.addEventListener("click", refreshDashboard);

logoutButton.addEventListener("click", () => {
  localStorage.removeItem("datatrain_token");
  localStorage.removeItem("datatrain_user");
  window.location.href = "index.html";
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    loadRecords(tab.dataset.tab).catch((error) => setStatus(error.message));
  });
});

window.addEventListener("resize", () => {
  if (currentChartRows.length) {
    loadChart().catch((error) => setStatus(error.message));
  }
});

refreshDashboard();
loadRecords("deadlines").catch((error) => setStatus(error.message));
