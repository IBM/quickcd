import os, signal, time, init
from common import sh, env
from events import fetchAndSaveNewEvents, processNextEvent, hasHandlers

EventCrd = """{
	"apiVersion":"apiextensions.k8s.io/v1beta1",
	"kind":"CustomResourceDefinition",
	"metadata":{
		"name":"githubevents.quickcd.cloud.ibm.com"
	},
	"spec":{
		"group":"quickcd.cloud.ibm.com",
		"names":{
			"kind":"GitHubEvent",
			"plural":"githubevents",
			"singular":"githubevent"
		},
		"scope":"Namespaced",
		"version":"v1"
	}
}"""

interrupted = False


def interrupt_handler(sig, frame):
    global interrupted
    if interrupted:
        print('Interrupted twice, exiting.')
        exit(1)
    else:
        interrupted = True
        print('INTERRUPTED. Exiting as soon as all handlers for event complete.')


def main():
    init.preInit()
    init.setupGit()
    init.generateKubeconfig()
    sh('kubectl apply -f-', input=EventCrd)
    init.postInit()

    if not hasHandlers():
        print("No handlers defined, exiting.")
        exit(0)

    fetchAndSaveNewEvents()

    signal.signal(signal.SIGINT, interrupt_handler)
    signal.signal(signal.SIGTERM, interrupt_handler)

    # keep dispatching events until all have been dispatched, unless an interrupt arrives which we catch so we can finish the current dispatch call
    while not interrupted and processNextEvent():
        time.sleep(1)  #will prevent busyloop in case of a bug of some sort

    if not interrupted:
        time.sleep(60)
    print('Clean exit.')
    exit(0)


# TODO: we exit by exception and explicitly - how do we prevent immediate restart? kube? or sleep?
if __name__ == "__main__":
    main()
