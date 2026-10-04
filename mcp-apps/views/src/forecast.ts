// S3 forecast chart. The 3/7/16 days and °C/°F controls call get_forecast
// again from the view (no new chat message), then update the model context.
import type { CallToolResult } from "@modelcontextprotocol/client";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import type { Attribution, Forecast, Units } from "./shared/types";
import {
  attributionEl,
  connect,
  createApp,
  cssVar,
  el,
  errorText,
  payloadOf,
  placeLabel,
  showError,
  showLoading,
} from "./shared/view";

Chart.register(
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Legend,
  Tooltip,
);

type Payload = Forecast & { attribution?: Attribution };

const DAY_OPTIONS = [3, 7, 16];
const root = document.getElementById("root")!;
const app = createApp("Forecast chart", () => current && renderForecast(current));
let current: Payload | null = null;
let chart: Chart | null = null;

app.ontoolinput = () => showLoading(root);
app.ontoolresult = (result) => render(result);

function render(result: CallToolResult): void {
  const data = payloadOf<Payload>(result);
  if (result.isError || !data || data.kind !== "forecast") return showError(root, errorText(result));
  current = data;
  renderForecast(data);
}

function renderForecast(f: Payload): void {
  const dayButtons = DAY_OPTIONS.map((d) =>
    control(`${d} days`, `days-${d}`, f.days === d, () => update({ days: d })),
  );
  const unitButtons = (["metric", "imperial"] as Units[]).map((u) =>
    control(u === "metric" ? "°C" : "°F", `units-${u}`, f.units === u, () => update({ units: u })),
  );
  const canvas = el("canvas", { "data-testid": "forecast-chart", "aria-label": f.summary });
  root.replaceChildren(
    el(
      "article",
      { class: "card", "data-testid": "forecast-card" },
      el("h2", { "data-testid": "place-name" }, placeLabel(f.place)),
      el("p", { class: "muted" }, `${f.days}-day forecast`),
      el(
        "div",
        { class: "row", "data-testid": "forecast-controls" },
        ...dayButtons,
        el("span", {}, " "),
        ...unitButtons,
      ),
      el("div", { style: "position: relative; height: 260px; margin-top: 8px" }, canvas),
    ),
    attributionEl(f.attribution),
  );
  drawChart(canvas, f);
}

function control(label: string, id: string, pressed: boolean, onClick: () => void): HTMLButtonElement {
  const b = el("button", { "data-testid": `control-${id}`, "aria-pressed": String(pressed) }, label);
  b.addEventListener("click", onClick);
  return b;
}

async function update(change: { days?: number; units?: Units }): Promise<void> {
  if (!current) return;
  root.querySelectorAll("button").forEach((b) => (b.disabled = true));
  const args = { place_id: current.place.id, days: current.days, units: current.units, ...change };
  const result = await app.callServerTool({ name: "get_forecast", arguments: args });
  render(result);
  if (!result.isError && current) {
    await app.updateModelContext({
      content: [{ type: "text", text: `The user changed the forecast view. ${current.summary}` }],
    });
  }
}

function drawChart(canvas: HTMLCanvasElement, f: Payload): void {
  chart?.destroy();
  const text = cssVar("--color-text-secondary", "#6b7280");
  const grid = cssVar("--color-border-primary", "#e5e7eb");
  const labels = f.daily.map((d) =>
    new Date(`${d.date}T12:00:00Z`).toLocaleDateString("en-GB", {
      weekday: "short",
      day: "numeric",
      timeZone: "UTC",
    }),
  );
  chart = new Chart(canvas, {
    data: {
      labels,
      datasets: [
        {
          type: "line",
          label: `Max ${f.unit_labels.temperature}`,
          data: f.daily.map((d) => d.temperature_max),
          borderColor: "#e4572e",
          backgroundColor: "#e4572e",
          yAxisID: "temp",
        },
        {
          type: "line",
          label: `Min ${f.unit_labels.temperature}`,
          data: f.daily.map((d) => d.temperature_min),
          borderColor: "#2e86de",
          backgroundColor: "#2e86de",
          yAxisID: "temp",
        },
        {
          type: "bar",
          label: `Precipitation ${f.unit_labels.precipitation}`,
          data: f.daily.map((d) => d.precipitation_sum),
          backgroundColor: "rgba(46, 134, 222, 0.3)",
          yAxisID: "precip",
        },
      ],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      color: text,
      scales: {
        x: { ticks: { color: text }, grid: { color: grid } },
        temp: { position: "left", ticks: { color: text }, grid: { color: grid } },
        precip: { position: "right", beginAtZero: true, ticks: { color: text }, grid: { display: false } },
      },
    },
  });
}

void connect(app);
