""" Satellite Data Source """
import logging
from dataclasses import InitVar, dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import xarray as xr
from numbers import Number


import nowcasting_dataset.time as nd_time
from nowcasting_dataset.consts import SAT_VARIABLE_NAMES
from nowcasting_dataset.data_sources.data_source import ZarrDataSource
from nowcasting_dataset.data_sources.satellite.satellite_model import Satellite

_LOG = logging.getLogger("nowcasting_dataset")


@dataclass
class SatelliteDataSource(ZarrDataSource):
    """Satellite Data Source."""

    channels: Optional[Iterable[str]] = SAT_VARIABLE_NAMES
    image_size_pixels: InitVar[int] = 128
    meters_per_pixel: InitVar[int] = 2_000

    def __post_init__(self, image_size_pixels: int, meters_per_pixel: int):
        """Post Init"""
        super().__post_init__(image_size_pixels, meters_per_pixel)
        n_channels = len(self.channels)
        self._shape_of_example = (
            self.total_seq_length,
            image_size_pixels,
            image_size_pixels,
            n_channels,
        )

    def open(self) -> None:
        """
        Open Satellite data

        We don't want to open_sat_data in __init__.
        If we did that, then we couldn't copy SatelliteDataSource
        instances into separate processes.  Instead,
        call open() _after_ creating separate processes.
        """
        self._data = self._open_data()
        self._data = self._data.sel(variable=list(self.channels))

    def _open_data(self) -> xr.DataArray:
        return open_sat_data(zarr_path=self.zarr_path, consolidated=self.consolidated)

    def get_data_model_for_batch(self):
        """Get the model that is used in the batch"""
        return Satellite

    def _get_time_slice(self, t0_dt: pd.Timestamp) -> xr.DataArray:
        start_dt = self._get_start_dt(t0_dt)
        end_dt = self._get_end_dt(t0_dt)
        data = self.data.sel(time=slice(start_dt, end_dt))
        assert type(data) == xr.DataArray

        return data

    def get_image_pixel(self, data_array: xr.DataArray, x_meters_center: Number, y_meters_center: Number) -> xr.DataArray:
        x_index = np.searchsorted(data_array.x.values, x_meters_center)-1 # To have the center fall within the pixel
        y_index = np.searchsorted(data_array.y.values, y_meters_center)-1
        min_y = y_index - (self._square.size_pixels // 2)
        min_x = x_index - (self._square.size_pixels // 2)
        assert min_y >= 0, f"Y location must be at least {(self._square.size_pixels // 2)} pixels from the edge of the area, but is {y_index} for y center of {y_meters_center}"
        assert min_x >= 0, f"X location must be at least {(self._square.size_pixels // 2)} pixels from the edge of the area, but is {x_index} for x center of {x_meters_center}"
        data_array = data_array.isel(x=slice(min_x, min_x + self._square.size_pixels),
                                     y=slice(min_y,min_y + self._square.size_pixels))
        return data_array

    def get_example(
            self, t0_dt: pd.Timestamp, x_meters_center: Number, y_meters_center: Number
            ) -> xr.Dataset:
        """
        Get Example data

        Args:
            t0_dt: list of timestamps for the datetime of the batches. The batch will also include
                data for historic and future depending on `history_minutes` and `future_minutes`.
            x_meters_center: x center batch locations
            y_meters_center: y center batch locations

        Returns: Example Data

        """
        selected_data = self._get_time_slice(t0_dt)
        selected_data = self.get_image_pixel(data_array = selected_data,
                                             x_meters_center = x_meters_center,
                                             y_meters_center = y_meters_center)

        selected_data = self._post_process_example(selected_data, t0_dt)

        if selected_data.shape != self._shape_of_example:
            raise RuntimeError(
                "Example is wrong shape! "
                f"x_meters_center={x_meters_center}\n"
                f"y_meters_center={y_meters_center}\n"
                f"t0_dt={t0_dt}\n"
                f"times are {selected_data.time}\n"
                f"expected shape={self._shape_of_example}\n"
                f"actual shape {selected_data.shape}"
                )

        return selected_data.load().to_dataset(name="data")


    def datetime_index(self, remove_night: bool = True) -> pd.DatetimeIndex:
        """Returns a complete list of all available datetimes

        Args:
            remove_night: If True then remove datetimes at night.
                We're interested in forecasting solar power generation, so we
                don't care about nighttime data :)

                In the UK in summer, the sun rises first in the north east, and
                sets last in the north west [1].  In summer, the north gets more
                hours of sunshine per day.

                In the UK in winter, the sun rises first in the south east, and
                sets last in the south west [2].  In winter, the south gets more
                hours of sunshine per day.

                |                        | Summer | Winter |
                |           ---:         |  :---: |  :---: |
                | Sun rises first in     | N.E.   | S.E.   |
                | Sun sets last in       | N.W.   | S.W.   |
                | Most hours of sunlight | North  | South  |

                Before training, we select timesteps which have at least some
                sunlight.  We do this by computing the clearsky global horizontal
                irradiance (GHI) for the four corners of the satellite imagery,
                and for all the timesteps in the dataset.  We only use timesteps
                where the maximum global horizontal irradiance across all four
                corners is above some threshold.

                The 'clearsky solar irradiance' is the amount of sunlight we'd
                expect on a clear day at a specific time and location. The SI unit
                of irradiance is watt per square meter.  The 'global horizontal
                irradiance' (GHI) is the total sunlight that would hit a
                horizontal surface on the surface of the Earth.  The GHI is the
                sum of the direct irradiance (sunlight which takes a direct path
                from the Sun to the Earth's surface) and the diffuse horizontal
                irradiance (the sunlight scattered from the atmosphere).  For more
                info, see: https://en.wikipedia.org/wiki/Solar_irradiance

        References:
          1. [Video of June 2019](https://www.youtube.com/watch?v=IOp-tj-IJpk)
          2. [Video of Jan 2019](https://www.youtube.com/watch?v=CJ4prUVa2nQ)
        """
        if self._data is None:
            sat_data = self._open_data()
        else:
            sat_data = self._data

        datetime_index = pd.DatetimeIndex(sat_data.time.values)

        if remove_night:
            border_locations = self.geospatial_border()
            datetime_index = nd_time.select_daylight_datetimes(
                datetimes=datetime_index, locations=border_locations
            )

        return datetime_index


def open_sat_data(zarr_path: str, consolidated: bool) -> xr.DataArray:
    """Lazily opens the Zarr store.

    Adds 1 minute to the 'time' coordinates, so the timestamps
    are at 00, 05, ..., 55 past the hour.

    Args:
      zarr_path: Cloud URL or local path pattern.  If GCP URL, must start with 'gs://'
      consolidated: Whether or not the Zarr metadata is consolidated.
    """
    _LOG.debug("Opening satellite data: %s", zarr_path)

    # We load using chunks=None so xarray *doesn't* use Dask to
    # load the Zarr chunks from disk.  Using Dask to load the data
    # seems to slow things down a lot if the Zarr store has more than
    # about a million chunks.
    # See https://github.com/openclimatefix/nowcasting_dataset/issues/23
    if Path(zarr_path).exists:
        dataset = xr.open_dataset(
            zarr_path, engine="zarr", consolidated=consolidated, mode="r", chunks=None
        )
    else:
        dataset = xr.open_mfdataset(
            zarr_path, chunks=None, mode="r", engine="zarr", concat_dim="time"
        )

    data_array = dataset["stacked_eumetsat_data"]
    del dataset
    # Flip coordinates to top-left first
    data_array = data_array.reindex(x=data_array.x[::-1], y=data_array.y[::-1])

    return data_array
