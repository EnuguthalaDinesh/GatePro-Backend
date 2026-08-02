import os
import json
import hashlib
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import init_db, get_db_connection
from auth import hash_password, verify_password, create_access_token, decode_access_token
from pyqs_data import INITIAL_PAPERS
from ai_engine import generate_custom_paper, parse_markdown_textbook, chat_with_mike, extract_questions_from_pdf, compute_pdf_hash, MOTIVATIONAL_QUOTES

app = FastAPI(
    title="GatePro API Engine",
    description="Backend API service for GatePro GATE Exam Prep Platform",
    version="1.0.0"
)

# Ensure upload directories exist and mount static route
os.makedirs("uploads/pdfs", exist_ok=True)
os.makedirs("uploads/images", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.on_event("startup")
def on_startup():
    """Automatically run database migrations and seed default data on startup."""
    try:
        from seed import seed_database
        seed_database()
    except Exception as e:
        print(f"[Startup Notice] Database initialization/seed: {e}")


# Enable CORS (configurable via ALLOWED_ORIGINS env variable in production)
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",")] if allowed_origins_raw != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        res = obj.get(key, default)
        return res if res is not None else default
    if hasattr(obj, key):
        res = getattr(obj, key, default)
        return res if res is not None else default
    return default

def safe_parse_json(val):
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []

def safe_json_dumps(obj):
    def default_serializer(o):
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if hasattr(o, "dict"):
            return o.dict()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)
    return json.dumps(obj, default=default_serializer)

# Pydantic Request Models
class UserRegisterModel(BaseModel):
    username: str
    email: str
    password: str
    full_name: Optional[str] = ""
    role: Optional[str] = "student"
    target_subject: Optional[str] = "Chemical Engineering"

class UserLoginModel(BaseModel):
    username_or_email: str
    password: str

class GeneratePaperModel(BaseModel):
    subject: str = "Chemical Engineering"
    total_questions: int = 10
    difficulty: str = "GATE Official"
    topics: Optional[List[str]] = None

class MikeChatModel(BaseModel):
    message: str
    current_question: Optional[Dict[str, Any]] = None

class SubmitTestModel(BaseModel):
    paper_title: str
    paper_year: int
    user_answers: Dict[str, str]
    questions: List[Dict[str, Any]]
    time_taken_seconds: int

class AlarmModel(BaseModel):
    time_str: str
    label: str
    is_active: bool = True
    sound_type: str = "default"

# Helper dependency to authenticate JWT
def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "").strip()
    return decode_access_token(token)

def get_current_user_required(authorization: Optional[str] = Header(None)) -> dict:
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user

@app.on_event("startup")
def startup_event():
    """Initializes Database tables & seeds initial GATE PYQ papers."""
    init_db()
    seed_pyq_data()

