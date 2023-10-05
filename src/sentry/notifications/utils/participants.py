from __future__ import annotations

import logging
from collections import defaultdict
from typing import (
    TYPE_CHECKING,
    Any,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Sequence,
    Tuple,
    Union,
)

from django.db.models import Q

from sentry import features
from sentry.models import (
    ActorTuple,
    Group,
    GroupAssignee,
    GroupSubscription,
    NotificationSetting,
    Organization,
    OrganizationMember,
    OrganizationMemberTeam,
    Project,
    Release,
    Rule,
    Team,
    User,
)
from sentry.models.commit import Commit
from sentry.models.projectownership import ProjectOwnership
from sentry.models.rulesnooze import RuleSnooze
from sentry.notifications.helpers import (
    get_values_by_provider_by_type,
    should_use_notifications_v2,
    transform_to_notification_settings_by_recipient,
)
from sentry.notifications.notificationcontroller import NotificationController
from sentry.notifications.notify import notification_providers
from sentry.notifications.types import (
    NOTIFICATION_SETTING_TYPES,
    ActionTargetType,
    FallthroughChoiceType,
    GroupSubscriptionReason,
    NotificationSettingEnum,
    NotificationSettingOptionValues,
    NotificationSettingsOptionEnum,
    NotificationSettingTypes,
)
from sentry.services.hybrid_cloud.actor import ActorType, RpcActor
from sentry.services.hybrid_cloud.notifications import notifications_service
from sentry.services.hybrid_cloud.organization import organization_service
from sentry.services.hybrid_cloud.user import RpcUser
from sentry.services.hybrid_cloud.user.service import user_service
from sentry.services.hybrid_cloud.user_option import get_option_from_list, user_option_service
from sentry.types.integrations import ExternalProviders
from sentry.utils import metrics
from sentry.utils.committers import AuthorCommitsSerialized, get_serialized_event_file_committers

if TYPE_CHECKING:
    from sentry.eventstore.models import Event

logger = logging.getLogger(__name__)


AVAILABLE_PROVIDERS = {
    ExternalProviders.EMAIL,
    ExternalProviders.SLACK,
}

FALLTHROUGH_NOTIFICATION_LIMIT = 20


class ParticipantMap:
    _dict: MutableMapping[ExternalProviders, MutableMapping[RpcActor, int]]

    def __init__(self) -> None:
        self._dict = defaultdict(dict)

    def get_participants_by_provider(
        self, provider: ExternalProviders
    ) -> set[Tuple[RpcActor, int]]:
        return {(k, v) for k, v in self._dict.get(provider, {}).items()}

    def add(self, provider: ExternalProviders, participant: RpcActor, reason: int) -> None:
        self._dict[provider][participant] = reason

    def add_all(self, provider: ExternalProviders, actor_group: Mapping[RpcActor, int]) -> None:
        self._dict[provider].update(actor_group)

    def update(self, other: ParticipantMap) -> None:
        for (provider, actor_group) in other._dict.items():
            self.add_all(provider, actor_group)

    def get_participant_sets(self) -> Iterable[Tuple[ExternalProviders, Iterable[RpcActor]]]:
        return ((provider, participants.keys()) for (provider, participants) in self._dict.items())

    def delete_participant_by_id(
        self, provider: ExternalProviders, actor_type: ActorType, participant_id: int
    ) -> None:
        provider_group = self._dict[provider]
        to_delete = [
            participant
            for participant in provider_group.keys()
            if participant.actor_type == actor_type and participant.id == participant_id
        ]
        for participant in to_delete:
            del provider_group[participant]

    def is_empty(self) -> bool:
        return not self._dict

    def split_participants_and_context(
        self,
    ) -> Iterable[
        Tuple[ExternalProviders, Iterable[RpcActor], Mapping[RpcActor, Mapping[str, Any]]]
    ]:
        for provider, participants_with_reasons in self._dict.items():
            extra_context = {
                participant: {"reason": reason}
                for participant, reason in participants_with_reasons.items()
                if participant is not None
            }
            yield provider, participants_with_reasons.keys(), extra_context


