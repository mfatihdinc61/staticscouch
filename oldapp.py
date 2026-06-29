from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError, ClientError
from openai import OpenAI
from markupsafe import Markup, escape
import os
import re
import json
import time
import base64

load_dotenv()

app = Flask(__name__)

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

TOPICS = [
    {"id": 1, "title": "Decomposing vectors into components along axes", "file": "1 - vector_axial_decomposition_practice.html", "icon": "↗"},
    {"id": 2, "title": "Determining support reactions and force directions", "file": "2- support_reactions_visual_module_v3.html", "icon": "⛓"},
    {"id": 3, "title": "Drawing FBD properly", "file": "3 - fbd_course.html", "icon": "□"},
    {"id": 4, "title": "Calculating moments", "file": "4 - moment-of-force.html", "icon": "↻"},
    {"id": 5, "title": "Understanding action-reaction relationships at joints", "file": "5 - action-reaction-joints.html", "icon": "⇄"},
    {"id": 6, "title": "Transforming between w(x), V(x), and M(x)", "file": "6 - shear_moment_diagrams.html", "icon": "∫"},
    {"id": 7, "title": "Solving systems of linear equations", "file": "7 - linear_systems_course.html", "icon": "A⁻¹"},
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


def normalize_latex(text):
    text = text or ""

    # Fix broken \left / \right pairs from AI
    text = text.replace(r"\left", "")
    text = text.replace(r"\right", "")

    # Convert [ equation ] to \[ equation \]
    text = re.sub(
        r"\[\s*(\\.+?)\s*\]",
        r"\\[\1\\]",
        text,
        flags=re.DOTALL
    )

    # Convert math-like plain parentheses to inline LaTeX
    text = re.sub(
        r"(?<!\\)\(([^()\n]*(?:\\|_|=|\^|\\frac|\\sum|\\vec|\\text)[^()\n]*)\)",
        r"\\(\1\\)",
        text
    )

    return text


def render_math_text(text):
    text = normalize_latex(text)
    safe = escape(text)
    safe = str(safe).replace("\n", "<br>")
    return Markup(safe)


def image_to_data_url(path):
    ext = os.path.splitext(path)[1].lower()

    if ext == ".png":
        mime = "image/png"
    elif ext in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    else:
        mime = "application/octet-stream"

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime};base64,{b64}"


def extract_json(text):
    text = (text or "").strip()

    if text.startswith("```json"):
        text = text.replace("```json", "", 1).replace("```", "").strip()
    elif text.startswith("```"):
        text = text.replace("```", "").strip()

    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        text = text[start:end + 1]

    return json.loads(text)


def default_error_feedback(raw_text):
    return {
        "is_relevant": False,
        "score": 0,
        "overall_feedback": "The AI response could not be parsed correctly.",
        "main_mistakes": [raw_text],
        "weak_subject_areas": [],
        "wrong_or_missing_equations": [],
        "recommended_practice": [],
        "next_step": "Try uploading again.",
        "detailed_latex_feedback": raw_text
    }


def apply_score_caps(feedback_data):
    text_all = " ".join([
        str(feedback_data.get("overall_feedback", "")),
        " ".join(feedback_data.get("main_mistakes", [])),
        " ".join(feedback_data.get("wrong_or_missing_equations", [])),
        str(feedback_data.get("detailed_latex_feedback", ""))
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
        "stops before solving"
    ]):
        score = min(score, 80)

    if "fbd is missing" in text_all or "free body diagram is missing" in text_all:
        score = min(score, 65)

    feedback_data["score"] = score
    return feedback_data


def calculate_final_score(feedback_data):
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



