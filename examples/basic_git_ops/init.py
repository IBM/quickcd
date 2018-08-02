import os
from common import sh, env


def generateKubeconfig():
    sh(f'bx login --apikey {env.CD_BX_TOKEN} -a https://api.ng.bluemix.net')
    sh(f'bx cs region-set {env.CD_REGION_DASHED}')
    confPath = sh(f'bx cs cluster-config --export {env.CD_CLUSTER_NAME}').split('=').pop()
    sh(f'ln -s {os.path.dirname(confPath)} $HOME/.kube')  # some certs in that dir along with config
    sh(f'mv $HOME/.kube/{os.path.basename(confPath)} $HOME/.kube/config')


def setupGit():
    sh(f'git config --global user.email "{env.CD_EMAIL_ADDRESS}"')
    sh('git config --global user.name "quickcd"')

    # allow git to work without ssh for private repos
    if 'CD_GITHUB_TOKEN' in env:
        sh("git config --global url.'https://%s:x-oauth-basic@%s/'.insteadOf 'https://%s/'" %
           (env.CD_GITHUB_TOKEN, env.CD_GITHUB_DOMAIN, env.CD_GITHUB_DOMAIN))


def preInit():
    pass


def postInit():
    pass
