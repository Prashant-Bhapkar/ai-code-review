from flask import Flask, request, jsonify
import os
import logging
import requests
from openai import OpenAI

# ───── APP SETUP ─────
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# ───── LOGGING CONFIG ─────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def get_last_position(patch):
    return sum(1 for line in patch.splitlines() if line.startswith("+"))

def extract_issues_per_file(result):
    """
    Parses OpenAI result and returns dict of filename => issues block.
    Assumes result contains sections like:
    Filename: api/index.py
    1. Issue:
       Location:
       Solution:
    """
    file_issues = {}
    current_file = None
    lines = result.splitlines()
    buffer = []
    for line in lines:
        if line.strip().startswith("Filename:"):
            if current_file and buffer:
                file_issues[current_file] = "\n".join(buffer).strip()
                buffer = []
            current_file = line.strip().split("Filename:")[-1].strip()
        elif current_file:
            buffer.append(line)
    if current_file and buffer:
        file_issues[current_file] = "\n".join(buffer).strip()
    return file_issues



# ───── FOR VERCEL ─────
app = app