def build_prompt(question_number):
    return f"""
You are an expert Statics tutor.

You are given:
1. The original Statics question image.
2. The official solution image.
3. The student's uploaded solution image/PDF.

The student is supposed to solve Question {question_number}.

First verify whether the uploaded student solution is actually for the given question.

If the uploaded solution is irrelevant, blank, unreadable, or for another problem, return this JSON:
{{
  "is_relevant": false,
  "score": 0,
  "overall_feedback": "This uploaded solution does not appear to be about the asked problem.",
  "main_mistakes": ["The uploaded work does not match the selected question."],
  "weak_subject_areas": [],
  "wrong_or_missing_equations": [],
  "recommended_practice": [],
  "next_step": "Upload the solution for the selected question.",
  "detailed_latex_feedback": "The submitted solution could not be graded because it does not correspond to the selected problem."
}}

If the solution is relevant, grade it strictly by comparing it with the official solution.

Very important grading rules:
- If the final numerical answer is missing, maximum score is 80.
- If equilibrium equations are only set up but not solved, maximum score is 75.
- If FBD is missing or seriously wrong, maximum score is 65.
- If support reactions are not identified correctly, maximum score is 70.
- If moment equations are missing when needed, maximum score is 70.
- Do not give 100 unless the solution is complete, correct, and includes final numerical answers with units.

Return ONLY valid JSON. Do not use markdown outside JSON.

Use this exact JSON structure:
{{
  "is_relevant": true,
  "score": 0,
  "overall_feedback": "",
  "main_mistakes": [],
  "weak_subject_areas": [],
  "wrong_or_missing_equations": [],
  "recommended_practice": [],
  "next_step": "",
  "detailed_latex_feedback": ""
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
- Never write plain square bracket equations like [ \\sum F_x = 0 ].
- Correct display format: \\[ \\sum F_x = 0 \\]
- For units, use \\(1.37\\,\\text{{kN}}\\), not 1.37 kN.

- Do not use \\left or \\right.
- Use normal parentheses instead, for example \\( F_{{CJ}}(3) \\).
- Wrong: \\left(3\\right)
- Correct: (3)
"""


def grade_with_gemini(prompt, question_path, official_solution_path, student_solution_path):
    uploaded_question = gemini_client.files.upload(file=question_path)
    uploaded_official_solution = gemini_client.files.upload(file=official_solution_path)
    uploaded_student_solution = gemini_client.files.upload(file=student_solution_path)

    response = gemini_client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
        contents=[
            prompt,
            uploaded_question,
            uploaded_official_solution,
            uploaded_student_solution
        ]
    )

    return response.text.strip()


def grade_with_openrouter(prompt, question_path, official_solution_path, student_solution_path):
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError("OPENROUTER_API_KEY is missing.")

    response = openrouter_client.chat.completions.create(
        model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
        extra_headers={
            "HTTP-Referer": os.getenv("SITE_URL", "http://127.0.0.1:5000"),
            "X-Title": os.getenv("SITE_NAME", "Statics AI Tutor"),
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(question_path)}},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(official_solution_path)}},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(student_solution_path)}},
                ],
            }
        ],
    )

    return response.choices[0].message.content.strip()


def grade_with_fallbacks(prompt, question_path, official_solution_path, student_solution_path):
    providers = []

    if os.getenv("GEMINI_API_KEY"):
        providers.append("gemini")

    if os.getenv("OPENROUTER_API_KEY"):
        providers.append("openrouter")

    last_error = None

    for provider in providers:
        for attempt in range(3):
            try:
                if provider == "gemini":
                    return grade_with_gemini(
                        prompt,
                        question_path,
                        official_solution_path,
                        student_solution_path
                    ), "Gemini"

                if provider == "openrouter":
                    return grade_with_openrouter(
                        prompt,
                        question_path,
                        official_solution_path,
                        student_solution_path
                    ), "OpenRouter"

            except (ServerError, ClientError, Exception) as e:
                last_error = e
                print(f"{provider} failed on attempt {attempt + 1}: {e}")
                time.sleep(2 ** attempt)

    raise RuntimeError(f"All AI providers failed. Last error: {last_error}")


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

    if not solution:
        return redirect(url_for("index"))

    filename = secure_filename(solution.filename)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    solution.save(save_path)

    question_path = os.path.join("static/questions", question_file)
    official_solution_path = os.path.join("static/questions", official_solution_file)

    prompt = build_prompt(question_number)

    try:
        raw_text, ai_provider = grade_with_fallbacks(
            prompt,
            question_path,
            official_solution_path,
            save_path
        )
    except Exception as e:
        raw_text = str(e)
        ai_provider = "None"
    try:
        feedback_data = extract_json(raw_text)
    except Exception:
        feedback_data = default_error_feedback(raw_text)

    feedback_data["score"] = calculate_final_score(feedback_data)
    feedback_data = apply_score_caps(feedback_data)

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
        ai_provider=ai_provider
    )


if __name__ == "__main__":
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.run(debug=True)