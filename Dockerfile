FROM alpine:3.8
RUN apk add --no-cache bash git curl ca-certificates bind-tools python3

# the line below may be needed to install some python packages
#RUN apk add --no-cache linux-headers build-base
RUN python3 -m pip install urllib3 certifi

# add kubectl
RUN curl -L https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl -o /usr/local/bin/kubectl && chmod +x /usr/local/bin/kubectl

CMD ["python3", "/app/main.py"]

COPY *.py /app/