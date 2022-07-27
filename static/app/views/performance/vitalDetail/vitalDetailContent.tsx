import {Fragment, useState} from 'react';
import {browserHistory, InjectedRouter} from 'react-router';
import styled from '@emotion/styled';
import {Location} from 'history';
import omit from 'lodash/omit';

import {Client} from 'sentry/api';
import Feature from 'sentry/components/acl/feature';
import Alert from 'sentry/components/alert';
import ButtonBar from 'sentry/components/buttonBar';
import OptionSelector from 'sentry/components/charts/optionSelector';
import {
  InlineContainer,
  SectionHeading,
  SectionValue,
} from 'sentry/components/charts/styles';
import {getInterval} from 'sentry/components/charts/utils';
import Count from 'sentry/components/count';
import {CreateAlertFromViewButton} from 'sentry/components/createAlertButton';
import DatePageFilter from 'sentry/components/datePageFilter';
import DropdownMenuControlV2 from 'sentry/components/dropdownMenuControlV2';
import {MenuItemProps} from 'sentry/components/dropdownMenuItemV2';
import EnvironmentPageFilter from 'sentry/components/environmentPageFilter';
import SearchBar from 'sentry/components/events/searchBar';
import * as Layout from 'sentry/components/layouts/thirds';
import LoadingIndicator from 'sentry/components/loadingIndicator';
import PageFilterBar from 'sentry/components/organizations/pageFilterBar';
import {normalizeDateTimeParams} from 'sentry/components/organizations/pageFilters/parse';
import * as TeamKeyTransactionManager from 'sentry/components/performance/teamKeyTransactionsManager';
import ProjectPageFilter from 'sentry/components/projectPageFilter';
import {IconCheckmark, IconClose} from 'sentry/icons';
import {t} from 'sentry/locale';
import space from 'sentry/styles/space';
import {Organization, Project} from 'sentry/types';
import {defined} from 'sentry/utils';
import trackAdvancedAnalyticsEvent from 'sentry/utils/analytics/trackAdvancedAnalyticsEvent';
import {getUtcToLocalDateObject} from 'sentry/utils/dates';
import EventView from 'sentry/utils/discover/eventView';
import {WebVital} from 'sentry/utils/discover/fields';
import {Browser} from 'sentry/utils/performance/vitals/constants';
import {decodeScalar} from 'sentry/utils/queryString';
import Teams from 'sentry/utils/teams';
import {MutableSearch} from 'sentry/utils/tokenizeSearch';
import withProjects from 'sentry/utils/withProjects';

import Breadcrumb from '../breadcrumb';
import {VITAL_TO_SETTING} from '../landing/widgets/utils';
import {WIDGET_DEFINITIONS} from '../landing/widgets/widgetDefinitions';
import {VitalWidget} from '../landing/widgets/widgets/vitalWidget';
import {getTransactionSearchQuery} from '../utils';

import Table from './table';
import {
  vitalAbbreviations,
  vitalAlertTypes,
  vitalDescription,
  vitalMap,
  vitalSupportedBrowsers,
} from './utils';
import VitalChart from './vitalChart';
import VitalInfo from './vitalInfo';

const FRONTEND_VITALS = [WebVital.FCP, WebVital.LCP, WebVital.FID, WebVital.CLS];

enum DisplayModes {
  WORST_VITALS = 'Worst Vitals',
  DURATION_P75 = 'P75',
}

type Props = {
  api: Client;
  eventView: EventView;
  location: Location;
  organization: Organization;
  projects: Project[];
  router: InjectedRouter;
  vitalName: WebVital;
};

function getSummaryConditions(query: string) {
  const parsed = new MutableSearch(query);
  parsed.freeText = [];

  return parsed.formatString();
}

