# 🎓 StaticsCoach.xyz

An AI-powered Statics practice platform that automatically grades handwritten engineering solutions and provides personalized feedback, topic recommendations, and learning resources.

🌐 Website: https://staticscoach.xyz

---

## Features

- 📷 Upload handwritten solutions (PNG, JPG, PDF)
- 🤖 AI-based grading using Google Gemini Vision
- 📊 Automatic scoring (0–100)
- 📝 Detailed solution feedback
- 🔍 Detects:
  - Missing Free Body Diagrams (FBD)
  - Missing equilibrium equations
  - Missing moment equations
  - Missing final answers
  - Missing units
  - Cropped or incomplete submissions
- 📚 Personalized topic recommendations
- 📖 Direct links to interactive learning modules
- ⚡ Modern Flask web interface

---

## Screenshots

### Home Page

(Add screenshot here)

### AI Feedback

(Add screenshot here)

---

## How It Works

1. Select a Statics question.
2. Upload your handwritten solution.
3. The AI compares your work with the official solution.
4. The system evaluates:

- Relevance of the uploaded solution
- Completeness
- Free Body Diagrams
- Equilibrium equations
- Moment equations (when applicable)
- Final numerical answers
- Units
- Overall correctness

5. A detailed feedback report is generated.

---

## Current Question Set

The platform currently supports 10 engineering statics problems including:

- Trusses
- Frames
- Cables
- 3D Equilibrium
- Friction
- Internal Forces

More problems will be added over time.

---

## Technology Stack

### Backend

- Python
- Flask
- Google Gemini API
- Gunicorn
- Nginx

### Frontend

- HTML
- CSS
- JavaScript

### Deployment

- AWS Lightsail
- Ubuntu
- Nginx Reverse Proxy
- Gunicorn

---

## AI Evaluation

The AI analyzes student submissions against the official instructor solution and produces structured feedback including:

- Overall score
- Main mistakes
- Weak subject areas
- Missing equations
- Recommended practice
- Detailed mathematical feedback
- Next learning step

---

## Learning Modules

When weaknesses are detected, the system recommends interactive modules covering:

- Vector decomposition
- Support reactions
- Free Body Diagrams
- Moments
- Action-reaction relationships
- Shear and Moment Diagrams
- Linear systems

---

## Installation

Clone the repository

```bash
git clone https://github.com/mfatihdinc61/staticscouch.git
cd staticscouch
```

Create virtual environment

```bash
python -m venv venv
```

Activate

Windows

```bash
venv\Scripts\activate
```

Linux

```bash
source venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

Create a `.env`

```text
GEMINI_API_KEY=your_api_key
GEMINI_MODEL=gemini-2.5-flash
```

Run

```bash
python app.py
```

---

## Project Structure

```
app.py
templates/
static/
    questions/
    uploads/
    topics/
requirements.txt
README.md
```

---

## Roadmap

- [x] AI grading
- [x] Question verification
- [x] Personalized feedback
- [x] Topic recommendations
- [x] AWS deployment
- [x] Custom domain
- [ ] Student accounts
- [ ] Instructor dashboard
- [ ] Question bank expansion
- [ ] Analytics
- [ ] Leaderboards
- [ ] Learning progress tracking

---

## License

This project is released under the MIT License.

---

## Author

**Muhammet Fatih Dinç**

Machine Learning Engineer

GitHub:
https://github.com/mfatihdinc61

Website:
https://staticscoach.xyz
