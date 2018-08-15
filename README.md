quickcd
=======

Quickcd is a way to define event handlers for GitHub repositories in Python.

Table of contents
-----------------
 - [How it works](#how-it-works)
 - [Key features](#key-features)
 - [Docker images](#docker-images)
 - [More info](#more-info)
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
 - Convenient function to run shell commands
 - Command logging to GitHub comments - see the result of your pipeline right in GitHub
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

More info
---------
For a more in-depth look at how to effectively use quickcd, see the [README.md](https://github.com/IBM/quickcd/tree/master/bundles/kdep) in the `bundles/kdep` folder.

Related work
------------
 - https://github.com/Azure/brigade

Questions & Suggestions
-----------------------
Please create an issue.
