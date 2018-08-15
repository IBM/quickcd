quickcd
=======

Quickcd is a way to define event handlers for GitHub repositories in Python.

Table of contents
-----------------
 - [How it works](#how-it-works)
 - [Key features](#key-features)
 - [Docker images](#docker-images)
 - [Defining event handlers](#defining-event-handlers)
 - [Using quickcd for chart deployment with kdep](#using-quickcd-for-chart-deployment-with-kdep)
 - [Related work](#related-work)
 - [Questions & suggestions](#questions--suggestions)

How it works
------------
Quickcd has a fairly simple loop:
  1. Poll a github repository for events which have a handler defined.
  2. If there are new events, save them as ConfigMaps in Kubernetes.
  3. Send every event, one by one, to the relevant handler(s).

Key features
------------
 - Easy to test event handlers locally
 - Logging to GitHub comments - see the result of your pipeline right in GitHub
 - Convenient way to run shell commands with logging
 - Event collection from GitHub is poll based, meaning:
   - No missed events if a webhook malfunctions
   - No need to set up an externally accessible webhook endpoint
 - Full Python environment available for expressing complex logic

Docker images
-------------
Images are built via `buildAndPushImages.sh` and are available on DockerHub under 3 tags:
 - base - this is vanilla quickcd which can be good for extending.
 - kdep - this is the base image + [kdep](https://github.com/IBM/kdep) for working with Helm charts
 - iks - this is the kdep image + tools to talk to IBM Cloud Kubernetes Service.
 
 The versions in the image tags correspond to the git tags/releases, with edge pointing to the latest commit on master.

Defining event handlers
-----------------------
Event handlers are defined in the `eventHandlers.py` file. One way to supply this file is to create a new image, overwriting the file, optionally installing additional tools/packages. Another option is to use the image provided as-is and mount this file from a ConfigMap.

Here is an example of a handler with inline explanation:
```python
from events import registerEventHandler as addHandler
from common import newCommitLogger, env, newLoggingShell

# a handler has a single argument which is a GitHub event
# GitHub event documentation can be found here: https://developer.github.com/v3/activity/events/types/
def pushToMaster(e):
  # this provides a way to log to a comment on a commit in GitHub
  log = newCommitLogger(e['head'])

  # this makes it so that all commands are automatically logged
  sh = newLoggingShell(log)

  # here we serialize the event that we're handling and log it for debugging purposes
  log('Event', json.dumps(e, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True))

  # here we fetch our repo and checkout the commit that this event is for
  # the current working directory is /tmp and is recreated for each handler
  sh(f'git clone {env.CD_REPO_URL} .')
  sh(f'git checkout {e["head"]}')

  # Now that we have the repo locally, we can do things like see what was changed in the commit,
  # deploy these changes, set the status on the github commit, etc
  pass

# now that the handler is defined above, we register it
# the first argument here is the type of GitHub event
#   See here for possible event types: https://developer.github.com/v3/activity/events/types/
# the second argument is a reference to the handler function
# the filterFn argument is optional and allows to subscribe to a subset of events of a given type
#   the example here subscribes to PushEvent but only if the push was to the master branch
addHandler('PushEvent', pushToMaster, filterFn=lambda e: e['ref'] == 'refs/heads/master')
```

For more complete examples of a pipeline, see https://github.com/IBM/quickcd/tree/master/examples

Using quickcd for chart deployment with kdep
--------------------------------------------
*This section assumes understanding of concepts covered in: https://github.com/IBM/kdep#overview--conventions*

To review, we combine microservices into logical groups and call these groups "Apps". We then place all the charts for an "App" into a dedicated git repository in GitHub. To start automatically deploying an "App", simply add to this repo a chart for quickcd and supply your custom `eventHandlers.py`.

A good example of a pipeline that deploys charts to three environments can be found here: https://github.com/IBM/quickcd/blob/master/examples/iks/eventHandlers.py

Related work
------------
 - https://github.com/Azure/brigade

Questions & Suggestions
-----------------------
Please create an issue.
