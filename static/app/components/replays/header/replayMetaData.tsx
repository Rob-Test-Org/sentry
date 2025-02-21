import {Link} from 'react-router';
import styled from '@emotion/styled';

import ErrorCounts from 'sentry/components/replays/header/errorCounts';
import HeaderPlaceholder from 'sentry/components/replays/header/headerPlaceholder';
import {IconCursorArrow} from 'sentry/icons';
import {t} from 'sentry/locale';
import {space} from 'sentry/styles/space';
import EventView from 'sentry/utils/discover/eventView';
import getRouteStringFromRoutes from 'sentry/utils/getRouteStringFromRoutes';
import {ColorOrAlias} from 'sentry/utils/theme';
import {useLocation} from 'sentry/utils/useLocation';
import {useRoutes} from 'sentry/utils/useRoutes';
import type {ReplayError, ReplayRecord} from 'sentry/views/replays/types';

type Props = {
  replayErrors: ReplayError[];
  replayRecord: ReplayRecord | undefined;
};

function ReplayMetaData({replayErrors, replayRecord}: Props) {
  const location = useLocation();
  const routes = useRoutes();
  const referrer = getRouteStringFromRoutes(routes);
  const eventView = EventView.fromLocation(location);

  const domEventsTab = {
    ...location,
    query: {
      referrer,
      ...eventView.generateQueryStringObject(),
      t_main: 'dom',
      f_d_type: 'ui.slowClickDetected',
    },
  };

  return (
    <KeyMetrics>
      <KeyMetricLabel>{t('Dead Clicks')}</KeyMetricLabel>
      <KeyMetricData>
        {replayRecord?.count_dead_clicks ? (
          <Link to={domEventsTab}>
            <ClickCount color="yellow300">
              <IconCursorArrow size="sm" />
              {replayRecord.count_dead_clicks}
            </ClickCount>
          </Link>
        ) : (
          <Count>0</Count>
        )}
      </KeyMetricData>

      <KeyMetricLabel>{t('Rage Clicks')}</KeyMetricLabel>
      <KeyMetricData>
        {replayRecord?.count_rage_clicks ? (
          <Link to={domEventsTab} color="red300">
            <ClickCount color="red300">
              <IconCursorArrow size="sm" />
              {replayRecord.count_rage_clicks}
            </ClickCount>
          </Link>
        ) : (
          <Count>0</Count>
        )}
      </KeyMetricData>

      <KeyMetricLabel>{t('Errors')}</KeyMetricLabel>
      <KeyMetricData>
        {replayRecord ? (
          <ErrorCounts replayErrors={replayErrors} replayRecord={replayRecord} />
        ) : (
          <HeaderPlaceholder width="80px" height="16px" />
        )}
      </KeyMetricData>
    </KeyMetrics>
  );
}

const KeyMetrics = styled('dl')`
  display: grid;
  grid-template-rows: max-content 1fr;
  grid-template-columns: repeat(4, max-content);
  grid-auto-flow: column;
  gap: 0 ${space(3)};
  align-items: center;
  align-self: end;
  color: ${p => p.theme.gray300};
  margin: 0;

  @media (min-width: ${p => p.theme.breakpoints.medium}) {
    justify-self: flex-end;
  }
`;

const KeyMetricLabel = styled('dt')`
  font-size: ${p => p.theme.fontSizeMedium};
`;

const KeyMetricData = styled('dd')`
  font-size: ${p => p.theme.fontSizeExtraLarge};
  font-weight: normal;
  display: flex;
  align-items: center;
  gap: ${space(1)};
  line-height: ${p => p.theme.text.lineHeightBody};
`;

const Count = styled('span')`
  font-variant-numeric: tabular-nums;
`;

const ClickCount = styled(Count)<{color: ColorOrAlias}>`
  color: ${p => p.theme[p.color]};
  display: flex;
  gap: ${space(0.75)};
  align-items: center;
`;

export default ReplayMetaData;
