import json
import logging
from database import get_db_connection, init_db
from auth import hash_password
from pyqs_data import INITIAL_PAPERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

def seed_database():
    """Seeds PostgreSQL database with initial users, PYQ papers, questions, sample attempts, and leaderboard entries."""
    logger.info("Initializing schema prior to seeding...")
    init_db()

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. Seed Users
            logger.info("Seeding Users...")
            student_pw = hash_password("password123")
            admin_pw = hash_password("admin123")
            
            cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, role, full_name, target_year, target_subject)
            VALUES (1, 'topper_raj', 'raj@gatepro.in', %s, 'student', 'Raj Sharma', 2025, 'Chemical Engineering')
            ON CONFLICT (username) DO NOTHING
            RETURNING id;
            """, (student_pw,))

            cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, role, full_name, target_year, target_subject)
            VALUES (2, 'admin', 'admin@gatepro.in', %s, 'admin', 'GatePro Administrator', 2025, 'Chemical Engineering')
            ON CONFLICT (username) DO NOTHING
            RETURNING id;
            """, (admin_pw,))
            
            cursor.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), coalesce(max(id), 1)) FROM users;")
            conn.commit()

            # 2. Seed Papers & Questions
            logger.info("Seeding GATE PYQ Papers & Questions...")
            for paper in INITIAL_PAPERS:
                cursor.execute("""
                INSERT INTO pyqs (year, subject, title, total_questions, total_marks, duration_minutes, difficulty, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id;
                """, (
                    paper["year"], paper["subject"], paper["title"],
                    paper["total_questions"], paper["total_marks"],
                    paper["duration_minutes"], paper["difficulty"],
                    paper["description"]
                ))
                row = cursor.fetchone()
                if row:
                    pyq_id = row["id"]
                    for q in paper["questions"]:
                        cursor.execute("""
                        INSERT INTO questions (
                            pyq_id, question_number, subject, topic, question_text, question_type,
                            options_json, correct_answer, nat_range_min, nat_range_max, marks,
                            negative_marks, difficulty, explanation, formulas_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
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

            # 3. Seed Sample Test Attempt & Results for User 1
            logger.info("Seeding Sample Test Results...")
            sample_breakdown = {
                "Fluid Mechanics": {"score": 5.0, "total": 5.0, "correct": 5, "total_q": 5},
                "Heat Transfer": {"score": 4.0, "total": 5.0, "correct": 4, "total_q": 5}
            }
            sample_user_answers = {"1": "A", "2": "B", "3": "C", "4": "D", "5": "A"}

            cursor.execute("""
            INSERT INTO test_results (
                user_id, paper_title, paper_year, score, max_score, accuracy,
                correct_count, incorrect_count, unattempted_count, time_taken_seconds,
                subject_breakdown_json, user_answers_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                1, "GATE 2024 Chemical Engineering (CH) Official PYQ Paper", 2024,
                24.5, 25.0, 96.0, 14, 1, 0, 7200,
                json.dumps(sample_breakdown), json.dumps(sample_user_answers)
            ))
            conn.commit()

            # 4. Seed Leaderboard Entries
            logger.info("Seeding Leaderboard...")
            cursor.execute("""
            INSERT INTO leaderboard (user_id, username, total_tests, highest_score, avg_accuracy, total_score, air_estimate, badge)
            VALUES (1, 'topper_raj', 12, 94.5, 96.2, 850.0, 15, 'AIR Top 50')
            ON CONFLICT (user_id) DO UPDATE SET
                highest_score = EXCLUDED.highest_score,
                avg_accuracy = EXCLUDED.avg_accuracy;
            """)
            conn.commit()

            logger.info("Database Seeding Completed Successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Error seeding database: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    seed_database()
