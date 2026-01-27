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

def get_jira_headers():
    headers = {
        "Content-Type": "application/json"
    }
    if not JIRA_USERNAME:
         headers["Authorization"] = f"Bearer {JIRA_API_KEY}"
    return headers

def get_jira_auth():
    if JIRA_USERNAME:
        return (JIRA_USERNAME, JIRA_API_KEY)
    return None

def process_jira_comment(issue_id, new_content, pr_url):
    """
    Adds a new comment or updates an existing one if it matches the PR URL.
    """
    if not JIRA_URL or not JIRA_API_KEY:
        print("Error: Jira configuration missing.")
        return False

    base_url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue/{issue_id}/comment"

    headers = get_jira_headers()
    auth = get_jira_auth()

    # 1. Get existing comments
    try:
        response = requests.get(base_url, headers=headers, auth=auth)
        response.raise_for_status()
        comments_data = response.json()
        comments = comments_data.get('comments', [])
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch comments for issue {issue_id}: {e}")
        return False

    # 2. Find existing comment for this PR
    target_comment = None
    for comment in comments:
        body = comment.get('body', '')
        # Simple check: does the body contain the PR URL?
        if pr_url in body:
            target_comment = comment
            break

    # 3. Create or Update
    if target_comment:
        # Update existing
        comment_id = target_comment.get('id')
        current_body = target_comment.get('body', '')

        # Avoid duplicating the exact same message if possible, but the requirement is "accumulate"
        # We append the new content.
        updated_body = current_body + "\n\n" + "---" + "\n\n" + new_content

        update_url = f"{base_url}/{comment_id}"
        payload = {"body": updated_body}

        try:
            response = requests.put(update_url, json=payload, headers=headers, auth=auth)
            response.raise_for_status()
            print(f"Comment updated on Jira issue {issue_id}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to update comment {comment_id} on issue {issue_id}: {e}")
            return False

    else:
        # Create new
        # We assume the first line identifies the PR context clearly.
        full_body = f"**Atualizações do Pull Request Azure DevOps**\nLink: {pr_url}\n\n{new_content}"
        payload = {"body": full_body}

        try:
            response = requests.post(base_url, json=payload, headers=headers, auth=auth)
            response.raise_for_status()
            print(f"New comment created on Jira issue {issue_id}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to create comment on issue {issue_id}: {e}")
            return False

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data:
        return jsonify({"message": "Nenhum payload JSON recebido"}), 400

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
    match = re.search(r'\[J:([\w-]+)\]', title)
    if not match:
        print("ID da tarefa Jira não encontrado no título do PR")
        return jsonify({"message": "ID da tarefa Jira não encontrado"}), 200

    jira_task_id = match.group(1)

    # Get PR URL
    pr_url = ""
    if 'web' in pr_links:
        pr_url = pr_links['web']['href']
    elif 'url' in resource:
        pr_url = resource['url']

    # Determine comment content based on event type (Portuguese)
    message_content = ""
    if event_type == 'git.pullrequest.created':
        message_content = f"Pull Request Criado: {title}"

    elif event_type == 'git.pullrequest.merged':
        merge_status = resource.get('mergeStatus', 'Desconhecido')
        message_content = f"Tentativa de Merge do PR.\nTítulo: {title}\nStatus do Merge: {merge_status}"

    elif event_type == 'git.pullrequest.updated':
        status = resource.get('status', 'Desconhecido')
        message_content = f"PR Atualizado.\nTítulo: {title}\nStatus: {status}"

    elif event_type == 'ms.vss-code.git-pullrequest-comment-event':
        comment_obj = resource.get('comment', {})
        author_display_name = comment_obj.get('author', {}).get('displayName', 'Desconhecido')
        content = comment_obj.get('content', '')
        message_content = f"Comentário de {author_display_name}:\n{content}"

    else:
        message_content = f"Evento Azure DevOps ({event_type}) relacionado ao PR: {title}"

    success = process_jira_comment(jira_task_id, message_content, pr_url)
    if success:
        return jsonify({"message": "Comentário adicionado/atualizado no Jira"}), 200
    else:
        return jsonify({"message": "Falha ao processar comentário no Jira"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
