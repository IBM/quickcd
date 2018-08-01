#!/bin/bash

# use local files instead of the built in ones for testing
# also use the env vars from current env
# create a file called envVars.sh that looks like below to use this run script
# envVars.sh is in .gitignore to make sure it's not committed
#
# # start of envVars.sh, do not use quotes.
# CD_ENVIRONMENT=development
# CD_REGION_DASHED=us-south
# CD_CLUSTER_NAME=OSSDev
# CD_GITHUB_TOKEN=get-this-from-github
# CD_BX_TOKEN=if-using-ibm-cloud-get-this-from-bluemix-console
# CD_GITHUB_ORG_NAME=org-or-user
# CD_GITHUB_REPO_NAME=repo-to-deploy
# CD_GITHUB_DOMAIN=github.com
# CD_EMAIL_ADDRESS=noreply@quickcd.ibm.com
# CD_SMTP_RELAY=smtp.relay.com
# CD_DEBUG=true
# # end of envVars.sh


cd `dirname "$0"`
exec docker run -it --rm --env-file envVars.sh -v`pwd`:/app quickcd