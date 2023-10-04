import logging

from django.db import models

from sentry.backup.scopes import RelocationScope
from sentry.constants import LOG_LEVELS, MAX_CULPRIT_LENGTH
from sentry.db.models import (
    BoundedBigIntegerField,
    BoundedPositiveIntegerField,
    FlexibleForeignKey,
    GzippedDictField,
    Model,
    region_silo_only_model,
)

TOMBSTONE_FIELDS_FROM_GROUP = ("project_id", "level", "message", "culprit", "data")


@region_silo_only_model
class GroupTombstone(Model):
    __relocation_scope__ = RelocationScope.Excluded

    previous_group_id = BoundedBigIntegerField(unique=True)
    project = FlexibleForeignKey("sentry.Project")
    level = BoundedPositiveIntegerField(
        choices=[(key, str(val)) for key, val in sorted(LOG_LEVELS.items())],
        default=logging.ERROR,
        blank=True,
    )
    message = models.TextField()
    culprit = models.CharField(max_length=MAX_CULPRIT_LENGTH, blank=True, null=True)
    data = GzippedDictField(blank=True, null=True)
    actor_id = BoundedPositiveIntegerField(null=True)

    class Meta:
        app_label = "sentry"
        db_table = "sentry_grouptombstone"

    def get_event_type(self):
        """
        Return the type of this issue.

        See ``sentry.eventtypes``.
        """
        return self.data.get("type", "default")

    def get_event_metadata(self):
        """
        Return the metadata of this issue.

        See ``sentry.eventtypes``.
        """
        return self.data["metadata"]
