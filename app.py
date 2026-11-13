"""Placement Management System - Flask web app (talks to MySQL through stored procedures)."""
import mysql.connector
from flask import Flask, flash, g, redirect, render_template, request, url_for

from config import DB_CONFIG, DB_NAME, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY


# ----------------------------------------------------------------- database helpers
def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(database=DB_NAME, **DB_CONFIG)
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().cursor(dictionary=True)
    cur.execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, args)
    db.commit()
    last_id = cur.lastrowid
    cur.close()
    return last_id


def call_with_message(proc, args):
    """Calls a stored procedure whose last parameter is an OUT message."""
    db = get_db()
    cur = db.cursor()
    result = cur.callproc(proc, list(args) + [""])
    db.commit()
    cur.close()
    msg = result[-1]
    return msg.decode() if isinstance(msg, (bytes, bytearray)) else msg


def flash_message(msg):
    flash(msg, "success" if msg.startswith("SUCCESS") else "error")


def call_for_rows(proc, args):
    """Calls a stored procedure that returns a result set."""
    db = get_db()
    cur = db.cursor()
    cur.callproc(proc, list(args))
    rows = []
    for result in cur.stored_results():
        cols = result.column_names
        rows = [dict(zip(cols, r)) for r in result.fetchall()]
    cur.close()
    return rows


# ----------------------------------------------------------------- dashboard
@app.route("/")
def dashboard():
    stats = query(
        """SELECT (SELECT COUNT(*) FROM students)                                   AS students,
                  (SELECT COUNT(*) FROM students WHERE placement_status='Placed')   AS placed,
                  (SELECT COUNT(*) FROM companies)                                  AS companies,
                  (SELECT COUNT(*) FROM drives WHERE status='Open')                 AS open_drives,
                  (SELECT ROUND(AVG(offered_ctc_lpa),2) FROM placements)            AS avg_ctc,
                  (SELECT MAX(offered_ctc_lpa) FROM placements)                     AS max_ctc""", one=True)
    stats["percent"] = round(100 * stats["placed"] / stats["students"], 1) if stats["students"] else 0
    recruiters = query("SELECT * FROM v_top_recruiters ORDER BY offers DESC LIMIT 5")
    courses = query("SELECT * FROM v_course_placement ORDER BY placement_percent DESC")
    upcoming = query(
        """SELECT d.drive_id, c.company_name, d.role_title, d.drive_date, d.registration_deadline
             FROM drives d JOIN companies c ON c.company_id = d.company_id
            WHERE d.status = 'Open' ORDER BY d.drive_date LIMIT 5""")
    return render_template("dashboard.html", stats=stats, recruiters=recruiters,
                           courses=courses, upcoming=upcoming)


# ----------------------------------------------------------------- students (CRUD)
@app.route("/students")
def students():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    sql = """SELECT s.*, co.course_name FROM students s
               JOIN courses co ON co.course_id = s.course_id WHERE 1=1"""
    args = []
    if q:
        sql += " AND (s.full_name LIKE %s OR s.enrollment_no LIKE %s OR s.email LIKE %s)"
        args += [f"%{q}%"] * 3
    if status in ("Placed", "Unplaced"):
        sql += " AND s.placement_status = %s"
        args.append(status)
    rows = query(sql + " ORDER BY s.student_id LIMIT 300", args)
    return render_template("students.html", students=rows, q=q, status=status)


FIELDS = ["enrollment_no", "full_name", "email", "phone", "course_id", "batch_year",
          "tenth_percent", "twelfth_percent", "grad_percent", "active_backlogs"]


@app.route("/students/new", methods=["GET", "POST"])
def student_new():
    courses = query("SELECT * FROM courses ORDER BY course_name")
    if request.method == "POST":
        try:
            execute(f"INSERT INTO students ({', '.join(FIELDS)}) VALUES ({', '.join(['%s'] * len(FIELDS))})",
                    [request.form[f].strip() for f in FIELDS])
            flash("SUCCESS: Student added", "success")
            return redirect(url_for("students"))
        except mysql.connector.Error as e:
            flash(f"Could not save student: {e.msg}", "error")
    return render_template("student_form.html", courses=courses, student=request.form or {}, editing=False)


