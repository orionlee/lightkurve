# Based on the sample from:
# https://github.com/GoogleCloudPlatform/python-docs-samples/blob/main/run/helloworld/Dockerfile

# Use the official lightweight Python image.
# https://hub.docker.com/_/python
FROM python:3.11-slim

# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install git (needed for the installing lightkurve from github source directly)
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
# Note: In gcloud service dashboard,
#       add environment variable BOKEH_EXTERNAL_HOSTNAME,
#       and set it to the public hostname of the deployed service.
CMD exec bokeh serve --port $PORT skyview  --allow-websocket-origin $BOKEH_EXTERNAL_HOSTNAME