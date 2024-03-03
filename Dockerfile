# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Set the working directory in the container to /app
WORKDIR /app

# Install necessary packages.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    curl \
    unzip \
    wget

# Install Shaka Packager
RUN wget https://github.com/shaka-project/shaka-packager/releases/download/v2.6.1/packager-linux-x64 -o /usr/local/bin/shaka-packager
RUN chmod +x /usr/local/bin/shaka-packager
ENV PATH="/usr/local/bin/shaka-packager:${PATH}"

# Copy the current directory contents into the container at /app.
COPY . /app

# Install Python application dependencies.
RUN pip install -r requirements.txt
