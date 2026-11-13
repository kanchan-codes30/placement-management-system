"""Fills the database with RANDOM DEMO DATA (no real students).

The data is created by calling the same stored procedures the web app uses,
so the eligibility rules and triggers are exercised while seeding.

Usage:  python seed_data.py
"""
import random

import mysql.connector

from config import DB_CONFIG, DB_NAME

random.seed(42)

COURSES = ["BCA", "B.Sc (CS)", "B.Sc (IT)", "B.Tech (CSE)", "BBA", "B.Com"]

FIRST = ["Aarav", "Riya", "Kunal", "Neha", "Rohan", "Priya", "Aman", "Sneha", "Vikas", "Anjali",
         "Harsh", "Pooja", "Mohit", "Kavya", "Sahil", "Isha", "Nikhil", "Divya", "Arjun", "Meera",
         "Yash", "Tanvi", "Deepak", "Simran", "Rahul", "Shreya", "Ankit", "Nisha", "Varun", "Komal"]
LAST = ["Sharma", "Verma", "Rawat", "Negi", "Bisht", "Joshi", "Pant", "Bhatt", "Singh", "Gupta",
        "Kumar", "Mehta", "Chauhan", "Thakur", "Rana", "Kandpal", "Arya", "Pandey", "Tiwari", "Saini"]

COMPANIES = [
    ("Cognizant", "IT Services", "Teaneck, USA"), ("TCS", "IT Services", "Mumbai"),
    ("Infosys", "IT Services", "Bengaluru"), ("Wipro", "IT Services", "Bengaluru"),
    ("Accenture", "Consulting", "Dublin"), ("Capgemini", "IT Services", "Paris"),
    ("HCLTech", "IT Services", "Noida"), ("Tech Mahindra", "IT Services", "Pune"),
    ("Zoho", "Software Products", "Chennai"), ("Genpact", "Business Services", "New York"),
]

