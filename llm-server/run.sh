#!/bin/bash

# Script to start the LLM server with the virtual environment
# Save this file as run.sh in the llm-server directory

# Activate the virtual environment
source venv/bin/activate

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8002 --reload

# Note: The virtual environment can be activated manually with:
# source venv/bin/activate
# 
# To deactivate the virtual environment, simply run:
# deactivate
