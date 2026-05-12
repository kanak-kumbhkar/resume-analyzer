import re
import io
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PyPDF2 import PdfReader
from docx import Document

# language_tool_python is optional (requires Java). We handle failures gracefully.
try:
    import language_tool_python
    TOOL = language_tool_python.LanguageTool('en-US')
except Exception as e:
    TOOL = None
    print(f"Warning: language_tool_python unavailable or failed to initialize: {e}")

# --- Helper Functions ---

COMMON_SKILLS = [
    "python", "javascript", "java", "c++", "c#", "react", "angular", "vue", "fastapi",
    "django", "flask", "spring", "sql", "nosql", "mongodb", "postgresql", "aws", "azure",
    "docker", "kubernetes", "git", "html", "css", "agile", "scrum", "pmp"
]

def extract_text(file_content: bytes, filename: str) -> str:
    """Extracts text content from PDF or DOCX file."""
    try:
        if filename.lower().endswith(".pdf"):
            reader = PdfReader(io.BytesIO(file_content))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        elif filename.lower().endswith(".docx"):
            document = Document(io.BytesIO(file_content))
            return "\n".join([paragraph.text for paragraph in document.paragraphs])
        else:
            raise ValueError("Unsupported file type. Only .pdf or .docx are supported.")
    except Exception as e:
        print(f"Error during text extraction: {e}")
        raise ValueError("Could not process file content. Make sure the file is a valid PDF or DOCX.")

def extract_email(text: str) -> str:
    """Extracts the first email address found using a robust regex."""
    email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    match = re.search(email_regex, text, re.IGNORECASE)
    return match.group(0) if match else "N/A"

def extract_phone(text: str) -> str:
    """Extracts a phone number (common international formats)."""
    phone_regex = r"(\+\d{1,3}\s?)?(\(\d{2,4}\)|\d{2,4})[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
    match = re.search(phone_regex, text)
    return match.group(0) if match else "N/A"

def extract_skills(text: str) -> List[str]:
    """Extracts skills by matching against a predefined list."""
    text_lower = text.lower()
    found_skills = set()
    for skill in COMMON_SKILLS:
        if skill.lower() in text_lower:
            found_skills.add(skill.capitalize())
    return sorted(list(found_skills))

def extract_experience(text: str) -> str:
    """Extracts lines containing typical experience date patterns"""
    exp_regex = r".(\d{4}[ \-–—]\s\d{4}|\d{4}[ \-–—]\s*Present|\d+\s+years?|\bJan\b|\bFeb\b|\bMar\b|\bApr\b|\bMay\b|\bJun\b|\bJul\b|\bAug\b|\bSep\b|\bOct\b|\bNov\b|\bDec\b).*"
    experience_lines = [
        line.strip() for line in text.split('\n')
        if re.search(exp_regex, line, re.IGNORECASE) and len(line.strip()) > 10
    ]
    if not experience_lines:
        return ""
    return "\n".join(experience_lines[:5])

def detect_missing_sections(text: str, email: str, phone: str, skills: List[str], experience_text: str) -> List[str]:
    """Return a list of missing/weak sections that should be suggested to the user."""
    text_lower = text.lower()
    missing = []

    # Contact details
    if email == "N/A" and phone == "N/A":
        missing.append("Contact details (email/phone)")

    # Email / Phone individually
    if email == "N/A":
        missing.append("Email")
    if phone == "N/A":
        missing.append("Phone number")

    # Skills
    if not skills:
        missing.append("Skills")

    # Education
    education_keywords = [
        "bachelor", "b.sc", "bsc", "btech", "b.e", "beng", "b.eng", "master", "m.sc", "msc", "mtech",
        "phd", "doctorate", "university", "college", "education", "degree"
    ]
    if not any(k in text_lower for k in education_keywords):
        missing.append("Education details")

    # Experience
    if not experience_text and not re.search(r"experience|worked at|intern|years? of experience", text_lower):
        missing.append("Experience / Work history")

    # Projects
    if "project" not in text_lower and "portfolio" not in text_lower:
        missing.append("Projects (examples of work)")

    # Certifications
    if "certificate" not in text_lower and "certified" not in text_lower and "certification" not in text_lower:
        missing.append("Certifications (if any)")

    # Summary / Objective
    if "summary" not in text_lower and "objective" not in text_lower and "professional summary" not in text_lower:
        missing.append("Professional summary / Objective")

    return missing

