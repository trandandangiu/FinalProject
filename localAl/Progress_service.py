from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, timedelta
import json
from decimal import Decimal

progress_bp = Blueprint("progress", __name__)

# ===================== HÀM HỖ TRỢ ĐẦU TIÊN =====================

def safe_float(value, default=0.0):
    """Chuyển đổi an toàn sang float"""
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value, default=0):
    """Chuyển đổi an toàn sang int"""
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            return int(value)
        return int(value)
    except (TypeError, ValueError):
        return default

def calculate_age(birth_date):
    """Tính tuổi từ ngày sinh"""
    if not birth_date:
        return 30
    today = datetime.now().date()
    
    # Chuyển đổi kiểu dữ liệu an toàn
    if isinstance(birth_date, str):
        birth_date = datetime.strptime(birth_date, '%Y-%m-%d').date()
    elif isinstance(birth_date, datetime):
        birth_date = birth_date.date()
    elif hasattr(birth_date, 'year'):  # Cho datetime, date objects
        birth_date = birth_date.date() if hasattr(birth_date, 'date') else birth_date
    else:
        return 30
    
    age = today.year - birth_date.year
    # Check if birthday hasn't occurred this year
    if today.month < birth_date.month or (today.month == birth_date.month and today.day < birth_date.day):
        age -= 1
    return age

def get_bmi_category(bmi):
    """Phân loại BMI"""
    bmi_float = safe_float(bmi)
    if bmi_float < 18.5:
        return "Thiếu cân"
    elif 18.5 <= bmi_float < 23:
        return "Bình thường"
    elif 23 <= bmi_float < 25:
        return "Tiền béo phì"
    elif 25 <= bmi_float < 30:
        return "Béo phì độ I"
    else:
        return "Béo phì độ II"

def get_current_status(progress):
    """Lấy trạng thái hiện tại từ tiến trình"""
    if not progress:
        return {}
    
    return {
        "current_weight": safe_float(progress['weight']),
        "current_bmi": safe_float(progress['bmi']),
        "bmi_category": progress['bmi_category'],
        "bmr": safe_float(progress['bmr']),
        "tdee": safe_float(progress['tdee'])
    }

def generate_progress_insights(cursor, user_id, current_weight, current_bmi, calorie_balance):
    """Tạo insights thông minh từ dữ liệu tiến trình"""
    insights = []
    
    # So sánh với tiến trình trước
    cursor.execute("""
        SELECT weight, bmi, date FROM progress 
        WHERE user_id = %s AND date < NOW() 
        ORDER BY date DESC LIMIT 1
    """, (user_id,))
    
    previous = cursor.fetchone()
    
    if previous:
        weight_change = current_weight - safe_float(previous['weight'])
        bmi_change = current_bmi - safe_float(previous['bmi'])
        
        if weight_change < -1:
            insights.append("🎉 Bạn đang giảm cân tốt! Tiếp tục phát huy.")
        elif weight_change > 1:
            insights.append("💪 Cân nặng đang tăng, hãy kiểm tra lại chế độ ăn và tập luyện.")
        
        if calorie_balance > 500:
            insights.append("⚡ Lượng calorie nạp vào cao, cân nhắc điều chỉnh chế độ ăn.")
        elif calorie_balance < -500:
            insights.append("🔋 Calorie tiêu thụ cao, đảm bảo nạp đủ năng lượng.")
    
    # Insights dựa trên BMI
    bmi_category = get_bmi_category(current_bmi)
    if bmi_category == "Thiếu cân":
        insights.append("📈 BMI ở mức thiếu cân, nên tăng cường dinh dưỡng.")
    elif bmi_category in ["Béo phì độ I", "Béo phì độ II"]:
        insights.append("🏃 BMI ở mức béo phì, nên tập trung vào tập luyện và ăn uống lành mạnh.")
    
    return insights

