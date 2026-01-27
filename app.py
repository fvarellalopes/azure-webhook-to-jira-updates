import os
import re
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
JIRA_URL = os.getenv('JIRA_URL')
JIRA_API_KEY = os.getenv('JIRA_API_KEY')
JIRA_USERNAME = os.getenv('JIRA_USERNAME')

def add_jira_comment(issue_id, comment):
    """
    Adds a comment to a Jira issue.
    """
    if not JIRA_URL or not JIRA_API_KEY:
        print("Error: Jira configuration missing.")
        return False

    url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue/{issue_id}/comment"

    headers = {
        "Content-Type": "application/json"
    }

    auth = None
    if JIRA_USERNAME:
        auth = (JIRA_USERNAME, JIRA_API_KEY)
    else:
        headers["Authorization"] = f"Bearer {JIRA_API_KEY}"

    payload = {
        "body": comment
    }

    try:
        response = requests.post(url, json=payload, headers=headers, auth=auth)
        response.raise_for_status()
        print(f"Comment added to Jira issue {issue_id}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Failed to add comment to Jira issue {issue_id}: {e}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data:
        return jsonify({"message": "No JSON payload received"}), 400

    event_type = data.get('eventType', '')
    resource = data.get('resource', {})

    # Handle specific event structures
    if event_type == 'ms.vss-code.git-pullrequest-comment-event':
        pr_resource = resource.get('pullRequest', {})
        title = pr_resource.get('title', '')
        pr_links = pr_resource.get('_links', {})
    else:
        title = resource.get('title', '')
        pr_links = resource.get('_links', {})

    # Extract Jira Task ID
    # Format: [J:PROJECT-123] or [J:123]
    # Supports alphanumeric and hyphens
    match = re.search(r'\[J:([\w-]+)\]', title)
    if not match:
        print("No Jira task ID found in PR title")
        return jsonify({"message": "No Jira task ID found"}), 200

    jira_task_id = match.group(1)

    # Get PR URL
    pr_url = ""
    if 'web' in pr_links:
        pr_url = pr_links['web']['href']
    elif 'url' in resource:
        pr_url = resource['url']

    # Determine comment content based on event type
    comment = ""
    if event_type == 'git.pullrequest.created':
        comment = f"Mentioned in Azure DevOps Pull Request Created: {title}\nLink: {pr_url}"

    elif event_type == 'git.pullrequest.merged':
        merge_status = resource.get('mergeStatus', 'Unknown')
        comment = f"Azure DevOps PR Merge Attempted.\nTitle: {title}\nMerge Status: {merge_status}\nLink: {pr_url}"

    elif event_type == 'git.pullrequest.updated':
        status = resource.get('status', 'Unknown')
        comment = f"Azure DevOps PR Updated.\nTitle: {title}\nStatus: {status}\nLink: {pr_url}"

    elif event_type == 'ms.vss-code.git-pullrequest-comment-event':
        comment_obj = resource.get('comment', {})
        author_display_name = comment_obj.get('author', {}).get('displayName', 'Unknown')
        content = comment_obj.get('content', '')
        comment = f"{author_display_name} commented on Azure DevOps PR: {title}\nContent: {content}\nLink: {pr_url}"

    else:
        # Default fallback for unhandled events that might match regex
        comment = f"Azure DevOps Event ({event_type}) related to PR: {title}\nLink: {pr_url}"

    success = add_jira_comment(jira_task_id, comment)
    if success:
        return jsonify({"message": "Comment added to Jira"}), 200
    else:
        return jsonify({"message": "Failed to add comment to Jira"}), 500

if __name__ == '__main__':
    app.run(port=5000)