def get_providers_from_which_to_remove_user(
    user_id: int,
    participants_by_provider: ParticipantMap,
) -> set[ExternalProviders]:
    """
    Given a mapping of provider to mappings of users to why they should receive
    notifications for an activity, return the set of providers where the user
    has opted out of receiving notifications.
    """

    providers = {
        provider
        for provider, participants in participants_by_provider.get_participant_sets()
        if user_id in map(lambda p: int(p.id), participants)
    }

    if (
        get_option_from_list(
            user_option_service.get_many(
                filter={"user_ids": [user_id], "keys": ["self_notifications"]}
            ),
            key="self_notifications",
            default="0",
        )
        == "0"
    ):
        return providers
    return set()


def get_participants_for_group(group: Group, user_id: int | None = None) -> ParticipantMap:
    participants_by_provider: ParticipantMap = GroupSubscription.objects.get_participants(group)
    if user_id:
        # Optionally remove the actor that created the activity from the recipients list.
        providers = get_providers_from_which_to_remove_user(user_id, participants_by_provider)
        for provider in providers:
            participants_by_provider.delete_participant_by_id(provider, ActorType.USER, user_id)

    return participants_by_provider


def get_reason(
    user: Union[User, RpcActor],
    value: NotificationSettingOptionValues | NotificationSettingsOptionEnum,
    user_ids: set[int],
) -> int | None:
    # Members who opt into all deploy emails.
    if value in [NotificationSettingOptionValues.ALWAYS, NotificationSettingsOptionEnum.ALWAYS]:
        return GroupSubscriptionReason.deploy_setting

    # Members which have been seen in the commit log.
    elif (
        value
        in [
            NotificationSettingOptionValues.COMMITTED_ONLY,
            NotificationSettingsOptionEnum.COMMITTED_ONLY,
        ]
        and user.id in user_ids
    ):
        return GroupSubscriptionReason.committed
    return None


def get_participants_for_release(
    projects: Iterable[Project], organization: Organization, commited_user_ids: set[int]
) -> ParticipantMap:
    # Collect all users with verified emails on a team in the related projects.
    user_ids = list(
        OrganizationMember.objects.filter(
            teams__projectteam__project__in=projects,
            user_is_active=True,
            user_id__isnull=False,
        )
        .distinct()
        .values_list("user_id", flat=True)
    )

    # filter those user ids by verified emails
    user_ids = user_service.get_many_ids(
        filter=dict(
            user_ids=user_ids,
            email_verified=True,
        )
    )

    actors = RpcActor.many_from_object(RpcUser(id=user_id) for user_id in user_ids)
    if should_use_notifications_v2(organization):
        providers_by_recipient = notifications_service.get_participants(
            recipients=actors,
            project_ids=[project.id for project in projects],
            organization_id=organization.id,
            type=NotificationSettingEnum.DEPLOY,
        )

        users_to_reasons_by_provider = ParticipantMap()
        for actor in actors:
            settings = providers_by_recipient.get(actor.id, {})
            for provider_str, val_str in settings.items():
                provider = ExternalProviders(provider_str)
                val = NotificationSettingsOptionEnum(val_str)
                reason = get_reason(actor, val, commited_user_ids)
                if reason:
                    users_to_reasons_by_provider.add(provider, actor, reason)
        return users_to_reasons_by_provider

    # Get all the involved users' settings for deploy-emails (including
    # users' organization-independent settings.)
    notification_settings = notifications_service.get_settings_for_recipient_by_parent(
        type=NotificationSettingTypes.DEPLOY,
        recipients=actors,
        parent_id=organization.id,
    )
    notification_settings_by_recipient = transform_to_notification_settings_by_recipient(
        notification_settings, actors
    )

    # Map users to their setting value. Prioritize user/org specific, then
    # user default, then product default.
    users_to_reasons_by_provider = ParticipantMap()
    for actor in actors:
        notification_settings_by_scope = notification_settings_by_recipient.get(actor, {})
        values_by_provider = get_values_by_provider_by_type(
            notification_settings_by_scope,
            notification_providers(),
            NotificationSettingTypes.DEPLOY,
            actor,
        )
        for provider, value in values_by_provider.items():
            reason_option = get_reason(actor, value, commited_user_ids)
            if reason_option:
                users_to_reasons_by_provider.add(provider, actor, reason_option)
    return users_to_reasons_by_provider


