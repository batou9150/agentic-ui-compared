// The weather catalog: the A2UI basic catalog plus two custom components,
// Chart and Clock. Same catalogId and props as a2ui/agent/src/a2ui_agent/catalog.py.
import { A2uiLitElement } from "@a2ui/lit/v0_9";
import { Catalog, CommonSchemas, basicCatalog } from "@a2ui/web_core/v0_9";
import {
  BarController,
  BarElement,
  CategoryScale,
  Chart as ChartJs,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  Tooltip,
} from "chart.js";
import { html, nothing, type PropertyValues } from "lit";
import { customElement } from "lit/decorators.js";
import { z } from "zod";

ChartJs.register(
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

export const WEATHER_CATALOG_ID =
  "https://github.com/batou9150/agentic-ui-compared/a2ui/weather-catalog.json";

const LINE_COLORS = ["#e4572e", "#2e86de", "#17a398", "#f3a712", "#8e44ad", "#c0392b"];
const BAR_COLORS = ["rgba(46, 134, 222, 0.3)", "rgba(228, 87, 46, 0.3)", "rgba(23, 163, 152, 0.3)"];

// ---- Chart -----------------------------------------------------------------

const SeriesSchema = z.object({
  label: z.string(),
  kind: z.enum(["line", "bar"]).default("line"),
  axis: z.enum(["left", "right"]).default("left"),
  values: z.array(z.number().nullable()),
});

export const ChartApi = {
  name: "Chart",
  schema: z
    .object({
      weight: z.number().optional(),
      title: CommonSchemas.DynamicString.optional(),
      labels: CommonSchemas.DynamicStringList,
      series: CommonSchemas.DynamicValue,
      leftUnit: CommonSchemas.DynamicString.optional(),
      rightUnit: CommonSchemas.DynamicString.optional(),
    })
    .strict(),
};

@customElement("weather-chart")
export class WeatherChartElement extends A2uiLitElement<typeof ChartApi> {
  protected readonly api = ChartApi;
  private chart?: ChartJs;

  render() {
    const props = this.controller?.props;
    if (!props) return nothing;
    return html`<figure class="weather-chart" data-testid="forecast-chart" style="margin: 0">
      ${props.title ? html`<figcaption>${props.title}</figcaption>` : nothing}
      <div style="position: relative; height: 260px"><canvas></canvas></div>
    </figure>`;
  }

  protected updated(changed: PropertyValues): void {
    super.updated(changed);
    const props = this.controller?.props;
    const canvas = this.renderRoot.querySelector("canvas");
    if (!props || !canvas) return;
    const series = z.array(SeriesSchema).safeParse(props.series);
    if (!series.success) return;
    const style = getComputedStyle(this);
    const text = style.getPropertyValue("--a2ui-color-on-surface").trim() || "#333";
    const grid = style.getPropertyValue("--a2ui-color-border").trim() || "#ccc";
    let line = 0;
    let bar = 0;
    const datasets = series.data.map((s) => {
      const color =
        s.kind === "bar" ? BAR_COLORS[bar++ % BAR_COLORS.length] : LINE_COLORS[line++ % LINE_COLORS.length];
      return {
        type: s.kind,
        label: s.label,
        data: s.values,
        borderColor: color,
        backgroundColor: color,
        yAxisID: s.axis,
      };
    });
    this.chart?.destroy();
    this.chart = new ChartJs(canvas, {
      data: { labels: props.labels as string[], datasets: datasets as never },
      options: {
        animation: false,
        maintainAspectRatio: false,
        color: text,
        scales: {
          x: { ticks: { color: text }, grid: { color: grid } },
          left: {
            position: "left",
            title: { display: !!props.leftUnit, text: String(props.leftUnit ?? ""), color: text },
            ticks: { color: text },
            grid: { color: grid },
          },
          right: {
            display: series.data.some((s) => s.axis === "right"),
            position: "right",
            beginAtZero: true,
            title: { display: !!props.rightUnit, text: String(props.rightUnit ?? ""), color: text },
            ticks: { color: text },
            grid: { display: false },
          },
        },
      },
    });
  }

  disconnectedCallback(): void {
    this.chart?.destroy();
    super.disconnectedCallback();
  }
}

// ---- Clock -----------------------------------------------------------------

export const ClockApi = {
  name: "Clock",
  schema: z
    .object({
      weight: z.number().optional(),
      timeZone: CommonSchemas.DynamicString,
      showSeconds: z.boolean().default(true).optional(),
    })
    .strict(),
};

// Ticks locally every second: no round trip to the agent.
@customElement("weather-clock")
export class WeatherClockElement extends A2uiLitElement<typeof ClockApi> {
  protected readonly api = ClockApi;
  private timer?: number;

  connectedCallback(): void {
    super.connectedCallback();
    this.timer = window.setInterval(() => this.requestUpdate(), 1000);
  }

  disconnectedCallback(): void {
    window.clearInterval(this.timer);
    super.disconnectedCallback();
  }

  render() {
    const props = this.controller?.props;
    if (!props?.timeZone) return nothing;
    const time = new Date().toLocaleTimeString("en-GB", {
      timeZone: String(props.timeZone),
      hour: "2-digit",
      minute: "2-digit",
      second: props.showSeconds === false ? undefined : "2-digit",
    });
    return html`<div
      class="weather-clock"
      data-testid="clock"
      style="font-size: 1.75rem; font-weight: 600; font-variant-numeric: tabular-nums"
    >
      ${time}
    </div>`;
  }
}

// ---- catalog ---------------------------------------------------------------

export const weatherCatalog = new Catalog(
  WEATHER_CATALOG_ID,
  "v0.9",
  [
    ...basicCatalog.components.values(),
    { ...ChartApi, tagName: "weather-chart" },
    { ...ClockApi, tagName: "weather-clock" },
  ],
  [...basicCatalog.functions.values()],
  basicCatalog.themeSchema,
);
