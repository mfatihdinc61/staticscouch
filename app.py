from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError, ClientError
from markupsafe import Markup, escape

import os
import re
import json
from datetime import datetime


# ------------------------------------------------------------
# Setup
# ------------------------------------------------------------

load_dotenv()

app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)


# ------------------------------------------------------------
# Course data
# ------------------------------------------------------------

TOPICS = [
    {
        "id": 1,
        "title": "Decomposing vectors into components along axes",
        "file": "1 - vector_axial_decomposition_practice.html",
        "icon": "↗",
    },
    {
        "id": 2,
        "title": "Determining support reactions and force directions",
        "file": "2- support_reactions_visual_module_v3.html",
        "icon": "⛓",
    },
    {
        "id": 3,
        "title": "Drawing FBD properly",
        "file": "3 - fbd_course.html",
        "icon": "□",
    },
    {
        "id": 4,
        "title": "Calculating moments",
        "file": "4 - moment-of-force.html",
        "icon": "↻",
    },
    {
        "id": 5,
        "title": "Understanding action-reaction relationships at joints",
        "file": "5 - action-reaction-joints.html",
        "icon": "⇄",
    },
    {
        "id": 6,
        "title": "Transforming between w(x), V(x), and M(x)",
        "file": "6 - shear_moment_diagrams.html",
        "icon": "∫",
    },
    {
        "id": 7,
        "title": "Solving systems of linear equations",
        "file": "7 - linear_systems_course.html",
        "icon": "A⁻¹",
    },
]

QUESTIONS = [
    {"number": 1, "question": "nq-5-75.png", "solution": "nqs-5-75.png"},
    {"number": 2, "question": "nq-5-79.png", "solution": "nqs-5-79.png"},
    {"number": 3, "question": "nq-5-86.png", "solution": "nqs-5-86.png"},
    {"number": 4, "question": "nq-6-21.png", "solution": "nqs-6-21.png"},
    {"number": 5, "question": "nq-6-43.png", "solution": "nqs-6-43.png"},
    {"number": 6, "question": "nq-7-80.png", "solution": "nqs-7-80.png"},
    {"number": 7, "question": "nq-7-86.png", "solution": "nqs-7-86.png"},
    {"number": 8, "question": "nq-7-90.png", "solution": "nqs-7-90.png"},
    {"number": 9, "question": "nq-8-41.png", "solution": "nqs-8-41.png"},
    {"number": 10, "question": "nq-8-63.png", "solution": "nqs-8-63.png"},
]

TOPIC_LINKS = {
    "Decomposing vectors into components along axes": "1 - vector_axial_decomposition_practice.html",
    "Determining support reactions and force directions": "2- support_reactions_visual_module_v3.html",
    "Drawing FBD properly": "3 - fbd_course.html",
    "Calculating moments": "4 - moment-of-force.html",
    "Understanding action-reaction relationships at joints": "5 - action-reaction-joints.html",
    "Transforming between w(x), V(x), and M(x)": "6 - shear_moment_diagrams.html",
    "Solving systems of linear equations": "7 - linear_systems_course.html",
}


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

def normalize_latex(text: str) -> str:
    """
    Fixes common AI LaTeX mistakes before MathJax renders it.
    """
    text = text or ""

    # Gemini sometimes generates broken \left / \right pairs.
    text = text.replace(r"\left", "")
    text = text.replace(r"\right", "")

    # Convert [ \sum F_x = 0 ] to \[ \sum F_x = 0 \]
    text = re.sub(
        r"\[\s*(\\.+?)\s*\]",
        r"\\[\1\\]",
        text,
        flags=re.DOTALL,
    )

    # Convert math-like plain parentheses to inline LaTeX.
    text = re.sub(
        r"(?<!\\)\(([^()\n]*(?:\\|_|=|\^|\\frac|\\sum|\\vec|\\text)[^()\n]*)\)",
        r"\\(\1\\)",
        text,
    )

    return text


def render_math_text(text: str) -> Markup:
    """
    Safely escapes AI text but keeps MathJax delimiters visible for rendering.
    """
    text = normalize_latex(text or "")
    safe = escape(text)
    safe = str(safe).replace("\n", "<br>")
    return Markup(safe)


def extract_json(text: str) -> dict:
    """
    Extracts JSON from a Gemini response, even if wrapped in markdown fences.
    """
    text = (text or "").strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1).replace("```", "").strip()
    elif text.startswith("```"):
        text = text.replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No valid JSON object found in AI response.")

    json_text = text[start:end + 1]
    return json.loads(json_text)


