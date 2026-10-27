import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import process_issues_locally as processor


class IssueProcessorTests(unittest.TestCase):
    def run_processor(self, *, existing=False, summary_status=0,
                      build_status=0, push_fails=False, save_summary=True,
                      state="OPEN", artifacts=True):
        issue = {"number": 61, "title": "https://youtu.be/MTVZxNnPLKo",
                 "body": "한국의 성공 요인은", "author": {"login": "meesokim"},
                 "state": state}
        video = {"youtube_id": "MTVZxNnPLKo", "issue_number": 61,
                 "filename": "sample", "title": "Sample"}
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if "fetch_and_summery.py" in command:
                if summary_status == 0 and save_summary:
                    Path("data/videos.json").write_text(json.dumps([video]))
                return subprocess.CompletedProcess(command, summary_status)
            if "generate.py" in command:
                return subprocess.CompletedProcess(command, build_status)
            if command[:2] == ["git", "push"] and push_fails:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 1 if command[1:3] == ["diff", "--cached"] else 0)

        with tempfile.TemporaryDirectory() as directory:
            original = os.getcwd()
            try:
                os.chdir(directory)
                Path("data").mkdir()
                Path("docs").mkdir()
                Path("data/videos.json").write_text(json.dumps([video] if existing else []))
                if artifacts:
                    for ext in ("html", "pptx"):
                        Path(f"docs/sample.{ext}").touch()
                with patch.object(processor, "get_repo_name", return_value="meesokim/my-youtube-gallary"), \
                     patch.object(processor, "check_gh_cli", return_value=True), \
                     patch.object(processor, "get_all_issues", return_value=[issue]), \
                     patch.object(processor.subprocess, "run", side_effect=run), \
                     patch.object(processor, "close_github_issue", return_value=True) as close, \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = processor.main()
                    return result, close.call_count, calls
            finally:
                os.chdir(original)

    def test_recovers_existing_open_issues_from_both_clients(self):
        for state in ("OPEN", "open"):
            with self.subTest(state=state):
                result, closed, calls = self.run_processor(existing=True, state=state)
                self.assertEqual((result, closed), (0, 1))
                self.assertEqual(calls, [])

    def test_failed_summary_keeps_issue_open_and_fails_run(self):
        result, closed, calls = self.run_processor(summary_status=1)
        self.assertEqual((result, closed), (1, 0))
        self.assertFalse(any("generate.py" in call for call in calls))

    def test_missing_summary_is_not_success(self):
        result, closed, _ = self.run_processor(save_summary=False)
        self.assertEqual((result, closed), (1, 0))

    def test_failed_build_keeps_issue_open(self):
        result, closed, _ = self.run_processor(build_status=1)
        self.assertEqual((result, closed), (1, 0))

    def test_failed_push_keeps_issue_open(self):
        result, closed, _ = self.run_processor(push_fails=True)
        self.assertEqual((result, closed), (1, 0))

    def test_missing_artifacts_keep_issue_open(self):
        result, closed, _ = self.run_processor(existing=True, artifacts=False)
        self.assertEqual((result, closed), (1, 0))

    def test_successful_summary_build_and_push_close_issue(self):
        result, closed, calls = self.run_processor()
        self.assertEqual((result, closed), (0, 1))
        self.assertIn(["git", "push", "origin", "main"], calls)

    def test_closed_issue_is_not_closed_again(self):
        result, closed, _ = self.run_processor(existing=True, state="CLOSED")
        self.assertEqual((result, closed), (0, 0))

    def test_admin_comments_are_loaded_across_pages(self):
        comments = [[{"user": {"login": "meesokim"}, "body": "승인"}], []]
        response = subprocess.CompletedProcess([], 0, stdout=json.dumps(comments))
        with patch.object(processor, "check_gh_cli", return_value=True), \
             patch.object(processor.subprocess, "run", return_value=response):
            self.assertEqual(processor.get_issue_comments("owner/repo", 61), comments[0])


if __name__ == "__main__":
    unittest.main()
