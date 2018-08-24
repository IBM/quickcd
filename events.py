import json, os, traceback, time
from common import http, checkResponse, sh, env, getFullName, setCurrentHandlerFnName, writeLabels
from collections import defaultdict, namedtuple
from base64 import b32encode

kubeList = {"apiVersion": "v1", "items": [], "kind": "List"}
kubeConfigMap = {"apiVersion": "v1", "data": {}, "kind": "ConfigMap", "metadata": {}}
Handler = namedtuple('Handler', ['filterFn', 'handlerFn', 'name', 'id', 'isBlocking'])
dispatchTable = defaultdict(list)


# this routine makes sure that we locally are up to date with all of the events that exist on github
def fetchAndSaveNewEvents():
    # todo: respect the x-poll-interval header
    # first run don't save anything, second run, even if no id saved previously, save all
    try:
        resource = json.loads(sh(f"kubectl -n {env.CD_NAMESPACE} get ConfigMap {getFullName('event-cursor')} -ojson"))
    except:
        firstRun = True
        fetchedETag = '"none"'
        fetchedEventID = 0
        print("Can't retrieve config, assumiing first run.")
    else:
        firstRun = False
        fetchedETag = resource['data']['ETag']
        fetchedEventID = int(resource['data']['eventID'])

    newETag = fetchedETag
    newEventID = fetchedEventID

    url = env.CD_REPO_API_URL + '/events'
    events = []
    for i in range(15):  # Current GH limit is 10 pages
        if i > 10:
            raise Exception("Github only provides 10 pages of results, something's wrong with pagination.")

        resp = http.request(
            'GET',
            url,
            headers=dict(http.headers, **{'If-None-Match': fetchedETag}) if i == 0 and not firstRun else http.headers)

        if resp.status == 304:
            print("Fetching events 304 (nothing new)")
            return
        else:
            checkResponse(resp)

        print(f"Processing page {i+1}")

        if i == 0 and 'ETag' in resp.headers:
            newETag = resp.headers['ETag']

        tmpEvents = json.loads(resp.data.decode('utf-8'))
        tmpEventsFiltered = [e for e in tmpEvents if int(e['id']) > fetchedEventID]
        events += tmpEventsFiltered
        if len(tmpEvents) != len(tmpEventsFiltered):
            break  # already reached event we saved last

        if firstRun:
            break  #during first run only want latest id

        linkKey = '; rel="next"'
        if 'Link' in resp.headers and linkKey in resp.headers['Link']:
            url = resp.headers['Link'].split(linkKey)[0].split(',').pop().strip('< >')
        else:
            break

    if events:
        newEventID = int(
            events[0]['id'])  # may be not an event that we saved, we save only filtered ones we're listening for
    else:
        print('Interesting, no events at all!')  # new repo or old repo?

    # only save events on subsequent runs
    if not firstRun:
        # get rid of duplicates and filter
        eventDict = dict(
            (e['id'], e) for e in events if any(handler.filterFn(e['payload']) for handler in dispatchTable[e['type']]))

        if eventDict:
            # use apply in case this command worked but saving cursor failed, resulting in resave
            # todo: not sure why yapf is using 3 space indenting here and below
            sh(f'kubectl -n {env.CD_NAMESPACE} apply -f-',
               input=json.dumps(
                   dict(
                       kubeList,
                       items=[
                           dict(
                               kubeConfigMap,
                               metadata={
                                   'name': getFullName(e['id']),
                                   'labels': {
                                       'owner': 'quickcd',
                                       'kind': 'GitHubEvent',
                                       'org': env.CD_GITHUB_ORG_NAME,
                                       'repo': env.CD_GITHUB_REPO_NAME,
                                       'status': 'pending'
                                   }
                               },
                               data={'event': json.dumps(e, ensure_ascii=False, allow_nan=False)})
                           for e in eventDict.values()
                       ]),
                   ensure_ascii=False,
                   allow_nan=False))

    # below we use create for first run to make sure we don't accidentally override a config that existed but failed to load above
    sh(f"kubectl -n {env.CD_NAMESPACE} {'create --save-config' if firstRun else 'apply'} -f-",
       input=json.dumps(
           dict(
               kubeConfigMap,
               metadata={
                   'name': getFullName('event-cursor'),
                   'labels': {
                       'owner': 'quickcd'
                   }
               },
               data={
                   'eventID': str(newEventID),
                   'ETag': newETag
               }),
           ensure_ascii=False,
           allow_nan=False))


