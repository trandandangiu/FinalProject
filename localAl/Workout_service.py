from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection

workout_bp = Blueprint("workout", __name__)

# ===================== LẤY DANH SÁCH BÀI TẬP =====================
@workout_bp.route("/workouts", methods=["GET"])
@jwt_required(optional=True)  # ✅ Cho phép cả user chưa login vẫn xem
def get_exercises():
    """
    Lấy danh sách bài tập.
    Filter: body_part, equipment, target.
    """
    try:
        body_part = request.args.get("body_part")
        equipment = request.args.get("equipment")
        target = request.args.get("target")
        limit = request.args.get("limit", 20, type=int)

        query = """
            SELECT exercise_id, name, body_part, equipment, target, secondary_muscles, video_url
            FROM exercises
            WHERE 1=1
        """
        params = []

        if body_part:
            query += " AND body_part = %s"
            params.append(body_part)
        if equipment:
            query += " AND equipment = %s"
            params.append(equipment)
        if target:
            query += " AND target = %s"
            params.append(target)

        query += " LIMIT %s"
        params.append(limit)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        exercises = cursor.fetchall()

        cursor.close()
        conn.close()
        return jsonify({"count": len(exercises), "exercises": exercises}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== TẠO BUỔI TẬP =====================
@workout_bp.route("/workouts/session", methods=["POST"])
@jwt_required()
def create_session():
    """
    Tạo 1 buổi tập mới cho user hiện tại.
    """
    try:
        data = request.get_json()
        user_id =int( get_jwt_identity())

        date = data.get("date")
        duration_min = data.get("duration_min", 0)
        total_calories = data.get("total_calories", 0)

        if not date:
            return jsonify({"msg": "Date is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sessions (user_id, date, duration_min, total_calories)
            VALUES (%s, %s, %s, %s)
        """, (user_id, date, duration_min, total_calories))
        conn.commit()
        session_id = cursor.lastrowid

        cursor.close()
        conn.close()
        return jsonify({"msg": "Session created", "session_id": session_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== THÊM BÀI TẬP VÀO BUỔI =====================
@workout_bp.route("/workouts/session_details", methods=["POST"])
@jwt_required()
def add_session_detail():
    """
    Thêm 1 bài tập vào buổi tập (session).
    """
    try:
        data = request.get_json()
        session_id = data.get("session_id")
        exercise_id = data.get("exercise_id")
        sets = data.get("sets", 3)
        reps = data.get("reps", 12)
        duration_min = data.get("duration_min", 10)
        calories_burned = data.get("calories_burned", 0)

        if not session_id or not exercise_id:
            return jsonify({"msg": "session_id and exercise_id are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO session_details (session_id, exercise_id, sets, reps, duration_min, calories_burned)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (session_id, exercise_id, sets, reps, duration_min, calories_burned))

        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"msg": "Exercise added to session"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== LỊCH SỬ TẬP LUYỆN =====================
@workout_bp.route("/workouts/history", methods=["GET"])
@jwt_required()
def get_workout_history():
    """
    Lịch sử tập luyện của user hiện tại (gom theo session).
    """
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT s.session_id, s.date, s.duration_min, s.total_calories,
                   e.name AS exercise_name, e.body_part, sd.sets, sd.reps,
                   sd.duration_min AS exercise_duration, sd.calories_burned
            FROM sessions s
            LEFT JOIN session_details sd ON s.session_id = sd.session_id
            LEFT JOIN exercises e ON sd.exercise_id = e.exercise_id
            WHERE s.user_id = %s
            ORDER BY s.date DESC, s.session_id DESC
        """, (user_id,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        # Gom nhóm theo session_id
        history = {}
        for row in rows:
            sid = row["session_id"]
            if sid not in history:
                history[sid] = {
                    "session_id": sid,
                    "date": row["date"],
                    "duration_min": row["duration_min"],
                    "total_calories": row["total_calories"],
                    "exercises": []
                }
            if row["exercise_name"]:
                history[sid]["exercises"].append({
                    "name": row["exercise_name"],
                    "body_part": row["body_part"],
                    "sets": row["sets"],
                    "reps": row["reps"],
                    "duration_min": row["exercise_duration"],
                    "calories_burned": row["calories_burned"]
                })

        return jsonify(list(history.values())), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== XOÁ BUỔI TẬP =====================
@workout_bp.route("/workouts/session/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    """
    Xoá buổi tập và toàn bộ chi tiết (chỉ cho user sở hữu).
    """
    try:
        user_id =int( get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor()

        # Kiểm tra session có thuộc user không
        cursor.execute("SELECT * FROM sessions WHERE session_id=%s AND user_id=%s", (session_id, user_id))
        if not cursor.fetchone():
            return jsonify({"error": "Session not found or not owned by user"}), 404

        cursor.execute("DELETE FROM session_details WHERE session_id = %s", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = %s AND user_id = %s", (session_id, user_id))
        conn.commit()

        cursor.close()
        conn.close()
        return jsonify({"msg": f"Session {session_id} deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
