import os
import re
import requests
import logging
from typing import Any, Dict, List, Optional
from flask import Flask, request, jsonify
from dotenv import load_dotenv

"""azure-webhook-to-jira-updates

Lightweight Flask webhook that receives Azure DevOps pull request events and
creates/updates a single comment on the linked Jira issue. Each incoming event
is appended to the end of the Jira comment, separated by a visible hyphen
delimiter. Sensitive values (API keys, cookies, headers, response bodies)
are not logged; errors log stacktraces only.
"""

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configuration
JIRA_URL = os.getenv('JIRA_URL')
JIRA_API_KEY = os.getenv('JIRA_API_KEY')
JIRA_USERNAME = os.getenv('JIRA_USERNAME')
JIRA_TIMEOUT = int(os.getenv('JIRA_TIMEOUT', '10'))

def get_jira_headers():
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Atlassian-Token": "no-check",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    if JIRA_API_KEY:
        headers["Authorization"] = f"Bearer {JIRA_API_KEY}"
    return headers

def jira_request(method, url, **kwargs):
    """Perform a single Jira HTTP request using a fresh Session.

    This helper resets cookies to avoid sharing state between calls and
    ensures headers from `get_jira_headers()` are applied. Returns the
    requests.Response object. Caller is responsible for inspecting status
    and content.
    """
    headers = get_jira_headers()
    extra_headers = kwargs.pop('headers', None)
    if extra_headers:
        headers.update(extra_headers)

    timeout = kwargs.pop('timeout', JIRA_TIMEOUT)

    session = requests.Session()
    # ensure no cookies are present
    session.cookies.clear()
    session.headers.update(headers)

    try:
        resp = session.request(method, url, timeout=timeout, **kwargs)
        return resp
    finally:
        session.close()


def vote_to_status(v: Any) -> str:
    """Map reviewer vote value to a Portuguese status string.

    - 10 -> 'Aprovado'
    - -10 -> 'Reprovado'
    - -5 -> 'Aguardando autor'
    - 0 -> 'Aguardando revisão'
    - other -> 'vote=<value>'
    """
    try:
        iv = int(v)
    except Exception:
        return str(v or '')
    if iv == 10:
        return 'Aprovado'
    if iv == -10:
        return 'Reprovado'
    if iv == -5:
        return 'Aguardando autor'
    if iv == 0:
        return 'Aguardando revisão'
    return f'vote={iv}'




