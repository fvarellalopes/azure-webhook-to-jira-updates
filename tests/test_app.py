import unittest
from unittest.mock import patch, MagicMock
import os
import json
import sys
import requests

# Add the parent directory to sys.path so we can import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

class TestWebhook(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.requests.post')
    def test_webhook_pr_created(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

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

        args, kwargs = mock_post.call_args
        self.assertIn('https://jira.example.com/rest/api/2/issue/DSFAFAB-3525/comment', args[0])
        self.assertIn('Mentioned in Azure DevOps Pull Request Created', kwargs['json']['body'])
        self.assertIn('Fix bug [J:DSFAFAB-3525]', kwargs['json']['body'])

    @patch('app.requests.post')
    def test_webhook_pr_merged(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        payload = {
            "eventType": "git.pullrequest.merged",
            "resource": {
                "title": "Merge feature [J:DSFAFAB-3525]",
                "mergeStatus": "succeeded",
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

        args, kwargs = mock_post.call_args
        self.assertIn('Azure DevOps PR Merge Attempted', kwargs['json']['body'])
        self.assertIn('Merge Status: succeeded', kwargs['json']['body'])

    @patch('app.requests.post')
    def test_webhook_pr_updated(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        payload = {
            "eventType": "git.pullrequest.updated",
            "resource": {
                "title": "Update feature [J:DSFAFAB-3525]",
                "status": "active",
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

        args, kwargs = mock_post.call_args
        self.assertIn('Azure DevOps PR Updated', kwargs['json']['body'])
        self.assertIn('Status: active', kwargs['json']['body'])

    @patch('app.requests.post')
    def test_webhook_pr_commented(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        payload = {
            "eventType": "ms.vss-code.git-pullrequest-comment-event",
            "resource": {
                "comment": {
                    "content": "Nice change!",
                    "author": {
                        "displayName": "John Doe"
                    }
                },
                "pullRequest": {
                    "title": "Feature [J:DSFAFAB-3525]",
                    "_links": {
                        "web": {
                            "href": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1"
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

        args, kwargs = mock_post.call_args
        self.assertIn('John Doe commented on Azure DevOps PR', kwargs['json']['body'])
        self.assertIn('Content: Nice change!', kwargs['json']['body'])

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
        self.assertEqual(response.json, {"message": "No Jira task ID found"})

if __name__ == '__main__':
    unittest.main()
