import datetime
from datetime import timezone

from sentry.utils.dates import parse_stats_period, to_datetime, to_timestamp


def test_timestamp_conversions():
    value = datetime.datetime(2015, 10, 1, 21, 19, 5, 648517, tzinfo=timezone.utc)
    assert int(to_timestamp(value)) == int(value.strftime("%s"))
    assert to_datetime(to_timestamp(value)) == value


def test_parse_stats_period():
    assert parse_stats_period("3s") == datetime.timedelta(seconds=3)
    assert parse_stats_period("30m") == datetime.timedelta(minutes=30)
    assert parse_stats_period("1h") == datetime.timedelta(hours=1)
    assert parse_stats_period("20d") == datetime.timedelta(days=20)
    assert parse_stats_period("20f") is None
    assert parse_stats_period("-1s") is None
    assert parse_stats_period("4w") == datetime.timedelta(weeks=4)
    assert parse_stats_period("900000000000d") is datetime.timedelta.max