def get_owners(
    project: Project,
    event: Event | None = None,
    fallthrough_choice: FallthroughChoiceType | None = None,
) -> Tuple[List[RpcActor], str]:
    """
    Given a project and an event, decide which users and teams are the owners.

    If when checking owners, there is a rule match we only notify the last owner
    (would-be auto-assignee) unless the organization passes the feature-flag
    """

    if event:
        owners, _ = ProjectOwnership.get_owners(project.id, event.data)
    else:
        owners = ProjectOwnership.Everyone

    if not owners:
        outcome = "empty"
        recipients: List[RpcActor] = list()

    elif owners == ProjectOwnership.Everyone:
        outcome = "everyone"
        users = user_service.get_many(
            filter=dict(user_ids=list(project.member_set.values_list("user_id", flat=True)))
        )
        recipients = RpcActor.many_from_object(users)

    else:
        outcome = "match"
        resolved_owners = ActorTuple.resolve_many(owners)
        recipients = RpcActor.many_from_object(resolved_owners)
        # Used to suppress extra notifications to all matched owners, only notify the would-be auto-assignee
        if not features.has("organizations:notification-all-recipients", project.organization):
            recipients = recipients[-1:]

    return (recipients, outcome)


def get_owner_reason(
    project: Project,
    target_type: ActionTargetType,
    event: Event | None = None,
    notification_type: NotificationSettingTypes = NotificationSettingTypes.ISSUE_ALERTS,
    fallthrough_choice: FallthroughChoiceType | None = None,
) -> str | None:
    """
    Provide a human readable reason for why a user is receiving a notification.
    Currently only used to explain "issue owners" w/ fallthrough to everyone
    """
    # Sent to a specific user or team
    if target_type != ActionTargetType.ISSUE_OWNERS:
        return None

    # Not an issue alert
    if event is None or notification_type != NotificationSettingTypes.ISSUE_ALERTS:
        return None

    # Describe why an issue owner was notified
    if fallthrough_choice == FallthroughChoiceType.ALL_MEMBERS:
        return f"We notified all members in the {project.get_full_name()} project of this issue"
    if fallthrough_choice == FallthroughChoiceType.ACTIVE_MEMBERS:
        return f"We notified recently active members in the {project.get_full_name()} project of this issue"

    return None


def get_suspect_commit_users(project: Project, event: Event) -> List[RpcUser]:
    """
    Returns a list of users that are suspect committers for the given event.

    `project`: The project that the event is associated to
    `event`: The event that suspect committers are wanted for
    """

    committers: Sequence[AuthorCommitsSerialized] = get_serialized_event_file_committers(
        project, event
    )
    user_emails = [committer["author"]["email"] for committer in committers]  # type: ignore
    suspect_committers = user_service.get_many_by_email(emails=user_emails, is_verified=True)
    in_project_user_ids = set(
        OrganizationMember.objects.filter(
            teams__projectteam__project__in=[project],
            user_id__in=[owner.id for owner in suspect_committers],
        ).values_list("user_id", flat=True)
    )

    return [committer for committer in suspect_committers if committer.id in in_project_user_ids]


def dedupe_suggested_assignees(suggested_assignees: Iterable[RpcActor]) -> Iterable[RpcActor]:
    return list({assignee.id: assignee for assignee in suggested_assignees}.values())


