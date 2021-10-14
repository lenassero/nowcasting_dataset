from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from nowcasting_dataset import time as nd_time
from nowcasting_dataset.time import THIRTY_MINUTES, FIVE_MINUTES


def test_select_daylight_datetimes():
    datetimes = pd.date_range("2020-01-01 00:00", "2020-01-02 00:00", freq="H")
    locations = [(0, 0), (20_000, 20_000)]
    daylight_datetimes = nd_time.select_daylight_datetimes(datetimes=datetimes, locations=locations)
    correct_daylight_datetimes = pd.date_range("2020-01-01 09:00", "2020-01-01 16:00", freq="H")
    np.testing.assert_array_equal(daylight_datetimes, correct_daylight_datetimes)


def test_intersection_of_datetimeindexes():
    # Test with just one
    index = pd.date_range("2010-01-01", "2010-01-02", freq="H")
    intersection = nd_time.intersection_of_datetimeindexes([index])
    np.testing.assert_array_equal(index, intersection)

    # Test with two identical:
    intersection = nd_time.intersection_of_datetimeindexes([index, index])
    np.testing.assert_array_equal(index, intersection)

    # Test with three with no intersection:
    index2 = pd.date_range("2020-01-01", "2010-01-02", freq="H")
    intersection = nd_time.intersection_of_datetimeindexes([index, index2])
    assert len(intersection) == 0

    # Test with three, with some intersection:
    index3 = pd.date_range("2010-01-01 06:00", "2010-01-02 06:00", freq="H")
    index4 = pd.date_range("2010-01-01 12:00", "2010-01-02 12:00", freq="H")
    intersection = nd_time.intersection_of_datetimeindexes([index, index3, index4])
    np.testing.assert_array_equal(
        intersection, pd.date_range("2010-01-01 12:00", "2010-01-02", freq="H")
    )


@pytest.mark.parametrize("total_seq_len", [2, 3, 12])
def test_get_start_datetimes_1(total_seq_len):
    dt_index1 = pd.date_range("2010-01-01", "2010-01-02", freq="5 min")
    start_datetimes = nd_time.get_start_datetimes(dt_index1, total_seq_len=total_seq_len)
    np.testing.assert_array_equal(start_datetimes, dt_index1[: 1 - total_seq_len])


@pytest.mark.parametrize("total_seq_len", [2, 3, 12])
def test_get_start_datetimes_2(total_seq_len):
    dt_index1 = pd.date_range("2010-01-01", "2010-01-02", freq="5 min")
    dt_index2 = pd.date_range("2010-02-01", "2010-02-02", freq="5 min")
    dt_index = dt_index1.union(dt_index2)
    start_datetimes = nd_time.get_start_datetimes(dt_index, total_seq_len=total_seq_len)
    correct_start_datetimes = dt_index1[: 1 - total_seq_len].union(dt_index2[: 1 - total_seq_len])
    np.testing.assert_array_equal(start_datetimes, correct_start_datetimes)


def test_datetime_features_in_example():
    index = pd.date_range("2020-01-01", "2020-01-06 23:00", freq="h")
    example = nd_time.datetime_features_in_example(index)
    assert len(example.hour_of_day_sin) == len(index)
    for col_name in ["hour_of_day_sin", "hour_of_day_cos"]:
        np.testing.assert_array_almost_equal(
            example.__getattribute__(col_name),
            np.tile(example.__getattribute__(col_name)[:24], reps=6),
        )


@pytest.mark.parametrize("history_length", [2, 3, 12])
@pytest.mark.parametrize("forecast_length", [2, 3, 12])
def test_get_t0_datetimes(history_length, forecast_length):
    index = pd.date_range("2020-01-01", "2020-01-06 23:00", freq="30T")
    total_seq_len = history_length + forecast_length + 1
    sample_period_dur = THIRTY_MINUTES
    history_dur = sample_period_dur * history_length

    t0_datetimes = nd_time.get_t0_datetimes(
        datetimes=index,
        total_seq_len=total_seq_len,
        history_dur=history_dur,
        max_gap=THIRTY_MINUTES,
    )

    assert len(t0_datetimes) == len(index) - history_length - forecast_length
    assert t0_datetimes[0] == index[0] + timedelta(minutes=30 * history_length)
    assert t0_datetimes[-1] == index[-1] - timedelta(minutes=30 * forecast_length)


