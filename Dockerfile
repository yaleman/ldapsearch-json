FROM python:3.10-alpine
# FROM python:3.10-alpine

ARG runuser=ldapsearch
ARG appname=ldapsearch_json

ENV PATH=/home/$runuser/.local/bin/:/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

########################################
# add a user so we're not running as root
########################################
# ubuntu mode
# RUN useradd $runuser

# alpine mode
RUN apk update \
    && apk add --no-cache jq \
    && rm -rf /var/cache/apk/*
RUN addgroup -S appgroup && adduser -S $runuser -G appgroup

RUN mkdir -p /home/$runuser/
RUN chown $runuser /home/$runuser -R

RUN mkdir -p build/$appname

WORKDIR /build

COPY $appname $appname
COPY poetry.lock .
COPY pyproject.toml .

# RUN python -m pip install poetry

RUN chown $runuser /build -R
WORKDIR /build/
USER $runuser


RUN python -m pip install --upgrade --no-warn-script-location --no-cache pip
RUN python -m pip install --no-warn-script-location --no-cache /build

USER root
RUN rm -rf /build
USER $runuser

WORKDIR /home/$runuser/

ENTRYPOINT [ "sh" ]
