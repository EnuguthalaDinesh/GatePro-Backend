"""
Comprehensive Test Script for AI-Powered GATE PDF Ingestion Pipeline
"""
import os
import sys
import json
import fitz  # PyMuPDF
from database import init_db, get_db_connection
from ai_engine import (
    compute_pdf_hash,
    convert_pdf_to_page_images,
    extract_figures_from_pdf,
    extract_questions_from_pdf
)
from main import save_paper_and_questions_to_db

def create_sample_gate_pdf() -> bytes:
    """Generates a sample GATE PDF document using PyMuPDF."""
    doc = fitz.open()
    
    # Page 1
    page1 = doc.new_page()
    rect1 = fitz.Rect(50, 50, 550, 800)
    text1 = """
GATE 2024 Official Chemical Engineering (CH) Question Paper

General Instructions:
1. This paper contains 65 questions.
2. Questions 1 to 35 carry 1 mark each. Questions 36 to 65 carry 2 marks each.

Q.1 For laminar flow of a Newtonian fluid in a circular pipe under steady state, the Fanning friction factor f is:
(A) f = 16 / Re
(B) f = 64 / Re
(C) f = 0.079 / Re^0.25
(D) f = 24 / Re

Q.2 Which of the following dimensionless numbers represent heat transfer ratio of conductive resistance to convective resistance?
(A) Reynolds Number
(B) Prandtl Number
(C) Nusselt Number
(D) Biot Number

Q.3 A continuous distillation column separates a binary mixture. The minimum reflux ratio is calculated as 1.5. Calculate the operating reflux ratio for 1.2 times R_min (round off to 2 decimal places).
"""
    page1.insert_textbox(rect1, text1, fontsize=12)

    # Page 2
    page2 = doc.new_page()
    rect2 = fitz.Rect(50, 50, 550, 800)
    text2 = """
Q.4 Which of the following statements is/are correct regarding ideal CSTR reactors? (Select all correct options)
(A) Fluid parameters are uniform throughout the reactor volume
(B) Exit stream composition is identical to the contents inside the reactor
(C) Space time equals volume divided by volumetric flow rate
(D) CSTR volume is always smaller than PFR volume for first-order reaction

Q.5 For an endothermic reaction A -> B operating at steady state, the equilibrium conversion increases with:
(A) Increasing Temperature
(B) Decreasing Temperature
(C) Increasing Pressure
(D) Addition of Inert Gas
"""
    page2.insert_textbox(rect2, text2, fontsize=12)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def test_pdf_pipeline():
    print("=== Initializing Database Migrations ===")
    init_db()

    print("=== Creating Sample GATE Question Paper PDF ===")
    pdf_bytes = create_sample_gate_pdf()
    print(f"Sample PDF created successfully ({len(pdf_bytes)} bytes).")

    print("\n=== Testing SHA-256 Hash Computation ===")
    file_hash = compute_pdf_hash(pdf_bytes)
    print(f"Computed SHA-256 Hash: {file_hash}")
    assert len(file_hash) == 64, "SHA-256 hash must be 64 hexadecimal characters"

    print("\n=== Testing PDF to Page Image Rendering ===")
    page_imgs = convert_pdf_to_page_images(pdf_bytes, file_hash, "uploads/images")
    print(f"Rendered {len(page_imgs)} page image(s):")
    for img in page_imgs:
        print(f" - Page #{img['page_number']}: {img['image_path']}")
        assert os.path.exists(img["image_path"]), f"Page image file missing: {img['image_path']}"

    import time
    test_title = f"GATE 2024 Test Official Paper {int(time.time())}"
    print("\n=== Testing Extraction Pipeline & Pydantic Validation ===")
    extracted_data = extract_questions_from_pdf(
        pdf_bytes=pdf_bytes,
        year=2024,
        subject="Chemical Engineering",
        title=test_title
    )

    print(f"Extracted Paper Title: {extracted_data['title']}")
    print(f"Total Questions Extracted: {extracted_data['total_questions']}")
    print(f"Total Marks: {extracted_data['total_marks']}")
    assert extracted_data['total_questions'] >= 5, f"Expected at least 5 questions, got {extracted_data['total_questions']}"

    print("\n=== Testing PostgreSQL Database Persistence (papers, questions, options, question_images) ===")
    paper_id = save_paper_and_questions_to_db(extracted_data, pdf_bytes, file_hash)
    print(f"Successfully saved paper to DB with Paper ID: {paper_id}")

    # Verify Database Rows
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # Check papers table
            cursor.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
            paper_row = cursor.fetchone()
            assert paper_row is not None, "Paper row not found in 'papers' table"
            assert paper_row["file_hash"] == file_hash, "Paper file_hash mismatch"
            print(f"[OK] Verified row in 'papers' table: ID={paper_row['id']}, Title='{paper_row['title']}'")

            # Check questions table
            cursor.execute("SELECT COUNT(*) AS count FROM questions WHERE paper_id = %s", (paper_id,))
            q_count = cursor.fetchone()["count"]
            assert q_count >= 5, f"Expected questions in DB >= 5, got {q_count}"
            print(f"[OK] Verified {q_count} question rows in 'questions' table.")

            # Check options table
            cursor.execute("""
            SELECT o.option_key, o.option_text, o.is_correct 
            FROM options o 
            JOIN questions q ON o.question_id = q.id 
            WHERE q.paper_id = %s
            """, (paper_id,))
            options_rows = cursor.fetchall()
            assert len(options_rows) > 0, "No options found in 'options' table"
            print(f"[OK] Verified {len(options_rows)} option rows in 'options' table.")

    finally:
        conn.close()

    print("\n=== Testing Duplicate Upload Prevention ===")
    try:
        save_paper_and_questions_to_db(extracted_data, pdf_bytes, file_hash)
        print("[FAIL] ERROR: Duplicate upload was NOT prevented!")
        sys.exit(1)
    except Exception as e:
        print(f"[OK] Successfully prevented duplicate upload: {e}")

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_pdf_pipeline()
