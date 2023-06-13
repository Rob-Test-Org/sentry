from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers


class GlobalParams:
    ORG_SLUG = OpenApiParameter(
        name="organization_slug",
        description="The slug of the organization the resource belongs to.",
        required=True,
        type=str,
        location="path",
    )
    PROJECT_SLUG = OpenApiParameter(
        name="project_slug",
        description="The slug of the project the resource belongs to.",
        required=True,
        type=str,
        location="path",
    )
    TEAM_SLUG = OpenApiParameter(
        name="team_slug",
        description="The slug of the team the resource belongs to.",
        required=True,
        type=str,
        location="path",
    )
    STATS_PERIOD = OpenApiParameter(
        name="statsPeriod",
        location="query",
        required=False,
        type=str,
        description="""The period of time for the query, will override the start & end parameters, a number followed by one of:
- `d` for days
- `h` for hours
- `m` for minutes
- `s` for seconds
- `w` for weeks

For example `24h`, to mean query data starting from 24 hours ago to now.""",
    )
    START = OpenApiParameter(
        name="start",
        location="query",
        required=False,
        type=OpenApiTypes.DATETIME,
        description="The start of the period of time for the query, expected in ISO-8601 format. For example `2001-12-14T12:34:56.7890`",
    )
    END = OpenApiParameter(
        name="end",
        location="query",
        required=False,
        type=OpenApiTypes.DATETIME,
        description="The end of the period of time for the query, expected in ISO-8601 format. For example `2001-12-14T12:34:56.7890`",
    )
    PROJECT = OpenApiParameter(
        name="project",
        location="query",
        required=False,
        many=True,
        type=int,
        description="The ids of projects to filter by. `-1` means all available projects. If this parameter is omitted, the request will default to using 'My Projects'",
    )
    ENVIRONMENT = OpenApiParameter(
        name="environment",
        location="query",
        required=False,
        many=True,
        type=str,
        description="The name of environments to filter by.",
    )

    @staticmethod
    def name(description: str, required: bool = False) -> OpenApiParameter:
        return OpenApiParameter(
            name="name",
            location="query",
            required=required,
            type=str,
            description=description,
        )

    @staticmethod
    def slug(description: str, required: bool = False) -> OpenApiParameter:
        return OpenApiParameter(
            name="slug",
            location="query",
            required=required,
            type=str,
            description=description,
        )


class SCIMParams:
    MEMBER_ID = OpenApiParameter(
        name="member_id",
        location="path",
        required=True,
        type=int,
        description="The id of the member you'd like to query.",
    )
    TEAM_ID = OpenApiParameter(
        name="team_id",
        location="path",
        required=True,
        type=int,
        description="The id of the team you'd like to query / update.",
    )


class IssueAlertParams:
    ISSUE_RULE_ID = OpenApiParameter(
        name="rule_id",
        location="path",
        required=True,
        type=int,
        description="The id of the rule you'd like to query",
    )


class VisibilityParams:
    QUERY = OpenApiParameter(
        name="query",
        location="query",
        required=False,
        type=str,
        description="""The search filter for your query, read more about query syntax [here](https://docs.sentry.io/product/sentry-basics/search/)

example: `query=(transaction:foo AND release:abc) OR (transaction:[bar,baz] AND release:def)`
""",
    )
    FIELD = OpenApiParameter(
        name="field",
        location="query",
        required=True,
        type=str,
        many=True,
        description="""The fields, functions, or equations to request for the query. At most 20 fields can be selected per request. Each field can be one of the following types:
- A built-in key field. See possible fields in the [properties table](/product/sentry-basics/search/searchable-properties/#properties-table), under any field that is an event property
    - example: `field=transaction`
- A tag. Tags should use the `tag[]` formatting to avoid ambiguity with any fields
    - example: `field=tag[isEnterprise]`
- A function which will be in the format of `function_name(parameters,...)`. See possible functions in the [query builder documentation](/product/discover-queries/query-builder/#stacking-functions)
    - when a function is included, Discover will group by any tags or fields
    - example: `field=count_if(transaction.duration,greater,300)`
- An equation when prefixed with `equation|`. Read more about [equations here](https://docs.sentry.io/product/discover-queries/query-builder/query-equations/)
    - example: `field=equation|count_if(transaction.duration,greater,300) / count() * 100`
""",
    )
    SORT = OpenApiParameter(
        name="sort",
        location="query",
        required=False,
        type=str,
        description="What to order the results of the query by. Must be something in the `field` list, excluding equations.",
    )
    PER_PAGE = OpenApiParameter(
        name="per_page",
        location="query",
        required=False,
        type=int,
        description="Limit the number of rows to return in the result. Default and maximum allowed is 100.",
    )