def test_get_t0_datetimes_night():
    history_length = 6
    forecast_length = 12
    sample_period_dur = FIVE_MINUTES
    index = pd.date_range("2020-06-15", "2020-06-15 22:15", freq=sample_period_dur)
    total_seq_len = history_length + forecast_length + 1
    history_dur = history_length * sample_period_dur

    t0_datetimes = nd_time.get_t0_datetimes(
        datetimes=index,
        total_seq_len=total_seq_len,
        history_dur=history_dur,
        max_gap=sample_period_dur,
    )

    assert len(t0_datetimes) == len(index) - history_length - forecast_length
    assert t0_datetimes[0] == index[0] + timedelta(minutes=5 * history_length)
    assert t0_datetimes[-1] == index[-1] - timedelta(minutes=5 * forecast_length)


def test_intersection_of_2_dataframes_of_periods():
    # Five ways in which two periods may overlap:
    #      1          2         3          4         5
    # a: |----| or |---|   or  |---| or   |--|   or |-|
    # b:  |--|       |---|   |---|      |------|    |-|
    #
    # Two ways in which two periods may *not* overlap:
    #      6                      7
    # a: |---|        or        |---|
    # b:       |---|      |---|
    #
    # Let's test all 6 ways.  The comment at the end of each line below
    # identifies the "overlapping configuration" in the little text
    # diagram above.

    dt = pd.Timestamp("2020-01-01 00:00")
    a = pd.DataFrame(
        [
            {"start_dt": dt, "end_dt": dt.replace(hour=3)},  # 1
            {"start_dt": dt.replace(hour=4), "end_dt": dt.replace(hour=6)},  # 2
            {"start_dt": dt.replace(hour=9), "end_dt": dt.replace(hour=11)},  # 3
            {"start_dt": dt.replace(hour=13), "end_dt": dt.replace(hour=14)},  # 4
            {"start_dt": dt.replace(day=2, hour=12), "end_dt": dt.replace(day=2, hour=14)},  # 5
            {"start_dt": dt.replace(hour=16), "end_dt": dt.replace(hour=17)},  # 6
            {"start_dt": dt.replace(hour=22), "end_dt": dt.replace(hour=23)},  # 7
        ]
    )

    b = pd.DataFrame(
        [
            {"start_dt": dt.replace(hour=1), "end_dt": dt.replace(hour=2)},  # 1
            {"start_dt": dt.replace(hour=5), "end_dt": dt.replace(hour=7)},  # 2
            {"start_dt": dt.replace(hour=8), "end_dt": dt.replace(hour=10)},  # 3
            {"start_dt": dt.replace(hour=12), "end_dt": dt.replace(hour=15)},  # 4
            {"start_dt": dt.replace(day=2, hour=12), "end_dt": dt.replace(day=2, hour=14)},  # 5
            {"start_dt": dt.replace(hour=18), "end_dt": dt.replace(hour=19)},  # 6
            {"start_dt": dt.replace(hour=20), "end_dt": dt.replace(hour=21)},  # 7
        ]
    )

    intersection = nd_time.intersection_of_2_dataframes_of_periods(a, b)

    correct_intersection = pd.DataFrame(
        [
            {"start_dt": dt.replace(hour=1), "end_dt": dt.replace(hour=2)},  # 1
            {"start_dt": dt.replace(hour=5), "end_dt": dt.replace(hour=6)},  # 2
            {"start_dt": dt.replace(hour=9), "end_dt": dt.replace(hour=10)},  # 3
            {"start_dt": dt.replace(hour=13), "end_dt": dt.replace(hour=14)},  # 4
            {"start_dt": dt.replace(day=2, hour=12), "end_dt": dt.replace(day=2, hour=14)},  # 5
        ]
    )

    pd.testing.assert_frame_equal(intersection, correct_intersection)
