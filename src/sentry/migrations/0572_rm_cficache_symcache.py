# Generated by Django 3.2.20 on 2023-10-05 09:51

from django.db import migrations

from sentry.new_migrations.migrations import CheckedMigration
from sentry.utils.query import RangeQuerySetWrapperWithProgressBar

# These two filetypes have not been created ever since
# <https://github.com/getsentry/sentry/commit/c14c8f0e3a30fb5c2221fdefa4c0f5167bdc8986#diff-08e824e030b14e7936ffeda41ccf81d8feed2cdcdfbc522d0c46d0064f3640c9L750>
# But there seems to be quite some leftover `File` objects sticking around we want to remove.
TYPES_TO_DELETE = ("project.symcache", "project.cficache")


def rm_cficache_symcache(apps, schema_editor):
    File = apps.get_model("sentry", "File")

    # According to <https://develop.sentry.dev/database-migrations/#filters>:
    # > it is better to iterate over the entire table instead of using a filter
    # Also, there is no index on `type` anyway.
    for file in RangeQuerySetWrapperWithProgressBar(File.objects.filter(type__in=TYPES_TO_DELETE)):
        if file.type in TYPES_TO_DELETE:
            file.delete()


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
        ("sentry", "0571_add_hybrid_cloud_foreign_key_to_slug_reservation"),
    ]

    operations = [
        migrations.RunPython(
            rm_cficache_symcache,
            migrations.RunPython.noop,
            hints={
                "tables": [
                    "sentry_file",
                    "sentry_fileblob",
                    "sentry_fileblobindex",
                    "sentry_fileblobowner",
                ]
            },
        ),
    ]