def calculate_ats_score(email: str, phone: str, skills: List[str], experience_text: str, text: str) -> int:
    """
    Calculate a simple ATS-like score (0-100) WITHOUT grammar/spelling impact.
    """
    raw = 0.0
    max_raw = 0.0

    # 1. Contact Info – total 10 points
    contact_points = 10.0
    max_raw += contact_points
    if email != "N/A":
        raw += 5.0
    if phone != "N/A":
        raw += 5.0

    # 2. Word Count – total 20 points
    wc_points = 20.0
    max_raw += wc_points
    word_count = len(text.split())
    if word_count > 100:
        scaled = min(1.0, (word_count - 100) / 400.0)  # scale between 100..500+
        raw += scaled * wc_points
    else:
        raw += 5.0  # penalize too-short resume

    # 3. Skills Match – total 30 points
    skills_points = 30.0
    max_raw += skills_points
    skill_ratio = (len(skills) / len(COMMON_SKILLS)) if COMMON_SKILLS else 0.0
    raw += skill_ratio * skills_points

    # 4. Experience – total 20 points
    exp_points = 20.0
    max_raw += exp_points
    exp_years_match = re.search(r'(\d+)\s+years?', experience_text, re.IGNORECASE)
    if exp_years_match:
        try:
            years = int(exp_years_match.group(1))
            exp_score = min(years / 5.0, 1.0) * exp_points  # 5+ years = full exp_points
        except Exception:
            exp_score = 5.0
    else:
        exp_score = 5.0
    raw += exp_score

    # Now scale raw / max_raw to 0-100
    if max_raw <= 0:
        return 0
    final = int(round(max(0.0, min(100.0, (raw / max_raw) * 100.0))))
    return final

# --- FastAPI Setup ---
app = FastAPI(title="Resume Analyzer API (Updated)")

origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "null"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request/Response Models ---
class GrammarCheckRequest(BaseModel):
    text: str

class GrammarError(BaseModel):
    incorrect: str
    message: str
    suggestion: str

class GrammarCheckResponse(BaseModel):
    errors: List[GrammarError]

# --- API Endpoints ---
@app.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """
    Analyzes an uploaded PDF or DOCX resume file.

    Returns:
      - email, phone, skills, word_count, ats_score, missing_sections (list)
      - full_text: the entire extracted text (used for grammar-check)
    """
    if file.content_type not in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ]:
        # Some browsers/clients may use different content-type; allow common fallbacks
        if not (file.filename.lower().endswith(".pdf") or file.filename.lower().endswith(".docx")):
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Please upload a PDF or DOCX."
            )

    file_content = await file.read()

    try:
        # 1. Extract Text
        text_content = extract_text(file_content, file.filename)
        if not text_content.strip():
            raise ValueError("The uploaded file contains no extractable text.")

        # 2. Extract Data Points
        email = extract_email(text_content)
        phone = extract_phone(text_content)
        skills = extract_skills(text_content)
        experience_summary = extract_experience(text_content)  # still used for ATS calculation

        # 3. Calculate Score (grammar removed from ATS)
        ats_score = calculate_ats_score(email, phone, skills, experience_summary, text_content)

        # 4. Word Count
        word_count = len(text_content.split())

        # 5. Missing sections / suggestions
        missing_sections = detect_missing_sections(text_content, email, phone, skills, experience_summary)

        # 6. Return Results
        return {
            "email": email,
            "phone": phone,
            "skills": skills,
            "word_count": word_count,
            "ats_score": ats_score,
            "missing_sections": missing_sections,
            "full_text": text_content
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during processing.")

@app.post("/grammar-check", response_model=GrammarCheckResponse)
async def check_grammar(request: GrammarCheckRequest):
    """
    Performs grammar check (NOT spelling) on the provided text.
    Uses language_tool_python if available. We filter out likely spelling matches.
    """
    if not request.text:
        return {"errors": []}

    if TOOL is None:
        # LanguageTool unavailable — return a 503 (service unavailable) with explanatory error
        raise HTTPException(status_code=503, detail="Grammar checking service unavailable on server.")

    try:
        matches = TOOL.check(request.text)
        errors: List[GrammarError] = []

        for match in matches:
            msg_lower = (match.message or "").lower()
            rule_id = getattr(match, "ruleId", "") or ""
            rule_repr = ""
            try:
                rule_repr = str(getattr(match, "rule", "")) or ""
            except Exception:
                rule_repr = ""

            is_spelling = False
            # Detect likely spelling issues and skip them
            if "spelling" in msg_lower or "misspelling" in msg_lower:
                is_spelling = True
            if "spelling" in rule_repr.lower() or "spell" in rule_id.lower():
                is_spelling = True

            if is_spelling:
                continue  # skip spelling issues

            suggestion = match.replacements[0] if match.replacements else "N/A"
            incorrect_text = request.text[match.offset: match.offset + getattr(match, "errorLength", 0)]
            if not incorrect_text and getattr(match, "context", None):
                incorrect_text = match.context

            errors.append(GrammarError(
                incorrect=incorrect_text or "N/A",
                message=match.message or "Issue detected",
                suggestion=suggestion
            ))

        return {"errors": errors}

    except Exception as e:
        print(f"Grammar check error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during grammar check.")