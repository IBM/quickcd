import time, init, json
from common import sh, env, sleep, stillAlive, setInterruptHandlers
from events import fetchAndSaveNewEvents, processEvent, processNextEvent, hasHandlers
from pathlib import Path

def main():
    init.preInit()
    init.setupGit()
    init.postInit()

    if not hasHandlers():
        print("No handlers defined, exiting.")
        exit(0)

    if Path("/app/testEvents.json").is_file():
        print("Found test events, entering debug mode.")
        init.generateKubeconfig()
        with open("/app/testEvents.json") as f:
            for event in json.load(f):
                processEvent(event)
    else:
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

        print('Clean exit.')
        exit(0)


if __name__ == "__main__":
    main()
