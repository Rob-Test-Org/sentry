# Generated by Django 2.2.28 on 2023-02-14 19:42
import uuid
from datetime import datetime
from typing import Any, Mapping, Sequence, Tuple

from django.db import migrations
from django.db.models import Count

from sentry.event_manager import GroupInfo
from sentry.eventstore.models import Event
from sentry.issues.grouptype import (
    PerformanceConsecutiveDBQueriesGroupType,
    PerformanceFileIOMainThreadGroupType,
    PerformanceMNPlusOneDBQueriesGroupType,
    PerformanceNPlusOneAPICallsGroupType,
    PerformanceNPlusOneGroupType,
    PerformanceRenderBlockingAssetSpanGroupType,
    PerformanceSlowDBQueryGroupType,
    PerformanceUncompressedAssetsGroupType,
)
from sentry.issues.ingest import process_occurrence_data, send_issue_occurrence_to_eventstream
from sentry.issues.issue_occurrence import IssueOccurrence, IssueOccurrenceData
from sentry.issues.occurrence_consumer import lookup_event
from sentry.new_migrations.migrations import CheckedMigration
from sentry.snuba.dataset import Dataset, EntityKey


def backfill_eventstream(apps, schema_editor):
    """
    Backfills Performance-issue events from the transaction table to the IssuePlatform dataset(search_issues).
    1. Read all transactions that back a performance-issue(s) with the following criteria:
        a. non-null group_ids column
        b.
    2. Prepare and format each transaction to be submitted through the eventstream.
    3. Send it through the eventstream.
    """

    Group = apps.get_model("sentry", "Group")
    GroupHash = apps.get_model("sentry", "GroupHash")

    project_perf_issues = (
        Group.objects.all()
        .filter(
            type__in=(
                PerformanceSlowDBQueryGroupType.type_id,
                PerformanceRenderBlockingAssetSpanGroupType.type_id,
                PerformanceNPlusOneGroupType.type_id,
                PerformanceConsecutiveDBQueriesGroupType.type_id,
                PerformanceFileIOMainThreadGroupType.type_id,
                PerformanceNPlusOneAPICallsGroupType.type_id,
                PerformanceMNPlusOneDBQueriesGroupType.type_id,
                PerformanceUncompressedAssetsGroupType.type_id,
            )
        )
        .values("id", "project_id")
        .annotate(issue_counts=Count("id"))
        .order_by("project_id")
    )

    for project_perf_issue in project_perf_issues:
        backfill_by_project(project_perf_issue["project_id"], Group, GroupHash)


def backfill_by_project(project_id: int, Group: Any, GroupHash: Any):
    # retrieve rows
    rows = _query_performance_issue_events(
        project_ids=[project_id],
        start=datetime(2008, 5, 8),
        end=datetime.now(),
    )

    for row in rows:
        try:
            # don't need to store in node_store since it should be there already
            # create issue occurrence
            # save issue occurrence
            project_id = row["project_id"]
            group_id = row["group_id"]
            event_id = row["event_id"]

            group: Group = Group.objects.get(id=group_id)
            group_hash: GroupHash = GroupHash.objects.get(group_id=group_id)

            event: Event = lookup_event(project_id=project_id, event_id=event_id)

            from sentry import eventtypes

            et = eventtypes.get(group.data.get("type", "default"))()
            issue_title = et.get_title(group.data["metadata"])
            assert issue_title
            # need to map the base raw data to an issue occurrence
            # make sure this is consistent with how we plan to ingest performance issue occurrences
            occurrence_data: IssueOccurrenceData = IssueOccurrenceData(
                id=uuid.uuid4().hex,
                project_id=project_id,
                event_id=event_id,
                fingerprint=[group_hash.hash],
                issue_title=issue_title,  # TODO: verify
                subtitle=group.culprit,  # TODO: verify
                resource_id=None,
                evidence_data={},  # TODO: verify
                evidence_display=[],  # TODO: verify
                type=group.type,
                detection_time=datetime.now().timestamp(),
                level=None,
            )

            occurrence, group_info = __save_issue_occurrence(occurrence_data, event, group)

            send_issue_occurrence_to_eventstream(event, occurrence, group_info, skip_consume=True)
        except Exception:
            print("Failed to process row")  # noqa: S002


