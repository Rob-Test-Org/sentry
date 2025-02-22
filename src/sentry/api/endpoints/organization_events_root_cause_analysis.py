from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from rest_framework.response import Response
from snuba_sdk import Column, Condition, Function, LimitBy, Op

from sentry import features
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.organization_events import OrganizationEventsEndpointBase
from sentry.api.endpoints.organization_events_spans_performance import EventID, get_span_description
from sentry.api.helpers.span_analysis import span_analysis
from sentry.search.events.builder import QueryBuilder
from sentry.search.events.types import QueryBuilderConfig
from sentry.search.utils import parse_datetime_string
from sentry.snuba.dataset import Dataset
from sentry.snuba.metrics_performance import query as metrics_query
from sentry.utils.snuba import raw_snql_query

DEFAULT_LIMIT = 50
QUERY_LIMIT = 10000 // 2
BUFFER = timedelta(hours=6)
REFERRER = "api.organization-events-root-cause-analysis"

_query_thread_pool = ThreadPoolExecutor()


def init_query_builder(params, transaction, regression_breakpoint, type):
    selected_columns = [
        "count(span_id) as span_count",
        "percentileArray(spans_exclusive_time, 0.95) as p95_self_time",
        "array_join(spans_op) as span_op",
        "array_join(spans_group) as span_group",
        # want a single event id to fetch from nodestore for the span description
        "any(id) as sample_event_id",
    ]

    builder = QueryBuilder(
        dataset=Dataset.Discover,
        params=params,
        selected_columns=selected_columns,
        equations=[],
        query=f"transaction:{transaction}",
        orderby=["span_op", "span_group", "p95_self_time"],
        limit=QUERY_LIMIT,
        config=QueryBuilderConfig(
            auto_aggregations=True,
            use_aggregate_conditions=True,
            functions_acl=[
                "array_join",
                "sumArray",
                "percentileArray",
            ],
        ),
    )

    builder.columns.append(
        Function(
            "if",
            [
                Function("greaterOrEquals", [Column("timestamp"), regression_breakpoint]),
                "after",
                "before",
            ],
            "period",
        )
    )
    builder.columns.append(Function("countDistinct", [Column("event_id")], "transaction_count"))
    builder.groupby.append(Column("period"))
    builder.limitby = LimitBy([Column("period")], QUERY_LIMIT)

    # Filter out timestamp because we want to control the timerange for parallelization
    builder.where = [
        condition for condition in builder.where if condition.lhs != Column("timestamp")
    ]
    if type == "before":
        builder.where += [
            Condition(Column("timestamp"), Op.GTE, params.get("start")),
            Condition(Column("timestamp"), Op.LT, regression_breakpoint - BUFFER),
        ]
    else:
        builder.where += [
            Condition(Column("timestamp"), Op.GTE, regression_breakpoint + BUFFER),
            Condition(Column("timestamp"), Op.LT, params.get("end")),
        ]

    return builder


def get_parallelized_snql_queries(transaction, regression_breakpoint, params):
    return [
        init_query_builder(params, transaction, regression_breakpoint, "before").get_snql_query(),
        init_query_builder(params, transaction, regression_breakpoint, "after").get_snql_query(),
    ]


def query_spans(transaction, regression_breakpoint, params):
    snql_queries = get_parallelized_snql_queries(transaction, regression_breakpoint, params)

    # Parallelize the request for span data
    snuba_results = list(_query_thread_pool.map(raw_snql_query, snql_queries, [REFERRER, REFERRER]))
    span_results = []

    # append all the results
    for result in snuba_results:
        output_dict = result["data"]
        span_results += output_dict

    return span_results


@region_silo_endpoint
class OrganizationEventsRootCauseAnalysisEndpoint(OrganizationEventsEndpointBase):
    publish_status = {
        "GET": ApiPublishStatus.UNKNOWN,
    }

    def get(self, request, organization):
        if not features.has(
            "organizations:performance-duration-regression-visible",
            organization,
            actor=request.user,
        ):
            return Response(status=404)

        # TODO: Extract this into a custom serializer to handle validation
        transaction_name = request.GET.get("transaction")
        project_id = request.GET.get("project")
        regression_breakpoint = request.GET.get("breakpoint")
        if not transaction_name or not project_id or not regression_breakpoint:
            # Project ID is required to ensure the events we query for are
            # the same transaction
            return Response(status=400)

        regression_breakpoint = parse_datetime_string(regression_breakpoint)

        params = self.get_snuba_params(request, organization)

        with self.handle_query_errors():
            transaction_count_query = metrics_query(
                ["count()"],
                f"event.type:transaction transaction:{transaction_name} project_id:{project_id}",
                params,
                referrer="api.organization-events-root-cause-analysis",
            )

        if transaction_count_query["data"][0]["count"] == 0:
            return Response(status=400, data="Transaction not found")

        span_data = query_spans(
            transaction=transaction_name,
            regression_breakpoint=regression_breakpoint,
            params=params,
        )

        span_analysis_results = span_analysis(span_data)

        for result in span_analysis_results:
            result["span_description"] = get_span_description(
                EventID(project_id, result["sample_event_id"]),
                result["span_op"],
                result["span_group"],
            )

        limit = int(request.GET.get("per_page", DEFAULT_LIMIT))
        return Response(span_analysis_results[:limit], status=200)