def determine_eligible_recipients(
    project: Project,
    target_type: ActionTargetType,
    target_identifier: int | None = None,
    event: Event | None = None,
    fallthrough_choice: FallthroughChoiceType | None = None,
) -> Iterable[RpcActor]:
    """
    Either get the individual recipient from the target type/id or the
    owners as determined by rules for this project and event.
    """
    if not (project and project.teams.exists()):
        logger.debug(f"Tried to send notification to invalid project: {project}")

    elif target_type == ActionTargetType.MEMBER:
        user = get_user_from_identifier(project, target_identifier)
        if user:
            return [RpcActor.from_object(user)]

    elif target_type == ActionTargetType.TEAM:
        team = get_team_from_identifier(project, target_identifier)
        if team:
            return [RpcActor.from_orm_team(team)]

    elif target_type == ActionTargetType.ISSUE_OWNERS:
        if not event:
            return []

        suggested_assignees, outcome = get_owners(project, event, fallthrough_choice)

        # We're adding the current assignee to the list of suggested assignees because
        # a new issue could have multiple codeowners and one of them got auto-assigned.
        group_assignee: GroupAssignee | None = GroupAssignee.objects.filter(
            group_id=event.group_id
        ).first()
        if group_assignee:
            outcome = "match"
            assignee_actor = RpcActor.from_orm_actor(
                group_assignee.assigned_actor().resolve_to_actor()
            )
            suggested_assignees.append(assignee_actor)

        suspect_commit_users = None
        if features.has("organizations:streamline-targeting-context", project.organization):
            try:
                suspect_commit_users = RpcActor.many_from_object(
                    get_suspect_commit_users(project, event)
                )
                suggested_assignees.extend(suspect_commit_users)
            except (Release.DoesNotExist, Commit.DoesNotExist):
                logger.info("Skipping suspect committers because release does not exist.")
            except Exception:
                logger.exception("Could not get suspect committers. Continuing execution.")

        metrics.incr(
            "features.owners.send_to",
            tags={
                "outcome": outcome
                if outcome == "match" or fallthrough_choice is None
                else fallthrough_choice.value,
                "hasSuspectCommitters": str(bool(suspect_commit_users)),
            },
        )

        if suggested_assignees:
            return dedupe_suggested_assignees(suggested_assignees)

        return RpcActor.many_from_object(get_fallthrough_recipients(project, fallthrough_choice))

    return set()


def get_send_to(
    project: Project,
    target_type: ActionTargetType,
    target_identifier: int | None = None,
    event: Event | None = None,
    notification_type: NotificationSettingTypes = NotificationSettingTypes.ISSUE_ALERTS,
    fallthrough_choice: FallthroughChoiceType | None = None,
    rules: Iterable[Rule] | None = None,
) -> Mapping[ExternalProviders, set[RpcActor]]:
    recipients = determine_eligible_recipients(
        project, target_type, target_identifier, event, fallthrough_choice
    )

    if rules:
        rule_snoozes = RuleSnooze.objects.filter(Q(rule__in=rules))
        muted_user_ids = []
        for rule_snooze in rule_snoozes:
            if rule_snooze.user_id is None:
                return {}
            else:
                muted_user_ids.append(rule_snooze.user_id)

        if muted_user_ids:
            recipients = filter(
                lambda x: x.actor_type != ActorType.USER or x.id not in muted_user_ids, recipients
            )
    return get_recipients_by_provider(project, recipients, notification_type)


def get_fallthrough_recipients(
    project: Project, fallthrough_choice: FallthroughChoiceType | None
) -> Iterable[RpcUser]:
    if not features.has(
        "organizations:issue-alert-fallback-targeting",
        project.organization,
        actor=None,
    ):
        return []

    if not fallthrough_choice:
        logger.warning(f"Missing fallthrough type in project: {project}")
        return []

    if fallthrough_choice == FallthroughChoiceType.NO_ONE:
        return []

    elif fallthrough_choice == FallthroughChoiceType.ALL_MEMBERS:
        return user_service.get_many(
            filter=dict(user_ids=list(project.member_set.values_list("user_id", flat=True)))
        )

    elif fallthrough_choice == FallthroughChoiceType.ACTIVE_MEMBERS:
        member_users = user_service.get_many(
            filter={
                "user_ids": list(project.member_set.values_list("user_id", flat=True)),
            },
        )
        member_users.sort(
            key=lambda u: u.last_active.isoformat() if u.last_active else "", reverse=True
        )
        return member_users[:FALLTHROUGH_NOTIFICATION_LIMIT]

    raise NotImplementedError(f"Unknown fallthrough choice: {fallthrough_choice}")


