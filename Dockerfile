FROM alpine
RUN apk add --no-cache bash git curl ca-certificates bind-tools python3

# the line below may be needed to install some python packages
#RUN apk add --no-cache linux-headers build-base
RUN python3 -m pip install urllib3 certifi

# add kubectl
RUN curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/darwin/amd64/kubectl
RUN chmod +x ./kubectl
RUN mv ./kubectl /usr/local/bin/

RUN mkdir -p /app
COPY *.py /app/
CMD ["python3", "/app/main.py"]