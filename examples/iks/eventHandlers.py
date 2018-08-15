import traceback
from events import registerEventHandler as addHandler
from common import env, setCommitStatus, BuildStatus
from charts import Chart, DeployableDiff
from emailClient import sendEmail

# Some advice:
# try to avoid using try except and if you have to use it, use it in the smallest section possible.
# that way unexpected exceptions can stop upgrades until pipeline code is fixed

# register our handlers
if env.CD_ENVIRONMENT == 'development':

    def PRToStaging(e):
        diff = DeployableDiff.createFromPR(e['pull_request'])
        if not diff:
            setCommitStatus(e['pull_request']['head']['sha'], BuildStatus.failure, 'Merge conflict', '')
        else:
            processDiff(diff)

    def filterStagingAndOpened(e):
        return e['pull_request']['base']['ref'] == 'staging' and e['action'] in ['opened', 'reopened']

    addHandler('PullRequestEvent', PRToStaging, filterFn=filterStagingAndOpened)

elif env.CD_ENVIRONMENT == 'staging':

    def pushToStaging(e):
        diff = DeployableDiff.createFromMerge(e)
        processDiff(diff)

    addHandler('PushEvent', pushToStaging, filterFn=lambda e: e['ref'] == 'refs/heads/staging')

elif env.CD_ENVIRONMENT == 'production':

    def pushToProduction(e):
        diff = DeployableDiff.createFromMerge(e)
        processDiff(diff)

    addHandler('PushEvent', pushToProduction, filterFn=lambda e: e['ref'] == 'refs/heads/production')


def processDiff(diff):
    setCommitStatus(diff.head, BuildStatus.pending, 'Starting deployment..', diff.outputURL)

    try:
        # here is the main pipeline
        diff.initializeCharts()
        upgradeOK = False
        testOK = False
        rollbackOK = False
        try:
            upgradeOK = diff.deploy()
            if upgradeOK:
                setCommitStatus(diff.head, BuildStatus.pending, 'Deployment OK, starting tests..', diff.outputURL)
                testOK = diff.runTests()
        finally:
            try:
                if not upgradeOK or not testOK:
                    setCommitStatus(diff.head, BuildStatus.failure, 'Deployment or tests failed, starting rollback..',
                                    diff.outputURL)
                    rollbackOK = diff.rollback()
            finally:
                #report status
                if upgradeOK and testOK:
                    setCommitStatus(diff.head, BuildStatus.success, 'Deployment and tests successful!', diff.outputURL)
                else:
                    sendEmail(
                        f"Failed to deploy to {env.CD_CLUSTER_ID}",
                        diff.authors,
                        f"This is a test email and is safe to ignore, for more info contact roman@us.ibm.com\n" +
                        f"Failed to deploy commit: {diff.head}\nCluster: {env.CD_CLUSTER_ID}\n" +
                        f"Changes {'were rolled' if rollbackOK else 'failed to roll'} back.\n" +
                        f"Here is a link to the output:\n{diff.outputURL}")
                    setCommitStatus(
                        diff.head, BuildStatus.failure,
                        f"Deployment failed. Changes {'were rolled' if rollbackOK else 'failed to roll'} back.",
                        diff.outputURL)
    except:
        # print some debug info before exit
        # Pipeline should not throw exceptions so if there is an Exception we log it to help with debugging
        setCommitStatus(diff.head, BuildStatus.failure, "Deployment failed due to an Exception.", diff.outputURL)
        diff.log('Exception', traceback.format_exc())
        diff.log('Chart status summary:', diff.chartStatusSummary())
        raise
