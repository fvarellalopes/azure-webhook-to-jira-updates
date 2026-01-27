import unittest
from unittest.mock import patch, MagicMock
import os
import json
import sys

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

class TestWebhook(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.post')
    @patch('app.requests.get')
    def test_webhook_pr_created_new_comment(self, mock_get, mock_post):
        # Mock GET comments: return empty list
        mock_get_response = MagicMock()
        mock_get_response.raise_for_status.return_value = None
        mock_get_response.json.return_value = {"comments": []}
        mock_get.return_value = mock_get_response

        # Mock POST comment
        mock_post_response = MagicMock()
        mock_post_response.raise_for_status.return_value = None
        mock_post.return_value = mock_post_response

        payload = {
            "eventType": "git.pullrequest.created",
            "resource": {
                "title": "Fix bug [J:DSFAFAB-3525]",
                "_links": {
                    "web": {
                        "href": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1"
                    }
                }
            }
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), \
             patch('app.JIRA_API_KEY', 'fake_token'):
            response = self.app.post('/webhook',
                                     data=json.dumps(payload),
                                     content_type='application/json')

        self.assertEqual(response.status_code, 200)

        # Verify GET called
        mock_get.assert_called()

        # Verify POST called
        args, kwargs = mock_post.call_args
        self.assertIn('https://jira.example.com/rest/api/2/issue/DSFAFAB-3525/comment', args[0])
        # Check Portuguese text
        self.assertIn('**Atualizações do Pull Request Azure DevOps**', kwargs['json']['body'])
        self.assertIn('Pull Request Criado', kwargs['json']['body'])

    @patch('app.requests.put')
    @patch('app.requests.get')
    def test_webhook_pr_comment_append(self, mock_get, mock_put):
        pr_url = "https://dev.azure.com/org/proj/_git/repo/pullrequest/1"

        # Mock GET comments: return existing comment with PR URL
        mock_get_response = MagicMock()
        mock_get_response.raise_for_status.return_value = None
        existing_comment_body = f"**Atualizações do Pull Request Azure DevOps**\nLink: {pr_url}\n\nPull Request Criado: ..."
        mock_get_response.json.return_value = {
            "comments": [
                {
                    "id": "10001",
                    "body": existing_comment_body
                }
            ]
        }
        mock_get.return_value = mock_get_response

        # Mock PUT comment
        mock_put_response = MagicMock()
        mock_put_response.raise_for_status.return_value = None
        mock_put.return_value = mock_put_response

        payload = {
            "eventType": "ms.vss-code.git-pullrequest-comment-event",
            "resource": {
                "comment": {
                    "content": "Boa mudança!",
                    "author": {
                        "displayName": "João Silva"
                    }
                },
                "pullRequest": {
                    "title": "Feature [J:DSFAFAB-3525]",
                    "_links": {
                        "web": {
                            "href": pr_url
                        }
                    }
                }
            }
        }

        with patch('app.JIRA_URL', 'https://jira.example.com'), \
             patch('app.JIRA_API_KEY', 'fake_token'):
            response = self.app.post('/webhook',
                                     data=json.dumps(payload),
                                     content_type='application/json')

        self.assertEqual(response.status_code, 200)

        # Verify PUT called (not POST)
        args, kwargs = mock_put.call_args
        self.assertIn('https://jira.example.com/rest/api/2/issue/DSFAFAB-3525/comment/10001', args[0])

        updated_body = kwargs['json']['body']
        self.assertIn(existing_comment_body, updated_body)
        self.assertIn("---", updated_body)
        self.assertIn("Comentário de João Silva", updated_body)
        self.assertIn("Boa mudança!", updated_body)

    def test_webhook_no_jira_id(self):
        payload = {
            "resource": {
                "title": "Fix bug without id"
            }
        }
        response = self.app.post('/webhook',
                                 data=json.dumps(payload),
                                 content_type='application/json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"message": "ID da tarefa Jira não encontrado"})

if __name__ == '__main__':
    unittest.main()
