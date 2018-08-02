#!/bin/bash
set -eu

v=$1

docker build . -t ibmcom/quickcd:$v-base
cd bundles/kdep
docker build . -t ibmcom/quickcd:$v-kdep
cd ../ibmcloud
docker build . -t ibmcom/quickcd:$v-ibmcloud

docker push ibmcom/quickcd:$v-base
docker push ibmcom/quickcd:$v-kdep
docker push ibmcom/quickcd:$v-ibmcloud