@app.route("/students/<int:sid>/edit", methods=["GET", "POST"])
def student_edit(sid):
    courses = query("SELECT * FROM courses ORDER BY course_name")
    student = query("SELECT * FROM students WHERE student_id = %s", (sid,), one=True)
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("students"))
    if request.method == "POST":
        try:
            execute(f"UPDATE students SET {', '.join(f + ' = %s' for f in FIELDS)} WHERE student_id = %s",
                    [request.form[f].strip() for f in FIELDS] + [sid])
            flash("SUCCESS: Student updated", "success")
            return redirect(url_for("student_detail", sid=sid))
        except mysql.connector.Error as e:
            flash(f"Could not update student: {e.msg}", "error")
            student = request.form
    return render_template("student_form.html", courses=courses, student=student, editing=True, sid=sid)


@app.route("/students/<int:sid>")
def student_detail(sid):
    student = query("""SELECT s.*, co.course_name FROM students s
                         JOIN courses co ON co.course_id = s.course_id
                        WHERE s.student_id = %s""", (sid,), one=True)
    if not student:
        flash("Student not found", "error")
        return redirect(url_for("students"))
    applications = query(
        """SELECT a.application_id, c.company_name, d.role_title, d.drive_date, a.applied_at, a.status
             FROM applications a JOIN drives d ON d.drive_id = a.drive_id
             JOIN companies c ON c.company_id = d.company_id
            WHERE a.student_id = %s ORDER BY a.applied_at DESC""", (sid,))
    open_drives = query(
        """SELECT d.drive_id, c.company_name, d.role_title, d.drive_date, d.registration_deadline, d.ctc_lpa,
                  fn_eligibility_reason(%s, d.drive_id) AS reason
             FROM drives d JOIN companies c ON c.company_id = d.company_id
            WHERE d.status = 'Open' ORDER BY d.drive_date""", (sid,))
    return render_template("student_detail.html", s=student, applications=applications, open_drives=open_drives)


@app.route("/students/<int:sid>/delete", methods=["POST"])
def student_delete(sid):
    execute("DELETE FROM students WHERE student_id = %s", (sid,))
    flash("SUCCESS: Student deleted (their applications were removed too)", "success")
    return redirect(url_for("students"))


# ----------------------------------------------------------------- registration / results
@app.route("/register", methods=["POST"])
def register():
    msg = call_with_message("sp_register_for_drive", [int(request.form["student_id"]), int(request.form["drive_id"])])
    flash_message(msg)
    return redirect(request.form.get("next") or url_for("drives"))


@app.route("/applications/<int:aid>/result", methods=["POST"])
def application_result(aid):
    msg = call_with_message("sp_update_application_result", [aid, request.form["status"]])
    flash_message(msg)
    return redirect(request.form.get("next") or url_for("drives"))


@app.route("/applications/<int:aid>/delete", methods=["POST"])
def application_delete(aid):
    execute("DELETE FROM applications WHERE application_id = %s", (aid,))
    flash("SUCCESS: Application withdrawn", "success")
    return redirect(request.form.get("next") or url_for("drives"))


# ----------------------------------------------------------------- companies
@app.route("/companies", methods=["GET", "POST"])
def companies():
    if request.method == "POST":
        try:
            execute("INSERT INTO companies (company_name, industry, headquarters) VALUES (%s,%s,%s)",
                    [request.form["company_name"].strip(), request.form["industry"].strip(),
                     request.form["headquarters"].strip()])
            flash("SUCCESS: Company added", "success")
        except mysql.connector.Error as e:
            flash(f"Could not add company: {e.msg}", "error")
        return redirect(url_for("companies"))
    rows = query("""SELECT c.*, COUNT(DISTINCT d.drive_id) AS drives, COUNT(DISTINCT p.placement_id) AS offers
                      FROM companies c LEFT JOIN drives d ON d.company_id = c.company_id
                      LEFT JOIN placements p ON p.drive_id = d.drive_id
                     GROUP BY c.company_id ORDER BY c.company_name""")
    return render_template("companies.html", companies=rows)


# ----------------------------------------------------------------- drives
@app.route("/drives")
def drives():
    rows = query("SELECT * FROM v_drive_summary ORDER BY drive_date DESC")
    return render_template("drives.html", drives=rows)


