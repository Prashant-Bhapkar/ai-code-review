from flask import Flask, request, jsonify
import os
import openai
import requests
import logging

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = request.headers.get("X-GitHub-Event")
        payload = request.get_json()

        if event == "issue_comment":
            comment_body = payload["comment"]["body"]
            if comment_body.strip() == "/ai-bot":
                pr_url = payload["issue"]["pull_request"]["url"]
                comment_url = payload["issue"]["comments_url"]

                logger.info(f"Triggered by comment on PR: {pr_url}")

                diff = requests.get(pr_url + ".diff", headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}"
                }).text

                with open("rules.txt") as f:
                    rules = f.read()

                prompt = (
                    f"You are an AI code reviewer. ONLY check for violations listed in the rules below.\n"
                    f"Rules:\n{rules}\n\n"
                    f"Code Diff:\n{diff}\n\n"
                    f"Format your response like this:\n"
                    f"Issue:\nLocation:\nSolution:\n"
                )

                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )

                result = response.choices[0].message["content"]

                requests.post(comment_url, json={"body": result}, headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json"
                })

        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("Error handling webhook")
        return jsonify({"error": str(e)}), 500

app = app