function VitalDetailContent(props: Props) {
  const [error, setError] = useState<string | undefined>(undefined);
  const [totalEventsCount, setTotalEventsCount] = useState<number>(0);

  const display = decodeScalar(props.location.query.display, DisplayModes.WORST_VITALS);

  function handleSearch(query: string) {
    const {location} = props;

    const queryParams = normalizeDateTimeParams({
      ...(location.query || {}),
      query,
    });

    // do not propagate pagination when making a new search
    const searchQueryParams = omit(queryParams, 'cursor');

    browserHistory.push({
      pathname: location.pathname,
      query: searchQueryParams,
    });
  }

  function renderCreateAlertButton() {
    const {eventView, organization, projects, vitalName} = props;

    return (
      <CreateAlertFromViewButton
        eventView={eventView}
        organization={organization}
        projects={projects}
        useAlertWizardV3={organization.features.includes('alert-wizard-v3')}
        aria-label={t('Create Alert')}
        alertType={vitalAlertTypes[vitalName]}
        referrer="performance"
      />
    );
  }

  function renderVitalSwitcher() {
    const {vitalName, location, organization} = props;

    const position = FRONTEND_VITALS.indexOf(vitalName);

    if (position < 0) {
      return null;
    }

    const items: MenuItemProps[] = FRONTEND_VITALS.reduce(
      (acc: MenuItemProps[], newVitalName) => {
        const itemProps = {
          key: newVitalName,
          label: vitalAbbreviations[newVitalName],
          onAction: function switchWebVital() {
            browserHistory.push({
              pathname: location.pathname,
              query: {
                ...location.query,
                vitalName: newVitalName,
                cursor: undefined,
              },
            });

            trackAdvancedAnalyticsEvent('performance_views.vital_detail.switch_vital', {
              organization,
              from_vital: vitalAbbreviations[vitalName] ?? 'undefined',
              to_vital: vitalAbbreviations[newVitalName] ?? 'undefined',
            });
          },
        };

        if (vitalName === newVitalName) {
          acc.unshift(itemProps);
        } else {
          acc.push(itemProps);
        }

        return acc;
      },
      []
    );

    return (
      <DropdownMenuControlV2
        items={items}
        triggerLabel={vitalAbbreviations[vitalName]}
        triggerProps={{
          'aria-label': `Web Vitals: ${vitalAbbreviations[vitalName]}`,
          prefix: t('Web Vitals'),
        }}
        placement="bottom left"
      />
    );
  }

  function renderError() {
    if (!error) {
      return null;
    }

    return (
      <Alert type="error" showIcon>
        {error}
      </Alert>
    );
  }

  function generateDisplayOptions() {
    const chartSetting = VITAL_TO_SETTING[vital];

    return [
      {
        value: DisplayModes.WORST_VITALS,
        label: WIDGET_DEFINITIONS({organization})[chartSetting].title,
      },
      {value: DisplayModes.DURATION_P75, label: t(DisplayModes.DURATION_P75)},
    ];
  }

  function handleDisplayChange(value: string) {
    browserHistory.push({
      pathname: location.pathname,
      query: {
        ...location.query,
        display: value,
      },
    });
  }

  function renderContent(vital: WebVital) {
    const {location, organization, eventView, projects} = props;

    const {fields, start, end, statsPeriod, environment, project} = eventView;

    const query = decodeScalar(location.query.query, '');
    const orgSlug = organization.slug;
    const localDateStart = start ? getUtcToLocalDateObject(start) : null;
    const localDateEnd = end ? getUtcToLocalDateObject(end) : null;
    const interval = getInterval(
      {start: localDateStart, end: localDateEnd, period: statsPeriod},
      'high'
    );
    const filterString = getTransactionSearchQuery(location);
    const summaryConditions = getSummaryConditions(filterString);

    const chartSetting = VITAL_TO_SETTING[vital];
    const chartDefinition = WIDGET_DEFINITIONS({organization})[chartSetting];
    chartDefinition.isVitalDetailView = true;

    // ContainerActions: React.FC<{isLoading: boolean}>;
    // chartDefinition: ChartDefinition;
    // chartHeight: number;

    // chartSetting: PerformanceWidgetSetting;
    // eventView: EventView;
    // fields: string[];
    // location: Location;

    // organization: Organization;
    // title: string;
    // titleTooltip: string;

    // chartColor?: string;

    // withStaticFilters?: boolean;

    return (
      <Fragment>
        <FilterActions>
          <PageFilterBar condensed>
            <ProjectPageFilter />
            <EnvironmentPageFilter />
            <DatePageFilter alignDropdown="left" />
          </PageFilterBar>
          <SearchBar
            searchSource="performance_vitals"
            organization={organization}
            projectIds={project}
            query={query}
            fields={fields}
            onSearch={handleSearch}
          />
        </FilterActions>

        {display === DisplayModes.WORST_VITALS ? (
          <VitalWidgetWrapper>
            <VitalWidget
              chartDefinition={chartDefinition}
              chartSetting={chartSetting}
              chartHeight={180}
              fields={['measurements.lcp']}
              location={location}
              ContainerActions={() => null}
              eventView={eventView}
              organization={organization}
              title={WIDGET_DEFINITIONS({organization})[chartSetting].title}
              titleTooltip={WIDGET_DEFINITIONS({organization})[chartSetting].titleTooltip}
              isVitalDetailView
              setTotalEventsCount={setTotalEventsCount}
            />
          </VitalWidgetWrapper>
        ) : (
          <VitalChart
            organization={organization}
            query={query}
            project={project}
            environment={environment}
            start={localDateStart}
            end={localDateEnd}
            statsPeriod={statsPeriod}
            interval={interval}
          />
        )}

        <DropdownContainer>
          <InlineContainer>
            <SectionHeading textColor="gray500">{t('Total Events')}</SectionHeading>
            <SectionValue textColor="gray500" data-test-id="total-value">
              {display === DisplayModes.WORST_VITALS && defined(totalEventsCount) ? (
                <Count value={totalEventsCount} />
              ) : (
                '\u2014'
              )}
            </SectionValue>
          </InlineContainer>
          <InlineContainer data-test-id="display-toggle">
            <OptionSelector
              title={t('Display')}
              selected={display}
              options={generateDisplayOptions()}
              onChange={handleDisplayChange}
            />
          </InlineContainer>
        </DropdownContainer>

        <StyledVitalInfo>
          <VitalInfo
            orgSlug={orgSlug}
            location={location}
            vital={vital}
            project={project}
            environment={environment}
            start={start}
            end={end}
            statsPeriod={statsPeriod}
          />
        </StyledVitalInfo>

        <Teams provideUserTeams>
          {({teams, initiallyLoaded}) =>
            initiallyLoaded ? (
              <TeamKeyTransactionManager.Provider
                organization={organization}
                teams={teams}
                selectedTeams={['myteams']}
                selectedProjects={project.map(String)}
              >
                <Table
                  eventView={eventView}
                  projects={projects}
                  organization={organization}
                  location={location}
                  setError={setError}
                  summaryConditions={summaryConditions}
                />
              </TeamKeyTransactionManager.Provider>
            ) : (
              <LoadingIndicator />
            )
          }
        </Teams>
      </Fragment>
    );
  }

  const {location, organization, vitalName} = props;

  const vital = vitalName || WebVital.LCP;

  return (
    <Fragment>
      <Layout.Header>
        <Layout.HeaderContent>
          <Breadcrumb organization={organization} location={location} vitalName={vital} />
          <Layout.Title>{vitalMap[vital]}</Layout.Title>
        </Layout.HeaderContent>
        <Layout.HeaderActions>
          <ButtonBar gap={1}>
            {renderVitalSwitcher()}
            <Feature organization={organization} features={['incidents']}>
              {({hasFeature}) => hasFeature && renderCreateAlertButton()}
            </Feature>
          </ButtonBar>
        </Layout.HeaderActions>
      </Layout.Header>
      <Layout.Body>
        {renderError()}
        <Layout.Main fullWidth>
          <StyledDescription>{vitalDescription[vitalName]}</StyledDescription>
          <SupportedBrowsers>
            {Object.values(Browser).map(browser => (
              <BrowserItem key={browser}>
                {vitalSupportedBrowsers[vitalName]?.includes(browser) ? (
                  <IconCheckmark color="green300" size="sm" />
                ) : (
                  <IconClose color="red300" size="sm" />
                )}
                {browser}
              </BrowserItem>
            ))}
          </SupportedBrowsers>
          {renderContent(vital)}
        </Layout.Main>
      </Layout.Body>
    </Fragment>
  );
}

