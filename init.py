from common import sh

# this file is meant to be overridden to match the cluster setup
# see the examples directory for ideas on what to put here


# this method should make it so kubectl can be called
# usually done via kube config file in home dir
def generateKubeconfig():
    pass


# basic git setup, like username and email
def setupGit():
    pass


def preInit():
    pass


def postInit():
    pass