def __save_issue_occurrence(
    occurrence_data: IssueOccurrenceData, event: Event, group
) -> Tuple[IssueOccurrence, GroupInfo]:
    process_occurrence_data(occurrence_data)
    # Convert occurrence data to `IssueOccurrence`
    occurrence = IssueOccurrence.from_dict(occurrence_data)
    if occurrence.event_id != event.event_id:
        raise ValueError("IssueOccurrence must have the same event_id as the passed Event")
    # Note: For now we trust the project id passed along with the event. Later on we should make
    # sure that this is somehow validated.
    occurrence.save()

    # don't need to create releases or environments since they should be created already

    # synthesize a 'fake' group_info based off of existing data in postgres
    group_info: GroupInfo = GroupInfo(group=group, is_new=False, is_regression=False)

    return occurrence, group_info


# def __send_issue_occurrence_to_eventstream(
#     event: Event, occurrence: IssueOccurrence, group_info: GroupInfo
# ) -> None:
#     from sentry import eventstream
#
#     group_event = event.for_group(group_info.group)
#     group_event.occurrence = occurrence
#
#     eventstream.insert(
#         event=group_event,
#         is_new=group_info.is_new,
#         is_regression=group_info.is_regression,
#         is_new_group_environment=group_info.is_new_group_environment,
#         primary_hash=occurrence.fingerprint[0],
#         received_timestamp=group_event.data.get("received") or group_event.datetime,
#         skip_consume=True,
#         group_states=[
#             {
#                 "id": group_info.group.id,
#                 "is_new": group_info.is_new,
#                 "is_regression": group_info.is_regression,
#                 "is_new_group_environment": group_info.is_new_group_environment,
#             }
#         ],
#     )


def _query_performance_issue_events(
    project_ids: Sequence[int], start: datetime, end: datetime
) -> Sequence[Mapping[str, Any]]:
    from snuba_sdk import Column, Condition, Entity, Function, Op, Query, Request

    snuba_request = Request(
        dataset=Dataset.Transactions.value,
        app_id="migration",
        query=Query(
            match=Entity(EntityKey.Transactions.value),
            select=[
                Function("arrayJoin", parameters=[Column("group_ids")], alias="group_id"),
                Column("project_id"),
                Column("event_id"),
            ],
            where=[
                Condition(Column("group_ids"), Op.IS_NOT_NULL),
                Condition(Column("project_id"), Op.IN, project_ids),
                Condition(Column("finish_ts"), Op.GTE, start),
                Condition(Column("finish_ts"), Op.LT, end),
            ],
            groupby=[Column("group_id"), Column("project_id"), Column("event_id")],
        ),
    )
    from sentry.utils.snuba import raw_snql_query

    result_snql = raw_snql_query(
        snuba_request,
        referrer="0372_backfill_perf_issue_events_issue_platform._query_performance_issue_events",
        use_cache=False,
    )

    return result_snql["data"]


class Migration(CheckedMigration):
    # This flag is used to mark that a migration shouldn't be automatically run in production. For
    # the most part, this should only be used for operations where it's safe to run the migration
    # after your code has deployed. So this should not be used for most operations that alter the
    # schema of a table.
    # Here are some things that make sense to mark as dangerous:
    # - Large data migrations. Typically we want these to be run manually by ops so that they can
    #   be monitored and not block the deploy for a long period of time while they run.
    # - Adding indexes to large tables. Since this can take a long time, we'd generally prefer to
    #   have ops run this and not block the deploy. Note that while adding an index is a schema
    #   change, it's completely safe to run the operation after the code has deployed.
    is_dangerous = True

    dependencies = [
        ("sentry", "0371_monitor_make_org_slug_unique"),
    ]

    operations = [
        migrations.RunPython(
            backfill_eventstream,
            reverse_code=migrations.RunPython.noop,
            hints={"tables": ["sentry_groupedmessage", "sentry_grouphash"]},
        )
    ]
