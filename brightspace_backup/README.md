# 🎓 D2L Brightspace Course Backup Tool

An automated, intelligent Python backup utility for **D2L Brightspace** learning management systems (e.g., [brightspace.tudelft.nl](https://brightspace.tudelft.nl)). 

It downloads and archives all your enrolled courses—preserving the exact folder hierarchy of learning modules, slides, lecture notes, assignments, your personal student submissions, instructor feedback & rubrics, announcements, quizzes, and gradebooks.

---

## 🌟 What Gets Backed Up

| Component | Description | Output Format |
| :--- | :--- | :--- |
| **📁 Course Content & Modules** | Lecture slides, notes, code examples, ZIPs, PDFs, reading materials | Original files in preserved folder hierarchy |
| **📝 Module Descriptions** | Instructor descriptions and introductory HTML notes | `_Module_Description.md` |
| **📢 Announcements** | Complete chronological archive of course news & announcements | `Announcements/All_Announcements.md` |
| **📤 Assignments & Dropbox** | Assignment prompts, deadlines, instructor attachment briefs | `Assignments/<Name>/Instructions.md` + attachments |
| **🙋 Your Submissions** | Files and code you submitted, with submission dates and comments | `Assignments/<Name>/My_Submissions/` |
| **💬 Instructor Feedback** | Graded scores, instructor comments, rubric assessments, feedback files | `Assignments/<Name>/Feedback/Feedback.md` + attachments |
| **📊 Grades & Assessments** | Full gradebook overview table (points, weights, grades, comments) | `Grades/Grades_Overview.md` + `grades_raw.json` |
| **❓ Quizzes** | Quiz instructions, descriptions, due dates, and your past attempts | `Quizzes/<Quiz_Name>.md` |
| **🎥 Videos & External Links** | Streamed lectures (Panopto, YouTube, Kaltura, Vimeo) | Downloaded via `yt-dlp` or saved as `.md` bookmarks |

---

## ⚙️ Prerequisites & Installation

Activate your conda environment first:

```bash
conda activate mt
```

Install the required Python dependencies:

```bash
pip install requests
```

*(Optional)* If you want to download streaming lecture videos directly, install `yt-dlp`:

```bash
pip install yt-dlp
```

---

## 🔑 How to Get Your Brightspace Session Cookies

Because universities (like TU Delft) use Single Sign-On (SSO) with Multi-Factor Authentication (2FA), you authenticate using your active browser session cookies (`d2lSessionVal` and `d2lSecureSessionVal`).

### Step-by-Step (Chrome / Edge / Brave / Firefox):

1. Open your browser and log into your Brightspace portal (e.g. **https://brightspace.tudelft.nl**).
2. Press **`F12`** (or right-click anywhere and select **Inspect**) to open **Developer Tools**.
3. Navigate to:
   - **Chrome / Edge / Brave:** `Application` tab ➔ `Storage` (in left sidebar) ➔ `Cookies` ➔ `https://brightspace.tudelft.nl`
   - **Firefox:** `Storage` tab ➔ `Cookies` ➔ `https://brightspace.tudelft.nl`
4. Look for the following two cookie names:
   - `d2lSessionVal`
   - `d2lSecureSessionVal`
5. Click each cookie and copy its **Value** (a string of alphanumeric characters).

> [!NOTE]
> These session cookies are temporary tokens that typically remain valid for several hours or until you log out. If you see an `Authentication failed` message, refresh Brightspace in your browser and copy fresh cookie values.

---

## 🚀 How to Use

Navigate to the workspace root:

```bash
cd /mnt/c/Users/prats/Documents/Uni\(Tudelft\)/job_hunt/pratham2442000
```

### 1. Back Up All Enrolled Courses

```bash
python brightspace_backup/brightspace_backup_tool.py \
  --host "brightspace.tudelft.nl" \
  --session-val "YOUR_D2L_SESSION_VAL" \
  --secure-session-val "YOUR_D2L_SECURE_SESSION_VAL"
```

### 2. Back Up a Specific Course (Filter by Name or Code)

You can filter by course code (e.g. `CS4240`) or course title keyword (e.g. `Deep Learning`, `Machine Learning`):

```bash
python brightspace_backup/brightspace_backup_tool.py \
  --host "brightspace.tudelft.nl" \
  --session-val "YOUR_D2L_SESSION_VAL" \
  --secure-session-val "YOUR_D2L_SECURE_SESSION_VAL" \
  --course "Deep Learning"
```

### 3. Back Up with Automatic Video Downloading

If you have `yt-dlp` installed and want to download lecture videos automatically:

```bash
python brightspace_backup/brightspace_backup_tool.py \
  --host "brightspace.tudelft.nl" \
  --session-val "YOUR_D2L_SESSION_VAL" \
  --secure-session-val "YOUR_D2L_SECURE_SESSION_VAL" \
  --course "CS4240" \
  --videos
```

### 4. Custom Output Directory

Specify where to save the downloaded archive:

```bash
python brightspace_backup/brightspace_backup_tool.py \
  --host "brightspace.tudelft.nl" \
  --session-val "YOUR_D2L_SESSION_VAL" \
  --secure-session-val "YOUR_D2L_SECURE_SESSION_VAL" \
  --output "/mnt/c/Users/prats/Desktop/TU_Delft_Archive"
```

---

## 📋 Command-Line Options

| Argument | Required | Default | Description |
| :--- | :---: | :---: | :--- |
| `--host` | **Yes** | — | Brightspace domain (e.g. `brightspace.tudelft.nl`) |
| `--session-val` | **Yes** | — | Value of the `d2lSessionVal` cookie |
| `--secure-session-val` | **Yes** | — | Value of the `d2lSecureSessionVal` cookie |
| `--output` | No | `./brightspace_backup` | Destination directory for downloaded files |
| `--course` | No | `None` (All) | Filter courses by name or code substring (case-insensitive) |
| `--videos` | No | `False` | Attempt to download video streams using `yt-dlp` |

---

## 📂 Backup Directory Structure

When the backup completes, your files are structured cleanly as follows:

```
brightspace_backup/
└── CS4240_Deep_Learning/
    ├── metadata.json                          # Course metadata (ID, code, name)
    ├── Announcements/
    │   └── All_Announcements.md               # Complete announcement history
    ├── Course_Content/
    │   ├── Week_01_Introduction/
    │   │   ├── _Module_Description.md         # Module overview text
    │   │   ├── Lecture_01_Slides.pdf          # Slides and documents
    │   │   └── Tutorial_01_Code.zip
    │   └── Week_02_CNNs/
    │       ├── Lecture_02_Slides.pdf
    │       └── Video_Lecture_Link.md          # Video link bookmark (or .mp4 if --videos)
    ├── Assignments/
    │   └── Assignment_1_Neural_Networks/
    │       ├── Instructions.md                # Task description & due date
    │       ├── Assignment_Brief.pdf           # Instructor attachments
    │       ├── My_Submissions/
    │       │   ├── Submission_1_Info.md       # Submission date, comment, and details
    │       │   └── report_pratham.pdf         # Your submitted file
    │       └── Feedback/
    │           ├── Feedback.md                # Score, grade symbol & instructor comments
    │           └── graded_rubric.pdf          # Instructor feedback files
    ├── Grades/
    │   ├── Grades_Overview.md                 # Markdown table with scores & weights
    │   └── grades_raw.json                    # Full raw gradebook JSON
    └── Quizzes/
        └── Quiz_1_Foundations.md              # Instructions, due date & attempt scores
```

---

## 💡 Key Features & Resilience

- **Smart Resume / Deduplication:** The script checks existing file sizes against HTTP `Content-Length`. If a file has already been downloaded, it will not be re-downloaded, making it safe to interrupt and resume anytime.
- **Cross-Platform Filename Sanitization:** Automatically strips illegal filesystem characters (`:`, `*`, `?`, `"`, `<`, `>`, `|`, `/`, `\`) so filenames are safe on both Windows and Linux/WSL.
- **Graceful Error Handling:** If certain modules or old gradebook endpoints return `403 Restricted` or `404 Not Found`, the tool logs a note and continues without crashing.
