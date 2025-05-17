from flask import Flask, request, jsonify
import requests
import openai
import os
import logging

# ─── CONFIGURE LOGGING ─────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── FLASK APP SETUP ───────────────────────────────
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# ─── HELPER FUNCTIONS ──────────────────────────────

def load_rules():
    try:
        with open("rules.txt") as f:
            rules = f.read()
        logger.info("Loaded rules.txt successfully.")
        return rules
    except Exception as e:
        logger.error(f"Failed to load rules.txt: {e}")
        return ""

def get_pr_diff(pr_url):
    try:
        headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
        diff_url = pr_url + ".diff"
        response = requests.get(diff_url, headers=headers)
        logger.info(f"Fetched PR diff from: {diff_url}")
        return response.text
    except Exception as e:
        logger.error(f"Error fetching PR diff: {e}")
        return ""

def call_openai(diff, rules):
    try:
        prompt = (
            f"You are an AI code reviewer. Check only the issues based on the following rules:\n"
            f"{rules}\n\n"
            f"Here is the code diff:\n{diff}\n\n"
            f"Reply only in the below format:\n\n"
            f"Issue:\nLocation:\nSolution:\n"
        )
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        logger.info("OpenAI API call successful.")
        return response.choices[0].message["content"]
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return "Issue:\nLocation:\nSolution:\n(OpenAI failed to generate review.)"

def post_comment(comment_url, body):
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        response = requests.post(comment_url, json={"body": body}, headers=headers)
        if response.status_code == 201:
            logger.info("Successfully posted review comment.")
        else:
            logger.warning(f"Failed to post comment: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error posting comment: {e}")

# ─── MAIN ROUTE ─────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def github_webhook():
    try:
        payload = request.json
        event = request.headers.get("X-GitHub-Event")

        logger.info(f"Received GitHub event: {event}")

        if event == "issue_comment":
            comment = payload["comment"]["body"]
            logger.info(f"Comment body: {comment}")

            if comment.strip() == "/ai-bot":
                pr_url = payload["issue"]["pull_request"]["url"]
                comment_url = payload["issue"]["comments_url"]

                logger.info(f"Triggered on PR: {pr_url}")

                diff = get_pr_diff(pr_url)
                rules = load_rules()
                result = call_openai(diff, rules)
                post_comment(comment_url, result)

        return jsonify({"status": "OK"})
    except Exception as e:
        logger.exception("Unhandled exception occurred during webhook handling.")
        return jsonify({"error": str(e)}), 500

# ─── ENTRY POINT ─────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
