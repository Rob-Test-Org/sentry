import ExternalLink from 'sentry/components/links/externalLink';
import {Layout, LayoutProps} from 'sentry/components/onboarding/gettingStartedDoc/layout';
import {ModuleProps} from 'sentry/components/onboarding/gettingStartedDoc/sdkDocumentation';
import {StepType} from 'sentry/components/onboarding/gettingStartedDoc/step';
import {t, tct} from 'sentry/locale';

// Configuration Start
export const steps = ({
  dsn,
  sourcePackageRegistries,
}: Partial<
  Pick<ModuleProps, 'dsn' | 'sourcePackageRegistries'>
> = {}): LayoutProps['steps'] => [
  {
    type: StepType.INSTALL,
    description: (
      <p>
        {tct(
          'Sentry captures data by using an SDK within your application’s runtime. Add the following to your [pubspec: pubspec.yaml]',
          {
            pubspec: <code />,
          }
        )}
      </p>
    ),
    configurations: [
      {
        language: 'yml',
        partialLoading: sourcePackageRegistries?.isLoading,
        code: `
dependencies:
  sentry: ^${
    sourcePackageRegistries?.isLoading
      ? t('\u2026loading')
      : sourcePackageRegistries?.data?.['sentry.dart']?.version ?? '7.8.0'
  }
        `,
      },
    ],
  },
  {
    type: StepType.CONFIGURE,
    description: (
      <p>
        {tct('Import [sentry: sentry] and initialize it', {
          sentry: <code />,
        })}
      </p>
    ),
    configurations: [
      {
        language: 'dart',
        code: `
import 'package:sentry/sentry.dart';

Future<void> main() async {
  await Sentry.init((options) {
      options.dsn = '${dsn}';
      // Set tracesSampleRate to 1.0 to capture 100% of transactions for performance monitoring.
      // We recommend adjusting this value in production.
      options.tracesSampleRate = 1.0;
    });

  // or define SENTRY_DSN via Dart environment variable (--dart-define)
}
        `,
        additionalInfo: (
          <p>
            {tct(
              'You can configure the [sentryDsn: SENTRY_DSN], [sentryRelease: SENTRY_RELEASE], [sentryDist: SENTRY_DIST], and [sentryEnv: SENTRY_ENVIRONMENT] via the Dart environment variables passing the [dartDefine: --dart-define] flag to the compiler, as noted in the code sample.',
              {
                sentryDsn: <code />,
                sentryRelease: <code />,
                sentryDist: <code />,
                sentryEnv: <code />,
                dartDefine: <code />,
              }
            )}
          </p>
        ),
      },
    ],
  },
  {
    type: StepType.VERIFY,
    description: t(
      'Create an intentional error, so you can test that everything is working:'
    ),
    configurations: [
      {
        language: 'dart',
        code: `
import 'package:sentry/sentry.dart';

try {
  aMethodThatMightFail();
} catch (exception, stackTrace) {
  await Sentry.captureException(
    exception,
    stackTrace: stackTrace,
  );
}
        `,
        additionalInfo: (
          <p>
            {tct(
              "If you're new to Sentry, use the email alert to access your account and complete a product tour.[break] If you're an existing user and have disabled alerts, you won't receive this email.",
              {
                break: <br />,
              }
            )}
          </p>
        ),
      },
    ],
  },
  {
    title: t('Performance'),
    description: t(
      "You'll be able to monitor the performance of your app using the SDK. For example:"
    ),
    configurations: [
      {
        language: 'dart',
        code: `
import 'package:sentry/sentry.dart';

final transaction = Sentry.startTransaction('processOrderBatch()', 'task');

try {
  await processOrderBatch(transaction);
} catch (exception) {
  transaction.throwable = exception;
  transaction.status = SpanStatus.internalError();
} finally {
  await transaction.finish();
}

Future<void> processOrderBatch(ISentrySpan span) async {
  // span operation: task, span description: operation
  final innerSpan = span.startChild('task', description: 'operation');

  try {
    // omitted code
  } catch (exception) {
    innerSpan.throwable = exception;
    innerSpan.status = SpanStatus.notFound();
  } finally {
    await innerSpan.finish();
  }
}
        `,
        additionalInfo: (
          <p>
            {tct(
              'To learn more about the API and automatic instrumentations, check out the [perfDocs: performance documentation].',
              {
                perfDocs: (
                  <ExternalLink href="https://docs.sentry.io/platforms/dart/performance/instrumentation/" />
                ),
              }
            )}
          </p>
        ),
      },
    ],
  },
];
// Configuration End

export function GettingStartedWithDart({
  dsn,
  sourcePackageRegistries,
  ...props
}: ModuleProps) {
  return <Layout steps={steps({dsn, sourcePackageRegistries})} {...props} />;
}

export default GettingStartedWithDart;
