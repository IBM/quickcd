ARG VERSION
FROM ibmcom/quickcd:${VERSION}-kdep
#RUN curl -L https://clis.ng.bluemix.net/install/linux | sh
RUN curl -L https://clis.ng.bluemix.net/download/bluemix-cli/latest/linux64 | tar -vxzC /tmp && /tmp/Bluemix_CLI/install_bluemix_cli && rm -rf /tmp/Bluemix_CLI
RUN bx plugin install container-service -r Bluemix
COPY init.py /app/
