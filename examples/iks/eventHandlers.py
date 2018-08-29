import traceback, json
from events import addBlockingHandler, addNonBlockingHandler
from common import env, setCommitStatus, BuildStatus, getJSON, getFullName, newCommitLogger, newLoggingShell
from charts import Chart, DeployableDiff
from emailClient import sendEmail

# Some advice:
# try to avoid using try except and if you have to use it, use it in the smallest section possible.
# that way unexpected exceptions can stop upgrades until pipeline code is fixed


def cmdSkip(commit, sh, log):
    '''Skip deploying this commit. One use for this is to stop trying to deploy a commit that will never succeed.'''
    obj = {"apiVersion": "v1", "data": {}, "kind": "ConfigMap", "metadata": {"name": getFullName(f'skip-{commit}')}}
    sh(f'kubectl -n {env.CD_NAMESPACE} apply -f-', input=json.dumps(obj, ensure_ascii=False, allow_nan=False))
    log(f'Future deploy attempts for {commit} will be skipped.')


def cmdRedeploy(commit, sh, log):
    '''Redeploy the given commit'''  # doesn't seem to be an easy way to tell which PR a PR commit belongs to
    pass  # todo


def cmdHelp(commit, sh, log):
    '''Show available commands.'''
    log('Available commands are:', '\n'.join(f'{cmd}: {func.__doc__}' for cmd, func in commands.items()))


commands = {'help': cmdHelp, 'skip': cmdSkip, 'redeploy': cmdRedeploy}


# register command handler
def quickCommand(e):
    commit = e['comment']['commit_id']
    command = e['comment']['body'].strip()[len('/quickcd'):].strip()
    log = newCommitLogger(commit)
    sh = newLoggingShell(log)
    log("Processing command: " + command)
    if command in commands:
        commands[command](commit, sh, log)
    else:
        log('Unknown command.')
        commands['help'](commit, sh, log)


addNonBlockingHandler(
    'CommitCommentEvent', quickCommand, filterFn=lambda e: e['comment']['body'].startswith('/quickcd'))

# register deploy handlers
if env.CD_ENVIRONMENT == 'development':

    def PRToStaging(e):
        if getJSON(e['pull_request']['url'])['state'] != 'open':
            print('Skip building a closed PR')
            return

        diff = DeployableDiff.createFromPR(e['pull_request'])
        if not diff:
            setCommitStatus(e['pull_request']['head']['sha'], BuildStatus.failure, 'Merge conflict', '')
        else:
            processDiff(diff)

    def filterStagingAndOpened(e):
        return e['pull_request']['base']['ref'] == 'staging' and e['action'] in ['opened', 'reopened']

    addNonBlockingHandler('PullRequestEvent', PRToStaging, filterFn=filterStagingAndOpened)

elif env.CD_ENVIRONMENT == 'staging':

    def pushToStaging(e):
        diff = DeployableDiff.createFromMerge(e)
        processDiff(diff)

    addBlockingHandler('PushEvent', pushToStaging, filterFn=lambda e: e['ref'] == 'refs/heads/staging')

elif env.CD_ENVIRONMENT == 'production':

    def pushToProduction(e):
        diff = DeployableDiff.createFromMerge(e)
        processDiff(diff)

    addBlockingHandler('PushEvent', pushToProduction, filterFn=lambda e: e['ref'] == 'refs/heads/production')


def processDiff(diff):
    if len(
            diff.sh(f'kubectl -n {env.CD_NAMESPACE} get ConfigMap --ignore-not-found ' +
                    getFullName(f'skip-{diff.head}'))):
        diff.log('Skipping this commit.')
        return

    setCommitStatus(diff.head, BuildStatus.pending, 'Starting deployment..', diff.outputURL)

    try:
        # here is the main pipeline, should normally not have any excpetions
        try:
            clusterUntouched = True
            upgradeOK = False
            testOK = False
            rollbackOK = False
            diff.initializeCharts()
            try:
                clusterUntouched = False
                upgradeOK = diff.deploy()
                if upgradeOK:
                    setCommitStatus(diff.head, BuildStatus.pending, 'Deployment OK, starting tests..', diff.outputURL)
                    testOK = diff.runTests()
                    if testOK:
                        setCommitStatus(diff.head, BuildStatus.success, 'Deployment and tests successful!',
                                        diff.outputURL)
                        diff.log('Result: OK')
            finally:
                if not upgradeOK or not testOK:
                    setCommitStatus(diff.head, BuildStatus.failure, 'Deployment or tests failed, starting rollback..',
                                    diff.outputURL)
                    rollbackOK = diff.rollback()
        finally:
            # report status on failure
            if not upgradeOK or not testOK:
                if clusterUntouched:
                    status = 'No changes made to cluster.'
                else:
                    status = f"Changes {'were rolled' if rollbackOK else 'failed to roll'} back."
                finalStatus
                setCommitStatus(diff.head, BuildStatus.failure, "Deployment failed. " + status, diff.outputURL)
                diff.log(f'Result: Failure. ({status})')
                # Try to find who to notify:
                commit = getJSON(f'{env.CD_REPO_API_URL}/commits/{diff.head}')
                tags = ', '.join(
                    '@' + x for x in set(commit[role]['login'] for role in ('committer', 'author') if commit[role]))
                if tags:
                    diff.log('Tags: ' + tags)

    except:
        # Pipeline should not throw exceptions so if there is an Exception we log it to help with debugging
        setCommitStatus(diff.head, BuildStatus.failure, "Deployment failed due to an Exception!", diff.outputURL)
        diff.log('Important: got an exception! Pipeline should not have exceptions. Please look into this:')
        diff.log('Exception', traceback.format_exc())
        diff.log('Chart status summary:', diff.chartStatusSummary())
        raise
