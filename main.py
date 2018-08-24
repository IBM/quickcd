import time, init, json
from common import sh, env, sleep, stillAlive, setInterruptHandlers
from events import fetchAndSaveNewEvents, runHandlers, processNextEvent, hasHandlers
from pathlib import Path


def main():
    init.preInit()
    init.setupGit()
    init.postInit()

    if not hasHandlers():
        print("No handlers defined, exiting.")
        exit(0)

    if env.CD_LOCAL_MODE == 'false':
        setInterruptHandlers()

        lastConfig = 0
        while stillAlive():
            # refresh config token once an hour
            if time.time() - lastConfig > 60 * 60:
                print('Refreshing Kube config')
                init.generateKubeconfig()
                lastConfig = time.time()

            if stillAlive():
                fetchAndSaveNewEvents()

            # keep dispatching events until all have been dispatched
            # unless an interrupt arrives which we catch so we can finish the current dispatch call
            while stillAlive() and processNextEvent():
                sleep(1)  #will prevent busyloop in case of a bug of some sort

            # finished processing all events, take a break
            if stillAlive():
                sleep(60)

        print("Clean exit.")
        exit(0)
    else:
        print("Running in local mode: no comments an no status updates in GH, reading events from /app/testEvents.json")
        init.generateKubeconfig()
        print("Running handlers for events in /app/testEvents.json")
        with open("/app/testEvents.json") as f:
            events = json.load(f)
            for event in events:
                runHandlers(event, False)
            for event in events:
                runHandlers(event, True)
        print("Clean exit.")


if __name__ == "__main__":
    main()