def log_ai_response(raw_text: str, provider: str) -> None:
    """
    Saves raw AI responses for debugging.
    """
    try:
        os.makedirs("logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join("logs", f"ai_response_{timestamp}_{provider}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw_text or "")
    except Exception as e:
        print("Could not write AI log:", e)


def default_error_feedback(raw_text: str) -> dict:
    return {
        "is_relevant": False,
        "is_cropped": False,
        "solution_complete": False,
        "fbd_visible": False,
        "equilibrium_equations_visible": False,
        "moment_equations_visible": False,
        "equations_solved": False,
        "final_answers_visible": False,
        "units_visible": False,
        "suggested_score": 0,
        "score": 0,
        "overall_feedback": "The AI response could not be parsed correctly.",
        "main_mistakes": [raw_text],
        "weak_subject_areas": [],
        "wrong_or_missing_equations": [],
        "recommended_practice": [],
        "next_step": "Try uploading again.",
        "detailed_latex_feedback": raw_text,
    }


def quota_feedback() -> dict:
    return {
        "is_relevant": False,
        "is_cropped": False,
        "solution_complete": False,
        "fbd_visible": False,
        "equilibrium_equations_visible": False,
        "moment_equations_visible": False,
        "equations_solved": False,
        "final_answers_visible": False,
        "units_visible": False,
        "suggested_score": 0,
        "score": 0,
        "overall_feedback": (
            "This platform relies on Gemini's free API services, and the quota has been reached. "
            "Please use the AI assistant later."
        ),
        "main_mistakes": [],
        "weak_subject_areas": [],
        "wrong_or_missing_equations": [],
        "recommended_practice": [],
        "next_step": "Please try again later after the Gemini free API quota resets.",
        "detailed_latex_feedback": "Gemini free API quota has been reached. The solution was not graded.",
    }


def unavailable_feedback() -> dict:
    return {
        "is_relevant": False,
        "is_cropped": False,
        "solution_complete": False,
        "fbd_visible": False,
        "equilibrium_equations_visible": False,
        "moment_equations_visible": False,
        "equations_solved": False,
        "final_answers_visible": False,
        "units_visible": False,
        "suggested_score": 0,
        "score": 0,
        "overall_feedback": (
            "Gemini is currently busy or temporarily unavailable. Please try again later."
        ),
        "main_mistakes": [],
        "weak_subject_areas": [],
        "wrong_or_missing_equations": [],
        "recommended_practice": [],
        "next_step": "Please retry after a short time.",
        "detailed_latex_feedback": "Gemini service is temporarily unavailable.",
    }


def unexpected_error_feedback(error_text: str) -> dict:
    return {
        "is_relevant": False,
        "is_cropped": False,
        "solution_complete": False,
        "fbd_visible": False,
        "equilibrium_equations_visible": False,
        "moment_equations_visible": False,
        "equations_solved": False,
        "final_answers_visible": False,
        "units_visible": False,
        "suggested_score": 0,
        "score": 0,
        "overall_feedback": "An unexpected error occurred while grading the solution.",
        "main_mistakes": [error_text],
        "weak_subject_areas": [],
        "wrong_or_missing_equations": [],
        "recommended_practice": [],
        "next_step": "Please try again later.",
        "detailed_latex_feedback": error_text,
    }


# ------------------------------------------------------------
# Grading logic
# ------------------------------------------------------------

def calculate_final_score(feedback_data: dict) -> int:
    """
    Python is the final grading authority.
    AI suggests a score, but Python applies hard caps.
    """
    try:
        score = int(feedback_data.get("suggested_score", feedback_data.get("score", 0)))
    except Exception:
        score = 0

    if not feedback_data.get("is_relevant", True):
        return 0

    if feedback_data.get("is_cropped", False):
        score = min(score, 70)

    if not feedback_data.get("solution_complete", True):
        score = min(score, 75)

    if not feedback_data.get("fbd_visible", True):
        score = min(score, 65)

    if not feedback_data.get("equilibrium_equations_visible", True):
        score = min(score, 70)

    if not feedback_data.get("moment_equations_visible", True):
        score = min(score, 70)

    if not feedback_data.get("equations_solved", True):
        score = min(score, 75)

    if not feedback_data.get("final_answers_visible", True):
        score = min(score, 80)

    if not feedback_data.get("units_visible", True):
        score = min(score, 90)

    return max(0, min(score, 100))


