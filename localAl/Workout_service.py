from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, date
import json

workout_bp = Blueprint("workout", __name__)

# ===================== LẤY DANH SÁCH BÀI TẬP NÂNG CAO =====================
@workout_bp.route("/workouts", methods=["GET"])
@jwt_required(optional=True)
def get_exercises():
    """
    Lấy danh sách bài tập với filter nâng cao và video
    Filter: body_part, equipment, target, level, search
    """
    try:
        # 🆕 THAM SỐ FILTER NÂNG CAO
        body_part = request.args.get("body_part")
        equipment = request.args.get("equipment")
        target = request.args.get("target")
        level = request.args.get("level")
        search = request.args.get("search")  # 🆕 Tìm kiếm theo tên
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        
        offset = (page - 1) * limit

        query = """
            SELECT exercise_id, name, body_part, equipment, target, secondary_muscles,
                   video_path, level
            FROM exercises
            WHERE is_active = 1
        """
        params = []

        # 🆕 FILTER NÂNG CAO
        if body_part:
            query += " AND body_part = %s"
            params.append(body_part)
        if equipment:
            query += " AND equipment = %s"
            params.append(equipment)
        if target:
            query += " AND target = %s"
            params.append(target)
        if level:
            query += " AND level = %s"
            params.append(level)
        if search:  # 🆕 TÌM KIẾM THEO TÊN
            query += " AND name LIKE %s"
            params.append(f"%{search}%")

        # 🆕 PHÂN TRANG
        query += " ORDER BY name LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        exercises = cursor.fetchall()

        # 🆕 ĐẾM TỔNG SỐ BÀI TẬP (cho phân trang)
        count_query = "SELECT COUNT(*) as total FROM exercises WHERE is_active = 1"
        count_params = []
        
        if body_part:
            count_query += " AND body_part = %s"
            count_params.append(body_part)
        if equipment:
            count_query += " AND equipment = %s"
            count_params.append(equipment)
        if target:
            count_query += " AND target = %s"
            count_params.append(target)
        if level:
            count_query += " AND level = %s"
            count_params.append(level)
        if search:
            count_query += " AND name LIKE %s"
            count_params.append(f"%{search}%")

        cursor.execute(count_query, tuple(count_params))
        total_count = cursor.fetchone()['total']

        cursor.close()
        conn.close()

        return jsonify({
            "count": len(exercises),
            "total": total_count,
            "page": page,
            "limit": limit,
            "exercises": exercises
        }), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== LẤY CHI TIẾT BÀI TẬP =====================
