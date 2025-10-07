from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
import datetime

progress_bp = Blueprint("progress", __name__)

# ===================== API ĐỂ THÊM TIẾN TRÌNH =====================
@progress_bp.route("/progress", methods=["POST"])
@jwt_required()
def add_progress():
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())

        # Lấy weight và height từ bảng profile
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT weight, height FROM profiles WHERE user_id = %s", (user_id,))
        profile_data = cursor.fetchone()
        
        if not profile_data:
            return jsonify({"msg": "Profile not found for user"}), 404
        
        weight = profile_data["weight"]
        height = profile_data["height"]

        body_fat_pct = data.get("body_fat_pct")
        notes = data.get("notes")
        calories_in = data.get("calories_in")
        calories_out = data.get("calories_out")

        if not weight or not height:
            return jsonify({"msg": "Weight and height are required in profile"}), 400

        # Tính BMI
        bmi = weight / ((height / 100) ** 2)  # Công thức tính BMI

        # Thêm tiến trình vào bảng progress
        cursor.execute("""
            INSERT INTO progress (user_id, weight, body_fat_pct, notes, calories_in, calories_out, bmi, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, weight, body_fat_pct, notes, calories_in, calories_out, bmi))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"msg": "Progress added successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===================== API LẤY TIẾN TRÌNH CỦA NGƯỜI DÙNG =====================
@progress_bp.route("/progress", methods=["GET"])
@jwt_required()
def get_progress():
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Lấy tất cả tiến trình của người dùng từ bảng progress
        cursor.execute("SELECT * FROM progress WHERE user_id = %s ORDER BY date DESC", (user_id,))
        progress_data = cursor.fetchall()
        
        cursor.close()
        conn.close()

        if not progress_data:
            return jsonify({"msg": "No progress data found"}), 404

        return jsonify({"progress": progress_data}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ===================== API CẬP NHẬT TIẾN TRÌNH =====================
@progress_bp.route("/progress/<int:log_id>", methods=["PUT"])
@jwt_required()
def update_progress(log_id):
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())

        # Lấy weight và height từ bảng profile
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT weight, height FROM profiles WHERE user_id = %s", (user_id,))
        profile_data = cursor.fetchone()
        
        if not profile_data:
            return jsonify({"msg": "Profile not found for user"}), 404
        
        weight = profile_data["weight"]
        height = profile_data["height"]

        body_fat_pct = data.get("body_fat_pct")
        notes = data.get("notes")
        calories_in = data.get("calories_in")
        calories_out = data.get("calories_out")

        if not weight or not height:
            return jsonify({"msg": "Weight and height are required in profile"}), 400

        # Tính lại BMI
        bmi = weight / ((height / 100) ** 2)

        # Cập nhật tiến trình của người dùng
        cursor.execute("""
            UPDATE progress SET weight = %s, body_fat_pct = %s, notes = %s, 
            calories_in = %s, calories_out = %s, bmi = %s
            WHERE log_id = %s AND user_id = %s
        """, (weight, body_fat_pct, notes, calories_in, calories_out, bmi, log_id, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"msg": "Progress updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===================== API XÓA TIẾN TRÌNH =====================
@progress_bp.route("/progress/<int:log_id>", methods=["DELETE"])
@jwt_required()
def delete_progress(log_id):
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor()

        # Xóa tiến trình của người dùng
        cursor.execute("DELETE FROM progress WHERE log_id = %s AND user_id = %s", (log_id, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"msg": f"Progress {log_id} deleted successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

