from datetime import datetime, timedelta

import pytest
from django.utils import timezone as django_timezone

from sentry.sentry_metrics.use_case_id_registry import UseCaseID
from sentry.snuba.metrics.naming_layer import SessionMRI, TransactionMRI
from sentry.snuba.metrics_layer.api import run_metrics_query
from sentry.testutils.cases import BaseMetricsTestCase, TestCase
from sentry.testutils.helpers.datetime import freeze_time

pytestmark = pytest.mark.sentry_metrics

MOCK_DATETIME = (django_timezone.now() - timedelta(days=1)).replace(
    hour=10, minute=0, second=0, microsecond=0
)


@freeze_time(MOCK_DATETIME)
class MetricsAPITestCase(TestCase, BaseMetricsTestCase):
    def now(self):
        return MOCK_DATETIME

    def ts(self, dt: datetime) -> int:
        return int(dt.timestamp())

    def test_with_transactions(self) -> None:
        for value, transaction, platform, time in (
            (1, "/hello", "android", self.now()),
            (3, "/hello", "ios", self.now()),
            (5, "/world", "windows", self.now() + timedelta(minutes=30)),
            (3, "/hello", "ios", self.now() + timedelta(hours=1)),
            (2, "/hello", "android", self.now() + timedelta(hours=1)),
            (3, "/world", "windows", self.now() + timedelta(hours=1, minutes=30)),
        ):
            self.store_metric(
                self.project.organization.id,
                self.project.id,
                "distribution",
                TransactionMRI.DURATION.value,
                {"transaction": transaction, "platform": platform},
                self.ts(time),
                value,
                UseCaseID.TRANSACTIONS,
            )

        # Query with just one aggregation.
        field = f"sum({TransactionMRI.DURATION.value})"
        results = run_metrics_query(
            fields=[field],
            query=None,
            group_bys=None,
            start=self.now() - timedelta(minutes=30),
            end=self.now() + timedelta(hours=1, minutes=30),
            interval=3600,
            use_case_id=UseCaseID.TRANSACTIONS,
            organization=self.project.organization,
            projects=[self.project],
        )
        groups = results["groups"]
        assert len(groups) == 1
        assert groups[0]["by"] == {}
        assert groups[0]["series"] == {field: [None, 9.0, 8.0]}

        # Query with one aggregation and two group by.
        field = f"sum({TransactionMRI.DURATION.value})"
        results = run_metrics_query(
            fields=[field],
            query=None,
            group_bys=["transaction", "platform"],
            start=self.now() - timedelta(minutes=30),
            end=self.now() + timedelta(hours=1, minutes=30),
            interval=3600,
            use_case_id=UseCaseID.TRANSACTIONS,
            organization=self.project.organization,
            projects=[self.project],
        )
        groups = results["groups"]
        assert len(groups) == 3
        assert groups[0]["by"] == {"platform": "android", "transaction": "/hello"}
        assert groups[0]["series"] == {field: [None, 1.0, 2.0]}
        assert groups[1]["by"] == {"platform": "ios", "transaction": "/hello"}
        assert groups[1]["series"] == {field: [None, 3.0, 3.0]}
        assert groups[2]["by"] == {"platform": "windows", "transaction": "/world"}
        assert groups[2]["series"] == {field: [None, 5.0, 3.0]}

        # Query with one aggregation, one group by and two filters.
        field = f"sum({TransactionMRI.DURATION.value})"
        results = run_metrics_query(
            fields=[field],
            query="platform:ios transaction:/hello",
            group_bys=["platform"],
            start=self.now() - timedelta(minutes=30),
            end=self.now() + timedelta(hours=1, minutes=30),
            interval=3600,
            use_case_id=UseCaseID.TRANSACTIONS,
            organization=self.project.organization,
            projects=[self.project],
        )
        groups = results["groups"]
        assert len(groups) == 1
        assert groups[0]["by"] == {"platform": "ios"}
        assert groups[0]["series"] == {field: [None, 3.0, 3.0]}

    @pytest.mark.skip(reason="use_case_id for Sessions is wrongly set to '' instead of 'sessions'")
    def test_with_sessions(self) -> None:
        self.store_session(
            self.build_session(
                project_id=self.project.id,
                started=(self.now() + timedelta(minutes=30)).timestamp(),
                status="exited",
                release="foobar@2.0",
                errors=2,
            )
        )

        field = f"sum({SessionMRI.RAW_SESSION.value})"
        results = run_metrics_query(
            fields=[field],
            query=None,
            group_bys=None,
            start=self.now(),
            end=self.now() + timedelta(hours=1),
            interval=3600,
            use_case_id=UseCaseID.SESSIONS,
            organization=self.project.organization,
            projects=[self.project],
        )
        groups = results["groups"]
        assert len(groups) == 1
        assert groups[0]["by"] == {}
        assert groups[0]["series"] == {field: [60.0]}