def get_user_from_identifier(
    project: Project, target_identifier: str | int | None
) -> RpcUser | None:
    if target_identifier is None:
        return None

    try:
        ident = int(target_identifier)
    except ValueError:
        return None

    try:
        organization_member_team = OrganizationMember.objects.get(
            organization_id=project.organization_id, user_id=ident
        )
    except OrganizationMember.DoesNotExist:
        return None

    team_ids = [t.id for t in project.teams.all()]
    omt = OrganizationMemberTeam.objects.filter(
        organizationmember_id=organization_member_team.id, team_id__in=team_ids
    ).first()
    if omt is None:
        return None
    return user_service.get_user(ident)


def get_team_from_identifier(project: Project, target_identifier: str | int | None) -> Team | None:
    if target_identifier is None:
        return None

    try:
        return Team.objects.get(id=int(target_identifier), projectteam__project=project)
    except Team.DoesNotExist:
        return None


def partition_recipients(
    recipients: Iterable[RpcActor],
) -> Mapping[ActorType, set[RpcActor]]:
    mapping = defaultdict(set)
    for recipient in recipients:
        mapping[recipient.actor_type].add(recipient)
    return mapping


def get_users_from_team_fall_back(
    teams: Iterable[RpcActor],
    recipients_by_provider: Mapping[ExternalProviders, Iterable[RpcActor]],
) -> Iterable[RpcUser]:
    assert all(team.actor_type == ActorType.TEAM for team in teams)

    teams_to_fall_back = set(teams)
    for recipients in recipients_by_provider.values():
        for recipient in recipients:
            teams_to_fall_back.remove(recipient)

    user_ids: set[int] = set()
    for team in teams_to_fall_back:
        # Fall back to notifying each subscribed user if there aren't team notification settings
        members = organization_service.get_team_members(team_id=team.id)
        user_ids |= {member.user_id for member in members if member.user_id is not None}
    return user_service.get_many(filter={"user_ids": list(user_ids)})


def combine_recipients_by_provider(
    teams_by_provider: Mapping[ExternalProviders, Iterable[RpcActor]],
    users_by_provider: Mapping[ExternalProviders, Iterable[RpcActor]],
) -> Mapping[ExternalProviders, set[RpcActor]]:
    """TODO(mgaeta): Make this more generic and move it to utils."""
    recipients_by_provider = defaultdict(set)
    for provider, teams in teams_by_provider.items():
        for team in teams:
            recipients_by_provider[provider].add(team)
    for provider, users in users_by_provider.items():
        for user in users:
            recipients_by_provider[provider].add(user)
    return recipients_by_provider


def get_recipients_by_provider(
    project: Project,
    recipients: Iterable[RpcActor],
    notification_type: NotificationSettingTypes = NotificationSettingTypes.ISSUE_ALERTS,
) -> Mapping[ExternalProviders, set[RpcActor]]:
    """Get the lists of recipients that should receive an Issue Alert by ExternalProvider."""
    setting_type = NotificationSettingEnum(NOTIFICATION_SETTING_TYPES[notification_type])

    # notification v2 is enabled for the organization
    if should_use_notifications_v2(project.organization):
        controller = NotificationController(
            recipients=recipients,
            organization_id=project.organization_id,
            project_ids=[project.id],
            type=setting_type,
        )
        return controller.get_notification_recipients(type=setting_type)

    recipients_by_type = partition_recipients(recipients)
    teams = recipients_by_type[ActorType.TEAM]
    users = recipients_by_type[ActorType.USER]

    # First evaluate the teams for old notification settings.
    teams_by_provider: Mapping[
        ExternalProviders, Iterable[RpcActor]
    ] = NotificationSetting.objects.filter_to_accepting_recipients(
        project, teams, notification_type
    )

    # Teams cannot receive emails so omit EMAIL settings.
    teams_by_provider = {
        provider: teams
        for provider, teams in teams_by_provider.items()
        if provider != ExternalProviders.EMAIL
    }

    # If there are any teams that didn't get added, fall back and add all users.
    users |= set(RpcActor.many_from_object(get_users_from_team_fall_back(teams, teams_by_provider)))

    # Repeat for users.
    users_by_provider: Mapping[
        ExternalProviders, Iterable[RpcActor]
    ] = NotificationSetting.objects.filter_to_accepting_recipients(
        project, users, notification_type
    )

    return combine_recipients_by_provider(teams_by_provider, users_by_provider)
