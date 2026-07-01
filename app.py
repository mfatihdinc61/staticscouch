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
    {"number": 1, "question": "nq-5-75.png", "solution": "nqs-5-75.png", "requires_moment": True},
    {"number": 2, "question": "nq-5-79.png", "solution": "nqs-5-79.png", "requires_moment": True},
    {"number": 3, "question": "nq-5-86.png", "solution": "nqs-5-86.png", "requires_moment": True},
    {"number": 4, "question": "nq-6-21.png", "solution": "nqs-6-21.png", "requires_moment": True},
    {"number": 5, "question": "nq-6-43.png", "solution": "nqs-6-43.png", "requires_moment": True},
    {"number": 6, "question": "nq-7-80.png", "solution": "nqs-7-80.png", "requires_moment": False},
    {"number": 7, "question": "nq-7-86.png", "solution": "nqs-7-86.png", "requires_moment": False},
    {"number": 8, "question": "nq-7-90.png", "solution": "nqs-7-90.png", "requires_moment": False},
    {"number": 9, "question": "nq-8-41.png", "solution": "nqs-8-41.png", "requires_moment": False},
    {"number": 10, "question": "nq-8-63.png", "solution": "nqs-8-63.png", "requires_moment": False},
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



def get_question_meta(question_number: str) -> dict:
    """
    Returns metadata for a selected question.
    """
    try:
        number = int(question_number)
    except Exception:
        return {}

    for question in QUESTIONS:
        if question.get("number") == number:
            return question

    return {}


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

def normalize_math_text(text: str) -> str:
    """
    Converts common LaTeX-like output into readable Unicode/plain math.

    This deliberately avoids MathJax. The final feedback is displayed as
    escaped plain text with symbols such as Σ, θ, ⇒, °, and subscripts as
    simple underscore notation: F_BC, N_B, A_x.
    """
    text = text or ""

    # Remove accidental MathJax/HTML if the model ever emits it.
    text = re.sub(r"<mjx-container.*?</mjx-container>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)

    # Remove markdown fences.
    text = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)

    # Remove LaTeX math delimiters, including over-escaped versions.
    for token in [r"\\[", r"\\]", r"\\(", r"\\)", r"\[", r"\]", r"\(", r"\)"]:
        text = text.replace(token, "")

    # Remove sizing commands.
    for token in [r"\\left", r"\\right", r"\left", r"\right"]:
        text = text.replace(token, "")

    # Convert common LaTeX commands to Unicode/plain text.
    replacements = {
        r"\\sum": "Σ",
        r"\sum": "Σ",
        r"\\Sigma": "Σ",
        r"\Sigma": "Σ",
        r"\\theta": "θ",
        r"\theta": "θ",
        r"\\alpha": "α",
        r"\alpha": "α",
        r"\\beta": "β",
        r"\beta": "β",
        r"\\gamma": "γ",
        r"\gamma": "γ",
        r"\\mu": "μ",
        r"\mu": "μ",
        r"\\implies": "⇒",
        r"\implies": "⇒",
        r"\\Rightarrow": "⇒",
        r"\Rightarrow": "⇒",
        r"\\rightarrow": "→",
        r"\rightarrow": "→",
        r"\\to": "→",
        r"\to": "→",
        r"\\cdot": "·",
        r"\cdot": "·",
        r"\\times": "×",
        r"\times": "×",
        r"\\circ": "°",
        r"\circ": "°",
        r"\\sin": "sin",
        r"\sin": "sin",
        r"\\cos": "cos",
        r"\cos": "cos",
        r"\\tan": "tan",
        r"\tan": "tan",
        r"\\,": " ",
        r"\,": " ",
    }

    for bad, good in replacements.items():
        text = text.replace(bad, good)

    # Convert \text{kN} or \\text{kN} to kN.
    text = re.sub(r"\\\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)

    # Convert simple fractions \frac{a}{b} to (a)/(b).
    text = re.sub(r"\\\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1)/(\2)", text)

    # Convert F_{BC} -> F_BC, N_{B} -> N_B.
    text = re.sub(r"([A-Za-z])_\{([^{}]+)\}", r"\1_\2", text)
    text = re.sub(r"_\{([^{}]+)\}", r"_\1", text)

    # Powers.
    text = text.replace("^2", "²")
    text = text.replace("^3", "³")
    text = text.replace("^\\circ", "°")
    text = text.replace("^\\\\circ", "°")

    # Remove remaining braces.
    text = text.replace("{", "").replace("}", "")

    # Clean spacing.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def render_math_text(text: str) -> Markup:
    """
    Safely escapes AI text and displays readable Unicode/plain math.
    """
    text = normalize_math_text(text or "")
    safe = escape(text)
    safe = str(safe).replace("\\n", "<br>")
    return Markup(safe)


def extract_json(text: str) -> dict:
    """
    Robustly extracts the first JSON object returned by Gemini.

    Handles:
    - ```json fenced output
    - extra text before/after JSON
    - raw Unicode/plain math
    - occasional illegal LaTeX backslashes inside JSON strings
    """
    if not text:
        raise ValueError("Empty AI response.")

    text = text.strip()

    # Remove markdown fences anywhere in the response.
    text = re.sub(r"```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found.")

    depth = 0
    in_string = False
    escaped = False
    end = None

    for i in range(start, len(text)):
        c = text[i]

        if escaped:
            escaped = False
            continue

        if c == "\\":
            escaped = True
            continue

        if c == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        raise ValueError("Incomplete JSON object.")

    json_text = text[start:end]

    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        # Last-resort fix for accidental raw LaTeX commands inside JSON strings.
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_text)
        return json.loads(fixed)


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