@workout_bp.route("/workouts/<int:exercise_id>", methods=["GET"])
@jwt_required(optional=True)
def get_exercise_detail(exercise_id):
    """
    Lấy chi tiết bài tập cụ thể
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🛠️ SỬA: Xóa usage_count vì không có trong database
        cursor.execute("""
            SELECT exercise_id, name, body_part, equipment, target, secondary_muscles,
                   video_path, level, is_active
            FROM exercises
            WHERE exercise_id = %s AND is_active = 1
        """, (exercise_id,))
        
        exercise = cursor.fetchone()

        if not exercise:
            return jsonify({"error": "Bài tập không tồn tại"}), 404

        cursor.close()
        conn.close()

        return jsonify({"exercise": exercise}), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== TẠO BUỔI TẬP THÔNG MINH =====================
@workout_bp.route("/workouts/session", methods=["POST"])
@jwt_required()
def create_session():
    """
    Tạo buổi tập mới
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())

        session_date = data.get("date")
        duration_min = data.get("duration_min", 0)
        total_calories = data.get("total_calories", 0)

        if not session_date:
            return jsonify({"error": "Ngày tập là bắt buộc"}), 400

        # 🛠️ SỬA: Validation ngày
        try:
            datetime.strptime(session_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Định dạng ngày không hợp lệ (YYYY-MM-DD)"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 🛠️ SỬA: Chỉ insert các cột có trong database
        cursor.execute("""
            INSERT INTO sessions (user_id, date, duration_min, total_calories)
            VALUES (%s, %s, %s, %s)
        """, (user_id, session_date, duration_min, total_calories))
        
        conn.commit()
        session_id = cursor.lastrowid

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Tạo buổi tập thành công",
            "session_id": session_id
        }), 201
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== THÊM BÀI TẬP VÀO BUỔI NÂNG CAO =====================
@workout_bp.route("/workouts/session_details", methods=["POST"])
@jwt_required()
def add_session_detail():
    """
    Thêm bài tập vào buổi tập
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        
        session_id = data.get("session_id")
        exercise_id = data.get("exercise_id")
        sets = data.get("sets", 3)
        reps = data.get("reps", 12)
        duration_min = data.get("duration_min", 0)
        calories_burned = data.get("calories_burned", 0)

        if not session_id or not exercise_id:
            return jsonify({"error": "session_id và exercise_id là bắt buộc"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🛠️ KIỂM TRA QUYỀN SỞ HỮU SESSION
        cursor.execute("SELECT user_id FROM sessions WHERE session_id = %s", (session_id,))
        session = cursor.fetchone()
        
        if not session:
            return jsonify({"error": "Buổi tập không tồn tại"}), 404
        
        if session['user_id'] != user_id:
            return jsonify({"error": "Không có quyền thêm bài tập vào buổi tập này"}), 403

        # 🛠️ KIỂM TRA BÀI TẬP TỒN TẠI
        cursor.execute("SELECT name FROM exercises WHERE exercise_id = %s AND is_active = 1", (exercise_id,))
        exercise = cursor.fetchone()
        
        if not exercise:
            return jsonify({"error": "Bài tập không tồn tại"}), 404

        # 🛠️ SỬA: Chỉ insert các cột có trong database
        cursor.execute("""
            INSERT INTO session_details (session_id, exercise_id, sets, reps, duration_min, calories_burned)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (session_id, exercise_id, sets, reps, duration_min, calories_burned))

        # 🛠️ CẬP NHẬT TỔNG CALORIES CỦA SESSION
        cursor.execute("""
            UPDATE sessions 
            SET total_calories = (
                SELECT SUM(calories_burned) 
                FROM session_details 
                WHERE session_id = %s
            )
            WHERE session_id = %s
        """, (session_id, session_id))

        conn.commit()
        detail_id = cursor.lastrowid

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Đã thêm bài tập vào buổi tập",
            "detail_id": detail_id,
            "exercise_name": exercise['name']
        }), 201
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== LỊCH SỬ TẬP LUYỆN NÂNG CAO =====================
@workout_bp.route("/workouts/history", methods=["GET"])
@jwt_required()
def get_workout_history():
    """
    Lịch sử tập luyện
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🛠️ SỬA: Xóa các cột không tồn tại (session_name, notes, weight_kg, rest_seconds)
        cursor.execute("""
            SELECT s.session_id, s.date, s.duration_min, s.total_calories,
                   e.exercise_id, e.name AS exercise_name, e.body_part, e.video_path,
                   sd.sets, sd.reps, sd.duration_min AS exercise_duration, 
                   sd.calories_burned
            FROM sessions s
            LEFT JOIN session_details sd ON s.session_id = sd.session_id
            LEFT JOIN exercises e ON sd.exercise_id = e.exercise_id
            WHERE s.user_id = %s
            ORDER BY s.date DESC, s.session_id DESC
        """, (user_id,))
        rows = cursor.fetchall()

        cursor.close()
        conn.close()

        # 🛠️ SỬA: Gom nhóm theo session_id
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
                    "exercise_id": row["exercise_id"],
                    "name": row["exercise_name"],
                    "body_part": row["body_part"],
                    "video_path": row["video_path"],
                    "sets": row["sets"],
                    "reps": row["reps"],
                    "duration_min": row["exercise_duration"],
                    "calories_burned": row["calories_burned"]
                })

        return jsonify(list(history.values())), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== THỐNG KÊ TẬP LUYỆN =====================
@workout_bp.route("/workouts/analytics", methods=["GET"])
@jwt_required()
def get_workout_analytics():
    """
    Thống kê tập luyện nâng cao
    - Tổng số buổi tập
    - Tổng calories đốt cháy
    - Phân bổ theo nhóm cơ
    - Xu hướng tập luyện
    """
    try:
        user_id = int(get_jwt_identity())
        period = request.args.get('period', '30')  # 7, 30, 90 days

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🆕 TỔNG QUAN
        cursor.execute("""
            SELECT 
                COUNT(*) as total_sessions,
                SUM(duration_min) as total_duration_min,
                SUM(total_calories) as total_calories_burned,
                AVG(duration_min) as avg_duration_min,
                MAX(date) as last_session_date
            FROM sessions 
            WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
        """, (user_id, period))

        overview = cursor.fetchone()

        # 🆕 PHÂN BỔ THEO NHÓM CƠ
        cursor.execute("""
            SELECT e.body_part, COUNT(*) as exercise_count, SUM(sd.calories_burned) as total_calories
            FROM session_details sd
            JOIN exercises e ON sd.exercise_id = e.exercise_id
            JOIN sessions s ON sd.session_id = s.session_id
            WHERE s.user_id = %s AND s.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY e.body_part
            ORDER BY total_calories DESC
        """, (user_id, period))

        body_part_stats = cursor.fetchall()

        # 🆕 XU HƯỚNG TẬP LUYỆN
        cursor.execute("""
            SELECT DATE(date) as workout_date, COUNT(*) as session_count, 
                   SUM(total_calories) as daily_calories
            FROM sessions 
            WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY DATE(date)
            ORDER BY workout_date
        """, (user_id, period))

        workout_trends = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "analytics": {
                "period_days": period,
                "overview": overview,
                "body_part_distribution": body_part_stats,
                "workout_trends": workout_trends
            }
        }), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== XOÁ BUỔI TẬP AN TOÀN =====================
@workout_bp.route("/workouts/session/<int:session_id>", methods=["DELETE"])
@jwt_required()
def delete_session(session_id):
    """
    Xoá buổi tập an toàn với kiểm tra quyền sở hữu
    """
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🛠️ SỬA: Chỉ lấy các cột có trong database
        cursor.execute("""
            SELECT session_id, date 
            FROM sessions 
            WHERE session_id=%s AND user_id=%s
        """, (session_id, user_id))
        
        session = cursor.fetchone()
        
        if not session:
            return jsonify({"error": "Không tìm thấy buổi tập hoặc không có quyền xóa"}), 404

        # 🛠️ XÓA CHI TIẾT TRƯỚC, RỒI XÓA SESSION
        cursor.execute("DELETE FROM session_details WHERE session_id = %s", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE session_id = %s AND user_id = %s", (session_id, user_id))
        conn.commit()

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"Đã xóa buổi tập ngày {session['date']}",
            "session_id": session_id
        }), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== CẬP NHẬT BUỔI TẬP =====================
@workout_bp.route("/workouts/session/<int:session_id>", methods=["PUT"])
@jwt_required()
def update_session(session_id):
    """
    Cập nhật thông tin buổi tập
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 🛠️ KIỂM TRA QUYỀN SỞ HỮU
        cursor.execute("SELECT * FROM sessions WHERE session_id=%s AND user_id=%s", (session_id, user_id))
        if not cursor.fetchone():
            return jsonify({"error": "Không tìm thấy buổi tập"}), 404

        # 🛠️ SỬA: Chỉ cập nhật các cột có trong database
        update_fields = []
        update_values = []
        
        updatable_fields = ['date', 'duration_min', 'total_calories']  # 🛠️ Xóa session_name, notes
        
        for field in updatable_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                update_values.append(data[field])
        
        if update_fields:
            update_values.extend([session_id, user_id])
            
            update_query = f"UPDATE sessions SET {', '.join(update_fields)} WHERE session_id = %s AND user_id = %s"
            cursor.execute(update_query, tuple(update_values))
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": "Cập nhật buổi tập thành công", "session_id": session_id}), 200
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500