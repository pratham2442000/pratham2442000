#!/usr/bin/env python3
"""
Brightspace Course Backup Tool
Backs up all course materials, documents, slides, announcements, 
assignments, and video links from D2L Brightspace.
"""

import os
import re
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from urllib.parse import urljoin, unquote
import requests


class BrightspaceBackup:
    def __init__(self, host: str, session_val: str, secure_session_val: str, 
                 output_dir: str = "./brightspace_backup", download_videos: bool = False):
        self.host = host.rstrip("/")
        if not self.host.startswith("http"):
            self.host = f"https://{self.host}"
            
        self.output_dir = Path(output_dir)
        self.download_videos = download_videos
        
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*"
        })
        self.session.cookies.set("d2lSessionVal", session_val)
        self.session.cookies.set("d2lSecureSessionVal", secure_session_val)

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitizes names for cross-platform filesystem compatibility."""
        if not name:
            return "unnamed"
        # Remove invalid characters for Windows and Linux filesystems
        cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)
        # Collapse multiple spaces/underscores and strip
        cleaned = re.sub(r'[\s_]+', ' ', cleaned).strip('. ')
        return cleaned[:150] if cleaned else "unnamed"

    @staticmethod
    def extract_list(data) -> list:
        """Normalizes D2L API responses which can be either a list or an ObjectListPage / PagedResult dict."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["Objects", "Items", "SearchResults", "Values"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
        return []

    def get_json(self, endpoint: str, suppress_warning: bool = False):
        """Helper to send authenticated GET requests and parse JSON."""
        url = urljoin(self.host, endpoint)
        try:
            res = self.session.get(url, timeout=30)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 403:
                if not suppress_warning:
                    print(f"    [!] Access restricted (403): {endpoint}")
            elif res.status_code == 404:
                if not suppress_warning:
                    print(f"    [!] Not found (404): {endpoint}")
            else:
                if not suppress_warning:
                    print(f"    [!] HTTP {res.status_code} on {endpoint}")
        except Exception as e:
            if not suppress_warning:
                print(f"    [!] Error fetching {endpoint}: {e}")
        return None

    def verify_auth(self) -> bool:
        """Verifies session credentials by querying current user info."""
        whoami = self.get_json("/d2l/api/lp/1.45/users/whoami")
        if whoami and isinstance(whoami, dict) and "UniqueName" in whoami:
            name = f"{whoami.get('FirstName', '')} {whoami.get('LastName', '')}".strip()
            print(f"[+] Authenticated successfully as student: {name} ({whoami.get('UniqueName')})")
            return True
        print("[-] Authentication failed. Please check your d2lSessionVal and d2lSecureSessionVal.")
        return False

    def list_courses(self):
        """Fetches all enrolled courses."""
        data = self.get_json("/d2l/api/lp/1.45/enrollments/myenrollments/?orgUnitTypeId=3")
        courses = []
        items = self.extract_list(data)
        if not items:
            return courses

        for item in items:
            if not isinstance(item, dict):
                continue
            org = item.get("OrgUnit", {})
            if isinstance(org, dict):
                courses.append({
                    "id": org.get("Id"),
                    "name": org.get("Name"),
                    "code": org.get("Code", ""),
                    "is_active": item.get("Access", {}).get("IsActive", True) if isinstance(item.get("Access"), dict) else True
                })
        return courses

    def download_file(self, download_url: str, dest_path: Path, filename_hint: str = None) -> bool:
        """Downloads a binary file with chunking and skip-if-exists check."""
        try:
            res = self.session.get(download_url, stream=True, timeout=60)
            if res.status_code != 200:
                return False

            # Infer filename from Content-Disposition if not provided
            final_filename = filename_hint
            cd = res.headers.get("Content-Disposition", "")
            if "filename=" in cd:
                match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd)
                if match:
                    final_filename = unquote(match.group(1))

            if not final_filename:
                final_filename = "downloaded_file.bin"

            final_filename = self.sanitize_name(final_filename)
            target_file = dest_path / final_filename

            # Skip download if file already exists with non-zero size
            content_length = res.headers.get("Content-Length")
            if target_file.exists() and content_length and target_file.stat().st_size == int(content_length):
                print(f"    [=] Already downloaded: {final_filename}")
                return True

            with open(target_file, "wb") as f:
                for chunk in res.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        f.write(chunk)

            print(f"    [✓] Saved: {final_filename}")
            return True
        except Exception as e:
            print(f"    [!] Error downloading file: {e}")
            return False

    def handle_video(self, video_url: str, dest_path: Path, title: str):
        """Downloads video using yt-dlp if enabled, or creates an external link shortcut."""
        clean_title = self.sanitize_name(title)
        if self.download_videos and shutil.which("yt-dlp"):
            print(f"    [>] Downloading video via yt-dlp: {title}")
            out_template = str(dest_path / f"{clean_title}.%(ext)s")
            cmd = ["yt-dlp", "--no-warnings", "-q", "-o", out_template, video_url]
            try:
                subprocess.run(cmd, timeout=300, check=True)
                print(f"    [✓] Video saved: {clean_title}")
                return
            except Exception as e:
                print(f"    [!] Video download failed with yt-dlp ({e}). Creating link shortcut instead.")

        # Fallback: Save as a Markdown link bookmark
        link_file = dest_path / f"{clean_title}_Link.md"
        with open(link_file, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\nURL: [{video_url}]({video_url})\n")
        print(f"    [🔗] Saved video link: {clean_title}_Link.md")

    def backup_topic(self, org_id: str, topic: dict, dest_dir: Path):
        """Processes and downloads an individual course content topic."""
        topic_id = topic.get("TopicId")
        title = topic.get("Title", f"Topic_{topic_id}")
        topic_type = topic.get("TopicType")
        url = topic.get("Url", "")

        dest_dir.mkdir(parents=True, exist_ok=True)

        # TopicType 1: Uploaded File (Slides, PDFs, ZIPs, Code)
        if topic_type == 1 or url.startswith("/content/enforced/"):
            api_file_url = urljoin(self.host, f"/d2l/api/le/1.45/{org_id}/content/topics/{topic_id}/file")
            # Try API download endpoint first
            success = self.download_file(api_file_url, dest_dir, filename_hint=title)
            if not success and url:
                direct_url = urljoin(self.host, url)
                self.download_file(direct_url, dest_dir, filename_hint=title)

        # TopicType 3: External Link / Web Resource / Embedded Video
        elif topic_type == 3 or (url and url.startswith("http")):
            full_url = url if url.startswith("http") else urljoin(self.host, url)
            # Check for common video platforms
            if any(domain in full_url.lower() for domain in ["youtube.com", "youtu.be", "panopto", "kaltura", "mediasite", "vimeo"]):
                self.handle_video(full_url, dest_dir, title)
            else:
                link_file = dest_dir / f"{self.sanitize_name(title)}.md"
                with open(link_file, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\nExternal Resource: [{full_url}]({full_url})\n")
                print(f"    [🔗] Saved Link: {title}")

        # TopicType 2 / HTML descriptions & embedded content
        else:
            api_file_url = urljoin(self.host, f"/d2l/api/le/1.45/{org_id}/content/topics/{topic_id}/file")
            if not self.download_file(api_file_url, dest_dir, filename_hint=f"{title}.html"):
                link_file = dest_dir / f"{self.sanitize_name(title)}.md"
                with open(link_file, "w", encoding="utf-8") as f:
                    f.write(f"# {title}\n\nPath/URL: {url}\n")

    def backup_modules(self, org_id: str, modules: list, parent_path: Path):
        """Recursively parses modules and sub-modules to preserve folder structure."""
        for module in modules:
            mod_title = self.sanitize_name(module.get("Title", "Untitled_Module"))
            current_path = parent_path / mod_title
            current_path.mkdir(parents=True, exist_ok=True)
            print(f"  📁 Module: {module.get('Title')}")

            # Save module description if present
            desc = module.get("Description", {}).get("Html") or module.get("Description", {}).get("Text")
            if desc:
                with open(current_path / "_Module_Description.md", "w", encoding="utf-8") as f:
                    f.write(desc)

            # Backup Topics inside this module
            for topic in module.get("Topics", []):
                self.backup_topic(org_id, topic, current_path)

            # Recurse into Sub-Modules
            sub_modules = module.get("Modules", [])
            if sub_modules:
                self.backup_modules(org_id, sub_modules, current_path)

    def backup_announcements(self, org_id: str, course_path: Path):
        """Fetches and stores all course announcements."""
        news_raw = self.get_json(f"/d2l/api/le/1.45/{org_id}/news/", suppress_warning=True)
        news_data = self.extract_list(news_raw)
        if not news_data:
            return

        news_dir = course_path / "Announcements"
        news_dir.mkdir(parents=True, exist_ok=True)

        overview_path = news_dir / "All_Announcements.md"
        with open(overview_path, "w", encoding="utf-8") as out:
            out.write("# Course Announcements\n\n")
            for item in news_data:
                if not isinstance(item, dict):
                    continue
                title = item.get("Title", "Untitled Announcement")
                created = item.get("StartDate", "")
                body_obj = item.get("Body", {})
                body = (body_obj.get("Html", "") or body_obj.get("Text", "")) if isinstance(body_obj, dict) else ""
                
                out.write(f"## {title}\n*Date: {created}*\n\n{body}\n\n---\n\n")
        print(f"  [✓] Backed up {len(news_data)} announcements.")

    def backup_assignments(self, org_id: str, course_path: Path):
        """Fetches assignment instructions, teacher brief attachments, personal student submissions, and feedback."""
        dropbox_raw = self.get_json(f"/d2l/api/le/1.45/{org_id}/dropbox/folders/", suppress_warning=True)
        dropbox_data = self.extract_list(dropbox_raw)
        if not dropbox_data:
            return

        assign_dir = course_path / "Assignments"
        assign_dir.mkdir(parents=True, exist_ok=True)

        for folder in dropbox_data:
            if not isinstance(folder, dict):
                continue
            folder_id = folder.get("Id")
            folder_name = self.sanitize_name(folder.get("Name", f"Assignment_{folder_id}"))
            folder_path = assign_dir / folder_name
            folder_path.mkdir(parents=True, exist_ok=True)

            info_file = folder_path / "Instructions.md"
            instructions_obj = folder.get("CustomInstructions", {})
            instructions = (instructions_obj.get("Html", "") or instructions_obj.get("Text", "")) if isinstance(instructions_obj, dict) else ""
            due_date = folder.get("DueDate", "No due date specified")

            with open(info_file, "w", encoding="utf-8") as f:
                f.write(f"# {folder.get('Name')}\n**Due Date:** {due_date}\n\n### Instructions\n{instructions}\n")

            # 1. Download assignment brief attachments provided by instructor
            attachments = folder.get("Attachments", [])
            if isinstance(attachments, list):
                for att in attachments:
                    if not isinstance(att, dict):
                        continue
                    file_id = att.get("FileId")
                    file_name = att.get("FileName")
                    att_url = urljoin(self.host, f"/d2l/api/le/1.45/{org_id}/dropbox/folders/{folder_id}/attachments/{file_id}")
                    self.download_file(att_url, folder_path, filename_hint=file_name)

            # 2. Download personal student submissions & instructor feedback
            submissions_raw = self.get_json(
                f"/d2l/api/le/1.45/{org_id}/dropbox/folders/{folder_id}/submissions/mysubmissions/",
                suppress_warning=True
            )

            # Fallback to standard submissions endpoint if mysubmissions is empty
            if not submissions_raw:
                submissions_raw = self.get_json(
                    f"/d2l/api/le/1.45/{org_id}/dropbox/folders/{folder_id}/submissions/",
                    suppress_warning=True
                )

            submissions_data = self.extract_list(submissions_raw)
            if submissions_data:
                for entity_item in submissions_data:
                    if not isinstance(entity_item, dict):
                        continue
                    entity = entity_item.get("Entity", {})
                    entity_type = (entity.get("EntityType") or "user").lower() if isinstance(entity, dict) else "user"
                    entity_id = entity.get("EntityId") if isinstance(entity, dict) else None
                    submissions = entity_item.get("Submissions", [])

                    # Backup student submitted files and metadata
                    if isinstance(submissions, list) and submissions:
                        sub_dir = folder_path / "My_Submissions"
                        sub_dir.mkdir(parents=True, exist_ok=True)

                        for sub_idx, sub in enumerate(submissions, 1):
                            if not isinstance(sub, dict):
                                continue
                            sub_id = sub.get("Id")
                            sub_date = sub.get("SubmissionDate", "Unknown Date")
                            submitter_obj = sub.get("SubmittedBy", {})
                            submitter = submitter_obj.get("DisplayName", "Self") if isinstance(submitter_obj, dict) else "Self"
                            comment_obj = sub.get("Comment", {})
                            comment = (comment_obj.get("Html", "") or comment_obj.get("Text", "")) if isinstance(comment_obj, dict) else ""

                            info_text = (
                                f"# Submission {sub_idx} (ID: {sub_id})\n"
                                f"**Date:** {sub_date}\n"
                                f"**Submitted By:** {submitter}\n\n"
                                f"### Submission Comments:\n{comment}\n"
                            )
                            with open(sub_dir / f"Submission_{sub_idx}_Info.md", "w", encoding="utf-8") as sf:
                                sf.write(info_text)

                            # Download student submitted documents
                            files = sub.get("Files", [])
                            if isinstance(files, list):
                                for sub_file in files:
                                    if not isinstance(sub_file, dict):
                                        continue
                                    f_id = sub_file.get("FileId")
                                    f_name = sub_file.get("FileName", f"submission_{f_id}.bin")
                                    sub_file_url = urljoin(
                                        self.host,
                                        f"/d2l/api/le/1.45/{org_id}/dropbox/folders/{folder_id}/submissions/{sub_id}/files/{f_id}"
                                    )
                                    self.download_file(sub_file_url, sub_dir, filename_hint=f_name)

                    # Backup instructor feedback and rubrics
                    feedback = entity_item.get("Feedback")
                    if isinstance(feedback, dict):
                        fb_dir = folder_path / "Feedback"
                        fb_dir.mkdir(parents=True, exist_ok=True)

                        score = feedback.get("Score", "Not Graded")
                        graded_symbol = feedback.get("GradedSymbol", "")
                        fb_obj = feedback.get("Feedback", {})
                        fb_text = (fb_obj.get("Html", "") or fb_obj.get("Text", "No written comments")) if isinstance(fb_obj, dict) else "No written comments"

                        fb_content = [
                            f"# Assignment Feedback & Evaluation\n",
                            f"**Score:** {score}",
                            f"**Grade Symbol:** {graded_symbol}\n" if graded_symbol else "",
                            f"### Instructor Comments:\n{fb_text}\n"
                        ]

                        # Rubrics
                        rubrics = feedback.get("RubricAssessments", [])
                        if isinstance(rubrics, list) and rubrics:
                            fb_content.append("### Rubric Assessments\n")
                            for r in rubrics:
                                if not isinstance(r, dict):
                                    continue
                                r_name = r.get("Name", "Rubric")
                                r_score = r.get("Score", "")
                                fb_content.append(f"- **{r_name}:** Score: {r_score}\n")

                        with open(fb_dir / "Feedback.md", "w", encoding="utf-8") as fbf:
                            fbf.write("\n".join(fb_content))

                        # Download feedback attachment files
                        if entity_id:
                            fb_files = feedback.get("Files", [])
                            if isinstance(fb_files, list):
                                for fb_file in fb_files:
                                    if not isinstance(fb_file, dict):
                                        continue
                                    file_id = fb_file.get("FileId")
                                    file_name = fb_file.get("FileName", f"feedback_{file_id}.bin")
                                    fb_url = urljoin(
                                        self.host,
                                        f"/d2l/api/le/1.45/{org_id}/dropbox/folders/{folder_id}/feedback/{entity_type}/{entity_id}/attachments/{file_id}"
                                    )
                                    self.download_file(fb_url, fb_dir, filename_hint=file_name)

        print(f"  [✓] Backed up {len(dropbox_data)} assignment folders (including submissions & feedback).")

    def backup_grades(self, org_id: str, course_path: Path):
        """Fetches student's personal gradebook and feedback for this course."""
        grades_raw = self.get_json(f"/d2l/api/le/1.45/{org_id}/grades/values/myGradeValues/", suppress_warning=True)
        grades_data = self.extract_list(grades_raw)
        if not grades_data:
            return

        grades_dir = course_path / "Grades"
        grades_dir.mkdir(parents=True, exist_ok=True)

        overview_path = grades_dir / "Grades_Overview.md"
        with open(overview_path, "w", encoding="utf-8") as out:
            out.write("# Course Grades & Assessments\n\n")
            out.write("| Grade Item | Points / Score | Weight | Grade / Symbol | Comments |\n")
            out.write("| :--- | :--- | :--- | :--- | :--- |\n")

            for item in grades_data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("GradeObjectName", "Unnamed Item")).replace("|", "-")
                displayed = str(item.get("DisplayedGrade", "") or "")
                num = item.get("PointsNumerator")
                den = item.get("PointsDenominator")
                points = f"{num}/{den}" if (num is not None and den is not None) else displayed

                wnum = item.get("WeightedNumerator")
                wden = item.get("WeightedDenominator")
                weight = f"{wnum}/{wden}" if (wnum is not None and wden is not None) else "-"

                comments_obj = item.get("Comments", {})
                comment = ""
                if isinstance(comments_obj, dict):
                    comment = (comments_obj.get("Html", "") or comments_obj.get("Text", "")).replace("\n", " ").replace("|", "-")

                out.write(f"| {name} | {points} | {weight} | {displayed} | {comment} |\n")

        with open(grades_dir / "grades_raw.json", "w", encoding="utf-8") as jf:
            json.dump(grades_raw, jf, indent=2)

        print(f"  [✓] Backed up personal gradebook ({len(grades_data)} grade items).")

    def backup_quizzes(self, org_id: str, course_path: Path):
        """Fetches available quizzes, instructions, and student attempts."""
        quizzes_raw = self.get_json(f"/d2l/api/le/1.45/{org_id}/quizzes/", suppress_warning=True)
        quizzes = self.extract_list(quizzes_raw)
        if not quizzes:
            return

        quiz_dir = course_path / "Quizzes"
        quiz_dir.mkdir(parents=True, exist_ok=True)

        for quiz in quizzes:
            if not isinstance(quiz, dict):
                continue
            q_id = quiz.get("QuizId") or quiz.get("Id")
            q_name = self.sanitize_name(quiz.get("Name", f"Quiz_{q_id}"))
            desc_obj = quiz.get("Description", {})
            desc = (desc_obj.get("Html", "") or desc_obj.get("Text", "")) if isinstance(desc_obj, dict) else ""
            instruct_obj = quiz.get("Instructions", {})
            instructions = (instruct_obj.get("Html", "") or instruct_obj.get("Text", "")) if isinstance(instruct_obj, dict) else ""
            due_date = quiz.get("DueDate", "No due date")

            quiz_file = quiz_dir / f"{q_name}.md"
            with open(quiz_file, "w", encoding="utf-8") as qf:
                qf.write(f"# {quiz.get('Name')}\n**Due Date:** {due_date}\n\n")
                if desc:
                    qf.write(f"### Description\n{desc}\n\n")
                if instructions:
                    qf.write(f"### Instructions\n{instructions}\n\n")

                # Try fetching student's quiz attempts/scores if endpoint is available
                attempts_raw = self.get_json(f"/d2l/api/le/1.45/{org_id}/quizzes/{q_id}/myattempts/", suppress_warning=True)
                attempts = self.extract_list(attempts_raw)
                if attempts:
                    qf.write("### Your Quiz Attempts\n")
                    for att in attempts:
                        if not isinstance(att, dict):
                            continue
                        att_num = att.get("AttemptNumber", 1)
                        att_score = att.get("Score", "N/A")
                        qf.write(f"- **Attempt {att_num}:** Score: {att_score}\n")

        print(f"  [✓] Backed up {len(quizzes)} quizzes.")

    def run(self, course_filter: str = None):
        """Main execution flow."""
        if not self.verify_auth():
            return

        courses = self.list_courses()
        print(f"[+] Found {len(courses)} enrolled courses.")

        for course in courses:
            c_id = str(course["id"])
            c_name = course["name"]
            c_code = course["code"]

            if course_filter and (course_filter.lower() not in c_name.lower() and course_filter.lower() not in c_code.lower()):
                continue

            folder_title = f"{self.sanitize_name(c_code)}_{self.sanitize_name(c_name)}".strip("_")
            course_dir = self.output_dir / folder_title
            course_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n{'='*60}\n[>] Backing up Course: {c_name} (ID: {c_id})\n{'='*60}")

            # 1. Back up Table of Contents & Learning Materials
            toc = self.get_json(f"/d2l/api/le/1.45/{c_id}/content/toc", suppress_warning=True)
            if toc and "Modules" in toc:
                content_dir = course_dir / "Course_Content"
                content_dir.mkdir(parents=True, exist_ok=True)
                self.backup_modules(c_id, toc["Modules"], content_dir)

            # 2. Back up Announcements
            self.backup_announcements(c_id, course_dir)

            # 3. Back up Assignment folders, personal submissions, and feedback
            self.backup_assignments(c_id, course_dir)

            # 4. Back up Personal Grades
            self.backup_grades(c_id, course_dir)

            # 5. Back up Quizzes
            self.backup_quizzes(c_id, course_dir)

            # 6. Save metadata index
            with open(course_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(course, f, indent=2)

        print(f"\n[🎉] Backup completed! All files saved to: {self.output_dir.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Backup all materials from D2L Brightspace.")
    parser.add_argument("--host", required=True, help="Brightspace URL (e.g. brightspace.tudelft.nl)")
    parser.add_argument("--session-val", required=True, help="d2lSessionVal cookie value")
    parser.add_argument("--secure-session-val", required=True, help="d2lSecureSessionVal cookie value")
    parser.add_argument("--output", default="./brightspace_backup", help="Destination folder for backup")
    parser.add_argument("--course", default=None, help="Filter specific course by name or code")
    parser.add_argument("--videos", action="store_true", help="Download video streams using yt-dlp")

    args = parser.parse_args()

    backup = BrightspaceBackup(
        host=args.host,
        session_val=args.session_val,
        secure_session_val=args.secure_session_val,
        output_dir=args.output,
        download_videos=args.videos
    )
    backup.run(course_filter=args.course)


if __name__ == "__main__":
    main()