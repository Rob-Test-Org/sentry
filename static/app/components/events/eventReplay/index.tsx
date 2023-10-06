import {useCallback} from 'react';

import ErrorBoundary from 'sentry/components/errorBoundary';
import {EventReplaySection} from 'sentry/components/events/eventReplay/eventReplaySection';
import LazyLoad from 'sentry/components/lazyLoad';
import {Group} from 'sentry/types';
import {Event} from 'sentry/types/event';
import {getAnalyticsDataForEvent, getAnalyticsDataForGroup} from 'sentry/utils/events';
import {getReplayIdFromEvent} from 'sentry/utils/replays/getReplayIdFromEvent';
import {useHasOrganizationSentAnyReplayEvents} from 'sentry/utils/replays/hooks/useReplayOnboarding';
import {projectCanUpsellReplay} from 'sentry/utils/replays/projectSupportsReplay';
import useOrganization from 'sentry/utils/useOrganization';
import useProjectFromSlug from 'sentry/utils/useProjectFromSlug';

type Props = {
  event: Event;
  projectSlug: string;
  replayId: undefined | string;
  group?: Group;
};

function EventReplayContent({event, group, replayId}: Props) {
  const organization = useOrganization();
  const {hasOrgSentReplays, fetching} = useHasOrganizationSentAnyReplayEvents();

  const onboardingPanel = useCallback(() => import('./replayInlineOnboardingPanel'), []);
  const replayPreview = useCallback(() => import('./replayPreview'), []);

  if (fetching) {
    return null;
  }

  if (!hasOrgSentReplays) {
    return (
      <ErrorBoundary mini>
        <LazyLoad component={onboardingPanel} />
      </ErrorBoundary>
    );
  }

  if (!replayId) {
    return null;
  }

  const timeOfEvent = event?.dateCreated ?? event.dateReceived;
  const eventTimestampMs = timeOfEvent
    ? Math.floor(new Date(timeOfEvent).getTime() / 1000) * 1000
    : 0;

  return (
    <EventReplaySection>
      <ErrorBoundary mini>
        <LazyLoad
          component={replayPreview}
          replaySlug={replayId}
          orgSlug={organization.slug}
          eventTimestampMs={eventTimestampMs}
          buttonProps={{
            analyticsEventKey: 'issue_details.open_replay_details_clicked',
            analyticsEventName: 'Issue Details: Open Replay Details Clicked',
            analyticsParams: {
              ...getAnalyticsDataForEvent(event),
              ...getAnalyticsDataForGroup(group),
              organization,
            },
          }}
        />
      </ErrorBoundary>
    </EventReplaySection>
  );
}

export default function EventReplay({projectSlug, event, group}: Props) {
  const organization = useOrganization();
  const hasReplaysFeature = organization.features.includes('session-replay');

  const project = useProjectFromSlug({organization, projectSlug});
  const canUpsellReplay = projectCanUpsellReplay(project);
  const replayId = getReplayIdFromEvent(event);

  if (!hasReplaysFeature) {
    return null;
  }

  if (replayId || canUpsellReplay) {
    return <EventReplayContent {...{projectSlug, event, group, replayId}} />;
  }

  return null;
}
