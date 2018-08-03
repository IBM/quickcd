import json, os, traceback, time
from common import http, checkResponse, sh, env, getFullName, setCurrentHandlerFnName
from collections import defaultdict, namedtuple
from base64 import b32encode

kubeList = {"apiVersion": "v1", "items": [], "kind": "List"}
kubeConfigMap = {"apiVersion": "v1", "data": {}, "kind": "ConfigMap", "metadata": {}}
kubeEvent = {'apiVersion': 'quickcd.cloud.ibm.com/v1', 'kind': 'GitHubEvent'}
Handler = namedtuple('Handler', ['filterFn', 'handlerFn', 'name', 'id'])
dispatchTable = defaultdict(list)


# this routine makes sure that we locally are up to date with all of the events that exist on github
def fetchAndSaveNewEvents():
    # todo: respect the x-poll-interval header
    # first run don't save anything, second run, even if no id saved previously, save all
    eventListFilePath = '/tmp/eventList.json'
    try:
        resource = json.loads(sh(f"kubectl get ConfigMap {getFullName('event-cursor')} -ojson"))
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

        # save events to file and then to kube
        if eventDict:
            with open(eventListFilePath, 'w') as f:
                json.dump(
                    dict(
                        kubeList,
                        items=[
                            dict(
                                kubeEvent, **{
                                    'metadata': {
                                        'name': getFullName(e['id']),
                                        'labels': {
                                            'org': env.CD_GITHUB_ORG_NAME,
                                            'repo': env.CD_GITHUB_REPO_NAME,
                                            'status': 'pending'
                                        }
                                    },
                                    'spec': e
                                }) for e in eventDict.values()
                        ]),
                    f,
                    ensure_ascii=False,
                    allow_nan=False)
            sh(f'kubectl apply -f {eventListFilePath}'
              )  # use apply in case this command worked but saving cursor failed, resulting in resave

    # below we use create for first run to make sure we don't accidentally override a config that existed but failed to load above
    sh(f"kubectl {'create --save-config' if firstRun else 'apply'} -f-",
       input=json.dumps(
           dict(
               kubeConfigMap,
               metadata={'name': getFullName('event-cursor')},
               data={
                   'eventID': str(newEventID),
                   'ETag': newETag
               }),
           ensure_ascii=False,
           allow_nan=False))


def registerEventHandler(eventType, fn, filterFn=lambda e: True):
    def filterWrapper(e):
        try:
            return filterFn(e)
        except:
            return False

    # todo lambda support?
    id = 'handler-' + b32encode(fn.__name__.encode()).decode().replace('=', '-').lower()[::-1]
    dispatchTable[eventType].append(Handler(filterWrapper, fn, fn.__name__, id))
    print(f"Added handler {fn.__name__} for event {eventType}")
    return fn


# can be used like this:
# @handle('PushEvent', lambda e: e['ref'] == 'refs/heads/production')
def registerEventHandlerDecorator(eventType, filterFn=lambda e: True):
    def real_decorator(handlerFn):
        registerEventHandler(eventType, handlerFn, filterFn)
        return handlerFn

    return real_decorator


# return True if any work was done, execution or cleanup wise, and False if nothing to do
def processNextEvent():
    latestEventId = int(
        json.loads(sh('kubectl get configmap -ojson ' + getFullName('event-cursor')))['data']['eventID'])
    events = sh("kubectl get githubevents -o=jsonpath='{.items[*].metadata.name}' -lstatus=pending,org=%s,repo=%s" % (
        env.CD_GITHUB_ORG_NAME,
        env.CD_GITHUB_REPO_NAME,
    )).strip()
    if not events:
        return False
    eventIds = [eid for eid in (int(e.split('-').pop()) for e in events.split(' ')) if eid <= latestEventId]
    earliestEventId = min(eventIds)
    eventResource = json.loads(sh('kubectl get githubevent -o=json ' + getFullName(earliestEventId)))
    event = eventResource['spec']

    # now that we have the event of interest, fire all the (remaining) event handlers for it.
    for handler in dispatchTable[event['type']]:
        if handler.filterFn(event['payload']) and handler.id not in eventResource['metadata']['labels']:
            # reset workspace and call handler
            sh('rm -rf /tmp')
            sh('mkdir -m 777 /tmp')
            os.chdir('/tmp')
            setCurrentHandlerFnName(handler.name)
            print(f"Event {earliestEventId}. Calling handler: {handler.name}")
            try:
                handler.handlerFn(event['payload'])
            except:
                print(traceback.format_exc())
                time.sleep(60)  #prevent fast retries, todo: stop pipeline instead of infinite retries, retries module
                raise  # stop pipeline on exc
            sh(f'kubectl label --overwrite githubevent {getFullName(earliestEventId)} {handler.id}=complete')

    sh(f'kubectl label --overwrite githubevent {getFullName(earliestEventId)} status=handled')
    return True


def hasHandlers():
    return len(dispatchTable) != 0


# at the end since handlers imports this file also, process handler registrations via decorators
import eventHandlers