def seed_pyq_data():
    """Seeds default GATE 2020-2024 papers into PostgreSQL if empty."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM pyqs")
            row = cursor.fetchone()
            count = row["count"] if row else 0
            
            if count == 0:
                for paper in INITIAL_PAPERS:
                    cursor.execute("""
                    INSERT INTO pyqs (year, subject, title, total_questions, total_marks, duration_minutes, difficulty, description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """, (
                        paper["year"], paper["subject"], paper["title"],
                        paper["total_questions"], paper["total_marks"],
                        paper["duration_minutes"], paper["difficulty"],
                        paper["description"]
                    ))
                    pyq_id = cursor.fetchone()["id"]
                    
                    for q in paper["questions"]:
                        cursor.execute("""
                        INSERT INTO questions (
                            pyq_id, question_number, subject, topic, question_text, question_type,
                            options_json, correct_answer, nat_range_min, nat_range_max, marks,
                            negative_marks, difficulty, explanation, formulas_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            pyq_id, q["question_number"], q.get("subject", paper["subject"]),
                            q.get("topic", "General"), q["question_text"], q.get("question_type", "MCQ"),
                            json.dumps(q.get("options", [])), str(q["correct_answer"]),
                            q.get("nat_range_min"), q.get("nat_range_max"),
                            q.get("marks", 1), q.get("negative_marks", 0.33),
                            q.get("difficulty", "GATE Official"), q.get("explanation", ""),
                            json.dumps(q.get("formulas", []))
                        ))
                conn.commit()

                # Seed mock user & leaderboard entries
                mock_pw = hash_password("password123")
                cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, role, full_name)
                VALUES (1, 'topper_raj', 'raj@gatepro.in', %s, 'student', 'Raj Sharma')
                ON CONFLICT (username) DO NOTHING
                """, (mock_pw,))
                cursor.execute("""
                INSERT INTO users (id, username, email, password_hash, role, full_name)
                VALUES (2, 'admin', 'admin@gatepro.in', %s, 'admin', 'GatePro Administrator')
                ON CONFLICT (username) DO NOTHING
                """, (mock_pw,))
                conn.commit()
                
                # Fix serial sequence after explicit ID insertion
                cursor.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id), 1)) FROM users;")
                conn.commit()

                # Populate initial leaderboard
                cursor.execute("""
                INSERT INTO leaderboard (user_id, username, total_tests, highest_score, avg_accuracy, total_score, air_estimate, badge)
                VALUES (1, 'topper_raj', 12, 94.5, 96.2, 850, 15, 'AIR Top 50')
                ON CONFLICT (user_id) DO NOTHING
                """)
                conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error seeding PYQ data: {e}")
    finally:
        conn.close()

# ----------------- AUTH ENDPOINTS -----------------

@app.post("/api/auth/register")
def register(user_data: UserRegisterModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (user_data.username, user_data.email))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Username or email already exists")
            
            hashed_pw = hash_password(user_data.password)
            cursor.execute("""
            INSERT INTO users (username, email, password_hash, role, full_name, target_subject)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """, (user_data.username, user_data.email, hashed_pw, user_data.role, user_data.full_name or user_data.username, user_data.target_subject))
            
            user_id = cursor.fetchone()["id"]
            
            cursor.execute("""
            INSERT INTO leaderboard (user_id, username, total_tests, highest_score, avg_accuracy, total_score, air_estimate, badge)
            VALUES (%s, %s, 0, 0, 0, 0, 500, 'GATE Aspirant')
            ON CONFLICT (user_id) DO NOTHING
            """, (user_id, user_data.username))
            
            conn.commit()

            token = create_access_token({"sub": str(user_id), "username": user_data.username, "role": user_data.role})
            return {
                "status": "success",
                "token": token,
                "user": {
                    "id": user_id,
                    "username": user_data.username,
                    "email": user_data.email,
                    "role": user_data.role,
                    "full_name": user_data.full_name or user_data.username,
                    "target_subject": user_data.target_subject
                }
            }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/api/auth/login")
def login(login_data: UserLoginModel):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (login_data.username_or_email, login_data.username_or_email))
            user = cursor.fetchone()
            
            if not user or not verify_password(login_data.password, user["password_hash"]):
                raise HTTPException(status_code=400, detail="Invalid username/email or password")
            
            token = create_access_token({"sub": str(user["id"]), "username": user["username"], "role": user["role"]})
            return {
                "status": "success",
                "token": token,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "role": user["role"],
                    "full_name": user["full_name"],
                    "target_subject": user["target_subject"]
                }
            }
    finally:
        conn.close()

@app.get("/api/auth/me")
def get_me(user: dict = Depends(get_current_user_required)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username, email, role, full_name, target_subject, target_year FROM users WHERE id = %s", (int(user["sub"]),))
            u = cursor.fetchone()
            if not u:
                raise HTTPException(status_code=404, detail="User not found")
            return {"user": dict(u)}
    finally:
        conn.close()

# ----------------- PYQ & ADMIN PAPERS ENDPOINTS -----------------

@app.get("/api/pyq/years")
def get_pyq_years():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT year FROM pyqs ORDER BY year DESC")
            years = [row["year"] for row in cursor.fetchall()]
            return {"years": years}
    finally:
        conn.close()

# ----------------- PAPERS & PDF INGESTION REST APIS -----------------

def save_paper_and_questions_to_db(paper_data: dict, pdf_bytes: bytes, file_hash: str) -> int:
    """
    Saves PDF file and persists extracted data into PostgreSQL tables:
    - papers
    - questions
    - options
    - question_images
    - pyqs (for backward compatibility)
    """
    pdf_dir = "uploads/pdfs"
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_filename = f"{file_hash}.pdf"
    full_pdf_path = os.path.join(pdf_dir, pdf_filename)
    pdf_url_path = f"/uploads/pdfs/{pdf_filename}"

    with open(full_pdf_path, "wb") as f:
        f.write(pdf_bytes)

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Duplicate handling: If duplicate file_hash or matching title exists, delete old entry so it gets replaced
            cursor.execute("SELECT id FROM papers WHERE file_hash = %s", (file_hash,))
            dup_hash = cursor.fetchone()
            if not dup_hash:
                cursor.execute("SELECT id FROM pyqs WHERE title = %s AND year = %s AND subject = %s", (paper_data["title"], paper_data["year"], paper_data["subject"]))
                dup_hash = cursor.fetchone()

            if dup_hash:
                old_id = dup_hash["id"]
                cursor.execute("DELETE FROM options WHERE question_id IN (SELECT id FROM questions WHERE paper_id = %s OR pyq_id = %s)", (old_id, old_id))
                cursor.execute("DELETE FROM question_images WHERE question_id IN (SELECT id FROM questions WHERE paper_id = %s OR pyq_id = %s)", (old_id, old_id))
                cursor.execute("DELETE FROM questions WHERE pyq_id = %s OR paper_id = %s", (old_id, old_id))
                cursor.execute("DELETE FROM pyqs WHERE id = %s", (old_id,))
                cursor.execute("DELETE FROM papers WHERE id = %s", (old_id,))
                conn.commit()

            # 2. Insert into papers table
            cursor.execute("""
            INSERT INTO papers (
                year, subject, title, pdf_path, file_hash, total_questions, total_marks,
                duration_minutes, difficulty, description
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """, (
                paper_data["year"], paper_data["subject"], paper_data["title"],
                pdf_url_path, file_hash, paper_data["total_questions"],
                paper_data["total_marks"], paper_data["duration_minutes"],
                paper_data["difficulty"], paper_data["description"]
            ))
            paper_id = cursor.fetchone()["id"]

            # Also insert/upsert into pyqs table for backward compatibility
            cursor.execute("""
            INSERT INTO pyqs (id, year, subject, title, total_questions, total_marks, duration_minutes, difficulty, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                total_questions = EXCLUDED.total_questions,
                total_marks = EXCLUDED.total_marks;
            """, (
                paper_id, paper_data["year"], paper_data["subject"], paper_data["title"],
                paper_data["total_questions"], paper_data["total_marks"],
                paper_data["duration_minutes"], paper_data["difficulty"], paper_data["description"]
            ))

            # 3. Insert questions, options, question_images
            for i, q in enumerate(paper_data["questions"], 1):
                q_num = get_val(q, "question_number", i)
                q_text = get_val(q, "question_text", f"Question {q_num}")
                q_type = get_val(q, "question_type", "MCQ")
                marks = get_val(q, "marks", 1)
                neg_marks = get_val(q, "negative_marks", 0.33)
                corr_ans = str(get_val(q, "correct_answer", "A"))
                topic = get_val(q, "topic", "General")
                explanation = get_val(q, "explanation", "")
                nat_min = get_val(q, "nat_range_min")
                nat_max = get_val(q, "nat_range_max")

                options_list = get_val(q, "options", [])
                formulas_list = get_val(q, "formulas", [])

                cursor.execute("""
                INSERT INTO questions (
                    paper_id, pyq_id, question_number, subject, topic, question_text, question_type,
                    marks, negative_marks, correct_answer, nat_range_min, nat_range_max,
                    difficulty, explanation, formulas_json, options_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """, (
                    paper_id, paper_id, q_num, paper_data["subject"], topic, q_text, q_type,
                    marks, neg_marks, corr_ans, nat_min, nat_max,
                    paper_data["difficulty"], explanation,
                    safe_json_dumps(formulas_list), safe_json_dumps(options_list)
                ))
                question_id = cursor.fetchone()["id"]

                # 4. Insert into options table
                for o_idx, opt in enumerate(options_list):
                    key = get_val(opt, "option_key", chr(65 + o_idx))
                    text = get_val(opt, "option_text", get_val(opt, "text", str(opt)))
                    is_corr = get_val(opt, "is_correct", key == corr_ans)

                    cursor.execute("""
                    INSERT INTO options (question_id, option_key, option_text, is_correct)
                    VALUES (%s, %s, %s, %s);
                    """, (question_id, key, text, is_corr))

                # 5. Insert into question_images table
                for img in get_val(q, "images", []):
                    img_url = get_val(img, "image_url", get_val(img, "url", str(img)))
                    caption = get_val(img, "caption", "Question Diagram")
                    if img_url and isinstance(img_url, str):
                        cursor.execute("""
                        INSERT INTO question_images (question_id, image_url, caption)
                        VALUES (%s, %s, %s);
                        """, (question_id, img_url, caption))

            conn.commit()
            return paper_id
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(e)}")
    finally:
        conn.close()

@app.get("/api/papers")
@app.get("/api/pyq/list")
def list_papers(year: Optional[int] = None, subject: Optional[str] = None):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Query papers table first, fallback to pyqs
            query = "SELECT * FROM papers WHERE 1=1"
            params = []
            if year:
                query += " AND year = %s"
                params.append(year)
            if subject:
                query += " AND subject = %s"
                params.append(subject)
            query += " ORDER BY year DESC, id DESC"
            cursor.execute(query, params)
            rows = cursor.fetchall()
            papers = [dict(row) for row in rows]

            if not papers:
                query_pyq = "SELECT * FROM pyqs WHERE 1=1"
                p_params = []
                if year:
                    query_pyq += " AND year = %s"
                    p_params.append(year)
                if subject:
                    query_pyq += " AND subject = %s"
                    p_params.append(subject)
                query_pyq += " ORDER BY year DESC, id DESC"
                cursor.execute(query_pyq, p_params)
                papers = [dict(row) for row in cursor.fetchall()]

            return {"papers": papers}
    finally:
        conn.close()

@app.get("/api/papers/{paper_id}")
@app.get("/api/pyq/paper/{paper_id}")
def get_paper_details(paper_id: int):
    return get_paper_questions(paper_id)

@app.get("/api/papers/{paper_id}/questions")
def get_paper_questions(paper_id: int):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
            paper = cursor.fetchone()
            if not paper:
                cursor.execute("SELECT * FROM pyqs WHERE id = %s", (paper_id,))
                paper = cursor.fetchone()
                if not paper:
                    raise HTTPException(status_code=404, detail="Paper not found")

            cursor.execute("""
            SELECT * FROM questions 
            WHERE paper_id = %s OR pyq_id = %s 
            ORDER BY question_number ASC
            """, (paper_id, paper_id))
            q_rows = cursor.fetchall()

            questions = []
            for q in q_rows:
                qd = dict(q)
                q_id = qd["id"]

                # Fetch structured options from options table
                cursor.execute("""
                SELECT option_key, option_text, is_correct 
                FROM options 
                WHERE question_id = %s 
                ORDER BY option_key ASC
                """, (q_id,))
                opt_rows = cursor.fetchall()
                if opt_rows:
                    qd["options"] = [dict(o) for o in opt_rows]
                else:
                    qd["options"] = safe_parse_json(qd.get("options_json"))

                # Fetch question images from question_images table
                cursor.execute("""
                SELECT image_url, caption 
                FROM question_images 
                WHERE question_id = %s
                """, (q_id,))
                img_rows = cursor.fetchall()
                qd["images"] = [dict(img) for img in img_rows]
                qd["formulas"] = safe_parse_json(qd.get("formulas_json"))
                questions.append(qd)

            res = dict(paper)
            res["questions"] = questions
            return {"paper": res}
    finally:
        conn.close()

@app.post("/api/admin/papers/upload-pdf")
@app.post("/api/papers/upload")
@app.post("/api/pyq/upload-pdf")
async def upload_pdf_paper_pipeline(
    file: UploadFile = File(...),
    year: int = Form(2024),
    subject: str = Form("Chemical Engineering"),
    title: Optional[str] = Form(None),
    user: dict = Depends(get_current_user_required)
):
    try:
        pdf_bytes = await file.read()
        if not pdf_bytes or len(pdf_bytes) < 100:
            raise HTTPException(status_code=400, detail="Invalid or empty PDF file uploaded.")

        file_hash = compute_pdf_hash(pdf_bytes)

        paper_data = extract_questions_from_pdf(
            pdf_bytes=pdf_bytes,
            year=year,
            subject=subject,
            title=title or f"GATE {year} Official {subject} Paper (Uploaded PDF)"
        )

        if not paper_data.get("questions") or paper_data.get("total_questions", 0) == 0:
            raise HTTPException(status_code=400, detail="No questions could be extracted from this PDF. Please verify that the PDF contains readable text.")

        paper_id = save_paper_and_questions_to_db(paper_data, pdf_bytes, file_hash)

        return {
            "status": "success",
            "paper_id": paper_id,
            "pyq_id": paper_id,
            "file_hash": file_hash,
            "pdf_path": f"/uploads/pdfs/{file_hash}.pdf",
            "total_questions": paper_data["total_questions"],
            "total_marks": paper_data["total_marks"],
            "message": f"Successfully processed and published '{paper_data['title']}' ({paper_data['total_questions']} questions) into PostgreSQL!"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF Upload Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF Processing failed: {str(e)}")

@app.post("/api/pyq/upload")
def upload_pyq_paper(paper_json: dict, user: dict = Depends(get_current_user_required)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            year = int(paper_json.get("year", 2025))
            subject = paper_json.get("subject", "Chemical Engineering")
            title = paper_json.get("title", f"GATE {year} Official Question Paper")
            questions = paper_json.get("questions", [])
            
            total_marks = paper_json.get("total_marks", sum(int(q.get("marks", 1)) for q in questions) if questions else 100)
            duration_minutes = int(paper_json.get("duration_minutes", 180))
            difficulty = paper_json.get("difficulty", "GATE Official")
            description = paper_json.get("description", f"Official GATE {year} question paper uploaded by Admin.")

            cursor.execute("""
            INSERT INTO pyqs (year, subject, title, total_questions, total_marks, duration_minutes, difficulty, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """, (
                year, subject, title, len(questions), total_marks, duration_minutes, difficulty, description
            ))
            pyq_id = cursor.fetchone()["id"]
            
            for i, q in enumerate(questions, 1):
                cursor.execute("""
                INSERT INTO questions (
                    pyq_id, question_number, subject, topic, question_text, question_type,
                    options_json, correct_answer, nat_range_min, nat_range_max, marks,
                    negative_marks, difficulty, explanation, formulas_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    pyq_id, q.get("question_number", i), q.get("subject", subject),
                    q.get("topic", "General"), q.get("question_text", f"Question {i}"),
                    q.get("question_type", "MCQ"), json.dumps(q.get("options", [])),
                    str(q.get("correct_answer", "A")), q.get("nat_range_min"), q.get("nat_range_max"),
                    q.get("marks", 1), q.get("negative_marks", 0.33 if q.get("marks", 1) == 1 else 0.66),
                    q.get("difficulty", difficulty), q.get("explanation", ""),
                    json.dumps(q.get("formulas", []))
                ))
                
            conn.commit()
            return {
                "status": "success",
                "pyq_id": pyq_id,
                "message": f"Successfully uploaded '{title}' with {len(questions)} exact questions into database!"
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/pyq/paper/{pyq_id}")
@app.delete("/api/admin/papers/{pyq_id}")
def delete_paper(pyq_id: int, user: dict = Depends(get_current_user_required)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Cascading delete options and images for this paper's questions
            cursor.execute("""
            DELETE FROM options 
            WHERE question_id IN (SELECT id FROM questions WHERE paper_id = %s OR pyq_id = %s)
            """, (pyq_id, pyq_id))
            
            cursor.execute("""
            DELETE FROM question_images 
            WHERE question_id IN (SELECT id FROM questions WHERE paper_id = %s OR pyq_id = %s)
            """, (pyq_id, pyq_id))

            cursor.execute("DELETE FROM questions WHERE pyq_id = %s OR paper_id = %s", (pyq_id, pyq_id))
            cursor.execute("DELETE FROM pyqs WHERE id = %s", (pyq_id,))
            cursor.execute("DELETE FROM papers WHERE id = %s", (pyq_id,))
            conn.commit()
            return {"status": "success", "message": f"Paper #{pyq_id} deleted successfully from database!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.delete("/api/admin/papers/clear-all")
def clear_all_papers(user: dict = Depends(get_current_user_required)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM options")
            cursor.execute("DELETE FROM question_images")
            cursor.execute("DELETE FROM questions")
            cursor.execute("DELETE FROM pyqs")
            cursor.execute("DELETE FROM papers")
            conn.commit()
            return {"status": "success", "message": "All papers and questions cleared from PostgreSQL database!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ----------------- ADMIN DASHBOARD STATS -----------------

@app.get("/api/admin/stats")
def get_admin_stats(user: dict = Depends(get_current_user_required)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permissions required")
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM pyqs")
            pyq_count = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM papers")
            paper_count = cursor.fetchone()["count"]
            total_papers = max(pyq_count, paper_count)
            
            cursor.execute("SELECT COUNT(*) AS count FROM questions")
            total_questions = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) AS count FROM users")
            total_users = cursor.fetchone()["count"]

            cursor.execute("SELECT COUNT(*) AS count FROM test_results")
            total_tests_attempted = cursor.fetchone()["count"]
            
            cursor.execute("SELECT * FROM pyqs ORDER BY id DESC")
            all_papers = [dict(r) for r in cursor.fetchall()]
            if not all_papers:
                cursor.execute("SELECT * FROM papers ORDER BY id DESC")
                all_papers = [dict(r) for r in cursor.fetchall()]

            return {
                "total_papers": total_papers,
                "total_questions": total_questions,
                "total_users": total_users,
                "total_tests_attempted": total_tests_attempted,
                "papers": all_papers
            }
    finally:
        conn.close()

# ----------------- AI GENERATOR & PARSER -----------------

@app.post("/api/ai/generate-paper")
def generate_ai_paper(data: GeneratePaperModel):
    paper = generate_custom_paper(
        subject=data.subject,
        total_questions=data.total_questions,
        difficulty=data.difficulty,
        topics=data.topics
    )
    return {"paper": paper}

@app.post("/api/ai/parse-md")
async def parse_md_notes(file: Optional[UploadFile] = File(None), text_content: Optional[str] = Form(None)):
    content = ""
    if file:
        raw = await file.read()
        content = raw.decode("utf-8", errors="ignore")
    elif text_content:
        content = text_content
    else:
        raise HTTPException(status_code=400, detail="No markdown file or text content provided")
        
    result = parse_markdown_textbook(content)
    return {"status": "success", "data": result}

@app.post("/api/ai/mike-chat")
def mike_chatbot(data: MikeChatModel):
    response = chat_with_mike(data.message, data.current_question)
    return response

# ----------------- TEST SUBMISSION -----------------

@app.post("/api/test/submit")
def submit_test(data: SubmitTestModel, user_jwt: Optional[dict] = Depends(get_current_user_optional)):
    user_id = int(user_jwt["sub"]) if user_jwt else 1
    
    score = 0.0
    max_score = 0.0
    correct_cnt = 0
    incorrect_cnt = 0
    unattempted_cnt = 0
    
    subject_scores = {}
    
    for q in data.questions:
        q_id_key = str(q.get("id", q.get("question_number")))
        user_ans = data.user_answers.get(q_id_key, "").strip()
        
        q_marks = float(q.get("marks", 1))
        neg_marks = float(q.get("negative_marks", 0.33))
        q_type = q.get("question_type", "MCQ")
        correct_ans = str(q.get("correct_answer", "")).strip()
        subj = q.get("subject", "General")
        
        if subj not in subject_scores:
            subject_scores[subj] = {"score": 0.0, "total": 0.0, "correct": 0, "total_q": 0}
            
        max_score += q_marks
        subject_scores[subj]["total"] += q_marks
        subject_scores[subj]["total_q"] += 1
        
        if not user_ans:
            unattempted_cnt += 1
            continue
            
        is_correct = False
        if q_type == "NAT":
            try:
                user_num = float(user_ans)
                min_r = q.get("nat_range_min")
                max_r = q.get("nat_range_max")
                if min_r is not None and max_r is not None:
                    is_correct = (min_r <= user_num <= max_r)
                else:
                    is_correct = abs(user_num - float(correct_ans)) < 0.1
            except ValueError:
                is_correct = False
        else:
            is_correct = (user_ans.lower() == correct_ans.lower())
            
        if is_correct:
            score += q_marks
            correct_cnt += 1
            subject_scores[subj]["score"] += q_marks
            subject_scores[subj]["correct"] += 1
        else:
            score -= neg_marks
            incorrect_cnt += 1
            subject_scores[subj]["score"] -= neg_marks

    total_attempted = correct_cnt + incorrect_cnt
    accuracy = round((correct_cnt / total_attempted * 100), 1) if total_attempted > 0 else 0.0
    final_score = round(max(0.0, score), 2)
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            INSERT INTO test_results (
                user_id, paper_title, paper_year, score, max_score, accuracy,
                correct_count, incorrect_count, unattempted_count, time_taken_seconds,
                subject_breakdown_json, user_answers_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, data.paper_title, data.paper_year, final_score, max_score, accuracy,
                correct_cnt, incorrect_cnt, unattempted_cnt, data.time_taken_seconds,
                json.dumps(subject_scores), json.dumps(data.user_answers)
            ))
            
            cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            u_row = cursor.fetchone()
            uname = u_row["username"] if u_row else f"User_{user_id}"
            
            cursor.execute("""
            INSERT INTO leaderboard (user_id, username, total_tests, highest_score, avg_accuracy, total_score, air_estimate)
            VALUES (%s, %s, 1, %s, %s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                total_tests = leaderboard.total_tests + 1,
                highest_score = GREATEST(leaderboard.highest_score, EXCLUDED.highest_score),
                total_score = leaderboard.total_score + EXCLUDED.highest_score,
                avg_accuracy = (leaderboard.avg_accuracy + EXCLUDED.avg_accuracy) / 2.0,
                air_estimate = GREATEST(1, CAST(1000 - (leaderboard.total_score * 5) AS INT))
            """, (user_id, uname, final_score, accuracy, final_score, max(1, int(1000 - (final_score * 10)))))
            
            conn.commit()
            
            return {
                "status": "success",
                "result": {
                    "score": final_score,
                    "max_score": max_score,
                    "accuracy": accuracy,
                    "correct_count": correct_cnt,
                    "incorrect_count": incorrect_cnt,
                    "unattempted_count": unattempted_cnt,
                    "time_taken_seconds": data.time_taken_seconds,
                    "subject_breakdown": subject_scores,
                    "air_estimate": max(1, int(1000 - (final_score * 8)))
                }
            }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ----------------- LEADERBOARD & STATS -----------------

@app.get("/api/leaderboard")
def get_leaderboard():
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT user_id, username, total_tests, highest_score, avg_accuracy, total_score, air_estimate, badge
            FROM leaderboard
            ORDER BY highest_score DESC, avg_accuracy DESC
            LIMIT 20
            """)
            rows = [dict(r) for r in cursor.fetchall()]
            return {"leaderboard": rows}
    finally:
        conn.close()

@app.get("/api/user/stats")
def get_user_stats(user: dict = Depends(get_current_user_required)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            user_id = int(user["sub"])
            cursor.execute("SELECT * FROM test_results WHERE user_id = %s ORDER BY created_at DESC", (user_id,))
            tests = [dict(r) for r in cursor.fetchall()]
            
            cursor.execute("SELECT * FROM leaderboard WHERE user_id = %s", (user_id,))
            rank_row = cursor.fetchone()
            
            return {
                "test_history": tests,
                "leaderboard_info": dict(rank_row) if rank_row else None
            }
    finally:
        conn.close()

# ----------------- ALARMS & DAILY QUOTE -----------------

@app.get("/api/quotes/daily")
def get_daily_quote():
    import random
    return {"quote": random.choice(MOTIVATIONAL_QUOTES)}

@app.get("/api/alarms")
def get_alarms(user: dict = Depends(get_current_user_required)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM user_alarms WHERE user_id = %s ORDER BY time_str ASC", (int(user["sub"]),))
            alarms = [dict(r) for r in cursor.fetchall()]
            return {"alarms": alarms}
    finally:
        conn.close()

@app.post("/api/alarms")
def add_alarm(alarm: AlarmModel, user: dict = Depends(get_current_user_required)):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
            INSERT INTO user_alarms (user_id, time_str, label, is_active, sound_type)
            VALUES (%s, %s, %s, %s, %s)
            """, (int(user["sub"]), alarm.time_str, alarm.label, 1 if alarm.is_active else 0, alarm.sound_type))
            conn.commit()
            return {"status": "success", "message": "Alarm created!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    is_reload = os.getenv("ENV", "development") == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=is_reload)
