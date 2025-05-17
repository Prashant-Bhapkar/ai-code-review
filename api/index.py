from flask import Flask, request, jsonify
import os
import logging
import requests
from openai import OpenAI

# ───── Flask + OpenAI Setup ─────
app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# ───── Logging Setup ─────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ───── Health Check ─────
@app.route("/healthz", methods=["GET"])
def health_check():
    logger.info("Health check requested")
    return jsonify({"status": "ok"}), 200

# ───── GitHub Webhook Handler ─────
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = request.headers.get("X-GitHub-Event")
        payload = request.get_json()
        logger.info(f"Received GitHub event: {event}")

        if event != "issue_comment":
            logger.info("Ignored: Not an issue_comment event")
            return jsonify({"status": "ignored"})

        comment_body = payload["comment"]["body"]
        logger.info(f"Comment body: {comment_body}")

        # Check if it's a PR comment
        if "pull_request" not in payload["issue"]:
            logger.info("Ignored: Comment is not on a pull request")
            return jsonify({"status": "ignored - not a PR comment"})

        if comment_body.strip() != "/ai-bot":
            logger.info("Ignored: Comment is not the /ai-bot trigger")
            return jsonify({"status": "ignored - no trigger"})

        # Extract URLs
        pr_url = payload["issue"]["pull_request"]["url"]
        comment_url = payload["issue"]["comments_url"]

        logger.info(f"Triggered on PR: {pr_url}")
        logger.info("Fetching PR diff...")

        diff_url = pr_url + ".diff"
        diff_response = requests.get(diff_url, headers={"Authorization": f"Bearer {GITHUB_TOKEN}"})

        if diff_response.status_code != 200:
            logger.error(f"Failed to fetch diff: {diff_response.status_code} - {diff_response.text}")
            return jsonify({"error": "Failed to fetch PR diff"}), 500

        diff = diff_response.text
        logger.info("PR diff fetched")

        try:
            with open("rules.txt") as f:
                rules = f.read()
            logger.info("Rules loaded from rules.txt")
        except Exception as e:
            logger.error(f"Failed to load rules.txt: {e}")
            return jsonify({"error": "Missing rules.txt"}), 500

        prompt = (
            f"You are an AI code reviewer. ONLY check for violations listed in the rules below.\n"
            f"Rules:\n{rules}\n\n"
            f"Code Diff:\n{diff}\n\n"
            f"Format your response like this:\n"
            f"Issue:\nLocation:\nSolution:\n"
        )

        logger.info("Sending to OpenAI...")
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            result = response.choices[0].message.content
            logger.info("OpenAI response received")
        except Exception as e:
            logger.exception("OpenAI API call failed")
            return jsonify({"error": "OpenAI failed"}), 500

        logger.info("Posting review comment to GitHub...")
        post_response = requests.post(comment_url, json={"body": result}, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        })

        if post_response.status_code == 201:
            logger.info("Comment posted successfully ✅")
        else:
            logger.error(f"Failed to post comment: {post_response.status_code} - {post_response.text}")
            return jsonify({"error": "Failed to post comment"}), 500

        return jsonify({"status": "review posted ✅"})
    except Exception as e:
        logger.exception("Unexpected error occurred in webhook")
        return jsonify({"error": str(e)}), 500

# ───── Required for Vercel ─────
app = app
