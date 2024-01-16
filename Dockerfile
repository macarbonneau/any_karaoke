# base image
# FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
FROM ubuntu:latest

# # set environment variables
# ENV HTTP_PROXY "http://proxy.ubisoft.org:3128"
# ENV HTTPS_PROXY "http://proxy.ubisoft.org:3128"
# ENV http_proxy "http://proxy.ubisoft.org:3128"
# ENV https_proxy "http://proxy.ubisoft.org:3128"
# ENV PIP_INDEX_URL "https://artifactory.ubisoft.org/api/pypi/laforge-pypi/simple"
# ENV PIP_EXTRA_INDEX_URL "https://artifactory.ubisoft.org/api/pypi/laforge-playground-pypi/simple"

# install linux packages
# RUN apt-get update -y && apt-get upgrade -y && apt-get install -y g++ gcc git sox

# copy source code
# COPY . /opt/soundstorm
# RUN pip3 install -U -e /opt/soundstorm/.
