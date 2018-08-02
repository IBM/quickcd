FROM ibmcom/quickcd:1-base
RUN apk add --no-cache unzip
RUN curl -L https://github.com/IBM/kdep/releases/download/v0.1/linux.tar.gz | tar -xvzC /usr/local/bin

#binaries used by kdep
RUN curl -L https://releases.hashicorp.com/vault/0.10.4/vault_0.10.4_linux_amd64.zip | funzip > /usr/local/bin/vault && chmod +x /usr/local/bin/vault
RUN curl -L https://releases.hashicorp.com/consul-template/0.19.5/consul-template_0.19.5_linux_amd64.tgz | tar -xvzC /usr/local/bin
RUN curl -L https://storage.googleapis.com/kubernetes-helm/helm-v2.9.1-linux-amd64.tar.gz | tar --strip-components 1 -xvzC /usr/local/bin
RUN curl -L https://github.com/stedolan/jq/releases/download/jq-1.5/jq-linux64 -o /usr/local/bin/jq && chmod +x /usr/local/bin/jq
RUN curl -L https://github.com/mikefarah/yq/releases/download/2.1.1/yq_linux_amd64 -o /usr/local/bin/yq && chmod +x /usr/local/bin/yq

