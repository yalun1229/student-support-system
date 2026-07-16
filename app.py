from flask import Flask, render_template, request, redirect, session
import sqlite3
import os


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "student_support_secret")


# =========================
# データベース補助
# =========================
def ensure_column(cursor, table_name, column_name, definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if column_name not in existing_columns:
        cursor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} {definition}"
        )


# =========================
# データベース初期化
# =========================
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            explanation_level TEXT NOT NULL,
            answer TEXT NOT NULL,
            feedback TEXT,
            japanese_level TEXT DEFAULT 'N2',
            knowledge_level TEXT DEFAULT 'beginner',
            requested_level TEXT DEFAULT 'auto',
            selection_mode TEXT DEFAULT 'auto',
            adaptation_reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 既存データベースにも新しい列を追加する
    ensure_column(
        cursor,
        "ai_conversations",
        "japanese_level",
        "TEXT DEFAULT 'N2'"
    )
    ensure_column(
        cursor,
        "ai_conversations",
        "knowledge_level",
        "TEXT DEFAULT 'beginner'"
    )
    ensure_column(
        cursor,
        "ai_conversations",
        "requested_level",
        "TEXT DEFAULT 'auto'"
    )
    ensure_column(
        cursor,
        "ai_conversations",
        "selection_mode",
        "TEXT DEFAULT 'auto'"
    )
    ensure_column(
        cursor,
        "ai_conversations",
        "adaptation_reason",
        "TEXT"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learner_profiles (
            username TEXT PRIMARY KEY,
            japanese_level TEXT NOT NULL DEFAULT 'N2',
            knowledge_level TEXT NOT NULL DEFAULT 'beginner'
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO learner_profiles (
            username,
            japanese_level,
            knowledge_level
        )
        VALUES ('admin', 'N2', 'beginner')
    """)

    conn.commit()
    conn.close()


# =========================
# 説明レベルの決定
# =========================
def determine_explanation_level(
    requested_level,
    japanese_level,
    knowledge_level
):
    level_names = {
        "easy": "やさしい日本語",
        "standard": "標準",
        "detailed": "詳しい説明"
    }

    # 手動選択
    if requested_level in level_names:
        reason = (
            "学習者が説明レベルを手動で"
            f"「{level_names[requested_level]}」に設定したためです。"
        )
        return requested_level, "manual", reason

    # 自動調整
    if japanese_level == "N3" and knowledge_level == "beginner":
        return (
            "easy",
            "auto",
            "日本語レベルがN3程度で、IT知識が初級のため、"
            "短く分かりやすい「やさしい日本語」を選択しました。"
        )

    if japanese_level == "N3":
        return (
            "easy",
            "auto",
            "日本語レベルがN3程度のため、"
            "理解しやすい「やさしい日本語」を選択しました。"
        )

    if knowledge_level == "beginner":
        return (
            "easy",
            "auto",
            "IT知識が初級のため、専門用語を抑えた"
            "「やさしい日本語」を選択しました。"
        )

    if japanese_level == "N1" and knowledge_level == "advanced":
        return (
            "detailed",
            "auto",
            "日本語レベルがN1程度で、IT知識が上級のため、"
            "専門的な「詳しい説明」を選択しました。"
        )

    return (
        "standard",
        "auto",
        "日本語レベルとIT知識の組み合わせから、"
        "基礎内容を含む「標準」の説明を選択しました。"
    )


# =========================
# 研究試作版の回答生成
# =========================
def generate_demo_answer(question, level="easy", action="ask"):
    question_lower = question.lower()

    explanations = {
        "外部キー": {
            "easy": (
                "外部キーとは、別のテーブルにあるデータと"
                "つながりを作るための項目です。"
            ),
            "standard": (
                "外部キーとは、あるテーブルの項目から、"
                "別のテーブルの主キーを参照するための項目です。"
                "複数のテーブルのデータを関連付ける際に使用します。"
            ),
            "detailed": (
                "外部キーは、リレーショナルデータベースにおいて、"
                "別のテーブルの主キーまたは一意キーを参照する列です。"
                "データ間の整合性を保ち、存在しないデータへの参照を"
                "防止するために利用されます。"
            ),
            "example": (
                "例えば、学生テーブルに学生番号があり、"
                "成績テーブルにも学生番号を保存する場合、"
                "成績テーブルの学生番号が外部キーになります。"
                "これにより、誰の成績なのかを確認できます。"
            )
        },

        "主キー": {
            "easy": (
                "主キーとは、テーブルの中で一つのデータを"
                "特定するための項目です。"
            ),
            "standard": (
                "主キーとは、テーブル内の各レコードを"
                "重複なく識別するための項目です。"
            ),
            "detailed": (
                "主キーは、テーブル内の各行を一意に識別するための列です。"
                "同じ値を重複して登録することはできず、"
                "通常は空の値も登録できません。"
            ),
            "example": (
                "例えば、学生テーブルの学生番号は、"
                "学生一人ひとりを区別するための主キーとして使用できます。"
            )
        },

        "API": {
            "easy": (
                "APIとは、別のシステムの機能やデータを"
                "利用するための仕組みです。"
            ),
            "standard": (
                "APIとは、アプリケーション同士が情報を交換するための"
                "接続方法やルールです。"
            ),
            "detailed": (
                "APIはApplication Programming Interfaceの略で、"
                "異なるソフトウェア間で機能やデータを安全に利用するための"
                "仕様や接続方法を定義したものです。"
            ),
            "example": (
                "例えば、天気アプリが気象サービスのAPIを利用すると、"
                "自分で天気を測定しなくても、最新の天気情報を"
                "画面に表示できます。"
            )
        },

        "クラウド": {
            "easy": (
                "クラウドとは、インターネットを通して、"
                "サーバーやデータ保存場所を利用する仕組みです。"
            ),
            "standard": (
                "クラウドコンピューティングとは、サーバー、ストレージ、"
                "ソフトウェアなどをインターネット経由で利用する仕組みです。"
            ),
            "detailed": (
                "クラウドコンピューティングは、コンピュータ資源を"
                "ネットワーク経由で必要な分だけ利用する形態です。"
                "設備購入や保守の負担を減らせる一方、"
                "セキュリティや通信環境への配慮が必要です。"
            ),
            "example": (
                "例えば、Google Driveでは、自分のパソコンだけではなく、"
                "インターネット上のサーバーにファイルを保存しています。"
            )
        },

        "正規化": {
            "easy": (
                "正規化とは、データの重複を減らし、"
                "整理して保存する方法です。"
            ),
            "standard": (
                "データベースの正規化とは、データの重複や更新時の問題を"
                "減らすために、テーブルを適切に分割することです。"
            ),
            "detailed": (
                "正規化は、データの依存関係を整理し、"
                "挿入、更新、削除時の不整合を防ぐための設計手法です。"
                "第1正規形、第2正規形、第3正規形などがあります。"
            ),
            "example": (
                "例えば、学生情報と所属学科情報を一つの表に何度も保存せず、"
                "学生テーブルと学科テーブルに分けて管理します。"
            )
        },

        "仮想化": {
            "easy": (
                "仮想化とは、1台のコンピュータの中で、"
                "複数のコンピュータのように動かす技術です。"
            ),
            "standard": (
                "仮想化とは、CPUやメモリなどの物理的な資源を分割し、"
                "複数の仮想環境として利用する技術です。"
            ),
            "detailed": (
                "仮想化では、ハイパーバイザーなどを利用して、"
                "一つの物理マシン上に複数の仮想マシンを構築します。"
                "資源利用の効率化や環境分離に役立ちます。"
            ),
            "example": (
                "例えば、1台のパソコン上でWindowsとLinuxを"
                "別々の仮想マシンとして動かすことができます。"
            )
        }
    }

    matched_topic = None

    for topic in explanations:
        if topic.lower() in question_lower:
            matched_topic = topic
            break

    if matched_topic is None:
        return (
            "現在の研究試作版には、この質問に対応する説明データがありません。"
            "現在は「外部キー」「主キー」「API」「クラウド」"
            "「正規化」「仮想化」に対応しています。"
            "今後、生成AI APIを接続し、自由な専門質問に対応する予定です。"
        )

    topic_data = explanations[matched_topic]

    if action == "example":
        return topic_data["example"]

    if action == "simpler":
        return topic_data["easy"]

    return topic_data.get(level, topic_data["standard"])


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == "admin" and password == "1234":
            session["user"] = username
            return redirect("/dashboard")

        return render_template(
            "login.html",
            error="ユーザー名またはパスワードが違います。"
        )

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    error = None

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        hours_text = request.form.get("hours", "").strip()

        if not subject:
            error = "科目名を入力してください。"
        else:
            try:
                hours = int(hours_text)
                if hours <= 0:
                    error = "学習時間は1以上で入力してください。"
            except ValueError:
                error = "学習時間は数字で入力してください。"

        if error is None:
            cursor.execute(
                "INSERT INTO records (subject, hours) VALUES (?, ?)",
                (subject, hours)
            )
            conn.commit()
            conn.close()
            return redirect("/dashboard")

    cursor.execute("""
        SELECT id, subject, hours
        FROM records
        ORDER BY id DESC
    """)

    records = cursor.fetchall()
    total_hours = sum(record[2] for record in records)
    subject_count = len(set(record[1] for record in records))

    conn.close()

    return render_template(
        "dashboard.html",
        records=records,
        total_hours=total_hours,
        subject_count=subject_count,
        error=error
    )


@app.route("/ai", methods=["GET", "POST"])
def ai():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]

    answer = None
    question = ""
    selected_level = "auto"
    effective_level = None
    selection_mode = None
    adaptation_reason = None
    conversation_id = None
    error = None
    message = None

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT japanese_level, knowledge_level
        FROM learner_profiles
        WHERE username = ?
        """,
        (username,)
    )

    profile = cursor.fetchone()

    if profile is None:
        japanese_level = "N2"
        knowledge_level = "beginner"

        cursor.execute(
            """
            INSERT INTO learner_profiles (
                username,
                japanese_level,
                knowledge_level
            )
            VALUES (?, ?, ?)
            """,
            (username, japanese_level, knowledge_level)
        )
        conn.commit()
    else:
        japanese_level = profile[0]
        knowledge_level = profile[1]

    if request.method == "POST":
        action = request.form.get("action", "ask")

        if action == "ask":
            question = request.form.get("question", "").strip()
            selected_level = request.form.get("level", "auto")
            japanese_level = request.form.get(
                "japanese_level",
                japanese_level
            )
            knowledge_level = request.form.get(
                "knowledge_level",
                knowledge_level
            )

            allowed_levels = [
                "auto",
                "easy",
                "standard",
                "detailed"
            ]
            allowed_japanese_levels = ["N3", "N2", "N1"]
            allowed_knowledge_levels = [
                "beginner",
                "intermediate",
                "advanced"
            ]

            if selected_level not in allowed_levels:
                selected_level = "auto"

            if japanese_level not in allowed_japanese_levels:
                japanese_level = "N2"

            if knowledge_level not in allowed_knowledge_levels:
                knowledge_level = "beginner"

            cursor.execute(
                """
                UPDATE learner_profiles
                SET japanese_level = ?, knowledge_level = ?
                WHERE username = ?
                """,
                (
                    japanese_level,
                    knowledge_level,
                    username
                )
            )
            conn.commit()

            if not question:
                error = "質問内容を入力してください。"

            elif len(question) > 500:
                error = "質問内容は500文字以内で入力してください。"

            else:
                (
                    effective_level,
                    selection_mode,
                    adaptation_reason
                ) = determine_explanation_level(
                    selected_level,
                    japanese_level,
                    knowledge_level
                )

                answer = generate_demo_answer(
                    question,
                    effective_level,
                    "ask"
                )

                cursor.execute(
                    """
                    INSERT INTO ai_conversations (
                        question,
                        explanation_level,
                        answer,
                        japanese_level,
                        knowledge_level,
                        requested_level,
                        selection_mode,
                        adaptation_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        question,
                        effective_level,
                        answer,
                        japanese_level,
                        knowledge_level,
                        selected_level,
                        selection_mode,
                        adaptation_reason
                    )
                )

                conversation_id = cursor.lastrowid
                conn.commit()

                if selection_mode == "auto":
                    level_names = {
                        "easy": "やさしい日本語",
                        "standard": "標準",
                        "detailed": "詳しい説明"
                    }

                    message = (
                        "学習者設定に基づき、説明レベルを"
                        f"「{level_names[effective_level]}」に自動調整しました。"
                    )

        elif action in ["understood", "simpler", "example"]:
            submitted_id = request.form.get("conversation_id")

            if not submitted_id:
                error = "対象となる回答が見つかりません。"
            else:
                cursor.execute(
                    """
                    SELECT
                        id,
                        question,
                        explanation_level,
                        answer,
                        japanese_level,
                        knowledge_level,
                        requested_level
                    FROM ai_conversations
                    WHERE id = ?
                    """,
                    (submitted_id,)
                )

                previous = cursor.fetchone()

                if previous is None:
                    error = "対象となる回答が見つかりません。"
                else:
                    previous_id = previous[0]
                    question = previous[1]
                    effective_level = previous[2]
                    previous_answer = previous[3]
                    japanese_level = previous[4] or japanese_level
                    knowledge_level = previous[5] or knowledge_level
                    selected_level = previous[6] or effective_level

                    cursor.execute(
                        """
                        UPDATE ai_conversations
                        SET feedback = ?
                        WHERE id = ?
                        """,
                        (action, previous_id)
                    )

                    if action == "understood":
                        answer = previous_answer
                        conversation_id = previous_id
                        selection_mode = "feedback"
                        adaptation_reason = (
                            "学習者が「理解できた」を選択したため、"
                            "現在の説明を維持しました。"
                        )
                        message = (
                            "「理解できた」という"
                            "フィードバックを記録しました。"
                        )
                    else:
                        selection_mode = "feedback"

                        if action == "simpler":
                            effective_level = "easy"
                            selected_level = "easy"
                            adaptation_reason = (
                                "学習者が「もっと簡単に」を選択したため、"
                                "説明レベルを「やさしい日本語」に変更しました。"
                            )
                        else:
                            adaptation_reason = (
                                "学習者が「具体例がほしい」を選択したため、"
                                "同じ専門内容を具体例で再説明しました。"
                            )

                        answer = generate_demo_answer(
                            question,
                            effective_level,
                            action
                        )

                        cursor.execute(
                            """
                            INSERT INTO ai_conversations (
                                question,
                                explanation_level,
                                answer,
                                japanese_level,
                                knowledge_level,
                                requested_level,
                                selection_mode,
                                adaptation_reason
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                question,
                                effective_level,
                                answer,
                                japanese_level,
                                knowledge_level,
                                selected_level,
                                selection_mode,
                                adaptation_reason
                            )
                        )

                        conversation_id = cursor.lastrowid

                    conn.commit()

    cursor.execute(
        """
        SELECT
            id,
            question,
            explanation_level,
            answer,
            feedback,
            datetime(created_at, '+9 hours'),
            japanese_level,
            knowledge_level,
            requested_level,
            selection_mode,
            adaptation_reason
        FROM ai_conversations
        ORDER BY id DESC
        LIMIT 10
        """
    )

    history = cursor.fetchall()
    conn.close()

    return render_template(
        "ai.html",
        answer=answer,
        question=question,
        selected_level=selected_level,
        effective_level=effective_level,
        selection_mode=selection_mode,
        adaptation_reason=adaptation_reason,
        japanese_level=japanese_level,
        knowledge_level=knowledge_level,
        conversation_id=conversation_id,
        error=error,
        message=message,
        history=history
    )


@app.route("/edit/<int:record_id>", methods=["GET", "POST"])
def edit_record(record_id):
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, subject, hours FROM records WHERE id = ?",
        (record_id,)
    )
    record = cursor.fetchone()

    if record is None:
        conn.close()
        return redirect("/dashboard")

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        hours_text = request.form.get("hours", "").strip()

        if not subject:
            conn.close()
            return render_template(
                "edit.html",
                record=record,
                error="科目名を入力してください。"
            )

        try:
            hours = int(hours_text)
            if hours <= 0:
                raise ValueError
        except ValueError:
            conn.close()
            return render_template(
                "edit.html",
                record=record,
                error="学習時間は1以上の数字で入力してください。"
            )

        cursor.execute(
            """
            UPDATE records
            SET subject = ?, hours = ?
            WHERE id = ?
            """,
            (subject, hours, record_id)
        )

        conn.commit()
        conn.close()
        return redirect("/dashboard")

    conn.close()
    return render_template("edit.html", record=record)


