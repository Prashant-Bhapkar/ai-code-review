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

# ───── HEALTH CHECK ─────
@app.route("/healthz", methods=["GET"])
def health_check():
    logger.info("Health check triggered")
    return jsonify({"status": "ok"}), 200

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
                comment_url = payload["issue"]["comments_url"]

                logger.info(f"Triggered on PR: {pr_url}")
                logger.info("Fetching PR diff...")

                diff = requests.get(pr_url + ".diff", headers={
                    "Authorization": f"Bearer {GITHUB_TOKEN}"
                }).text

                logger.info("PR diff fetched successfully")

                try:
                    with open("rules.txt") as f:
                        rules = f.read()
                        logger.info("Rules loaded from rules.txt")
                except Exception as e:
                    logger.error(f"Error reading rules.txt: {e}")
                    return jsonify({"error": "Failed to load rules file"}), 500

                prompt = (
                    f"You are an AI code reviewer. ONLY check for violations listed in the rules below.\n"
                    f"Rules:\n{rules}\n\n"
                    f"Code Diff:\n{diff}\n\n"
                    f"Format your response like this:\n"
                    f"Issue:\nLocation:\nSolution:\n"
                )

                logger.info("Calling OpenAI API...")

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )

                result = response.choices[0].message.content
                logger.info("OpenAI response received")

                logger.info("Posting comment back to GitHub...")
                logger.info(f"Comment URL: {comment_url}")

                headers = {
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json"
                }

                response = requests.post(comment_url, json={"body": result}, headers=headers)

                if response.status_code == 201:
                    logger.info("✅ Comment posted successfully!")
                else:
                    logger.warning(f"❌ Failed to post comment: {response.status_code} - {response.text}")


        return jsonify({"status": "ok"})
    except Exception as e:
        logger.exception("Webhook error occurred")
        return jsonify({"error": str(e)}), 500

# ───── FOR VERCEL ─────
app = app
