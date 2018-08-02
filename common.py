import subprocess, os, signal, urllib3, certifi, json, re, traceback


class Env:
    def __init__(self):
        # computed env vars
        self.CD_CLUSTER_ID = f"{os.environ['CD_ENVIRONMENT']}/{os.environ['CD_REGION_DASHED']}/{os.environ['CD_CLUSTER_NAME']}"
        self.CD_REPO_API_URL = 'https://%s/api/v3/repos/%s/%s' % (
            os.environ['CD_GITHUB_DOMAIN'], os.environ['CD_GITHUB_ORG_NAME'], os.environ['CD_GITHUB_REPO_NAME'])
        self.CD_REPO_URL = 'https://%s/%s/%s' % (os.environ['CD_GITHUB_DOMAIN'], os.environ['CD_GITHUB_ORG_NAME'],
                                                 os.environ['CD_GITHUB_REPO_NAME'])
        self.CD_DEBUG = os.environ.get('CD_DEBUG', 'false')

    # this method only called in absense of instance attribute
    def __getattr__(self, attr):
        try:
            return os.environ[attr]
        except:
            raise AttributeError

    def __contains__(self, key):
        return key in os.environ


env = Env()

# default retries are set to 3 times but only for connection errors, maybe we should add things like 500?
http = urllib3.PoolManager(
    timeout=10,
    cert_reqs='CERT_REQUIRED',
    ca_certs=certifi.where(),
    headers={'Authorization': f'token {env.CD_GITHUB_TOKEN}'})
M = 60  # 60s in a minute


# returns a resource name with the full prefix
def getFullName(name, category=None):
    return '-'.join(
        re.sub('[^0-9a-z-]+', '-',
               str(part).lower())
        for part in ('quickcd', env.CD_GITHUB_ORG_NAME, env.CD_GITHUB_REPO_NAME, category, name)
        if part)


# todo: add graceful shutdown via SIGTERM first
# basic command execution function
# input should ideally be bytes, and is converted to bytes if not already
def exec(cmd, timeout, input=b''):
    # not threadsafe, surround with lock if switch to multithread model
    p = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, start_new_session=True)

    input = input.encode() if input and not isinstance(input, bytes) else (input or None)
    try:
        out, err = p.communicate(input=input, timeout=timeout - 2)
    except subprocess.TimeoutExpired:
        print(f"WARNING: Killing cmd: {cmd}")
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        try:
            out, err = p.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            return 255, "", "Very strange, failed to kill.."
    return p.returncode, out, err


# a convenience wrapper on top of exec that returns string output and has a default timeout
def sh(cmd, timeout=5 * M, input=b''):
    if env.CD_DEBUG == 'true':
        print(cmd)
        if input:
            print(input)
    ret, out, err = exec(cmd, timeout, input)
    if not ret:
        out = out.decode().strip()
        if env.CD_DEBUG == 'true' and out:
            print(out)
        return out
    else:
        raise Exception(f'Failed executing `{cmd}`. Exit code: {ret}. Stdout: {out}. Stderr: {err}')


# returns a function that can be used to log messages to GitHub commit/PR
def newCommitLogger(commitHash):
    return newGithubLogger(f'{env.CD_REPO_API_URL}/commits/{commitHash}/comments')


def newPRLogger(prNumber):
    return newGithubLogger(f'{env.CD_REPO_API_URL}/issues/{prNumber}/comments')


def newGithubLogger(newCommentURL):
    content = [f'## {env.CD_CLUSTER_ID}: {currentHandlerFnName}\n']
    comment = POST(newCommentURL, {'body': '\n'.join(content)})
    commentAPIURL = comment['url']
    commentHTMLURL = comment['html_url']

    def log(title, body='', isCmd=False, replaceLast=False):
        section = wrapCommentSection(title, body, isCmd=isCmd) if body or isCmd else f'{title}<br/>'
        if replaceLast:
            content[-1] = section
        else:
            content.append(section)
        PATCH(commentAPIURL, {'body': '\n'.join(content)})
        if env.CD_DEBUG == 'true' and not isCmd:
            print(f"Log: {title}\n{body}")

    log.commentAPIURL = commentAPIURL
    log.commentHTMLURL = commentHTMLURL
    return log


def wrapCommentSection(title, body='', isCmd=True):
    commentSection = '<details><summary>%s</summary>\n\n```\n%s\n```\n</details>'
    if isCmd:
        title = '<code>' + title + '</code>'
    return commentSection % (title, body)


# returns a convenience wrapper around sh that logs to a third party, like a comment in github
def newLoggingShell(log=None):
    if not log:
        return sh

    def loggingShell(*args, **kwargs):
        skipLog = False
        replaceLast = False
        if 'skipLog' in kwargs:
            kwargs.pop('skipLog')
            skipLog = True
        if 'replaceLast' in kwargs:
            kwargs.pop('replaceLast')
            replaceLast = True

        out = sh(*args, **kwargs)
        if not skipLog:
            log(args[0], out, isCmd=True, replaceLast=replaceLast)
        return out

    return loggingShell


currentHandlerFnName = None


def setCurrentHandlerFnName(name):
    global currentHandlerFnName
    currentHandlerFnName = name


def getCurrentHandlerFnName():
    return currentHandlerFnName


# these will raise exception for non 2xx code
# urllib3 autoretries and follows redirects
def GET(url):
    return json.loads(checkResponse(http.request('GET', url)).data.decode('utf-8'))


def POST(url, data, method='POST'):
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False, allow_nan=False)
    return json.loads(
        checkResponse(
            http.request(
                'POST',
                url,
                body=data.encode('utf-8'),
                headers=dict(http.headers, **{'Content-Type': 'application/json'}))).data.decode('utf-8'))


def PATCH(*args, **kwargs):
    kwargs['method'] = 'PATCH'
    return POST(*args, **kwargs)


def checkResponse(resp):
    if resp.status < 200 or resp.status > 299:
        raise Exception(f'Unexpected status: {resp.status}. Headers: {resp.headers}. Body: {resp.data}')
    return resp


# GitHub's build statuses
class BuildStatus:
    pending = "pending"
    failure = "failure"
    error = "error"
    success = "success"


def getCommitStatuses(commitHash):
    resp = GET(f'{env.CD_REPO_API_URL}/commits/{commitHash}/status')
    return dict((status['context'], status) for status in resp['statuses'])


def getCommitStatus(commitHash):
    return getCommitStatuses(commitHash).get(env.CD_CLUSTER_ID, {'state': None})['state']


def setCommitStatus(commitHash, status, description='', url=''):
    try:
        POST(f'{env.CD_REPO_API_URL}/statuses/{commitHash}', {
            "state": status,
            "description": description,
            "context": env.CD_CLUSTER_ID,
            "target_url": url
        })
    except:  # non critical
        print(traceback.format_exc())