def registerEventHandler(eventType, fn, filterFn=lambda e: True, blocking=True):
    def filterWrapper(e):
        try:
            return filterFn(e)
        except:
            return False

    id = 'handler-' + b32encode(fn.__name__.encode()).decode().replace('=', '-').lower()[::-1]
    dispatchTable[eventType].append(Handler(filterWrapper, fn, fn.__name__, id, blocking))
    print(f"Added handler {fn.__name__} for event {eventType}")
    return fn


def addBlockingHandler(*args, **kwargs):
    kwargs['blocking'] = True
    return registerEventHandler(*args, **kwargs)


def addNonBlockingHandler(*args, **kwargs):
    kwargs['blocking'] = False
    return registerEventHandler(*args, **kwargs)


# can be used like this:
# @handle('PushEvent', lambda e: e['ref'] == 'refs/heads/production')
def registerEventHandlerDecorator(eventType, filterFn=lambda e: True):
    def real_decorator(handlerFn):
        registerEventHandler(eventType, handlerFn, filterFn)
        return handlerFn

    return real_decorator


# return True if any work was done, execution or cleanup wise, and False if nothing to do
def processNextEvent():
    maxEventId = int(
        json.loads(sh(f'kubectl -n {env.CD_NAMESPACE} get configmap -ojson ' +
                      getFullName('event-cursor')))['data']['eventID'])
    events = sh(
        f"kubectl -n {env.CD_NAMESPACE} get configmaps -o=jsonpath='{{.items[*].metadata.name}}'" +
        f" -lowner=quickcd,kind=GitHubEvent,status=pending,org={env.CD_GITHUB_ORG_NAME},repo={env.CD_GITHUB_REPO_NAME}"
    ).strip()
    if not events:
        return False
    eventIds = [eid for eid in (int(e.split('-').pop()) for e in events.split(' ')) if eid <= maxEventId]

    # run nonblocking handlers first if we can
    for eid in eventIds:
        eventResource = json.loads(sh(f'kubectl -n {env.CD_NAMESPACE} get configmap -o=json ' + getFullName(eid)))
        if runHandlers(json.loads(eventResource['data']['event']), False, eid, eventResource['metadata']['labels']):
            return True

    earliestEventId = min(eventIds)
    eventResource = json.loads(
        sh(f'kubectl -n {env.CD_NAMESPACE} get configmap -o=json ' + getFullName(earliestEventId)))
    return runHandlers(
        json.loads(eventResource['data']['event']), True, earliestEventId, eventResource['metadata']['labels'])


def runHandlers(event, blocking, eventID=0, labels={}):
    # now that we have the event of interest, fire all the (remaining) event handlers for it.
    workPerformed = False
    for handler in dispatchTable[event['type']]:
        if handler.isBlocking == blocking and handler.filterFn(event['payload']) and handler.id not in labels:
            if eventID:
                lastRun = float(labels.get(f'{handler.id}_last_run', '0'))
                attempts = int(labels.get(f'{handler.id}_attempts', '0'))
                if (time.time() - lastRun) / 60 < attempts**3:
                    continue
                writeLabels(eventID, **{f'{handler.id}_last_run': time.time(), f'{handler.id}_attempts': attempts + 1})
            workPerformed = True
            # reset workspace and call handler
            sh('rm -rf /tmp')
            sh('mkdir -m 777 /tmp')
            os.chdir('/tmp')
            setCurrentHandlerFnName(handler.name)
            print(f"Event {eventID}. Calling handler: {handler.name}")
            try:
                handler.handlerFn(event['payload'])
            except:
                print(traceback.format_exc())
                if blocking:
                    return True  # don't run other handlers for this event since encountered an error
                else:
                    continue  # run remaining nonblocking handlers for this evt
            if eventID:
                writeLabels(eventID, **{f'{handler.id}': 'complete'})

    # check if any handlers remaining and mark complete if not
    if eventID:
        allDone = True
        for handler in dispatchTable[event['type']]:
            if handler.filterFn(event['payload']) and handler.id not in labels:
                allDone = False
                break
        if allDone:
            writeLabels(eventID, status='handled')

    return workPerformed


def hasHandlers():
    return len(dispatchTable) != 0


# at the end since handlers imports this file also, process handler registrations via decorators
import eventHandlers
