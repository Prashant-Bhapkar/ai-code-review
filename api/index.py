from flask import Flask, request, jsonify
import requests
import openai
import os
import logging

app = Flask(__name__)

openai.api_key = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# ── Health Check ─────────────────────────────
@app.route("/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200

# ── Webhook Handler ──────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = request.headers.get("X-GitHub-Event")
        data = request.get_json()

        if event == "issue_comment":
            comment = data["comment"]["body"]
            if comment.strip() == "/ai-bot":
                pr_url = data["issue"]["pull_request"]["url"]
                comment_url = data["issue"]["comments_url"]

                headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
                diff = requests.get(pr_url + ".diff", headers=headers).text

                with open("rules.txt") as f:
                    rules = f.read()

                prompt = f"You are an AI code reviewer. Use rules:\n{rules}\n\nDiff:\n{diff}\n\nRespond:\nIssue:\nLocation:\nSolution:\n"
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                )

                result = response.choices[0].message["content"]

                requests.post(comment_url, json={"body": result}, headers=headers)

        return jsonify({"status": "done"})
    except Exception as e:
        logger.exception("Webhook error")
        return jsonify({"error": str(e)}), 500

# ── Vercel Handler ───────────────────────────
def handler(environ, start_response):
    return app.wsgi_app(environ, start_response)

# Required alias for Vercel
app = app