@app.route("/drives/new", methods=["GET", "POST"])
def drive_new():
    companies_ = query("SELECT * FROM companies ORDER BY company_name")
    courses = query("SELECT * FROM courses ORDER BY course_name")
    if request.method == "POST":
        f = request.form
        selected_courses = f.getlist("courses")
        if not selected_courses:
            flash("Choose at least one eligible course", "error")
        else:
            db = get_db()
            cur = db.cursor()
            try:
                cur.execute(
                    """INSERT INTO drives (company_id, role_title, drive_date, registration_deadline, ctc_lpa,
                                           min_tenth, min_twelfth, min_grad, max_backlogs)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [f["company_id"], f["role_title"].strip(), f["drive_date"], f["registration_deadline"],
                     f["ctc_lpa"], f["min_tenth"], f["min_twelfth"], f["min_grad"], f["max_backlogs"]])
                did = cur.lastrowid
                cur.executemany("INSERT INTO drive_courses (drive_id, course_id) VALUES (%s,%s)",
                                [(did, c) for c in selected_courses])
                db.commit()
                flash("SUCCESS: Drive created", "success")
                return redirect(url_for("drive_detail", did=did))
            except mysql.connector.Error as e:
                db.rollback()
                flash(f"Could not create drive: {e.msg}", "error")
            finally:
                cur.close()
    return render_template("drive_form.html", companies=companies_, courses=courses, f=request.form or {})


@app.route("/drives/<int:did>")
def drive_detail(did):
    drive = query("""SELECT d.*, c.company_name FROM drives d
                       JOIN companies c ON c.company_id = d.company_id WHERE d.drive_id = %s""", (did,), one=True)
    if not drive:
        flash("Drive not found", "error")
        return redirect(url_for("drives"))
    summary = (call_for_rows("sp_drive_summary", [did]) or [None])[0]
    allowed = query("""SELECT co.course_name FROM drive_courses dc
                         JOIN courses co ON co.course_id = dc.course_id
                        WHERE dc.drive_id = %s ORDER BY co.course_name""", (did,))
    applicants = query("SELECT * FROM v_drive_applicants WHERE drive_id = %s ORDER BY full_name", (did,))
    eligible = []
    if drive["status"] == "Open":
        eligible = query("""SELECT s.student_id, s.full_name, s.enrollment_no, co.course_name, s.grad_percent
                              FROM students s JOIN courses co ON co.course_id = s.course_id
                             WHERE fn_eligibility_reason(s.student_id, %s) = 'ELIGIBLE'
                             ORDER BY s.full_name LIMIT 50""", (did,))
    return render_template("drive_detail.html", d=drive, summary=summary, allowed=allowed,
                           applicants=applicants, eligible=eligible)


@app.route("/drives/<int:did>/status", methods=["POST"])
def drive_status(did):
    status = request.form["status"]
    if status in ("Open", "Closed", "Completed"):
        execute("UPDATE drives SET status = %s WHERE drive_id = %s", (status, did))
        flash(f"SUCCESS: Drive marked as {status}", "success")
    return redirect(url_for("drive_detail", did=did))


# ----------------------------------------------------------------- placements & reports
@app.route("/placements")
def placements():
    rows = query("SELECT * FROM v_company_selected ORDER BY placed_on DESC, company_name, full_name")
    log = query("""SELECT l.logged_at, l.event_type, l.details, s.full_name, c.company_name
                     FROM placement_log l
                     LEFT JOIN students s ON s.student_id = l.student_id
                     LEFT JOIN drives d ON d.drive_id = l.drive_id
                     LEFT JOIN companies c ON c.company_id = d.company_id
                    ORDER BY l.log_id DESC LIMIT 15""")
    return render_template("placements.html", rows=rows, log=log)


@app.route("/reports")
def reports():
    return render_template(
        "reports.html",
        drive_summary=query("SELECT * FROM v_drive_summary ORDER BY drive_date"),
        recruiters=query("SELECT * FROM v_top_recruiters ORDER BY offers DESC"),
        courses=query("SELECT * FROM v_course_placement ORDER BY placement_percent DESC"))


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)