class CursorQueryParam(serializers.Serializer):
    cursor = serializers.CharField(
        help_text="A pointer to the last object fetched and its sort order; used to retrieve the next or previous results.",
        required=False,
    )


class MonitorParams:
    MONITOR_SLUG = OpenApiParameter(
        name="monitor_slug",
        location="path",
        required=True,
        type=str,
        description="The slug of the monitor",
    )
    CHECKIN_ID = OpenApiParameter(
        name="checkin_id",
        location="path",
        required=True,
        type=OpenApiTypes.UUID,
        description="The id of the check-in",
    )


class EventParams:
    EVENT_ID = OpenApiParameter(
        name="event_id",
        location="path",
        required=True,
        type=OpenApiTypes.UUID,
        description="The id of the event",
    )

    FRAME_IDX = OpenApiParameter(
        name="frame_idx",
        location="query",
        required=True,  # TODO: make not required
        type=int,
        description="Index of the frame that should be used for source map resolution.",
    )

    EXCEPTION_IDX = OpenApiParameter(
        name="exception_idx",
        location="query",
        required=True,
        type=int,
        description="Index of the exception that should be used for source map resolution.",
    )


class ProjectParams:
    ACTIONS = OpenApiParameter(
        name="actions",
        location="query",
        required=False,
        type=str,
        description="The actions to filter by. See [actions](/product/discover-queries/actions/) for more details.",
    )

    ACTION_MATCH = OpenApiParameter(
        name="actionMatch",
        required=False,
        type=str,
        description="The action match to filter by. See [action match](/product/discover-queries/action-match/) for more details.",
    )

    CONDITIONS = OpenApiParameter(
        name="conditions",
        location="query",
        required=False,
        type=str,
        description="The conditions to filter by. See [conditions](/product/discover-queries/conditions/) for more details.",
    )

    DEFAULT_RULES = OpenApiParameter(
        name="default_rules",
        location="query",
        required=False,
        type=bool,
        description="Defaults to true where the behavior is to alert the user on every new issue. Setting this to false will turn this off and the user must create their own alerts to be notified of new issues.",
    )

    FILTERS = OpenApiParameter(
        name="filters",
        location="query",
        required=False,
        type=str,
        description="The filters to filter by. See [filters](/product/discover-queries/filters/) for more details.",
    )

    FILTER_MATCH = OpenApiParameter(
        name="filterMatch",
        location="query",
        required=False,
        type=str,
        description="The filter match to filter by. See [filter match](/product/discover-queries/filter-match/) for more details.",
    )

    OWNER = OpenApiParameter(
        name="owner",
        location="query",
        required=False,
        type=str,
        description="The owner to filter by. See [owner](/product/discover-queries/owner/) for more details.",
    )

    @staticmethod
    def platform(description: str) -> OpenApiParameter:
        return OpenApiParameter(
            name="platform",
            location="query",
            required=False,
            type=str,
            description=description,
        )


class TeamParams:
    DETAILED = OpenApiParameter(
        name="detailed",
        location="query",
        required=False,
        type=str,
        description='Specify "0" to return team details that do not include projects',
    )
