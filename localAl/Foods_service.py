from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection

Foods_bp = Blueprint("foods", __name__)

# ===================== LẤY DANH SÁCH THỰC PHẨM =====================
@Foods_bp.route("/foods", methods=["GET"])
@jwt_required(optional=True)
def get_foods():
    try:
        goal = request.args.get("goal")
        keyword = request.args.get("q")
        limit = request.args.get("limit", 50, type=int)

        query = "SELECT * FROM foods WHERE 1=1"
        params = []

        if goal:
            query += " AND goal LIKE %s"
            params.append(f"%{goal}%")
        if keyword:
            query += " AND name LIKE %s"
            params.append(f"%{keyword}%")
        
        query += " LIMIT %s"
        params.append(limit)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        foods = cursor.fetchall()
        cursor.close()
        conn.close()

        if not foods:
            return jsonify({"message": "No foods found matching criteria"}), 404
        
        return jsonify({"count": len(foods), "foods": foods}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== TÌM THỰC PHẨM (SEARCH) =====================
@Foods_bp.route("/foods/search", methods=["GET"])
@jwt_required(optional=True)
def search_foods():
    try:
        keyword = request.args.get("q")
        if not keyword:
            return jsonify({"msg": "q is required"}), 400
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM foods WHERE name LIKE %s LIMIT 10", (f"%{keyword}%",))
        foods = cursor.fetchall()
        cursor.close()
        conn.close()

        if not foods:
            return jsonify({"message": "No foods found matching the search criteria"}), 404
        
        return jsonify({"count": len(foods), "foods": foods}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== TẠO BỮA ĂN =====================
@Foods_bp.route("/meals", methods=["POST"])
@jwt_required()
def create_meal():
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        meal_type = data.get("meal_type", "other")
        date = data.get("date")
        foods = data.get("foods", [])

        if not date or not foods:
            return jsonify({"msg": "Date và foods là bắt buộc"}), 400

        conn = get_db_connection(); cursor = conn.cursor()
        total_calories = 0

        cursor.execute("""
            INSERT INTO meals (user_id, date, meal_type, total_calories)
            VALUES (%s, %s, %s, %s)
        """, (user_id, date, meal_type, 0))
        meal_id = cursor.lastrowid

        for f in foods:
            cursor.execute("SELECT calories FROM foods WHERE food_id=%s", (f["food_id"],))
            food = cursor.fetchone()
            if food:
                calories = float(food[0]) * float(f.get("quantity", 1))
                total_calories += calories
                cursor.execute("""
                    INSERT INTO meal_details (meal_id, food_id, quantity, calories)
                    VALUES (%s, %s, %s, %s)
                """, (meal_id, f["food_id"], f.get("quantity", 1), calories))

        cursor.execute("UPDATE meals SET total_calories=%s WHERE meal_id=%s", (total_calories, meal_id))
        conn.commit(); cursor.close(); conn.close()

        return jsonify({"msg": "Meal created", "meal_id": meal_id, "total_calories": total_calories}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== TẠO BỮA ĂN BẰNG TÊN =====================
@Foods_bp.route("/meals/add_by_name", methods=["POST"])
@jwt_required()
def add_meal_by_name():
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        date = data.get("date")
        meal_type = data.get("meal_type", "other")
        items = data.get("items", [])  # [{"name": "Gạo trắng", "quantity": 2}]

        if not date or not items:
            return jsonify({"msg": "Date và items là bắt buộc"}), 400

        conn = get_db_connection(); cursor = conn.cursor()
        total_calories = 0
        cursor.execute("INSERT INTO meals (user_id, date, meal_type, total_calories) VALUES (%s,%s,%s,%s)",
                       (user_id, date, meal_type, 0))
        meal_id = cursor.lastrowid

        for item in items:
            cursor.execute("SELECT food_id, calories FROM foods WHERE name LIKE %s LIMIT 1", (f"%{item['name']}%",))
            food = cursor.fetchone()
            if food:
                food_id, cal = food
                calories = float(cal) * float(item.get("quantity", 1))
                total_calories += calories
                cursor.execute("""
                    INSERT INTO meal_details (meal_id, food_id, quantity, calories)
                    VALUES (%s, %s, %s, %s)
                """, (meal_id, food_id, item.get("quantity", 1), calories))

        cursor.execute("UPDATE meals SET total_calories=%s WHERE meal_id=%s", (total_calories, meal_id))
        conn.commit(); cursor.close(); conn.close()

        return jsonify({"msg": "Meal created", "meal_id": meal_id, "total_calories": total_calories}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== GỢI Ý BỮA ĂN THEO GOAL =====================
@Foods_bp.route("/meals/suggest", methods=["GET"])
@jwt_required(optional=True)
def suggest_meals():
    try:
        goal = request.args.get("goal", "tăng cơ")
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name, calories, protein, carbs, fat FROM foods WHERE goal LIKE %s LIMIT 5", (f"%{goal}%",))
        foods = cursor.fetchall()
        cursor.close(); conn.close()
        return jsonify({"goal": goal, "foods": foods}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== XOÁ BỮA ĂN =====================
@Foods_bp.route("/meals/<int:meal_id>", methods=["DELETE"])
@jwt_required()
def delete_meal(meal_id):
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT * FROM meals WHERE meal_id=%s AND user_id=%s", (meal_id, user_id))
        if not cursor.fetchone():
            return jsonify({"error": "Meal not found or not owned by user"}), 404
        cursor.execute("DELETE FROM meal_details WHERE meal_id=%s", (meal_id,))
        cursor.execute("DELETE FROM meals WHERE meal_id=%s AND user_id=%s", (meal_id, user_id))
        conn.commit(); cursor.close(); conn.close()
        return jsonify({"msg": f"Meal {meal_id} deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===================== LỊCH SỬ ĂN UỐNG =====================
@Foods_bp.route("/meals/history", methods=["GET"])
@jwt_required()
def get_meal_history():
    try:
        user_id = int(get_jwt_identity())
        date = request.args.get("date")         # ⚡ filter theo ngày (YYYY-MM-DD)
        meal_type = request.args.get("meal_type")  # ⚡ filter theo bữa (breakfast, lunch, dinner)

        query = """
            SELECT m.meal_id, m.date, m.meal_type, m.total_calories,
                   f.name AS food_name, md.quantity, md.calories
            FROM meals m
            LEFT JOIN meal_details md ON m.meal_id = md.meal_id
            LEFT JOIN foods f ON md.food_id = f.food_id
            WHERE m.user_id = %s
        """
        params = [user_id]

        if date:
            query += " AND DATE(m.date) = %s"
            params.append(date)

        if meal_type:
            query += " AND m.meal_type = %s"
            params.append(meal_type)

        query += " ORDER BY m.date DESC, m.meal_id DESC"

        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        cursor.close(); conn.close()

        history = {}
        for row in rows:
            mid = row["meal_id"]
            if mid not in history:
                history[mid] = {
                    "meal_id": mid,
                    "date": row["date"],
                    "meal_type": row["meal_type"],
                    "total_calories": row["total_calories"],
                    "foods": []
                }
            if row["food_name"]:
                history[mid]["foods"].append({
                    "name": row["food_name"],
                    "quantity": row["quantity"],
                    "calories": row["calories"]
                })

        return jsonify(list(history.values())), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    # Thêm vào mỗi service file
from flask import Flask, jsonify
import datetime

app = Flask(__name__)

@app.route('/health', methods=['GET', 'POST'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Foods_service',  # Thay tên tương ứng
        'timestamp': datetime.datetime.now().isoformat(),
        'version': '1.0.0'
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({'message': 'Service is running!'})