def calculate_final_score(feedback_data: dict, question_number: str = None) -> int:
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

    question_meta = get_question_meta(question_number)
    moment_required = question_meta.get("requires_moment", False)

    # Do not penalize missing moment equations when the selected problem can be solved
    # without moment equations.
    if moment_required and not feedback_data.get("moment_equations_visible", True):
        score = min(score, 70)

    if not moment_required:
        feedback_data["moment_equations_visible"] = True

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
Use detailed_latex_feedback as plain Unicode math feedback, not LaTeX.
Python will calculate the final score.

Grade ONLY what is visible in the student's uploaded image.
Never assume missing work exists outside the image.
Never infer continuation from the official solution.
The official solution is ONLY a grading reference.
If the student's image is cropped, cut off, incomplete, or missing lower/right parts, mark it clearly.

For this selected question, moment equations are required: {get_question_meta(question_number).get("requires_moment", False)}.
If moment equations are not required for this selected question, set "moment_equations_applicable": false and set "moment_equations_visible": true.
Do not penalize the student for missing moment equations when they are not necessary for the selected problem.


Return ONLY valid JSON. Do not wrap the JSON in markdown fences. Do not write ```json. Do not add any text before or after the JSON.

Use this exact JSON structure:
{{
  "is_relevant": true,
  "is_cropped": false,
  "solution_complete": true,
  "fbd_visible": true,
  "equilibrium_equations_visible": true,
  "moment_equations_visible": true,
  "moment_equations_applicable": false,
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

Plain text math rules for detailed_latex_feedback:
- Do not use LaTeX.
- Do not use MathJax.
- Do not use markdown code blocks.
- Do not use dollar signs.
- Do not use \( ... \) or \[ ... \].
- Do not use <mjx-container> or any HTML.
- Use readable Unicode/plain notation instead.
- Good examples:
  ΣF_y = 0 ⇒ N_B - F_BC cos θ = 0
  ΣF_x = 0 ⇒ F_BC sin θ - 0.6N_B = 0
  tan θ = 0.6 ⇒ θ = 31.0°
  F_BC = 17.6 kN
- For subscripts, use plain underscore form like F_BC, N_B, A_x, M_Az.
- For units, write 1.37 kN, 589 N·m, 2.5 m.
"""


def grade_with_gemini(prompt: str, question_path: str, official_solution_path: str, student_solution_path: str) -> str:
    uploaded_question = gemini_client.files.upload(file=question_path)
    uploaded_official_solution = gemini_client.files.upload(file=official_solution_path)
    uploaded_student_solution = gemini_client.files.upload(file=student_solution_path)

    try:
        # Ask Gemini to return JSON directly. This reduces parsing failures.
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt,
                uploaded_question,
                uploaded_official_solution,
                uploaded_student_solution,
            ],
            config={
                "response_mime_type": "application/json"
            },
        )
    except TypeError:
        # Fallback for older google-genai versions that do not support config.
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
    except Exception as e:
        print("========== RAW GEMINI RESPONSE ==========")
        print(raw_text)
        print("========== JSON PARSE ERROR ==========")
        print(e)
        print("======================================")
        feedback_data = default_error_feedback(raw_text)

    feedback_data["score"] = calculate_final_score(feedback_data, question_number)
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
