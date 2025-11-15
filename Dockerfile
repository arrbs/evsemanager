ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install requirements
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash

# Copy data
COPY run.sh /
COPY app/ /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir \
    requests \
    flask \
    gunicorn

RUN chmod a+x /run.sh

WORKDIR /app

CMD [ "/run.sh" ]
