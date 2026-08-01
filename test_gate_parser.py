"""
Test script for official GATE paper extraction (Q1 to Q65)
"""
import re

sample_gate_text = """
Chemical Engineering (CH)
General Aptitude (GA)
Q.1 – Q.5 Carry ONE mark Each

Q.1 “He often _____ the numbers. False claims are not going to help. Honesty _____ trust”, said the manager. 
Choose the option with the correct order of words to fill the blanks.
(A) exaggerates; engenders
(B) excels; encourages
(C) aggravates; alleviates
(D) diminishes; eliminates

Q.2 In the sequence of tiles shown below, the missing tile indicated by the question mark should be
(A) Tile Option A
(B) Tile Option B
(C) Tile Option C
(D) Tile Option D

Q.3 A school has 100 students distributed among 1st to 10th standards. 
Based on this, which one of the following statements is always correct?
(A) There are at least 10 students who belong to the same standard.
(B) There is at least one student in each standard.
(C) There are at most 10 students in 10th standard.
(D) The total number of students from 1st to 5th standards is at least 50.

Q.4 How many 3-digit numbers can be formed using three distinct single digit prime numbers?
(A) 64
(B) 24
(C) 12
(D) 4

Q.5 In a group of students, 10 students like Mathematics, 12 students like English...
(A) 18
(B) 20
(C) 24
(D) 32

Q.6 – Q.10 Carry TWO marks Each

Q.6 Charity : P :: Retaliation : Q
Choose the appropriate pair of words P and Q that fit the analogy.
(A) P = Parsimonious; Q = Vengeful
(B) P = Altruistic; Q = Amicable
(C) P = Resentful; Q = Spiteful
(D) P = Magnanimous; Q = Vindictive

Q.7 A paper shown in Panel I is folded along the dashed lines to construct a cube...
(A) Only (i) can correspond
(B) Only (ii) can correspond
(C) Both (i) and (ii)
(D) Neither (i) nor (ii)

Q.11 – Q.35 Carry ONE mark Each

Q.11 Which one of the following is NOT a type of chain conveyor?
(A) apron conveyor
(B) bucket conveyor
(C) scraper conveyor
(D) screw conveyor

Q.12 In the P&ID shown below, which one of the following is the function of PAH in the process?
(A) to maintain a constant pressure
(B) to alert when high pressure is detected
(C) to measure average pressure
(D) to regulate flow

Q.35 Using single step trapezoidal rule, the value of integral is ______ (rounded off to two decimal places).

Q.36 – Q.65 Carry TWO marks Each

Q.36 K value is defined as the ratio of mole fraction...
(A) 1110
(B) 1190
(C) 1310
(D) 1390

Q.65 The velocity profile for a fully developed laminar flow...
"""

def parse_gate_text(full_text):
    cleaned_text = re.sub(
        r'Q\s*[\.\:]?\s*\d+\s*[\–\-\—\to\-]+\s*Q\s*[\.\:]?\s*\d+.*?\n',
        '\n',
        full_text,
        flags=re.IGNORECASE
    )

    parts = re.split(r'\n(?=Q\s*[\.\:]?\s*\d{1,2}\b)', cleaned_text, flags=re.IGNORECASE)

    parsed_dict = {}
    for part in parts:
        part_str = part.strip()
        if not part_str:
            continue

        m_num = re.match(r'^Q\s*[\.\:]?\s*(\d{1,2})\b([\s\S]*)', part_str, flags=re.IGNORECASE)
        if not m_num:
            continue

        q_num = int(m_num.group(1))
        if not (1 <= q_num <= 65):
            continue

        body = m_num.group(2).strip()
        if not body or len(body) < 5:
            continue

        opt_matches = re.findall(
            r'(?:\(([A-Da-d])\)|([A-Da-d])[\.\)\:])\s*([^\n\(\)]+)',
            body
        )
        options = []
        if opt_matches:
            seen = set()
            for om in opt_matches:
                k = (om[0] or om[1]).upper()
                txt = om[2].strip()
                if k in ['A', 'B', 'C', 'D'] and k not in seen:
                    seen.add(k)
                    options.append({"option_key": k, "option_text": txt, "is_correct": (k == 'A')})

        q_statement = re.split(r'(?:\([A-Da-d]\)|[A-Da-d][\.\)\:])', body)[0].strip()
        q_statement = re.sub(r'^(?:Q\s*[\.\:]?\s*\d+\s*)', '', q_statement).strip()

        q_type = "MCQ" if len(options) >= 2 else "NAT"

        parsed_dict[q_num] = {
            "question_number": q_num,
            "question_text": q_statement if q_statement else body,
            "question_type": q_type,
            "options": options
        }

    return parsed_dict

if __name__ == "__main__":
    res = parse_gate_text(sample_gate_text)
    print(f"Extracted {len(res)} questions:")
    for num in sorted(res.keys()):
        q = res[num]
        print(f"Q{num}: {q['question_text'][:40]!r} | Options: {[o['option_key'] + ': ' + o['option_text'] for o in q['options']]}")