def apply_text_score_caps(feedback_data: dict) -> dict:
    """
    Extra protection if the model's boolean flags are inconsistent with its explanation.
    """
    text_all = " ".join([
        str(feedback_data.get("overall_feedback", "")),
        " ".join(map(str, feedback_data.get("main_mistakes", []))),
        " ".join(map(str, feedback_data.get("wrong_or_missing_equations", []))),
        str(feedback_data.get("detailed_latex_feedback", "")),
    ]).lower()

    try:
        score = int(feedback_data.get("score", 0))
    except Exception:
        score = 0

    if any(phrase in text_all for phrase in [
        "final values aren't shown",
        "final values are not shown",
        "final numerical values",
        "did not compute",
        "not solve the system",
        "missing final",
        "incomplete solution",
        "not solved",
        "stops before solving",
        "answer is missing",
        "final answer is missing",
    ]):
        score = min(score, 80)

    if any(phrase in text_all for phrase in [
        "fbd is missing",
        "free body diagram is missing",
        "free-body diagram is missing",
    ]):
        score = min(score, 65)

    if any(phrase in text_all for phrase in [
        "cropped",
        "cut off",
        "not visible",
        "image is incomplete",
    ]):
        score = min(score, 70)

    feedback_data["score"] = score
    return feedback_data


def build_prompt(question_number: str) -> str:
    return f"""
You are an expert Statics tutor.

You are given:
1. The original Statics question image.
2. The official solution image.
3. The student's uploaded solution image/PDF.

The student is supposed to solve Question {question_number}.

Your job is NOT to decide the final score.
Your job is to inspect the visible student work and return grading evidence as JSON.
Python will calculate the final score.

Grade ONLY what is visible in the student's uploaded image.
Never assume missing work exists outside the image.
Never infer continuation from the official solution.
The official solution is ONLY a grading reference.
If the student's image is cropped, cut off, incomplete, or missing lower/right parts, mark it clearly.

Return ONLY valid JSON.

Use this exact JSON structure:
{{
  "is_relevant": true,
  "is_cropped": false,
  "solution_complete": true,
  "fbd_visible": true,
  "equilibrium_equations_visible": true,
  "moment_equations_visible": true,
  "equations_solved": true,
  "final_answers_visible": true,
  "units_visible": true,
  "suggested_score": 0,
  "overall_feedback": "",
  "main_mistakes": [],
  "weak_subject_areas": [],
  "wrong_or_missing_equations": [],
  "recommended_practice": [],
  "next_step": "",
  "detailed_latex_feedback": ""
}}

If the uploaded solution is irrelevant, blank, unreadable, or for another problem, use:
{{
  "is_relevant": false,
  "is_cropped": false,
  "solution_complete": false,
  "fbd_visible": false,
  "equilibrium_equations_visible": false,
  "moment_equations_visible": false,
  "equations_solved": false,
  "final_answers_visible": false,
  "units_visible": false,
  "suggested_score": 0,
  "overall_feedback": "This uploaded solution does not appear to be about the asked problem.",
  "main_mistakes": ["The uploaded work does not match the selected question."],
  "weak_subject_areas": [],
  "wrong_or_missing_equations": [],
  "recommended_practice": [],
  "next_step": "Upload the solution for the selected question.",
  "detailed_latex_feedback": "The submitted solution could not be graded because it does not correspond to the selected problem."
}}

Weak subject areas must use ONLY these exact names:
1. Decomposing vectors into components along axes
2. Determining support reactions and force directions
3. Drawing FBD properly
4. Calculating moments
5. Understanding action-reaction relationships at joints
6. Transforming between w(x), V(x), and M(x)
7. Solving systems of linear equations

LaTeX rules for detailed_latex_feedback:
- Do not use Markdown formatting.
- Do not use * or **.
- Do not use underscores outside LaTeX.
- Every variable with subscript must be inside LaTeX, for example \\(F_{{CB}}\\), \\(A_x\\), \\((M_A)_z\\).
- Every equation must be inside \\[ ... \\].
- Never use dollar signs.
- Never use \\left or \\right.
- For units, use \\(1.37\\,\\text{{kN}}\\), not 1.37 kN.
"""


def grade_with_gemini(prompt: str, question_path: str, official_solution_path: str, student_solution_path: str) -> str:
    uploaded_question = gemini_client.files.upload(file=question_path)
    uploaded_official_solution = gemini_client.files.upload(file=official_solution_path)
    uploaded_student_solution = gemini_client.files.upload(file=student_solution_path)

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            prompt,
            uploaded_question,
            uploaded_official_solution,
            uploaded_student_solution,
        ],
    )

    return response.text.strip()