ALL = COURSES
IT = ["BCA", "B.Sc (CS)", "B.Sc (IT)", "B.Tech (CSE)"]
# (company, role, courses, min10, min12, min_grad, max_backlogs, ctc)
PAST_DRIVES = [
    ("Wipro", "Project Engineer", IT, 60, 60, 60, 0, 3.5),
    ("Genpact", "Process Associate", ALL, 50, 50, 50, 0, 3.0),
    ("TCS", "Assistant System Engineer", IT, 60, 60, 60, 0, 3.4),
    ("Cognizant", "Analyst Trainee (ITAT/ISMO)", IT, 60, 60, 60, 0, 4.0),
    ("Infosys", "Systems Engineer", IT, 60, 60, 60, 0, 3.6),
    ("Capgemini", "Analyst", IT + ["BBA"], 55, 55, 55, 1, 3.8),
    ("Cognizant", "Analyst Trainee (Multicloud/DWS)", ALL, 50, 50, 50, 0, 3.8),
    ("HCLTech", "Graduate Engineer Trainee", IT, 65, 65, 65, 0, 4.2),
    ("Zoho", "Software Developer", ["BCA", "B.Sc (CS)", "B.Tech (CSE)"], 70, 70, 70, 0, 7.0),
    ("Accenture", "Associate Software Engineer", IT, 60, 60, 60, 0, 4.6),
]
UPCOMING_DRIVES = [
    ("Tech Mahindra", "Software Engineer", IT, 60, 60, 60, 0, 3.6, 8),
    ("Cognizant", "Analyst Trainee 2027", ["BCA", "B.Sc (CS)", "B.Sc (IT)"], 60, 60, 60, 0, 4.0, 12),
    ("Genpact", "Data Analyst Trainee", ALL, 55, 55, 55, 0, 3.4, 16),
]


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    conn = mysql.connector.connect(database=DB_NAME, **DB_CONFIG)
    cur = conn.cursor()

    # ---- courses & companies
    cur.executemany("INSERT INTO courses (course_name) VALUES (%s)", [(c,) for c in COURSES])
    cur.executemany("INSERT INTO companies (company_name, industry, headquarters) VALUES (%s,%s,%s)", COMPANIES)
    conn.commit()
    cur.execute("SELECT course_id, course_name FROM courses")
    course_id = {n: i for i, n in cur.fetchall()}
    cur.execute("SELECT company_id, company_name FROM companies")
    company_id = {n: i for i, n in cur.fetchall()}

    # ---- students
    n_students = 160
    weights = [30, 18, 14, 14, 12, 12]
    for i in range(1, n_students + 1):
        first, last = random.choice(FIRST), random.choice(LAST)
        course = random.choices(COURSES, weights)[0]
        backlogs = 0 if random.random() < 0.86 else random.randint(1, 3)
        cur.execute(
            """INSERT INTO students (enrollment_no, full_name, email, phone, course_id, batch_year,
                                     tenth_percent, twelfth_percent, grad_percent, active_backlogs)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (f"ENR27{i:03d}", f"{first} {last}", f"{first}.{last}{i}@example.com".lower(),
             f"90000{random.randint(10000, 99999)}", course_id[course], 2027,
             round(clip(random.gauss(72, 10), 45, 96), 2),
             round(clip(random.gauss(70, 10), 45, 96), 2),
             round(clip(random.gauss(71, 8), 48, 95), 2), backlogs))
    conn.commit()
    cur.execute("SELECT student_id FROM students")
    student_ids = [r[0] for r in cur.fetchall()]

    def create_drive(company, role, courses, m10, m12, mg, mb, ctc, days_ahead):
        cur.execute(
            """INSERT INTO drives (company_id, role_title, drive_date, registration_deadline, ctc_lpa,
                                   min_tenth, min_twelfth, min_grad, max_backlogs, status)
               VALUES (%s,%s, CURDATE() + INTERVAL %s DAY, CURDATE() + INTERVAL %s DAY, %s,%s,%s,%s,%s,'Open')""",
            (company_id[company], role, days_ahead + 3, days_ahead, ctc, m10, m12, mg, mb))
        did = cur.lastrowid
        cur.executemany("INSERT INTO drive_courses (drive_id, course_id) VALUES (%s,%s)",
                        [(did, course_id[c]) for c in courses])
        conn.commit()
        return did

    def register(sid, did):
        cur.callproc("sp_register_for_drive", [sid, did, ""])
        conn.commit()

    def set_result(aid, status):
        cur.callproc("sp_update_application_result", [aid, status, ""])
        conn.commit()

    def eligible_students(did):
        cur.execute("SELECT student_id FROM students WHERE fn_eligibility_reason(student_id, %s) = 'ELIGIBLE'", (did,))
        return [r[0] for r in cur.fetchall()]

    # ---- completed (past) drives: register -> shortlist -> select/reject
    past_ids = []
    for spec in PAST_DRIVES:
        did = create_drive(*spec, days_ahead=30)
        eligible = eligible_students(did)
        applicants = random.sample(eligible, int(len(eligible) * random.uniform(0.65, 0.9))) if eligible else []
        for sid in applicants:
            register(sid, did)
        cur.execute("SELECT application_id FROM applications WHERE drive_id = %s", (did,))
        apps = [r[0] for r in cur.fetchall()]
        random.shuffle(apps)
        n_screened_out = int(len(apps) * 0.4)
        for aid in apps[:n_screened_out]:
            set_result(aid, "Rejected")
        shortlisted = apps[n_screened_out:]
        for aid in shortlisted:
            set_result(aid, "Shortlisted")
        n_select = max(1, round(len(shortlisted) * random.uniform(0.15, 0.28))) if shortlisted else 0
        for k, aid in enumerate(shortlisted):
            set_result(aid, "Selected" if k < n_select else "Rejected")
        cur.execute("UPDATE drives SET status = 'Completed' WHERE drive_id = %s", (did,))
        conn.commit()
        past_ids.append(did)

    # ---- move the completed drives into the past (about 3 weeks apart)
    n_past = len(past_ids)
    for i, did in enumerate(past_ids):
        back = (n_past - i) * 21
        cur.execute("UPDATE drives SET drive_date = CURDATE() - INTERVAL %s DAY, "
                    "registration_deadline = CURDATE() - INTERVAL %s DAY WHERE drive_id = %s",
                    (back, back + 5, did))
        cur.execute("UPDATE applications SET applied_at = NOW() - INTERVAL %s DAY WHERE drive_id = %s",
                    (back + 9, did))
        cur.execute("UPDATE placements SET placed_on = CURDATE() - INTERVAL %s DAY WHERE drive_id = %s",
                    (back - 2, did))
        cur.execute("UPDATE placement_log SET logged_at = NOW() - INTERVAL %s DAY WHERE drive_id = %s",
                    (back, did))
    conn.commit()

    # ---- upcoming open drives with some registrations
    for spec in UPCOMING_DRIVES:
        did = create_drive(*spec[:8], days_ahead=spec[8])
        eligible = eligible_students(did)
        for sid in random.sample(eligible, int(len(eligible) * random.uniform(0.3, 0.6))) if eligible else []:
            register(sid, did)

    cur.execute("SELECT (SELECT COUNT(*) FROM students), (SELECT COUNT(*) FROM students WHERE placement_status='Placed'),"
                " (SELECT COUNT(*) FROM drives), (SELECT COUNT(*) FROM applications), (SELECT COUNT(*) FROM placements)")
    s, p, d, a, pl = cur.fetchone()
    print(f"Seeded: {s} students ({p} placed), {d} drives, {a} applications, {pl} placements.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
