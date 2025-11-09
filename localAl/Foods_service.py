from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, date
import logging

Foods_bp = Blueprint("foods", __name__)

# ===================== LẤY DANH SÁCH THỰC PHẨM NÂNG CAO =====================
@Foods_bp.route("/foods", methods=["GET"])
@jwt_required(optional=True)
def get_foods():
    """
    Lấy danh sách thực phẩm với filter nâng cao
    - Filter theo goal, category, calories range
    - Tìm kiếm theo tên
    - Phân trang
    """
    try:
        # 🆕 THAM SỐ FILTER NÂNG CAO
        goal = request.args.get("goal")
        category = request.args.get("category")
        keyword = request.args.get("q")
        min_calories = request.args.get("min_calories", type=float)
        max_calories = request.args.get("max_calories", type=float)
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 20, type=int)
        
        offset = (page - 1) * limit

        query = """
            SELECT food_id, name, calories, protein, carbs, fat, goal, category
            FROM foods
            WHERE 1=1
        """
        params = []

        # 🆕 FILTER NÂNG CAO
        if goal:
            query += " AND goal LIKE %s"
            params.append(f"%{goal}%")
        if category:
            query += " AND category = %s"
            params.append(category)
        if keyword:
            query += " AND name LIKE %s"
            params.append(f"%{keyword}%")
        if min_calories is not None:
            query += " AND calories >= %s"
            params.append(min_calories)
        if max_calories is not None:
            query += " AND calories <= %s"
            params.append(max_calories)

        # 🆕 PHÂN TRANG
        query += " ORDER BY name LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        foods = cursor.fetchall()

        # 🆕 ĐẾM TỔNG SỐ THỰC PHẨM
        count_query = "SELECT COUNT(*) as total FROM foods WHERE 1=1"
        count_params = []
        
        if goal:
            count_query += " AND goal LIKE %s"
            count_params.append(f"%{goal}%")
        if category:
            count_query += " AND category = %s"
            count_params.append(category)
        if keyword:
            count_query += " AND name LIKE %s"
            count_params.append(f"%{keyword}%")
        if min_calories is not None:
            count_query += " AND calories >= %s"
            count_params.append(min_calories)
        if max_calories is not None:
            count_query += " AND calories <= %s"
            count_params.append(max_calories)

        cursor.execute(count_query, tuple(count_params))
        total_count = cursor.fetchone()['total']

        cursor.close()
        conn.close()

        if not foods:
            return jsonify({"message": "Không tìm thấy thực phẩm phù hợp"}), 404

        return jsonify({
            "count": len(foods),
            "total": total_count,
            "page": page,
            "limit": limit,
            "foods": foods
        }), 200

    except Exception as e:
        logging.error(f"Lỗi get_foods: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== LẤY CHI TIẾT THỰC PHẨM =====================
@Foods_bp.route("/foods/<int:food_id>", methods=["GET"])
@jwt_required(optional=True)
def get_food_detail(food_id):
    """
    Lấy chi tiết thực phẩm cụ thể
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT food_id, name, calories, protein, carbs, fat, goal, category
            FROM foods
            WHERE food_id = %s
        """, (food_id,))
        
        food = cursor.fetchone()

        if not food:
            return jsonify({"error": "Thực phẩm không tồn tại"}), 404

        cursor.close()
        conn.close()

        return jsonify({"food": food}), 200
    except Exception as e:
        logging.error(f"Lỗi get_food_detail: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== TÌM KIẾM THỰC PHẨM NÂNG CAO =====================
@Foods_bp.route("/foods/search", methods=["GET"])
@jwt_required(optional=True)
def search_foods():
    """
    Tìm kiếm thực phẩm nâng cao với phân trang
    """
    try:
        keyword = request.args.get("q")
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        
        if not keyword:
            return jsonify({"error": "Thiếu từ khóa tìm kiếm"}), 400
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT food_id, name, calories, protein, carbs, fat, goal, category
            FROM foods 
            WHERE name LIKE %s 
            LIMIT %s OFFSET %s
        """, (f"%{keyword}%", limit, offset))
        
        foods = cursor.fetchall()
        
        # Đếm tổng số kết quả
        cursor.execute("SELECT COUNT(*) as total FROM foods WHERE name LIKE %s", (f"%{keyword}%",))
        total_count = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()

        if not foods:
            return jsonify({"message": "Không tìm thấy thực phẩm phù hợp"}), 404
        
        return jsonify({
            "count": len(foods),
            "total": total_count,
            "page": page,
            "limit": limit,
            "foods": foods
        }), 200
    except Exception as e:
        logging.error(f"Lỗi search_foods: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== TẠO BỮA ĂN THÔNG MINH =====================
@Foods_bp.route("/meals", methods=["POST"])
@jwt_required()
def create_meal():
    """
    Tạo bữa ăn với tính năng thông minh
    - Validation dữ liệu
    - Tính toán calories tự động
    - Kiểm tra tồn tại thực phẩm
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        meal_type = data.get("meal_type", "other")
        meal_date = data.get("date")
        foods = data.get("foods", [])

        # 🆕 VALIDATION DỮ LIỆU
        if not meal_date:
            return jsonify({"error": "Ngày ăn là bắt buộc"}), 400
        
        if not foods:
            return jsonify({"error": "Danh sách thực phẩm không được để trống"}), 400

        # 🆕 VALIDATION NGÀY
        try:
            datetime.strptime(meal_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Định dạng ngày không hợp lệ (YYYY-MM-DD)"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        total_calories = 0
        meal_details = []

        # 🆕 TẠO BỮA ĂN
        cursor.execute("""
            INSERT INTO meals (user_id, date, meal_type, total_calories)
            VALUES (%s, %s, %s, %s)
        """, (user_id, meal_date, meal_type, 0))
        meal_id = cursor.lastrowid

        # 🆕 THÊM CHI TIẾT BỮA ĂN
        for food_item in foods:
            food_id = food_item.get("food_id")
            quantity = float(food_item.get("quantity", 1))
            
            if not food_id:
                continue

            # 🆕 KIỂM TRA THỰC PHẨM TỒN TẠI
            cursor.execute("SELECT name, calories FROM foods WHERE food_id = %s", (food_id,))
            food = cursor.fetchone()
            
            if not food:
                continue

            # 🆕 TÍNH CALORIES
            calories = float(food['calories']) * quantity
            total_calories += calories

            cursor.execute("""
                INSERT INTO meal_details (meal_id, food_id, quantity, calories)
                VALUES (%s, %s, %s, %s)
            """, (meal_id, food_id, quantity, calories))
            
            meal_details.append({
                "food_name": food['name'],
                "quantity": quantity,
                "calories": calories
            })

        # 🆕 CẬP NHẬT TỔNG CALORIES
        cursor.execute("UPDATE meals SET total_calories = %s WHERE meal_id = %s", 
                      (total_calories, meal_id))
        
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Tạo bữa ăn thành công",
            "meal_id": meal_id,
            "total_calories": total_calories,
            "meal_details": meal_details
        }), 201

    except Exception as e:
        logging.error(f"Lỗi create_meal: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== TẠO BỮA ĂN BẰNG TÊN THÔNG MINH =====================
@Foods_bp.route("/meals/add_by_name", methods=["POST"])
@jwt_required()
def add_meal_by_name():
    """
    Tạo bữa ăn bằng tên thực phẩm với xử lý thông minh
    - Tìm kiếm fuzzy match
    - Xử lý không tìm thấy thực phẩm
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())
        meal_date = data.get("date")
        meal_type = data.get("meal_type", "other")
        items = data.get("items", [])

        if not meal_date or not items:
            return jsonify({"error": "Ngày ăn và danh sách thực phẩm là bắt buộc"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        total_calories = 0
        found_items = []
        not_found_items = []

        # 🆕 TẠO BỮA ĂN
        cursor.execute("""
            INSERT INTO meals (user_id, date, meal_type, total_calories)
            VALUES (%s, %s, %s, %s)
        """, (user_id, meal_date, meal_type, 0))
        meal_id = cursor.lastrowid

        # 🆕 XỬ LÝ TỪNG MÓN ĂN
        for item in items:
            food_name = item.get('name', '').strip()
            quantity = float(item.get("quantity", 1))
            
            if not food_name:
                continue

            # 🆕 TÌM KIẾM THỰC PHẨM (fuzzy match)
            cursor.execute("""
                SELECT food_id, name, calories 
                FROM foods 
                WHERE name LIKE %s 
                LIMIT 1
            """, (f"%{food_name}%",))
            
            food = cursor.fetchone()

            if food:
                # 🆕 TÍNH CALORIES VÀ THÊM VÀO DB
                calories = float(food['calories']) * quantity
                total_calories += calories
                
                cursor.execute("""
                    INSERT INTO meal_details (meal_id, food_id, quantity, calories)
                    VALUES (%s, %s, %s, %s)
                """, (meal_id, food['food_id'], quantity, calories))
                
                found_items.append({
                    "name": food['name'],
                    "quantity": quantity,
                    "calories": calories
                })
            else:
                not_found_items.append(food_name)

        # 🆕 CẬP NHẬT TỔNG CALORIES
        cursor.execute("UPDATE meals SET total_calories = %s WHERE meal_id = %s", 
                      (total_calories, meal_id))
        
        conn.commit()
        cursor.close()
        conn.close()

        response_data = {
            "message": "Tạo bữa ăn thành công",
            "meal_id": meal_id,
            "total_calories": total_calories,
            "found_items": found_items
        }
        
        if not_found_items:
            response_data["not_found_items"] = not_found_items
            response_data["warning"] = f"Không tìm thấy {len(not_found_items)} món"

        return jsonify(response_data), 201

    except Exception as e:
        logging.error(f"Lỗi add_meal_by_name: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== GỢI Ý BỮA ĂN THÔNG MINH =====================
@Foods_bp.route("/meals/suggest", methods=["GET"])
@jwt_required(optional=True)
def suggest_meals():
    """
    Gợi ý bữa ăn thông minh theo mục tiêu
    - Phân loại theo category
    - Giới hạn calories
    """
    try:
        goal = request.args.get("goal", "tăng cơ")
        max_calories = request.args.get("max_calories", 500, type=float)
        limit = request.args.get("limit", 8, type=int)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT name, calories, protein, carbs, fat, category, goal
            FROM foods 
            WHERE goal LIKE %s AND calories <= %s
            ORDER BY protein DESC, calories ASC
            LIMIT %s
        """, (f"%{goal}%", max_calories, limit))
        
        foods = cursor.fetchall()
        cursor.close()
        conn.close()

        # 🆕 PHÂN NHÓM THEO CATEGORY
        categorized_foods = {}
        for food in foods:
            category = food['category']
            if category not in categorized_foods:
                categorized_foods[category] = []
            categorized_foods[category].append(food)

        return jsonify({
            "goal": goal,
            "max_calories": max_calories,
            "total_suggestions": len(foods),
            "categorized_foods": categorized_foods
        }), 200
    except Exception as e:
        logging.error(f"Lỗi suggest_meals: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== LỊCH SỬ ĂN UỐNG NÂNG CAO =====================
@Foods_bp.route("/meals/history", methods=["GET"])
@jwt_required()
def get_meal_history():
    """
    Lịch sử ăn uống nâng cao với phân trang và filter
    - Filter theo ngày, loại bữa ăn
    - Thống kê calories
    """
    try:
        user_id = int(get_jwt_identity())
        meal_date = request.args.get("date")
        meal_type = request.args.get("meal_type")
        page = request.args.get("page", 1, type=int)
        limit = request.args.get("limit", 10, type=int)
        
        offset = (page - 1) * limit

        query = """
            SELECT m.meal_id, m.date, m.meal_type, m.total_calories,
                   f.name AS food_name, md.quantity, md.calories AS food_calories,
                   f.protein, f.carbs, f.fat
            FROM meals m
            LEFT JOIN meal_details md ON m.meal_id = md.meal_id
            LEFT JOIN foods f ON md.food_id = f.food_id
            WHERE m.user_id = %s
        """
        params = [user_id]

        if meal_date:
            query += " AND DATE(m.date) = %s"
            params.append(meal_date)

        if meal_type:
            query += " AND m.meal_type = %s"
            params.append(meal_type)

        query += " ORDER BY m.date DESC, m.meal_id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        # 🆕 THỐNG KÊ TỔNG QUAN
        stats_query = """
            SELECT 
                COUNT(*) as total_meals,
                SUM(total_calories) as total_calories,
                AVG(total_calories) as avg_calories_per_meal
            FROM meals 
            WHERE user_id = %s
        """
        stats_params = [user_id]
        
        if meal_date:
            stats_query += " AND DATE(date) = %s"
            stats_params.append(meal_date)
        if meal_type:
            stats_query += " AND meal_type = %s"
            stats_params.append(meal_type)
            
        cursor.execute(stats_query, tuple(stats_params))
        stats = cursor.fetchone()

        cursor.close()
        conn.close()

        # 🆕 GOM NHÓM THEO BỮA ĂN
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
                    "calories": row["food_calories"],
                    "protein": row["protein"],
                    "carbs": row["carbs"],
                    "fat": row["fat"]
                })

        return jsonify({
            "meals": list(history.values()),
            "stats": stats,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_meals": stats["total_meals"] if stats else 0
            }
        }), 200
    except Exception as e:
        logging.error(f"Lỗi get_meal_history: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== XOÁ BỮA ĂN AN TOÀN =====================
@Foods_bp.route("/meals/<int:meal_id>", methods=["DELETE"])
@jwt_required()
def delete_meal(meal_id):
    """
    Xoá bữa ăn an toàn với kiểm tra quyền sở hữu
    """
    try:
        user_id = int(get_jwt_identity())
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 KIỂM TRA QUYỀN SỞ HỮU
        cursor.execute("""
            SELECT meal_id, date, meal_type 
            FROM meals 
            WHERE meal_id=%s AND user_id=%s
        """, (meal_id, user_id))
        
        meal = cursor.fetchone()
        
        if not meal:
            return jsonify({"error": "Không tìm thấy bữa ăn hoặc không có quyền xóa"}), 404

        # 🆕 XÓA CHI TIẾT TRƯỚC, RỒI XÓA BỮA ĂN
        cursor.execute("DELETE FROM meal_details WHERE meal_id=%s", (meal_id,))
        cursor.execute("DELETE FROM meals WHERE meal_id=%s AND user_id=%s", (meal_id, user_id))
        conn.commit()

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"Đã xóa bữa ăn {meal['meal_type']} ngày {meal['date']}",
            "meal_id": meal_id
        }), 200
    except Exception as e:
        logging.error(f"Lỗi delete_meal: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== THỐNG KÊ DINH DƯỠNG =====================
@Foods_bp.route("/meals/nutrition_stats", methods=["GET"])
@jwt_required()
def get_nutrition_stats():
    """
    Thống kê dinh dưỡng theo khoảng thời gian
    """
    try:
        user_id = int(get_jwt_identity())
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date", date.today().isoformat())
        
        if not start_date:
            return jsonify({"error": "Thiếu ngày bắt đầu"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT 
                DATE(m.date) as date,
                SUM(m.total_calories) as daily_calories,
                SUM(md.quantity * f.protein) as total_protein,
                SUM(md.quantity * f.carbs) as total_carbs,
                SUM(md.quantity * f.fat) as total_fat,
                COUNT(DISTINCT m.meal_id) as meal_count
            FROM meals m
            JOIN meal_details md ON m.meal_id = md.meal_id
            JOIN foods f ON md.food_id = f.food_id
            WHERE m.user_id = %s AND m.date BETWEEN %s AND %s
            GROUP BY DATE(m.date)
            ORDER BY date
        """, (user_id, start_date, end_date))
        
        daily_stats = cursor.fetchall()
        
        cursor.close()
        conn.close()

        return jsonify({
            "period": f"{start_date} to {end_date}",
            "daily_stats": daily_stats,
            "total_days": len(daily_stats)
        }), 200
    except Exception as e:
        logging.error(f"Lỗi get_nutrition_stats: {str(e)}")
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== HEALTH CHECK =====================
@Foods_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Foods_service',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })