import os, time, traceback, json
from enum import Enum, auto
from common import newCommitLogger, env, newLoggingShell, GET

DEBUG = env.CD_CHARTS_DEBUG != 'false'

KDEP_FLAGS = ''
HELM_FLAGS = ''
if DEBUG:
    KDEP_FLAGS = '-d'
    HELM_FLAGS = '--debug --dry-run'


class ChartStatus(Enum):
    READY = auto()
    UPGRADING = auto()
    UPGRADED = auto()
    UPGRADEFAILED = auto()
    ROLLINGBACK = auto()
    ROLLEDBACK = auto()
    CANTROLLBACK = auto()


class DeployableDiff:
    '''
    base, head, and merge are commit hashes and authors is a list of tuples like [(john, foo@bar.com),...]
    for a commit, merge is same as head (since it's already merged)
    for a PR, merge is a new "virtual" commit that we make for the purposes of the diff
    '''

    def __init__(self, base, head, merge, authors, sh, log):
        self.base = base
        self.head = head
        self.merge = merge
        self.authors = authors
        self.sh = sh
        self.log = log
        self.outputURL = self.log.commentHTMLURL

        allReleases = set(self.sh('helm ls --short --all').split('\n'))
        changedFiles = self.sh(f'git diff --name-only {self.base}..{self.merge}')
        changedDirs = set(file.split('/')[0] for file in changedFiles.split('\n') if '/' in file)
        self.charts = [Chart(dir, allReleases, sh, log) for dir in changedDirs if os.path.isfile(dir + '/Chart.yaml')]

    @classmethod
    def createFromMerge(cls, e):
        log = newCommitLogger(e['head'])
        sh = newLoggingShell(log)
        log('Event', json.dumps(e, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))

        sh(f'git clone {env.CD_REPO_URL} .')
        sh(f'git checkout {e["head"]}')

        return cls(e['before'], e['head'], e['head'],
                   [(c['author']['name'], c['author']['email']) for c in e['commits']], sh, log)

    @classmethod
    def createFromPR(cls, e):
        log = newCommitLogger(e['head']['sha'])
        sh = newLoggingShell(log)
        log('Event', json.dumps(e, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))
        commits = [c['commit'] for c in GET(e['commits_url'])]

        sh(f'git clone -b {e["base"]["ref"]} {env.CD_REPO_URL} .')
        try:
            if e['head']['repo']['fork']:
                sh(f'git pull --no-edit --no-ff {e["head"]["repo"]["ssh_url"]} {e["head"]["ref"]}')
            else:
                sh(f'git merge --no-edit --no-ff origin/{e["head"]["ref"]}')
        except:
            return False
        else:
            mergeHash = sh('git rev-parse HEAD')
            return cls(e['base']['sha'], e['head']['sha'], mergeHash,
                       [(c['author']['name'], c['author']['email']) for c in commits], sh, log)

    def deploy(self):
        self.log(f'Chart deployment commencing.')
        for chart in self.charts:
            if chart.enabled:
                if not chart.upgrade():
                    return False
            else:
                self.log(f'Continuous deployment for chart {chart.name} not enabled, skipping.')
        self.log(f'Chart deployment complete.')
        return True

    def runTests(self):
        self.log(f'Tests commencing.')
        for chartName in set(sum((chart.tests for chart in self.charts if chart.enabled), [])):
            squad = chartName.split('-')[0]
            self.log(f'Launching integration test: {chartName}')
            releaseName = chartName + time.strftime('-%m-%d-%y--%H-%M-%S')
            self.sh(f'kdep -i {KDEP_FLAGS} -t {releaseName} ./{chartName}/{env.CD_REGION_DASHED}-{env.CD_ENVIRONMENT}-values.yaml')

            if not DEBUG:
                self.log('Job running... 0m')
                for i in range(60 * 60):
                    if i % 10:
                        time.sleep(1)
                    else:
                        self.log(f'Job running... {i//60}m', replaceLast=True)
                        job = json.loads(self.sh(f'kubectl get job -n {squad} {releaseName} -ojson', skipLog=True))
                        if 'active' not in job['status']:
                            ok = 'succeeded' in job['status']
                            self.log(f"{releaseName} {'succeeded' if ok else 'failed'}!")
                            self.sh(f'kubectl logs -ljob-name={releaseName} -n {squad}')
                            if ok:
                                break
                            else:
                                return False
                else:
                    self.log(f'Test {chartName} timed out...')
                    return False
        self.log(f'Tests complete.')
        return True

    def rollback(self):
        self.log('Starting rollbacks ...')

        lastException = None
        for chart in self.charts:
            if chart.enabled and chart.status in (ChartStatus.UPGRADED, ChartStatus.UPGRADEFAILED):
                try:
                    chart.rollback()
                except Exception as e:
                    lastException = e

        if lastException:
            self.log('Rollback failed, chart summary:', self.chartStatusSummary())
            raise lastException
        else:
            self.log('Rollback complete, chart summary:', self.chartStatusSummary())

        return all(chart.status == ChartStatus.ROLLEDBACK for chart in self.charts)

    def chartStatusSummary(self):
        return '\n'.join([
            f'Chart: {chart.name} Status: {chart.status.name} Last revision: {chart.lastRevision}'
            for chart in self.charts
        ])


class Chart:
    def __init__(self, name, allReleases, sh, log):
        self.name = name
        self.sh = sh
        self.log = log
        self.lastRevision = None
        self.enabled = False
        self.tests = []
        self.status = ChartStatus.READY

        self.log(f'Examining changed chart: {self.name}')
        values = json.loads(
            self.sh(f'kdep-merge-inherited-values ./{name}/{env.CD_REGION_DASHED}-{env.CD_ENVIRONMENT}-values.yaml'))
        if 'continuousDeployment' in values:
            self.enabled = values['continuousDeployment'].get('enabled', False)
            self.tests = list(values['continuousDeployment'].get('integrationTests', {}).keys())

        if self.name in allReleases:
            self.lastRevision = max(
                int(chart[0])
                for chart in [chart.split('\t') for chart in self.sh(f'helm history {self.name}').split('\n')]
                if len(chart) == 5 and 'DEPLOYED' in chart[2])

    def upgrade(self):
        if not self.enabled:
            raise Exception(f"Tried to ugrade {self.name} which is not enabled for auto deployment.")

        self.log(f'Upgrading {self.name}')

        try:
            self.status = ChartStatus.UPGRADING
            self.sh(f"kdep -i {KDEP_FLAGS} ./{self.name}/{env.CD_REGION_DASHED}-{env.CD_ENVIRONMENT}-values.yaml")
        except:
            self.status = ChartStatus.UPGRADEFAILED
            self.log(f'Error deploying chart {self.name}', traceback.format_exc())
        else:
            self.status = ChartStatus.UPGRADED
        return self.status == ChartStatus.UPGRADED

    def rollback(self):
        if self.status != ChartStatus.UPGRADED:
            raise Exception(f"Tried to roll back {self.name} which had status {self.status.name}.")

        self.log(f'Rolling {self.name} back to revision {self.lastRevision}')

        if self.lastRevision is not None:
            self.status = ChartStatus.ROLLINGBACK
            self.sh(f'helm rollback {HELM_FLAGS} --force {self.name} {self.lastRevision}')
            self.status = ChartStatus.ROLLEDBACK
        else:
            self.status = ChartStatus.CANTROLLBACK
            self.log(f"Didn't roll back {self.name} because no previous DEPLOYED revision found. " +
                     "Force delete manually if neccessary.")
