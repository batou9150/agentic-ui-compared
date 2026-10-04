// S4 world clock. Clocks tick in the view (no round trip per second); the
// weather is refreshed through the server at most every 15 minutes.
import type { CallToolResult } from "@modelcontextprotocol/client";
import { icon } from "./shared/icons";
import type { Attribution, CityWeather, Resolution, WorldClock } from "./shared/types";
import {
  attributionEl,
  connect,
  createApp,
  el,
  errorText,
  payloadOf,
  showError,
  showLoading,
} from "./shared/view";

type Payload = WorldClock & { attribution?: Attribution };

const REFRESH_MS = 15 * 60 * 1000;
const root = document.getElementById("root")!;
const app = createApp("World clock");
let clocks: { node: HTMLElement; timezone: string }[] = [];
let refreshTimer: number | undefined;

app.ontoolinput = () => showLoading(root);
app.ontoolresult = (result) => render(result);

function render(result: CallToolResult): void {
  const data = payloadOf<Payload>(result);
  if (result.isError || !data || data.kind !== "world_clock") return showError(root, errorText(result));
  clocks = [];
  const cards = data.items.map((item) => (item.kind === "weather" ? cityCard(item) : ambiguousCard(item)));
  root.replaceChildren(
    el("section", { class: "grid", "data-testid": "world-clock-grid" }, ...cards),
    attributionEl(data.attribution),
  );
  tick();
  scheduleRefresh(data);
}

function cityCard(w: CityWeather): HTMLElement {
  const clock = el("div", { class: "clock", "data-testid": "clock" });
  clocks.push({ node: clock, timezone: w.local_time.timezone });
  return el(
    "article",
    { class: "card", "data-testid": `city-card-${w.place.id}` },
    el("h2", { "data-testid": "place-name" }, w.place.name),
    el("p", { class: "muted" }, [w.place.country, w.local_time.abbreviation].filter(Boolean).join(" · ")),
    clock,
    el(
      "div",
      { class: "row" },
      el(
        "span",
        { class: "icon small", "data-icon": w.current.condition.icon },
        icon(w.current.condition.icon),
      ),
      el("span", { "data-testid": "temperature" }, `${w.current.temperature}${w.unit_labels.temperature}`),
      el("span", { class: "muted" }, w.current.condition.label),
    ),
  );
}

function ambiguousCard(r: Resolution): HTMLElement {
  return el(
    "article",
    { class: "card", "data-testid": "city-card-ambiguous" },
    el("h2", {}, r.query),
    el(
      "p",
      { class: "muted" },
      `Several places match: ${r.candidates.map((c) => c.region ?? c.country).join(", ")}. Ask for a specific one.`,
    ),
  );
}

function tick(): void {
  const now = new Date();
  for (const { node, timezone } of clocks) {
    node.textContent = now.toLocaleTimeString("en-GB", {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }
}

function scheduleRefresh(data: Payload): void {
  window.clearTimeout(refreshTimer);
  const placeIds = data.items.flatMap((i) => (i.kind === "weather" ? [i.place.id] : []));
  if (placeIds.length === 0) return;
  refreshTimer = window.setTimeout(async () => {
    render(
      await app.callServerTool({
        name: "get_world_clock",
        arguments: { place_ids: placeIds, units: data.units },
      }),
    );
  }, REFRESH_MS);
}

window.setInterval(tick, 1000);
void connect(app);