@app.route("/delete/<int:record_id>", methods=["POST"])
def delete_record(record_id):
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM records WHERE id = ?",
        (record_id,)
    )

    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/goals", methods=["GET", "POST"])
def goals():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    error = None

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        target_hours_text = request.form.get(
            "target_hours",
            ""
        ).strip()

        if not subject:
            error = "科目名を入力してください。"
        else:
            try:
                target_hours = int(target_hours_text)
                if target_hours <= 0:
                    error = "目標時間は1以上で入力してください。"
            except ValueError:
                error = "目標時間は数字で入力してください。"

        if error is None:
            cursor.execute(
                """
                INSERT INTO goals (subject, target_hours)
                VALUES (?, ?)
                """,
                (subject, target_hours)
            )
            conn.commit()

    cursor.execute("""
        SELECT id, subject, target_hours
        FROM goals
        ORDER BY id DESC
    """)

    goals_data = cursor.fetchall()
    goals_list = []

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
        progress = min(progress, 100)

        goals_list.append({
            "id": goal_id,
            "subject": subject,
            "target_hours": target_hours,
            "total_hours": total_hours,
            "progress": progress
        })

    conn.close()

    return render_template(
        "goals.html",
        goals=goals_list,
        error=error
    )


@app.route("/delete_goal/<int:goal_id>", methods=["POST"])
def delete_goal(goal_id):
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM goals WHERE id = ?",
        (goal_id,)
    )

    conn.commit()
    conn.close()
    return redirect("/goals")


