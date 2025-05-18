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

# ───── GITHUB WEBHOOK ─────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = request.headers.get("X-GitHub-Event")
        payload = request.get_json()

        logger.info(f"Received GitHub event: {event}")

        if event == "issue_comment":
            comment_body = payload["comment"]["body"]
            logger.info(f"Comment content: {comment_body}")

            if comment_body.strip() == "/ai-bot":
                pr_url = payload["issue"]["pull_request"]["url"]
                pr_number = pr_url.split("/")[-1]
                owner = payload["repository"]["owner"]["login"]
                repo = payload["repository"]["name"]

                logger.info(f"Triggered on PR: {pr_url}")
                logger.info("Fetching PR diff...")

                diff_response = requests.get(
                    pr_url + ".diff",
                    headers={
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github.v3.diff"
                    }
                )
                diff = diff_response.text
                logger.info("\n".join(diff.splitlines()[:10]))

                try:
                    with open("rules.txt") as f:
                        rules = f.read()
                        logger.info("Rules loaded from rules.txt")
                except Exception as e:
                    logger.error(f"Error reading rules.txt: {e}")
                    return jsonify({"error": "Failed to load rules file"}), 500

                prompt = (
                    "You're an AI code reviewer. Review the Git diff below for violations based on the given rules.\n"
                    "Group the issues by file and clearly format them as shown.\n"
                    "Do NOT suggest unrelated issues.\n\n"
                    "Format:\n"
                    "Filename: <filename>\n"
                    "1. Issue:\n   Location:\n   Solution:\n\n"
                    f"Rules:\n{rules}\n\n"
                    f"Git Diff:\n{diff}"
                )

                logger.info("Calling OpenAI API...")

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )

                result = response.choices[0].message.content.strip()
                logger.info("OpenAI response received")

                if not result or result.lower() == "none":
                    logger.info("No violations found. Skipping comment.")
                    return jsonify({"status": "no violations"})

                # Parse AI result by file
                file_issues = extract_issues_per_file(result)

                # Get PR info
                pr_data = requests.get(pr_url, headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}"
                }).json()
                commit_id = pr_data["head"]["sha"]

                files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
                files_data = requests.get(files_url, headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}"
                }).json()

                headers = {
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json"
                }

                review_comment_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"

                for file in files_data:
                    filename = file["filename"]
                    patch = file.get("patch", "")
                    if filename in file_issues:
                        position = get_last_position(patch)
                        body = f"👀 AI Code Review Feedback for `{filename}`:\n\n{file_issues[filename]}"

                        comment_payload = {
                            "body": body,
                            "commit_id": commit_id,
                            "path": filename,
                            "position": position
                        }

                        r = requests.post(review_comment_url, json=comment_payload, headers=headers)
                        logger.info(f"Posted comment for {filename}: {r.status_code}")

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("Webhook error occurred")
        return jsonify({"error": str(e)}), 500

# ───── FOR VERCEL ─────
app = app
