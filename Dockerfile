# Python's locking is inconsistent on alpine: https://github.com/docker-library/python/issues/328
FROM python:3.6-stretch
RUN apt-get update && apt-get install -y --no-install-recommends unzip dnsutils && rm -rf /var/lib/apt/lists/*
#RUN apk add --no-cache bash git curl ca-certificates bind-tools python3

# the line below may be needed to install some python packages
#RUN apk add --no-cache linux-headers build-base
RUN python -m pip install urllib3==1.23 certifi==2018.4.16

# add kubectl
RUN curl -L https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

CMD ["/usr/local/bin/python", "/app/main.py"]

COPY *.py /app/