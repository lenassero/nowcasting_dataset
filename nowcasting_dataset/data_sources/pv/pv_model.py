""" Model for output of PV data """

import logging

from nowcasting_dataset.data_sources.datasource_output import DataSourceOutput

logger = logging.getLogger(__name__)


class PV(DataSourceOutput):
    """Class to store PV data as a xr.Dataset with some validation"""

    __slots__ = ()
    _expected_dimensions = ("time", "id")
    _expected_data_vars = (
        "power_mw",
        "capacity_mwp",
        "pv_system_row_number",
        "x_coords",
        "y_coords",
    )

    @classmethod
    def model_validation(cls, v):
        """Check that all values are non NaNs"""
        v.check_nan_and_inf(data=v.power_mw)
        v.check_dataset_greater_than_or_equal_to(data=v.power_mw, min_value=0)

        v.check_data_var_dim(v.power_mw, ("example", "time_index", "id_index"))
        v.check_data_var_dim(v.capacity_mwp, ("example", "id_index"))
        v.check_data_var_dim(v.time, ("example", "time_index"))
        v.check_data_var_dim(v.x_coords, ("example", "id_index"))
        v.check_data_var_dim(v.y_coords, ("example", "id_index"))
        v.check_data_var_dim(v.pv_system_row_number, ("example", "id_index"))

        return v

    @property
    def power_normalized(self):
        """Normalized power"""
        return self.power_mw / self.capacity_mwp
