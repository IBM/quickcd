import os, signal, time, init
from common import sh, env
from events import fetchAndSaveNewEvents, processNextEvent, hasHandlers


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
    init.postInit()

    if not hasHandlers():
        print("No handlers defined, exiting.")
        exit(0)

    signal.signal(signal.SIGINT, interrupt_handler)
    signal.signal(signal.SIGTERM, interrupt_handler)

    lastConfig = 0
    while not interrupted:
        # refresh config token once an hour
        if time.time() - lastConfig > 60 * 60:
            print('Refreshing Kube config')
            init.generateKubeconfig()
            lastConfig = time.time()

        fetchAndSaveNewEvents()

        # keep dispatching events until all have been dispatched
        # unless an interrupt arrives which we catch so we can finish the current dispatch call
        while not interrupted and processNextEvent():
            time.sleep(1)  #will prevent busyloop in case of a bug of some sort

        # finished processing all events, take a break
        if not interrupted:
            time.sleep(60)

    print('Clean exit.')
    exit(0)


# TODO: we exit by exception and explicitly - how do we prevent immediate restart? kube? or sleep?
if __name__ == "__main__":
    main()
