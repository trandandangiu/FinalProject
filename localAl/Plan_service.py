from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime

plan_bp = Blueprint("plan", __name__)

# ==========================================================
# 🟢 1. TẠO KẾ HOẠCH MỚI
# ==========================================================
@plan_bp.route("/plans", methods=["POST"])
@jwt_required()
def create_plan():
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        plan_name = data.get("plan_name")
        plan_type = data.get("plan_type", "weekly")
        goal = data.get("goal", "tăng cơ")
        rec_type = data.get("rec_type", "manual")
        content = data.get("content", "")

        if not plan_name:
            return jsonify({"error": "plan_name is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO plans (user_id, plan_name, rec_type, content, plan_type, goal, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, plan_name, rec_type, content, plan_type, goal))
        conn.commit()
        plan_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return jsonify({"msg": "✅ Plan created successfully", "plan_id": plan_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 🟡 2. THÊM CHI TIẾT (BÀI TẬP / BỮA ĂN) VÀO KẾ HOẠCH
# ==========================================================
@plan_bp.route("/plans/details", methods=["POST"])
@jwt_required()
def add_plan_detail():
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        plan_id = data.get("plan_id")
        day_of_week = data.get("day_of_week")
        workout_id = data.get("workout_id")
        meal_id = data.get("meal_id")
        notes = data.get("notes", "")

        if not plan_id or not day_of_week:
            return jsonify({"error": "plan_id and day_of_week are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO plan_details (plan_id, user_id, day_of_week, workout_id, meal_id, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (plan_id, user_id, day_of_week, workout_id, meal_id, notes))
        conn.commit()
        detail_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return jsonify({"msg": "✅ Added to plan successfully", "detail_id": detail_id}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 🔵 3. CẬP NHẬT TRẠNG THÁI HOÀN THÀNH (Tick ✔️)
# ==========================================================
@plan_bp.route("/plans/details/<int:detail_id>", methods=["PUT"])
@jwt_required()
def update_completion(detail_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        is_completed = data.get("is_completed", True)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE plan_details 
            SET is_completed = %s
            WHERE detail_id = %s AND user_id = %s
        """, (is_completed, detail_id, user_id))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Plan detail not found or not authorized"}), 404

        cursor.close()
        conn.close()

        return jsonify({"msg": "✅ Plan detail updated"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 🟣 4. LẤY DANH SÁCH KẾ HOẠCH CỦA USER
# ==========================================================
@plan_bp.route("/plans/user", methods=["GET"])
@jwt_required()
def get_user_plans():
    try:
        user_id = int(get_jwt_identity())

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.plan_id, p.plan_name, p.goal, p.created_at, 
                   COUNT(pd.detail_id) AS total_items,
                   SUM(CASE WHEN pd.is_completed = 1 THEN 1 ELSE 0 END) AS completed_items
            FROM plans p
            LEFT JOIN plan_details pd ON p.plan_id = pd.plan_id
            WHERE p.user_id = %s
            GROUP BY p.plan_id
            ORDER BY p.created_at DESC
        """, (user_id,))
        plans = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify(plans), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 🔴 5. XEM CHI TIẾT KẾ HOẠCH (TỪNG NGÀY)
# ==========================================================
@plan_bp.route("/plans/<int:plan_id>/details", methods=["GET"])
@jwt_required()
def get_plan_details(plan_id):
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT pd.detail_id, pd.day_of_week, pd.is_completed, pd.notes,
                   e.name AS workout_name,
                   f.name AS meal_name
            FROM plan_details pd
            LEFT JOIN exercises e ON pd.workout_id = e.exercise_id
            LEFT JOIN meals m ON pd.meal_id = m.meal_id
            LEFT JOIN foods f ON m.meal_id = f.food_id
            WHERE pd.plan_id = %s AND pd.user_id = %s
            ORDER BY FIELD(pd.day_of_week, 'Mon','Tue','Wed','Thu','Fri','Sat','Sun')
        """, (plan_id, user_id))
        details = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify(details), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
