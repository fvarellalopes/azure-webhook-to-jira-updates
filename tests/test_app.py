import unittest
from unittest.mock import patch, MagicMock
import os
import json
import sys

# allow importing app from workspace
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

class TestWebhookUpdated(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    @patch('app.requests.Session')
    def test_pr_created_posts_comment(self, MockSession):
        # Session mock and responses
        session = MagicMock()
        MockSession.return_value = session

        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.status_code = 200
        get_resp.json.return_value = {"comments": []}
        session.get.return_value = get_resp

        post_resp = MagicMock()
        post_resp.raise_for_status.return_value = None
        post_resp.status_code = 201
        session.post.return_value = post_resp

        payload = {
            "eventType": "git.pullrequest.created",
            "resource": {
                "title": "Add feature [J:PROJ-1]",
                "_links": {"web": {"href": "https://dev.azure/.../pullrequest/1"}},
                "lastMergeSourceCommit": {"commitId": "abc123"},
                "creationDate": "2026-01-27T21:24:42Z"
            }
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), patch('app.JIRA_API_KEY', 'fake'):
            resp = self.client.post('/webhook', data=json.dumps(payload), content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        session.get.assert_called()
        session.post.assert_called_once()
        post_url = session.post.call_args[0][0]
        self.assertIn('/rest/api/2/issue/PROJ-1/comment', post_url)
        body = session.post.call_args[1]['json']['body']
        self.assertIn('Atualizações do Pull Request', body)
        self.assertIn('Pull Request Criado', body)
        self.assertIn('Hash: abc123', body)

    @patch('app.requests.Session')
    def test_pr_updated_with_hash_change_appends_pr_updated_block(self, MockSession):
        session = MagicMock()
        MockSession.return_value = session

        # existing comment contains old hash and correct PR link
        existing_body = "*Atualizações do Pull Request Azure DevOps*\nLink: https://dev.azure/.../pullrequest/2\n\nPull Request Criado\nHash: deadbeef\n"
        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.status_code = 200
        get_resp.json.return_value = {"comments": [{"id": "42", "body": existing_body}]}
        session.get.return_value = get_resp

        put_resp = MagicMock()
        put_resp.raise_for_status.return_value = None
        put_resp.status_code = 200
        session.put.return_value = put_resp

        payload = {
            "eventType": "git.pullrequest.updated",
            "resource": {
                "title": "Update [J:PROJ-2]",
                "_links": {"web": {"href": "https://dev.azure/.../pullrequest/2"}},
                "lastMergeSourceCommit": {"commitId": "cafebabe"},
                "creationDate": "2026-01-27T22:00:00Z",
                "status": "active"
            }
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), patch('app.JIRA_API_KEY', 'fake'):
            resp = self.client.post('/webhook', data=json.dumps(payload), content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        session.get.assert_called()
        session.post.assert_called_once()
        post_url = session.post.call_args[0][0]
        self.assertIn('/rest/api/2/issue/PROJ-2/comment', post_url)
        body = session.post.call_args[1]['json']['body']
        self.assertIn('PR Atualizado', body)
        self.assertIn('Hash: cafebabe', body)
        self.assertIn('Status: active', body)

    @patch('app.requests.Session')
    def test_reviewers_update_adds_reviewers_block_and_pr_hash_when_special_votes(self, MockSession):
        session = MagicMock()
        MockSession.return_value = session

        # existing comment without reviewers summary but with hash
        existing_body = "*Atualizações do Pull Request Azure DevOps*\nLink: https://dev.azure/.../pullrequest/3\n\nPull Request Criado\nHash: 111111\n"
        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.status_code = 200
        get_resp.json.return_value = {"comments": [{"id": "99", "body": existing_body}]}
        session.get.return_value = get_resp

        put_resp = MagicMock()
        put_resp.raise_for_status.return_value = None
        put_resp.status_code = 200
        session.put.return_value = put_resp

        reviewers = [
            {"displayName": "Reviewer One", "vote": 10},
            {"displayName": "Reviewer Two", "vote": 0},
        ]

        payload = {
            "eventType": "git.pullrequest.updated",
            "resource": {
                "title": "Reviewers [J:PROJ-3]",
                "_links": {"web": {"href": "https://dev.azure/.../pullrequest/3"}},
                "lastMergeSourceCommit": {"commitId": "222222"},
                "creationDate": "2026-01-27T23:00:00Z",
                "reviewers": reviewers,
                "status": "active"
            }
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), patch('app.JIRA_API_KEY', 'fake'):
            resp = self.client.post('/webhook', data=json.dumps(payload), content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        session.get.assert_called()
        session.post.assert_called_once()
        body = session.post.call_args[1]['json']['body']
        self.assertIn('Resumo de Revisores', body)
        self.assertIn('Reviewer One - *Aprovado*', body)
        # because Reviewer One had a special vote (10), the comment should include PR update details and the new hash
        self.assertIn('PR Atualizado', body)
        self.assertIn('Hash: 222222', body)

    @patch('app.requests.Session')
    def test_pr_comment_event_appends_comment_and_link_and_skips_reviewers_block(self, MockSession):
        session = MagicMock()
        MockSession.return_value = session

        existing_body = "*Atualizações do Pull Request Azure DevOps*\nLink: https://dev.azure/.../pullrequest/4\n\nPull Request Criado\nHash: deadbeef\n"
        get_resp = MagicMock()
        get_resp.raise_for_status.return_value = None
        get_resp.status_code = 200
        get_resp.json.return_value = {"comments": [{"id": "7", "body": existing_body}]}
        session.get.return_value = get_resp

        put_resp = MagicMock()
        put_resp.raise_for_status.return_value = None
        put_resp.status_code = 200
        session.put.return_value = put_resp

        payload = {
            "eventType": "ms.vss-code.git-pullrequest-comment-event",
            "resource": {
                "comment": {
                    "content": "Looks good to me",
                    "publishedDate": "2026-01-28T00:24:40Z",
                    "author": {"displayName": "Alice"}
                },
                "pullRequest": {
                    "title": "Comment [J:PROJ-4]",
                    "_links": {"web": {"href": "https://dev.azure/.../pullrequest/4"}},
                    "lastMergeSourceCommit": {"commitId": "abcabc"}
                }
            },
            "message": {"markdown": "Alice has [commented](https://dev.azure/.../pullrequest/4?_a=files&discussionId=5)"}
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), patch('app.JIRA_API_KEY', 'fake'):
            resp = self.client.post('/webhook', data=json.dumps(payload), content_type='application/json')

        self.assertEqual(resp.status_code, 200)
        session.get.assert_called()
        session.post.assert_called_once()
        body = session.post.call_args[1]['json']['body']
        self.assertIn('Comentário de Alice', body)
        self.assertIn('Looks good to me', body)
        self.assertIn('Link do comentário: https://dev.azure', body)
        # reviewers block must NOT be present for comment events
        self.assertNotIn('*Revisores atualizados*', body)

if __name__ == '__main__':
    unittest.main()
