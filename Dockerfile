# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Set the working directory in the container to /app
WORKDIR /app

# Install necessary packages
RUN apt-get update && apt-get install -y \
    ffmpeg \
    aria2 \
    curl \
    unzip

# Copy the current directory contents into the container at /app
COPY . /app

RUN pip install -r requirements.txt