# ===================== 1️⃣ THÊM TIẾN TRÌNH THÔNG MINH =====================
@progress_bp.route("/progress", methods=["POST"])
@jwt_required()
def add_progress():
    """
    Thêm tiến trình mới với tính năng thông minh
    - Tự động tính toán BMI, BMR, TDEE
    - Phân tích xu hướng
    - Tạo insights tự động
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())

        # 🆕 Lấy thông tin user profile nâng cao
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.weight, p.height, p.date_of_birth, p.gender, 
                   up.activity_level, up.diet_type
            FROM profiles p 
            LEFT JOIN user_preferences up ON p.user_id = up.user_id
            WHERE p.user_id = %s
        """, (user_id,))
        profile_data = cursor.fetchone()
        
        if not profile_data:
            return jsonify({"error": "Không tìm thấy thông tin hồ sơ người dùng"}), 404
        
        # 🛠️ SỬA: Sử dụng safe_float cho tất cả các giá trị số
        weight = safe_float(data.get("weight", profile_data["weight"] or 70))
        height = safe_float(profile_data["height"] or 170)
        body_fat_pct = safe_float(data.get("body_fat_pct"))
        muscle_mass = safe_float(data.get("muscle_mass"))
        notes = data.get("notes")
        calories_in = safe_int(data.get("calories_in"))
        calories_out = safe_int(data.get("calories_out"))
        water_intake = safe_int(data.get("water_intake"))
        sleep_quality = safe_int(data.get("sleep_quality"))
        mood = safe_int(data.get("mood"))

        if not weight:
            return jsonify({"error": "Cần có cân nặng"}), 400

        # 🆕 TÍNH TOÁN NÂNG CAO
        # BMI
        bmi = round(weight / ((height / 100) ** 2), 1)
        
        # 🆕 BMR (Basal Metabolic Rate)
        age = calculate_age(profile_data["date_of_birth"]) if profile_data["date_of_birth"] else 30
        age_int = safe_int(age)
        
        if profile_data["gender"] == 'male':
            bmr = round(10 * weight + 6.25 * height - 5 * age_int + 5, 1)
        else:
            bmr = round(10 * weight + 6.25 * height - 5 * age_int - 161, 1)
        
        # 🆕 TDEE (Total Daily Energy Expenditure)
        activity_multipliers = {
            'sedentary': 1.2,
            'light': 1.375,
            'moderate': 1.55,
            'active': 1.725,
            'very_active': 1.9
        }
        activity_level = profile_data.get("activity_level", "moderate")
        tdee = round(bmr * activity_multipliers.get(activity_level, 1.55), 1)
        
        # 🆕 CALORIE BALANCE
        calorie_balance = calories_in - calories_out if calories_in is not None and calories_out is not None else 0
        
        # 🆕 PHÂN LOẠI BMI
        bmi_category = get_bmi_category(bmi)

        # 🆕 THÊM TIẾN TRÌNH VỚI DỮ LIỆU NÂNG CAO
        cursor.execute("""
            INSERT INTO progress (
                user_id, weight, height, body_fat_pct, muscle_mass, notes, 
                calories_in, calories_out, water_intake, sleep_quality, mood,
                bmi, bmr, tdee, calorie_balance, bmi_category, date
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            user_id, weight, height, body_fat_pct, muscle_mass, notes,
            calories_in, calories_out, water_intake, sleep_quality, mood,
            bmi, bmr, tdee, calorie_balance, bmi_category
        ))

        log_id = cursor.lastrowid
        
        # 🆕 TẠO INSIGHTS TỰ ĐỘNG
        insights = generate_progress_insights(cursor, user_id, weight, bmi, calorie_balance)
        
        # 🆕 CẬP NHẬT PROFILE WEIGHT MỚI NHẤT
        cursor.execute("""
            UPDATE profiles SET weight = %s  
            WHERE user_id = %s
        """, (weight, user_id))
        
        # 🆕 TẠO NOTIFICATION
        try:
            cursor.execute("""
                INSERT INTO notifications (user_id, type, message, is_read)
                VALUES (%s, 'progress', %s, 0)
            """, (user_id, f"📊 Đã thêm tiến trình mới: {weight}kg, BMI: {bmi} ({bmi_category})"))
        except Exception as e:
            print(f"Lỗi tạo notification: {e}")
            
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Thêm tiến trình thành công",
            "log_id": log_id,
            "calculations": {
                "bmi": bmi,
                "bmi_category": bmi_category,
                "bmr": bmr,
                "tdee": tdee,
                "calorie_balance": calorie_balance
            },
            "insights": insights
        }), 201

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== 2️⃣ LẤY TIẾN TRÌNH VỚI PHÂN TÍCH =====================
@progress_bp.route("/progress", methods=["GET"])
@jwt_required()
def get_progress():
    """
    Lấy tiến trình với phân tích nâng cao
    - Phân trang
    - Filter theo thời gian
    - Thống kê xu hướng
    """
    try:
        user_id = int(get_jwt_identity())
        
        # 🆕 THAM SỐ PHÂN TRANG VÀ FILTER
        page = safe_int(request.args.get('page', 1))
        limit = safe_int(request.args.get('limit', 30))
        days = request.args.get('days')  # Lọc theo số ngày
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 BUILD DYNAMIC QUERY
        where_conditions = ["user_id = %s"]
        query_params = [user_id]
        
        if days:
            where_conditions.append("date >= DATE_SUB(NOW(), INTERVAL %s DAY)")
            query_params.append(safe_int(days))
        elif start_date and end_date:
            where_conditions.append("date BETWEEN %s AND %s")
            query_params.extend([start_date, end_date])
        
        # Query chính
        base_query = """
            SELECT log_id, weight, height, body_fat_pct, muscle_mass, notes,
                   calories_in, calories_out, water_intake, sleep_quality, mood,
                   bmi, bmr, tdee, calorie_balance, bmi_category, date
            FROM progress 
            WHERE """ + " AND ".join(where_conditions) + """
            ORDER BY date DESC
            LIMIT %s OFFSET %s
        """
        
        query_params.extend([limit, offset])
        cursor.execute(base_query, query_params)
        progress_data = cursor.fetchall()
        
        # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho progress_data
        for item in progress_data:
            for key in ['weight', 'height', 'body_fat_pct', 'muscle_mass', 'bmi', 'bmr', 'tdee', 'calorie_balance']:
                if item.get(key) is not None:
                    item[key] = safe_float(item[key])
            for key in ['calories_in', 'calories_out', 'water_intake', 'sleep_quality', 'mood']:
                if item.get(key) is not None:
                    item[key] = safe_int(item[key])
        
        # 🆕 THỐNG KÊ XU HƯỚNG
        stats_query = """
            SELECT 
                COUNT(*) as total_entries,
                AVG(weight) as avg_weight,
                AVG(bmi) as avg_bmi,
                AVG(body_fat_pct) as avg_body_fat,
                AVG(calories_in) as avg_calories_in,
                AVG(calories_out) as avg_calories_out,
                AVG(sleep_quality) as avg_sleep_quality,
                MIN(date) as first_entry,
                MAX(date) as last_entry
            FROM progress 
            WHERE """ + " AND ".join(where_conditions)
        
        cursor.execute(stats_query, query_params[:-2])
        stats = cursor.fetchone()
        
        # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho stats
        if stats:
            for key in ['avg_weight', 'avg_bmi', 'avg_body_fat', 'avg_calories_in', 'avg_calories_out', 'avg_sleep_quality']:
                if stats.get(key) is not None:
                    stats[key] = safe_float(stats[key])
        
        # 🆕 XU HƯỚNG CÂN NẶNG 7 NGÀY
        cursor.execute("""
            SELECT DATE(date) as date, AVG(weight) as avg_weight
            FROM progress 
            WHERE user_id = %s AND date >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY DATE(date)
            ORDER BY date
        """, (user_id,))
        weight_trend = cursor.fetchall()
        
        # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho weight_trend
        for item in weight_trend:
            if item.get('avg_weight') is not None:
                item['avg_weight'] = safe_float(item['avg_weight'])
        
        cursor.close()
        conn.close()

        if not progress_data:
            return jsonify({"message": "Chưa có dữ liệu tiến trình"}), 404

        return jsonify({
            "progress": progress_data,
            "analytics": {
                "summary": stats,
                "weight_trend": weight_trend,
                "current_status": get_current_status(progress_data[0] if progress_data else None)
            },
            "pagination": {
                "page": page,
                "limit": limit,
                "total": stats["total_entries"] or 0
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== 3️⃣ CẬP NHẬT TIẾN TRÌNH THÔNG MINH =====================
@progress_bp.route("/progress/<int:log_id>", methods=["PUT"])
@jwt_required()
def update_progress(log_id):
    """
    Cập nhật tiến trình với tính năng thông minh
    """
    try:
        data = request.get_json()
        user_id = int(get_jwt_identity())

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 KIỂM TRA QUYỀN SỞ HỮU
        cursor.execute("SELECT * FROM progress WHERE log_id = %s AND user_id = %s", (log_id, user_id))
        existing_log = cursor.fetchone()
        
        if not existing_log:
            return jsonify({"error": "Không tìm thấy tiến trình"}), 404

        # 🆕 CHỈ CẬP NHẬT CÁC TRƯỜNG ĐƯỢC GỬI LÊN
        update_fields = []
        update_values = []
        
        updatable_fields = [
            'weight', 'body_fat_pct', 'muscle_mass', 'notes', 
            'calories_in', 'calories_out', 'water_intake', 
            'sleep_quality', 'mood'
        ]
        
        for field in updatable_fields:
            if field in data:
                update_fields.append(f"{field} = %s")
                # 🛠️ SỬA: Sử dụng safe_float/safe_int cho giá trị số
                if field in ['weight', 'body_fat_pct', 'muscle_mass']:
                    update_values.append(safe_float(data[field]))
                else:
                    update_values.append(safe_int(data[field]))
        
        # 🆕 TÍNH LẠI CÁC CHỈ SỐ NẾU CÓ THAY ĐỔI WEIGHT
        if 'weight' in data:
            height = safe_float(existing_log['height'])
            new_weight = safe_float(data['weight'])
            
            # Tính lại BMI
            bmi = round(new_weight / ((height / 100) ** 2), 1)
            update_fields.append("bmi = %s")
            update_values.append(bmi)
            
            # Tính lại BMR
            cursor.execute("SELECT date_of_birth, gender FROM profiles WHERE user_id = %s", (user_id,))
            profile = cursor.fetchone()
            if profile:
                age = calculate_age(profile["date_of_birth"]) if profile["date_of_birth"] else 30
                age_int = safe_int(age)
                if profile["gender"] == 'male':
                    bmr = round(10 * new_weight + 6.25 * height - 5 * age_int + 5, 1)
                else:
                    bmr = round(10 * new_weight + 6.25 * height - 5 * age_int - 161, 1)
                update_fields.append("bmr = %s")
                update_values.append(bmr)
            
            # Phân loại BMI
            bmi_category = get_bmi_category(bmi)
            update_fields.append("bmi_category = %s")
            update_values.append(bmi_category)
            
            # 🆕 CẬP NHẬT PROFILE WEIGHT
            cursor.execute("UPDATE profiles SET weight = %s WHERE user_id = %s", (new_weight, user_id))
        
        # Tính lại calorie balance
        calories_in = safe_int(data.get('calories_in', existing_log['calories_in']))
        calories_out = safe_int(data.get('calories_out', existing_log['calories_out']))
        if calories_in is not None and calories_out is not None:
            calorie_balance = calories_in - calories_out
            update_fields.append("calorie_balance = %s")
            update_values.append(calorie_balance)
        
        update_fields.append("updated_at = NOW()")
        update_values.extend([log_id, user_id])
        
        if update_fields:
            update_query = f"UPDATE progress SET {', '.join(update_fields)} WHERE log_id = %s AND user_id = %s"
            cursor.execute(update_query, update_values)
            conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            "message": "Cập nhật tiến trình thành công",
            "log_id": log_id
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== 4️⃣ XÓA TIẾN TRÌNH AN TOÀN =====================
@progress_bp.route("/progress/<int:log_id>", methods=["DELETE"])
@jwt_required()
def delete_progress(log_id):
    """
    Xóa tiến trình với kiểm tra an toàn
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 KIỂM TRA QUYỀN VÀ LẤY THÔNG TIN TRƯỚC KHI XÓA
        cursor.execute("SELECT weight, date FROM progress WHERE log_id = %s AND user_id = %s", (log_id, user_id))
        progress = cursor.fetchone()
        
        if not progress:
            return jsonify({"error": "Không tìm thấy tiến trình hoặc không có quyền xóa"}), 404

        # 🆕 XÓA TIẾN TRÌNH
        cursor.execute("DELETE FROM progress WHERE log_id = %s AND user_id = %s", (log_id, user_id))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            "message": f"Đã xóa tiến trình ngày {progress['date']} thành công",
            "log_id": log_id
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== 5️⃣ API MỚI: PHÂN TÍCH XU HƯỚNG =====================
@progress_bp.route("/progress/analytics", methods=["GET"])
@jwt_required()
def get_progress_analytics():
    """
    Phân tích xu hướng tiến trình chi tiết
    """
    try:
        user_id = int(get_jwt_identity())
        period = request.args.get('period', '30')  # 7, 30, 90, 365 days
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 XU HƯỚNG CÂN NẶNG
        cursor.execute("""
            SELECT 
                DATE(date) as date,
                AVG(weight) as avg_weight,
                AVG(body_fat_pct) as avg_body_fat,
                AVG(bmi) as avg_bmi,
                AVG(calories_in) as avg_calories_in,
                AVG(calories_out) as avg_calories_out
            FROM progress 
            WHERE user_id = %s AND date >= DATE_SUB(NOW(), INTERVAL %s DAY)
            GROUP BY DATE(date)
            ORDER BY date
        """, (user_id, period))
        
        trends = cursor.fetchall()
        
        # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho trends
        for item in trends:
            for key in ['avg_weight', 'avg_body_fat', 'avg_bmi', 'avg_calories_in', 'avg_calories_out']:
                if item.get(key) is not None:
                    item[key] = safe_float(item[key])
        
        # 🆕 THỐNG KÊ TỔNG QUAN
        cursor.execute("""
            SELECT 
                COUNT(*) as total_entries,
                MIN(weight) as min_weight,
                MAX(weight) as max_weight,
                AVG(weight) as current_weight,
                AVG(bmi) as current_bmi,
                AVG(body_fat_pct) as current_body_fat,
                SUM(calories_in) as total_calories_in,
                SUM(calories_out) as total_calories_out
            FROM progress 
            WHERE user_id = %s AND date >= DATE_SUB(NOW(), INTERVAL %s DAY)
        """, (user_id, period))
        
        overview = cursor.fetchone()
        
        # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho overview
        if overview:
            for key in ['min_weight', 'max_weight', 'current_weight', 'current_bmi', 'current_body_fat', 'total_calories_in', 'total_calories_out']:
                if overview.get(key) is not None:
                    overview[key] = safe_float(overview[key])
        
        # 🆕 DỰ ĐOÁN XU HƯỚNG
        weight_change = 0
        if len(trends) >= 2:
            first_weight = safe_float(trends[0]['avg_weight'])
            last_weight = safe_float(trends[-1]['avg_weight'])
            weight_change = round(last_weight - first_weight, 1)
        
        cursor.close()
        conn.close()

        return jsonify({
            "analytics": {
                "period_days": period,
                "trends": trends,
                "overview": overview,
                "insights": {
                    "weight_change": weight_change,
                    "trend_direction": "giảm" if weight_change < 0 else "tăng" if weight_change > 0 else "ổn định",
                    "avg_daily_calorie_balance": round(
    (safe_float(overview.get('total_calories_in', 0)) - safe_float(overview.get('total_calories_out', 0))) / 
    max(safe_float(overview.get('total_entries', 1)), 1),  # 🛠️ SỬA: dùng max() để tránh chia 0
    1
)
                }
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500

# ===================== 6️⃣ API MỚI: LẤY TIẾN TRÌNH GẦN NHẤT =====================
@progress_bp.route("/progress/latest", methods=["GET"])
@jwt_required()
def get_latest_progress():
    """
    Lấy tiến trình gần nhất và so sánh
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 TIẾN TRÌNH GẦN NHẤT
        cursor.execute("""
            SELECT * FROM progress 
            WHERE user_id = %s 
            ORDER BY date DESC 
            LIMIT 1
        """, (user_id,))
        
        latest = cursor.fetchone()
        
        if latest:
            # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho latest
            for key in ['weight', 'height', 'body_fat_pct', 'muscle_mass', 'bmi', 'bmr', 'tdee', 'calorie_balance']:
                if latest.get(key) is not None:
                    latest[key] = safe_float(latest[key])
            for key in ['calories_in', 'calories_out', 'water_intake', 'sleep_quality', 'mood']:
                if latest.get(key) is not None:
                    latest[key] = safe_int(latest[key])
        
        # 🆕 TIẾN TRÌNH TRƯỚC ĐÓ (ĐỂ SO SÁNH)
        cursor.execute("""
            SELECT * FROM progress 
            WHERE user_id = %s AND date < %s
            ORDER BY date DESC 
            LIMIT 1
        """, (user_id, latest['date'] if latest else None))
        
        previous = cursor.fetchone()
        
        if previous:
            # 🛠️ SỬA: Chuyển đổi kiểu dữ liệu cho previous
            for key in ['weight', 'height', 'body_fat_pct', 'muscle_mass', 'bmi', 'bmr', 'tdee', 'calorie_balance']:
                if previous.get(key) is not None:
                    previous[key] = safe_float(previous[key])
            for key in ['calories_in', 'calories_out', 'water_intake', 'sleep_quality', 'mood']:
                if previous.get(key) is not None:
                    previous[key] = safe_int(previous[key])
        
        cursor.close()
        conn.close()

        if not latest:
            return jsonify({"message": "Chưa có dữ liệu tiến trình"}), 404

        comparison = {}
        if previous:
            comparison = {
                "weight_change": round(safe_float(latest['weight']) - safe_float(previous['weight']), 1),
                "bmi_change": round(safe_float(latest['bmi']) - safe_float(previous['bmi']), 1),
                "days_between": (latest['date'] - previous['date']).days
            }

        return jsonify({
            "latest_progress": latest,
            "comparison": comparison,
            "summary": get_current_status(latest)
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500