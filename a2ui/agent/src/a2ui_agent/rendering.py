"""Designed surfaces for tool results, shared by the A2A and AG-UI transports.

Surface ids are numbered per conversation (A2A context, AG-UI thread), so a
Scripted run produces the same ids, and the same bytes, on every replay.
"""

from collections import defaultdict

from weather_core import CityWeather, Forecast, Resolution, Units

from . import surfaces
from .tools import UiRequest


class SurfaceRenderer:
    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)

    def surface_id(self, conv: str, kind: str) -> str:
        self._counts[conv] += 1
        return f"{kind}-{self._counts[conv]}"

    def render(
        self, conv: str, req: UiRequest, surface_id: str | None = None
    ) -> list[surfaces.Message]:
        """A new surface for the result, or an update of `surface_id` in place."""
        if surface_id:
            return self.update(surface_id, req)
        result, units = req.result, Units(req.args.get("units", "metric"))
        if isinstance(result, Resolution):
            then = "forecast" if req.tool == "get_forecast" else "weather"
            sid = self.surface_id(conv, "picker")
            return surfaces.picker_surface(
                sid, result, then=then, units=units, days=int(req.args.get("days", 7))
            )
        if isinstance(result, CityWeather):
            return surfaces.weather_surface(self.surface_id(conv, "weather"), result)
        if isinstance(result, Forecast):
            return surfaces.forecast_surface(self.surface_id(conv, "forecast"), result)
        if isinstance(result, list):
            return surfaces.world_clock_surface(self.surface_id(conv, "clock"), result)
        raise TypeError(f"No designed surface for {type(result).__name__}")

    def update(self, surface_id: str, req: UiRequest) -> list[surfaces.Message]:
        """Redraw an existing surface: a picked place, or new forecast controls."""
        result = req.result
        if isinstance(result, CityWeather):
            return surfaces.weather_surface(surface_id, result, create=False)
        if isinstance(result, Forecast):
            if surface_id.startswith("picker-"):  # the picker becomes the chart
                return [
                    surfaces.update_components(surface_id, surfaces.forecast_layout()),
                    surfaces.update_data(surface_id, surfaces.forecast_data(result)),
                ]
            return surfaces.forecast_update(surface_id, result)
        raise TypeError(f"Cannot update a surface with {type(result).__name__}")


__all__ = ["SurfaceRenderer"]
