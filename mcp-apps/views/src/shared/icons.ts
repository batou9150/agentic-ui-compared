// Icon keys come from weather_core.wmo; each UI picks its own artwork.
const ICONS: Record<string, string> = {
  clear: "☀️",
  "clear-night": "🌙",
  "partly-cloudy": "⛅",
  "partly-cloudy-night": "☁️",
  overcast: "☁️",
  fog: "🌫️",
  drizzle: "🌦️",
  rain: "🌧️",
  "freezing-rain": "🧊",
  snow: "❄️",
  showers: "🌦️",
  "snow-showers": "🌨️",
  thunderstorm: "⛈️",
  unknown: "❔",
};

export function icon(key: string): string {
  return ICONS[key] ?? ICONS.unknown;
}
