from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "student_support_secret"

def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            hours INTEGER NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            target_hours INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == "admin" and password == "1234":
            session["user"] = username
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="ユーザー名またはパスワードが違います")

    return render_template("login.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        subject = request.form["subject"]
        hours = request.form["hours"]

        cursor.execute(
            "INSERT INTO records (subject, hours) VALUES (?, ?)",
            (subject, hours)
        )
        conn.commit()
        conn.close()

        return redirect("/dashboard")

    cursor.execute("SELECT id, subject, hours FROM records")
    records = cursor.fetchall()

    total_hours = 0
    for record in records:
        total_hours += record[2]

    subject_count = len(set([record[1] for record in records]))

    conn.close()

    return render_template(
        "dashboard.html",
        records=records,
        total_hours=total_hours,
        subject_count=subject_count
    )

@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        subject = request.form["subject"]
        hours = request.form["hours"]

        cursor.execute(
            "UPDATE records SET subject = ?, hours = ? WHERE id = ?",
            (subject, hours, record_id)
        )

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    cursor.execute(
        "SELECT id, subject, hours FROM records WHERE id = ?",
        (record_id,)
    )

    record = cursor.fetchone()
    conn.close()

    return render_template("edit.html", record=record)

@app.route("/delete/<int:record_id>")
def delete_record(record_id):
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/goals", methods=["GET", "POST"])
def goals():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":
        subject = request.form["subject"]
        target_hours = request.form["target_hours"]

        cursor.execute(
            "INSERT INTO goals (subject, target_hours) VALUES (?, ?)",
            (subject, target_hours)
        )

        conn.commit()

    cursor.execute("SELECT id, subject, target_hours FROM goals")
    goals_data = cursor.fetchall()

    goals = []

    for goal in goals_data:
        goal_id = goal[0]
        subject = goal[1]
        target_hours = goal[2]

        cursor.execute(
            "SELECT SUM(hours) FROM records WHERE subject = ?",
            (subject,)
        )

        total_hours = cursor.fetchone()[0]

        if total_hours is None:
            total_hours = 0

        progress = int((total_hours / target_hours) * 100)

        if progress > 100:
            progress = 100

        goals.append({
            "id": goal_id,
            "subject": subject,
            "target_hours": target_hours,
            "total_hours": total_hours,
            "progress": progress
        })

    conn.close()

    return render_template("goals.html", goals=goals)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

if __name__ == "__main__":
    init_db()
    app.run(debug=True) 