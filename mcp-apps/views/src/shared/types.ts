// Mirrors of the weather_core models as they arrive in structuredContent.

export type Units = "metric" | "imperial";

export interface Place {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  country: string | null;
  country_code: string | null;
  region: string | null;
  timezone: string;
  population: number | null;
}

export interface Condition {
  code: number;
  label: string;
  icon: string;
}

export interface UnitLabels {
  temperature: string;
  wind_speed: string;
  precipitation: string;
}

export interface Attribution {
  text: string;
  url: string;
  license: string;
}

export interface CityWeather {
  kind: "weather";
  place: Place;
  units: Units;
  unit_labels: UnitLabels;
  current: {
    observed_at: string;
    temperature: number;
    feels_like: number;
    humidity: number;
    wind_speed: number;
    wind_direction: number;
    is_day: boolean;
    condition: Condition;
  };
  local_time: { timezone: string; abbreviation: string; utc_offset_seconds: number; iso: string };
  summary: string;
}

export interface Resolution {
  kind: "choose_place";
  query: string;
  ambiguous: boolean;
  candidates: Place[];
  summary: string;
}

export interface Forecast {
  kind: "forecast";
  place: Place;
  units: Units;
  unit_labels: UnitLabels;
  days: number;
  daily: {
    date: string;
    condition: Condition;
    temperature_min: number;
    temperature_max: number;
    precipitation_sum: number;
    precipitation_probability: number | null;
  }[];
  summary: string;
}

export interface WorldClock {
  kind: "world_clock";
  units: Units;
  items: (CityWeather | Resolution)[];
}

export type Payload = (CityWeather | Resolution | Forecast | WorldClock) & {
  attribution?: Attribution;
};