# =========================
# 研究評価・データ分析
# =========================
@app.route("/evaluation")
def evaluation():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # 全対話数
    cursor.execute("SELECT COUNT(*) FROM ai_conversations")
    total_conversations = cursor.fetchone()[0]

    # 説明方法の選択方式
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN selection_mode = 'auto' THEN 1 ELSE 0 END),
            SUM(CASE WHEN selection_mode = 'manual' THEN 1 ELSE 0 END),
            SUM(CASE WHEN selection_mode = 'feedback' THEN 1 ELSE 0 END)
        FROM ai_conversations
        """
    )

    selection_counts = cursor.fetchone()
    auto_count = selection_counts[0] or 0
    manual_count = selection_counts[1] or 0
    reexplanation_count = selection_counts[2] or 0

    # フィードバック集計
    cursor.execute(
        """
        SELECT
            SUM(CASE WHEN feedback = 'understood' THEN 1 ELSE 0 END),
            SUM(CASE WHEN feedback = 'simpler' THEN 1 ELSE 0 END),
            SUM(CASE WHEN feedback = 'example' THEN 1 ELSE 0 END),
            SUM(
                CASE
                    WHEN feedback IS NULL OR feedback = ''
                    THEN 1
                    ELSE 0
                END
            )
        FROM ai_conversations
        """
    )

    feedback_counts = cursor.fetchone()
    understood_count = feedback_counts[0] or 0
    simpler_count = feedback_counts[1] or 0
    example_count = feedback_counts[2] or 0
    unevaluated_count = feedback_counts[3] or 0

    evaluated_count = (
        understood_count
        + simpler_count
        + example_count
    )

    if evaluated_count > 0:
        understanding_rate = round(
            understood_count / evaluated_count * 100,
            1
        )
    else:
        understanding_rate = 0

    # 説明レベル別の評価
    level_names = {
        "easy": "やさしい日本語",
        "standard": "標準",
        "detailed": "詳しい説明"
    }

    level_statistics = []

    for level_key in ["easy", "standard", "detailed"]:
        cursor.execute(
            """
            SELECT
                COUNT(*),
                SUM(
                    CASE
                        WHEN feedback = 'understood'
                        THEN 1
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN feedback = 'simpler'
                        THEN 1
                        ELSE 0
                    END
                ),
                SUM(
                    CASE
                        WHEN feedback = 'example'
                        THEN 1
                        ELSE 0
                    END
                )
            FROM ai_conversations
            WHERE explanation_level = ?
            """,
            (level_key,)
        )

        row = cursor.fetchone()

        total = row[0] or 0
        understood = row[1] or 0
        simpler = row[2] or 0
        example = row[3] or 0
        evaluated = understood + simpler + example

        if evaluated > 0:
            rate = round(
                understood / evaluated * 100,
                1
            )
        else:
            rate = 0

        level_statistics.append({
            "key": level_key,
            "name": level_names[level_key],
            "total": total,
            "understood": understood,
            "simpler": simpler,
            "example": example,
            "evaluated": evaluated,
            "understanding_rate": rate
        })

    # 学習者設定別の利用状況
    cursor.execute(
        """
        SELECT
            japanese_level,
            knowledge_level,
            COUNT(*)
        FROM ai_conversations
        GROUP BY japanese_level, knowledge_level
        ORDER BY COUNT(*) DESC
        """
    )

    profile_rows = cursor.fetchall()
    profile_statistics = []

    knowledge_names = {
        "beginner": "初級",
        "intermediate": "中級",
        "advanced": "上級"
    }

    for row in profile_rows:
        profile_statistics.append({
            "japanese_level": row[0] or "未設定",
            "knowledge_level": knowledge_names.get(
                row[1],
                "未設定"
            ),
            "count": row[2]
        })

    # 最近の対話データ
    cursor.execute(
        """
        SELECT
            question,
            explanation_level,
            feedback,
            japanese_level,
            knowledge_level,
            selection_mode,
            adaptation_reason,
            datetime(created_at, '+9 hours')
        FROM ai_conversations
        ORDER BY id DESC
        LIMIT 8
        """
    )

    recent_data = cursor.fetchall()

    conn.close()

    return render_template(
        "evaluation.html",
        total_conversations=total_conversations,
        auto_count=auto_count,
        manual_count=manual_count,
        reexplanation_count=reexplanation_count,
        understood_count=understood_count,
        simpler_count=simpler_count,
        example_count=example_count,
        unevaluated_count=unevaluated_count,
        evaluated_count=evaluated_count,
        understanding_rate=understanding_rate,
        level_statistics=level_statistics,
        profile_statistics=profile_statistics,
        recent_data=recent_data
    )


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)