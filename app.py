import os
import json
from flask import Flask, render_template, request, redirect, session, url_for, flash
from db import SessionLocal, init_db
import models
from ai import analyze_resume, extract_text_from_pdf

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "ai_resume_secret_key_123")

# Initialize database tables
init_db()


@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            return render_template("signup.html", error="Email and password are required.")

        db_session = SessionLocal()
        try:
            existing_user = db_session.query(models.User).filter_by(email=email).first()
            if existing_user:
                return render_template("signup.html", error="A user with this email already exists.")

            new_user = models.User(email=email, password=password)
            db_session.add(new_user)
            db_session.commit()

            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            db_session.rollback()
            return render_template("signup.html", error=f"Database error: {str(e)}")
        finally:
            db_session.close()

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        db_session = SessionLocal()
        try:
            user = db_session.query(models.User).filter_by(email=email, password=password).first()

            if user:
                session["user"] = user.email
                session["user_id"] = user.id
                return redirect(url_for("dashboard"))
            else:
                return render_template("login.html", error="Invalid email or password.")
        except Exception as e:
            return render_template("login.html", error=f"Database error: {str(e)}")
        finally:
            db_session.close()

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    user_email = session.get("user")
    user_id = session.get("user_id")

    if request.method == "POST":
        role = request.form.get("role", "").strip()
        resume_text = request.form.get("resume", "").strip()
        file = request.files.get("file")

        # Handle uploaded file (PDF / TXT)
        if file and file.filename != "":
            filename = file.filename.lower()
            if filename.endswith(".pdf"):
                try:
                    pdf_extracted_text = extract_text_from_pdf(file.stream)
                    if resume_text:
                        resume_text = f"{resume_text}\n\n[Uploaded PDF Content]:\n{pdf_extracted_text}"
                    else:
                        resume_text = pdf_extracted_text
                except Exception as e:
                    return render_template(
                        "dashboard.html",
                        user=user_email,
                        result={"error": f"PDF Processing Error: {str(e)}"},
                        role=role,
                        resume=resume_text
                    )
            elif filename.endswith(".txt"):
                try:
                    txt_content = file.read().decode("utf-8", errors="ignore").strip()
                    if resume_text:
                        resume_text = f"{resume_text}\n\n{txt_content}"
                    else:
                        resume_text = txt_content
                except Exception as e:
                    return render_template(
                        "dashboard.html",
                        user=user_email,
                        result={"error": f"TXT file reading error: {str(e)}"},
                        role=role,
                        resume=resume_text
                    )
            else:
                return render_template(
                    "dashboard.html",
                    user=user_email,
                    result={"error": "Unsupported file format. Please upload a .pdf or .txt file."},
                    role=role,
                    resume=resume_text
                )

        if not role:
            return render_template(
                "dashboard.html",
                user=user_email,
                result={"error": "Please specify a target role."},
                role=role,
                resume=resume_text
            )

        if not resume_text:
            return render_template(
                "dashboard.html",
                user=user_email,
                result={"error": "Please provide your resume by uploading a PDF or pasting the text."},
                role=role,
                resume=resume_text
            )

        # Analyze resume using OpenAI or Gemini
        try:
            result = analyze_resume(resume_text, role)
        except Exception as e:
            result = {
                "error": f"Analysis failed: {str(e)}",
                "skills": [],
                "missing_skills": [],
                "Roadmap": [],
                "interview_queastions": []
            }

        # Save successful analysis to database reports
        if result and not result.get("error"):
            db_session = SessionLocal()
            try:
                report = models.Reports(
                    user_id=user_id,
                    role=role,
                    resume_text=resume_text[:4000],
                    result=json.dumps(result)
                )
                db_session.add(report)
                db_session.commit()
            except Exception as e:
                print(f"[Warning] Failed to save report to database: {e}")
            finally:
                db_session.close()

        return render_template(
            "dashboard.html",
            user=user_email,
            result=result,
            role=role,
            resume=resume_text
        )

    return render_template("dashboard.html", user=user_email, result=None)


@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    db_session = SessionLocal()
    history_reports = []

    try:
        reports = (
            db_session.query(models.Reports)
            .filter_by(user_id=user_id)
            .order_by(models.Reports.id.desc())
            .all()
        )

        for rep in reports:
            raw_text = rep.resume_text or ""
            preview = raw_text[:160] + ("..." if len(raw_text) > 160 else "")
            created_str = rep.created_at.strftime("%b %d, %Y - %I:%M %p") if rep.created_at else "Recently"

            history_reports.append({
                "id": rep.id,
                "role": rep.role or "Target Role",
                "resume_preview": preview,
                "created_at": created_str,
                "data": rep.get_result_data()
            })
    except Exception as e:
        flash(f"Could not load history: {str(e)}", "error")
    finally:
        db_session.close()

    return render_template("history.html", reports=history_reports)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