def grade_with_gemini_safe(prompt: str, question_path: str, official_solution_path: str, student_solution_path: str):
    """
    Uses Gemini only. Returns (raw_text, ai_provider).
    Quota errors are converted to a friendly JSON response instead of crashing Flask.
    """
    if not GEMINI_API_KEY:
        return json.dumps(unexpected_error_feedback("GEMINI_API_KEY is missing.")), "Gemini config error"

    try:
        raw_text = grade_with_gemini(
            prompt,
            question_path,
            official_solution_path,
            student_solution_path,
        )
        return raw_text, "Gemini"

    except ClientError as e:
        error_text = str(e)

        if "RESOURCE_EXHAUSTED" in error_text or "quota" in error_text.lower() or "429" in error_text:
            return json.dumps(quota_feedback()), "Gemini quota reached"

        return json.dumps(unexpected_error_feedback(error_text)), "Gemini client error"

    except ServerError as e:
        error_text = str(e)

        if "UNAVAILABLE" in error_text or "503" in error_text:
            return json.dumps(unavailable_feedback()), "Gemini unavailable"

        return json.dumps(unexpected_error_feedback(error_text)), "Gemini server error"

    except Exception as e:
        return json.dumps(unexpected_error_feedback(str(e))), "Gemini error"


# ------------------------------------------------------------
# Routes
# ------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", topics=TOPICS, questions=QUESTIONS)


@app.route("/topic/<path:filename>")
def topic(filename):
    return send_from_directory("static/topics", filename)


@app.route("/grade", methods=["POST"])
def grade_solution():
    question_file = request.form.get("question_file")
    official_solution_file = request.form.get("official_solution_file")
    question_number = request.form.get("question_number")
    solution = request.files.get("solution")

    if not question_file or not official_solution_file or not question_number:
        feedback_data = unexpected_error_feedback(
            "Missing question metadata. Please refresh the page and try again."
        )
        detailed_html = render_math_text(feedback_data["detailed_latex_feedback"])
        return render_template(
            "result.html",
            feedback=feedback_data,
            detailed_html=detailed_html,
            topic_links=TOPIC_LINKS,
            question_file=question_file or "",
            question_number=question_number or "?",
            solution_file="",
            ai_provider="Metadata error",
        )

    if not solution:
        return redirect(url_for("index"))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    filename = secure_filename(solution.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    solution.save(save_path)

    question_path = os.path.join("static/questions", question_file)
    official_solution_path = os.path.join("static/questions", official_solution_file)

    if not os.path.exists(question_path):
        feedback_data = unexpected_error_feedback(f"Question image not found: {question_path}")
        detailed_html = render_math_text(feedback_data["detailed_latex_feedback"])
        return render_template(
            "result.html",
            feedback=feedback_data,
            detailed_html=detailed_html,
            topic_links=TOPIC_LINKS,
            question_file=question_file,
            question_number=question_number,
            solution_file=filename,
            ai_provider="File error",
        )

    if not os.path.exists(official_solution_path):
        feedback_data = unexpected_error_feedback(f"Official solution image not found: {official_solution_path}")
        detailed_html = render_math_text(feedback_data["detailed_latex_feedback"])
        return render_template(
            "result.html",
            feedback=feedback_data,
            detailed_html=detailed_html,
            topic_links=TOPIC_LINKS,
            question_file=question_file,
            question_number=question_number,
            solution_file=filename,
            ai_provider="File error",
        )

    prompt = build_prompt(question_number)

    raw_text, ai_provider = grade_with_gemini_safe(
        prompt,
        question_path,
        official_solution_path,
        save_path,
    )

    log_ai_response(raw_text, ai_provider.replace(" ", "_"))

    try:
        feedback_data = extract_json(raw_text)
    except Exception:
        feedback_data = default_error_feedback(raw_text)

    feedback_data["score"] = calculate_final_score(feedback_data)
    feedback_data = apply_text_score_caps(feedback_data)

    detailed_html = render_math_text(
        feedback_data.get("detailed_latex_feedback", "")
    )

    return render_template(
        "result.html",
        feedback=feedback_data,
        detailed_html=detailed_html,
        topic_links=TOPIC_LINKS,
        question_file=question_file,
        question_number=question_number,
        solution_file=filename,
        ai_provider=ai_provider,
    )


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.run(debug=True)