def process_jira_comment(
    issue_id: str,
    new_content: str,
    pr_url: str,
    pr_source_commit: Optional[str] = None,
    pr_event_date: Optional[str] = None,
    pr_status: Optional[str] = None,
    pr_reviewers: Optional[List[Dict[str, Any]]] = None,
    show_reviewers_summary: bool = True,
    consider_reviewers_delta: bool = True,
) -> bool:
    """Create or update a Jira comment for `issue_id` related to `pr_url`.

    - If a comment already exists that contains the PR link, update it by
      appending `new_content` and any detected deltas (hash/status/reviewers).
        - Otherwise, post a new comment containing `new_content`, PR link and
            optional `pr_source_commit` + `pr_event_date`.
        - `show_reviewers_summary`: when False, skip adding the compact reviewers
            summary to newly created comments (useful for PR created events).
        - `consider_reviewers_delta`: when False, do not append the "Revisores atualizados"
            block on updates (useful for comment events).

    Returns True on success, False otherwise.
    """
    if not JIRA_URL or not JIRA_API_KEY:
        logger.error("Jira configuration missing.")
        return False

    base_url = f"{JIRA_URL.rstrip('/')}/rest/api/2/issue/{issue_id}/comment"

    headers = get_jira_headers()

    # Use a single session so the initial GET can receive JSESSIONID and
    # subsequent PUT/POST reuse that cookie (per Jira cookie-based auth).
    session = requests.Session()
    session.headers.update(headers)
    session.cookies.clear()

    # No explicit login: rely on the initial GET to set JSESSIONID cookie (cookie-based auth)

    # 1. Get existing comments (this should return Set-Cookie: JSESSIONID)
    try:
        logger.info("Requesting Jira comments for issue %s", issue_id)
        response = session.get(base_url, timeout=JIRA_TIMEOUT)
        logger.info("Jira GET %s -> status=%s", base_url, response.status_code)
        try:
            response.raise_for_status()
            comments_data = response.json()
            comments = comments_data.get('comments', [])
            logger.info("Parsed %d comments from Jira", len(comments))
        except requests.exceptions.RequestException:
            logger.exception("Failed to fetch comments for issue %s (status=%s)", issue_id, response.status_code)
            try:
                session.close()
            except Exception:
                pass
            return False
        except ValueError:
            logger.exception("Failed to parse JSON from Jira GET for issue %s (status=%s)", issue_id, response.status_code)
            try:
                session.close()
            except Exception:
                pass
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch comments for issue {issue_id}: {e}")
        try:
            session.close()
        except Exception:
            pass
        return False

    # 2. Find existing comment for this PR
    target_comment = None
    for comment in comments:
        body = comment.get('body', '')
        # Simple check: does the body contain the PR URL?
        if pr_url in body:
            target_comment = comment
            break

    # Per new requirement: always create a new Jira comment for every incoming
    # Azure event. Do not update/append to existing comments.
    target_comment = None

    # 3. Create or Update (delegated to small helpers)

    def _create_jira_comment(session_obj, url, body_text) -> bool:
        payload = {"body": body_text}
        try:
            xsrf = session_obj.cookies.get('atlassian.xsrf.token')
            if xsrf:
                session_obj.headers['X-Atlassian-Token'] = xsrf
                session_obj.headers['Referer'] = JIRA_URL
                session_obj.headers['Origin'] = JIRA_URL
            logger.info("Creating new comment on issue %s", issue_id)
            resp = session_obj.post(url, json=payload, timeout=JIRA_TIMEOUT)
            logger.info("Jira POST %s -> status=%s", url, resp.status_code)
            resp.raise_for_status()
            logger.info("New comment created on Jira issue %s", issue_id)
            return True
        except requests.exceptions.RequestException:
            logger.exception("Failed to create comment on issue %s", issue_id)
            return False
    # Create new comment body and POST
    full_body = f"*Atualizações do Pull Request Azure DevOps*\nLink: {pr_url}\n\n{new_content}"
    if pr_source_commit:
        full_body += f"\nHash: {pr_source_commit}\nData: {pr_event_date or ''}\n"
    # include a compact reviewers summary if provided and allowed
    if pr_reviewers and show_reviewers_summary:
        try:
            parts = [f"{r.get('displayName')} - *{vote_to_status(r.get('vote'))}*" for r in pr_reviewers]
            summary = ", ".join(parts)
            full_body += f"\nResumo de Revisores: {summary}\n"
        except Exception:
            pass

    try:
        result = _create_jira_comment(session, base_url, full_body)
        return result
    finally:
        try:
            session.close()
        except Exception:
            pass

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data:
        logger.warning("No JSON payload received")
        return jsonify({"message": "Nenhum payload JSON recebido"}), 400

    event_type = data.get('eventType', '')
    resource = data.get('resource', {})

    logger.debug(f"Received event: {event_type}")

    # Handle specific event structures
    pr_resource = {}
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
        logger.info("ID da tarefa Jira não encontrado no título do PR")
        return jsonify({"message": "ID da tarefa Jira não encontrado"}), 200

    jira_task_id = match.group(1)
    logger.info(f"Found Jira Task ID: {jira_task_id}")

    # Get PR URL
    pr_url = ""
    if 'web' in pr_links:
        pr_url = pr_links['web']['href']
    elif 'url' in resource:
        pr_url = resource['url']

    # Fallbacks: sometimes the comment event places links in nested structures
    # or only provides a comment link in `message.markdown`. Try those sources
    # when `pr_url` is empty.
    if not pr_url:
        # try nested pullRequest._links
        nested_pr = None
        if isinstance(resource, dict):
            nested_pr = resource.get('pullRequest') or resource.get('resource')
        if nested_pr and isinstance(nested_pr, dict):
            nl = nested_pr.get('_links', {})
            if isinstance(nl, dict) and 'web' in nl and nl['web'].get('href'):
                pr_url = nl['web']['href']

    if not pr_url:
        # attempt to extract from message.markdown (comment events often include a link)
        message_md = data.get("message", {}).get("markdown", "") if isinstance(data.get("message"), dict) else ""
        mlink = re.search(r'\((https?://[^)]+)\)', message_md or "")
        if mlink:
            url = mlink.group(1)
            # drop query params
            url_no_q = url.split('?')[0]
            # capture up to /pullrequest/<id> if present
            mpr = re.search(r'(https?://[^/]+/.*/pullrequest/\d+)', url_no_q)
            pr_url = mpr.group(1) if mpr else url_no_q

    # Extract PR source commit and event date (createdDate from webhook or resource.creationDate)
    pr_source_commit = None
    # check pr_resource (comment event) first, then resource
    if pr_resource:
        pr_source_commit = pr_resource.get('lastMergeSourceCommit', {}).get('commitId')
    if not pr_source_commit:
        pr_source_commit = resource.get('lastMergeSourceCommit', {}).get('commitId')

    pr_event_date = data.get("createdDate") or resource.get("creationDate")
    # PR status extraction for use in comment updates
    pr_status = None
    if pr_resource:
        pr_status = pr_resource.get('status')
    if not pr_status:
        pr_status = resource.get('status')
    # Extract reviewers list for comparison (use pr_resource then resource)
    pr_reviewers = None
    if pr_resource and pr_resource.get('reviewers'):
        pr_reviewers = pr_resource.get('reviewers')
    elif resource.get('reviewers'):
        pr_reviewers = resource.get('reviewers')

    # Determine comment content based on event type (Portuguese)
    message_content = ""
    if event_type == 'git.pullrequest.created':
        message_content = f"Pull Request Criado: {title}"

    elif event_type == 'git.pullrequest.merged':
        merge_status = resource.get('mergeStatus', 'Desconhecido')
        message_content = f"Tentativa de Merge do PR.\nTítulo: {title}\nStatus do Merge: {merge_status}"

    elif event_type == 'git.pullrequest.updated':
        status = resource.get('status', 'Desconhecido')
        message_content = f"*PR Atualizado*.\nTítulo: {title}\nStatus: {status}"

    elif event_type == "ms.vss-code.git-pullrequest-comment-event":
        comment_obj = resource.get('comment', {})
        author_display_name = comment_obj.get('author', {}).get('displayName', 'Desconhecido')
        content = comment_obj.get('content', '')
        published = comment_obj.get('publishedDate', '')
        message_content = f"Comentário de {author_display_name}:\n{{noformat}}\n{content}\n{{noformat}}\nData do comentário: {published}"
        # extract direct comment link from message.markdown if present (first parenthesized URL)
        message_md = data.get("message", {}).get("markdown", "")
        mlink = re.search(r'\((https?://[^)]+)\)', message_md)
        if mlink:
            comment_link = mlink.group(1)
            message_content += f"\nLink do comentário: {comment_link}"
        # use the comment published date as the event date for this update
        pr_event_date = published or pr_event_date

    else:
        message_content = f"Evento Azure DevOps ({event_type}) relacionado ao PR: {title}"

    success = process_jira_comment(
        jira_task_id,
        message_content,
        pr_url,
        pr_source_commit=pr_source_commit,
        pr_event_date=pr_event_date,
        pr_status=pr_status,
        pr_reviewers=pr_reviewers,
            consider_reviewers_delta=(event_type != 'ms.vss-code.git-pullrequest-comment-event'),
    )
    if success:
        return jsonify({"message": "Comentário adicionado/atualizado no Jira"}), 200
    else:
        return jsonify({"message": "Falha ao processar comentário no Jira"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8023, debug=True)
