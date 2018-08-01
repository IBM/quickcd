import json
from events import registerEventHandler as addHandler
from common import newCommitLogger, env, newLoggingShell, setCommitStatus, BuildStatus, GET
from emailClient import sendEmail

# This file is an example, please override it with your own
# Some advice:
# try to avoid using try except and if you have to use it, use it in the smallest section possible.
# that way unexpected exceptions can stop upgrades until pipeline code is fixed

# register our handlers, just one way to do it
if env.CD_ENVIRONMENT == 'development':

    def deployAndTestPR(e):
        e = e['pull_request']
        log = newCommitLogger(e['head']['sha'])
        sh = newLoggingShell(log)
        log('Event', json.dumps(e, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
        commits = [c['commit'] for c in GET(e['commits_url'])]

        # fetch the repo and merge in changes from PR
        sh(f'git clone -b {e["base"]["ref"]} {env.CD_REPO_URL} .')
        try:
            if e['head']['repo']['fork']:
                sh(f'git pull --no-edit --no-ff {e["head"]["repo"]["ssh_url"]} {e["head"]["ref"]}')
            else:
                sh(f'git merge --no-edit --no-ff origin/{e["head"]["ref"]}')
        except:
            setCommitStatus(e["head"]["ref"], BuildStatus.failure, 'Merge failed', log.commentHTMLURL)

        pass  # logic to deploy to staging, or call common function

    addHandler('PullRequestEvent', deployAndTestPR)

elif env.CD_ENVIRONMENT == 'staging':

    def pushToStaging(e):
        log = newCommitLogger(e['head'])
        sh = newLoggingShell(log)
        log('Event', json.dumps(e, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))

        # fetch repo and checkout the commit that this event is for
        sh(f'git clone {env.CD_REPO_URL} .')
        sh(f'git checkout {e["head"]}')

        pass  # logic to deploy to staging, or call common function

    addHandler('PushEvent', pushToStaging, filterFn=lambda e: e['ref'] == 'refs/heads/staging')

elif env.CD_ENVIRONMENT == 'production':

    def pushToProduction(e):
        pass  # logic to deploy to production, or call common function

    addHandler('PushEvent', pushToProduction, filterFn=lambda e: e['ref'] == 'refs/heads/production')

exit(1)  # this is an example, copy your pipeline over this file
