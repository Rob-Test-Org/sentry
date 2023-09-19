from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import region_silo_endpoint
from sentry.api.bases.project import ProjectEndpoint
from sentry.api.serializers.models.project import SymbolSourcesSerializer
from sentry.apidocs.constants import RESPONSE_FORBIDDEN, RESPONSE_NOT_FOUND
from sentry.apidocs.parameters import GlobalParams
from sentry.lang.native.sources import parse_sources, redact_source_secrets
from sentry.models import Project
from sentry.utils import json


@extend_schema(tags=["Projects"])
@region_silo_endpoint
class ProjectSymbolSourcesEndpoint(ProjectEndpoint):
    publish_status = {
        "GET": ApiPublishStatus.PUBLIC,
    }

    @extend_schema(
        operation_id="Retrieve a Project's symbol sources",
        parameters=[GlobalParams.ORG_SLUG, GlobalParams.PROJECT_SLUG],
        request=None,
        responses={
            200: SymbolSourcesSerializer,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
        # examples=ProjectExamples.DETAILED_PROJECT,
    )
    def get(self, request: Request, project: Project) -> Response:
        """
        Return custom symbol sources configured for an individual project.
        """
        id = request.GET.get("id")
        custom_symbol_sources_json = project.get_option("sentry:symbol_sources") or []
        sources = parse_sources(custom_symbol_sources_json, False)
        redacted = redact_source_secrets(sources)

        if id:
            for source in redacted:
                if source["id"] == id:
                    return Response(source)
            raise Http404

        return Response(redacted)

    @extend_schema(
        operation_id="Retrieve a Project's symbol sources",
        parameters=[GlobalParams.ORG_SLUG, GlobalParams.PROJECT_SLUG],
        request=None,
        responses={
            200: SymbolSourcesSerializer,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
        # examples=ProjectExamples.DETAILED_PROJECT,
    )
    def delete(self, request: Request, project: Project) -> Response:
        """
        Return custom symbol sources configured for an individual project.
        """
        id = request.GET.get("id")
        custom_symbol_sources_json = project.get_option("sentry:symbol_sources") or []

        sources = parse_sources(custom_symbol_sources_json, False)

        if id:
            filtered_sources = [src for src in sources if src["id"] != id]
            if len(filtered_sources) == len(sources):
                raise Http404

            serialized = json.dumps(filtered_sources)
            project.update_option("sentry:symbol_sources", serialized)
            return Response(status=204)

        raise Http404