export default withProjects(VitalDetailContent);

const StyledDescription = styled('div')`
  font-size: ${p => p.theme.fontSizeMedium};
  margin-bottom: ${space(3)};
`;

const StyledVitalInfo = styled('div')`
  margin-bottom: ${space(3)};
`;

const SupportedBrowsers = styled('div')`
  display: inline-flex;
  gap: ${space(2)};
  margin-bottom: ${space(3)};
`;

const BrowserItem = styled('div')`
  display: flex;
  align-items: center;
  gap: ${space(1)};
`;

const FilterActions = styled('div')`
  display: grid;
  gap: ${space(2)};
  margin-bottom: ${space(2)};

  @media (min-width: ${p => p.theme.breakpoints.small}) {
    grid-template-columns: auto 1fr;
  }
`;

const DropdownContainer = styled('div')`
  border: 1px ${p => p.theme.border} solid;
  border-top: 0;
  border-radius: ${p => `0 0 ${p.theme.borderRadius} ${p.theme.borderRadius}`};
  box-shadow: ${p => p.theme.dropShadowLight};
  margin-bottom: ${space(2)};

  padding: ${space(1)} ${space(1)} ${space(1)} ${space(3)};
  @media (min-width: ${p => p.theme.breakpoints.small}) {
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
  }
`;

const VitalWidgetWrapper = styled('div')`
  padding-top: ${space(2)};
  border: 1px ${p => p.theme.border} solid;
  border-radius: ${p => `${p.theme.borderRadius} ${p.theme.borderRadius} 0 0`};
`;
