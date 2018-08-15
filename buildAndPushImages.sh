#!/bin/bash
set -eu

v=$1

docker build . -f Dockerfile -t ibmcom/quickcd:$v-base
docker build . -f bundles/kdep/Dockerfile -t ibmcom/quickcd:$v-kdep
docker build . -f bundles/iks/Dockerfile -t ibmcom/quickcd:$v-iks

docker push ibmcom/quickcd:$v-base
docker push ibmcom/quickcd:$v-kdep
docker push ibmcom/quickcd:$v-iks
