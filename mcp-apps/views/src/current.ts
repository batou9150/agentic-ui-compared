// S1 weather card and S2 place picker. A pick calls the server directly
// (tools/call through the host), then tells the model what the user chose.
import type { CallToolResult } from "@modelcontextprotocol/client";
import { icon } from "./shared/icons";
import type { Attribution, CityWeather, Place, Resolution, Units } from "./shared/types";
import {
  attributionEl,
  connect,
  createApp,
  el,
  errorText,
  payloadOf,
  placeLabel,
  showError,
  showLoading,
} from "./shared/view";

type Payload = (CityWeather | Resolution) & { attribution?: Attribution };

const root = document.getElementById("root")!;
const app = createApp("Weather card");
let units: Units = "metric";

app.ontoolinput = ({ arguments: args }) => {
  if (args?.units === "imperial") units = "imperial";
  showLoading(root);
};

app.ontoolresult = (result) => render(result);

function render(result: CallToolResult): void {
  const data = payloadOf<Payload>(result);
  if (result.isError || !data) return showError(root, errorText(result));
  if (data.kind === "choose_place") renderPicker(data);
  else renderCard(data);
  root.append(attributionEl(data.attribution));
}

function renderCard(w: CityWeather): void {
  const u = w.unit_labels;
  const time = new Date(w.local_time.iso).toLocaleTimeString("en-GB", {
    timeZone: w.local_time.timezone,
    hour: "2-digit",
    minute: "2-digit",
  });
  root.replaceChildren(
    el(
      "article",
      { class: "card", "data-testid": "weather-card" },
      el("h2", { "data-testid": "place-name" }, placeLabel(w.place)),
      el(
        "p",
        { class: "muted", "data-testid": "local-time" },
        `Local time ${time} ${w.local_time.abbreviation}`,
      ),
      el(
        "div",
        { class: "row" },
        el(
          "span",
          { class: "icon", "data-testid": "condition-icon", "data-icon": w.current.condition.icon },
          icon(w.current.condition.icon),
        ),
        el(
          "span",
          { class: "big", "data-testid": "temperature" },
          `${w.current.temperature}${u.temperature}`,
        ),
        el("span", { "data-testid": "condition" }, w.current.condition.label),
      ),
      el(
        "div",
        { class: "stats" },
        el("span", { "data-testid": "feels-like" }, `Feels like ${w.current.feels_like}${u.temperature}`),
        el("span", { "data-testid": "humidity" }, `Humidity ${w.current.humidity}%`),
        el("span", { "data-testid": "wind" }, `Wind ${w.current.wind_speed} ${u.wind_speed}`),
      ),
    ),
  );
}

function renderPicker(r: Resolution): void {
  const buttons = r.candidates.map((p) =>
    el(
      "button",
      { "data-testid": `place-option-${p.id}`, "data-place-id": String(p.id) },
      el("strong", {}, p.name),
      ` ${[p.region, p.country].filter(Boolean).join(", ")}`,
    ),
  );
  buttons.forEach((b, i) => b.addEventListener("click", () => pick(r.candidates[i], buttons)));
  root.replaceChildren(
    el(
      "section",
      { class: "card", "data-testid": "place-picker" },
      el("h2", {}, `Which ${r.query}?`),
      el("p", { class: "muted" }, "Several places match. Pick one:"),
      el("div", { class: "row" }, ...buttons),
    ),
  );
}

async function pick(place: Place, buttons: HTMLButtonElement[]): Promise<void> {
  buttons.forEach((b) => (b.disabled = true));
  const result = await app.callServerTool({
    name: "get_weather",
    arguments: { place_id: place.id, units },
  });
  render(result);
  const data = payloadOf<Payload>(result);
  if (!result.isError && data?.kind === "weather") {
    await app.updateModelContext({
      content: [{ type: "text", text: `The user picked ${placeLabel(place)}. ${data.summary}` }],
    });
  }
}

void connect(app);
