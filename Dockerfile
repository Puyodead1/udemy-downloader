# Credit to anthelinux for the updated file (https://github.com/Puyodead1/udemy-downloader/issues/256#issuecomment-2536394478)
# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Set the working directory in the container to /app
WORKDIR /app

# Install necessary packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    aria2 \
    unzip \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install FFmpeg from johnvansickle's builds (always latest stable version)
RUN wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz \
    && tar xvf ffmpeg-release-amd64-static.tar.xz \
    && mv ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/ \
    && mv ffmpeg-*-amd64-static/ffprobe /usr/local/bin/ \
    && rm -rf ffmpeg-*-amd64-static* \
    && chmod +x /usr/local/bin/ffmpeg \
    && chmod +x /usr/local/bin/ffprobe

# Install Shaka Packager
RUN wget https://github.com/shaka-project/shaka-packager/releases/download/v3.2.0/packager-linux-x64 -O /usr/local/bin/shaka-packager
RUN chmod +x /usr/local/bin/shaka-packager

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python application dependencies
RUN pip install -r requirements.txt
