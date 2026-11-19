import os
import re
import json
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()

def get_ai_client():
    """
    Returns configured OpenAI client, model name, and provider name.
    Supports both Google Gemini (via OpenAI-compatible endpoint) and native OpenAI.
    """
    # Reload .env so changes are picked up immediately
    load_dotenv(override=True)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    preferred_provider = os.getenv("AI_PROVIDER", "").strip().lower()

    # Determine provider
    provider = None
    if preferred_provider in ["gemini", "google"]:
        provider = "gemini"
    elif preferred_provider in ["openai", "gpt"]:
        provider = "openai"
    elif gemini_key and not openai_key:
        provider = "gemini"
    elif openai_key and not gemini_key:
        provider = "openai"
    elif gemini_key:
        # Default to Gemini if both or gemini is present
        provider = "gemini"
    elif openai_key:
        provider = "openai"

    if provider == "gemini":
        if not gemini_key:
            return None, None, "gemini"
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
        model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
        client = OpenAI(
            api_key=gemini_key,
            base_url=base_url
        )
        return client, model, "Gemini"

    elif provider == "openai":
        if not openai_key:
            return None, None, "openai"
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(
            api_key=openai_key
        )
        return client, model, "OpenAI"

    # Neither key found
    return None, None, None


def extract_text_from_pdf(file_input):
    """
    Extracts text from a PDF file (stream, BytesIO, or path) using PyPDF2.
    """
    try:
        from PyPDF2 import PdfReader
        
        # Reset file pointer if seekable
        if hasattr(file_input, "seek"):
            file_input.seek(0)
            
        reader = PdfReader(file_input)
        extracted_text = []
        for idx, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                extracted_text.append(text)
        
        full_text = "\n".join(extracted_text).strip()
        if not full_text:
            raise ValueError("No readable text found in this PDF. It appears to be an image-based or scanned PDF. Please paste your resume text in the box below.")
        return full_text
    except Exception as e:
        raise RuntimeError(f"Failed to extract PDF text: {str(e)}")


def clean_json_response(raw_text):
    """
    Strips markdown code fences (```json ... ```) and extracts valid JSON string.
    """
    text = raw_text.strip()
    # Match markdown json block if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return text


def analyze_resume(resume_text, role):
    """
    Analyzes resume against the target role using Gemini or OpenAI.
    Returns structured dictionary with:
    - skills
    - missing_skills
    - Roadmap
    - interview_queastions
    - match_percentage
    - summary
    """
    client, model, provider_name = get_ai_client()

    if not client:
        return {
            "error": "API Key is missing! Please configure GEMINI_API_KEY or OPENAI_API_KEY in your .env file.",
            "skills": [],
            "missing_skills": [],
            "Roadmap": [],
            "interview_queastions": []
        }

    system_prompt = (
        "You are an expert AI Career Coach, Tech Recruiter, and Resume Analyzer. "
        "Analyze the provided resume against the targeted job role. "
        "You must respond ONLY with a valid, parseable JSON object without any additional conversational text."
    )

    user_prompt = f"""
Target Job Role: {role}

Candidate Resume:
\"\"\"
{resume_text}
\"\"\"

Analyze this resume against the target role and output a JSON object with the following exact keys:
{{
  "match_percentage": <integer from 0 to 100>,
  "summary": "<2-3 sentence overview of the candidate's profile fit for the role>",
  "skills": ["<matched skill 1>", "<matched skill 2>", ...],
  "missing_skills": ["<missing skill 1 required for role>", "<missing skill 2>", ...],
  "Roadmap": ["<Step 1 learning milestone>", "<Step 2...>", "<Step 3...>"],
  "interview_queastions": ["<Relevant interview question 1>", "<Relevant interview question 2>", ...]
}}
Return ONLY valid JSON.
"""

    # Candidate models to try in case of 404 (model not found), 503 (overloaded), or 429 (rate limit)
    candidate_models = [model]
    if provider_name == "Gemini":
        for fallback in ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-1.5-flash"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)
    elif provider_name == "OpenAI":
        for fallback in ["gpt-4o-mini", "gpt-3.5-turbo"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

    last_error = None
    response = None
    successful_model = model

    for m in candidate_models:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            successful_model = m
            break
        except Exception as e:
            last_error = e
            status_code = getattr(e, "status_code", None)
            # Retry on 404 (model not found), 429 (quota/rate limit), 500/502/503/504 (server overload)
            if status_code in [404, 429, 500, 502, 503, 504]:
                continue
            # For terminal errors (e.g. invalid API key), stop loop
            break

    if not response:
        return {
            "error": f"AI Service Error ({provider_name or 'AI'}): {str(last_error)}",
            "skills": [],
            "missing_skills": [],
            "Roadmap": [],
            "interview_queastions": []
        }

    try:
        content = response.choices[0].message.content
        cleaned = clean_json_response(content)
        data = json.loads(cleaned)

        # Ensure required keys exist
        data.setdefault("skills", [])
        data.setdefault("missing_skills", [])
        data.setdefault("Roadmap", [])
        data.setdefault("interview_queastions", [])
        data.setdefault("match_percentage", 0)
        data.setdefault("summary", "Analysis completed.")

        # Alias for alternative spelling
        data["interview_questions"] = data["interview_queastions"]
        data["roadmap"] = data["Roadmap"]
        data["provider"] = provider_name
        data["model"] = successful_model

        return data

    except json.JSONDecodeError as e:
        return {
            "error": f"Failed to parse AI response as JSON: {str(e)}",
            "raw_response": content if 'content' in locals() else "",
            "skills": [],
            "missing_skills": [],
            "Roadmap": [],
            "interview_queastions": []
        }
    except Exception as e:
        return {
            "error": f"AI Analysis Error ({provider_name or 'AI'}): {str(e)}",
            "skills": [],
            "missing_skills": [],
            "Roadmap": [],
            "interview_queastions": []
        }


if __name__ == "__main__":
    print("Testing ai.py module...")
    client, model, prov = get_ai_client()
    print(f"Provider: {prov}, Model: {model}, Client Configured: {client is not None}")
