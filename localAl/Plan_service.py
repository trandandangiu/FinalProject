from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, date, timedelta
import json

plan_bp = Blueprint("plan", __name__)

def parse_json_field(field_value):
    """Parse JSON field từ database"""
    if not field_value:
        return []
    try:
        if isinstance(field_value, str) and field_value.startswith('['):
            return json.loads(field_value)
        return [field_value]
    except:
        return [field_value]

# ===================== 1️⃣ TẠO KẾ HOẠCH THỦ CÔNG HOÀN CHỈNH =====================
@plan_bp.route("/plans", methods=["POST"])
@jwt_required()
def create_plan():
    """
    User tự tạo kế hoạch cá nhân (manual) - Phiên bản hoàn chỉnh
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return jsonify({"error": "Dữ liệu gửi lên không hợp lệ"}), 400
            
        plan_name = data.get("plan_name")
        plan_type = data.get("plan_type", "weekly")
        goal = data.get("goal", "maintenance")
        rec_type = data.get("rec_type", "daily_plan")
        content = data.get("content")  # JSON string chứa chi tiết kế hoạch

        if not plan_name:
            return jsonify({"error": "Tên kế hoạch là bắt buộc"}), 400

        # Validate plan_type
        valid_plan_types = ['daily', 'weekly', 'monthly', 'custom']
        if plan_type not in valid_plan_types:
            return jsonify({"error": f"Loại kế hoạch không hợp lệ. Chọn: {', '.join(valid_plan_types)}"}), 400

        # Validate goal
        valid_goals = ['weight_loss', 'muscle_gain', 'maintenance', 'endurance', 'flexibility']
        if goal not in valid_goals:
            return jsonify({"error": f"Mục tiêu không hợp lệ. Chọn: {', '.join(valid_goals)}"}), 400
    
        valid_rec_types = ['nutrition', 'workout', 'daily_plan']  
        if rec_type not in valid_rec_types:
            return jsonify({"error": f"Loại recommendation không hợp lệ. Chọn: {', '.join(valid_rec_types)}"}), 400

        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO plans (user_id, plan_name, plan_type, goal, rec_type, content, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (user_id, plan_name, plan_type, goal, rec_type, content))
        conn.commit()

        plan_id = cursor.lastrowid
        
        # 🆕 THÊM: Tạo notification khi tạo plan mới
        try:
            cursor.execute("""
                INSERT INTO notifications (user_id, type, message, is_read)
                VALUES (%s, 'system', %s, 0)
            """, (user_id, f"🎯 Kế hoạch '{plan_name}' đã được tạo thành công!"))
            conn.commit()
        except:
            pass  # Bỏ qua nếu không thể tạo notification
            
        cursor.close()
        conn.close()

        return jsonify({
            "message": "Tạo kế hoạch thành công",
            "plan_id": plan_id,
            "plan_name": plan_name,
            "plan_type": plan_type,
            "goal": goal,
            "rec_type": rec_type,
            
        }), 201

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 2️⃣ THÊM CHI TIẾT KẾ HOẠCH NÂNG CAO =====================
@plan_bp.route("/plans/details", methods=["POST"])
@jwt_required()
def add_plan_detail():
    """
    Thêm bài tập hoặc bữa ăn vào kế hoạch (theo ngày) - Phiên bản nâng cao
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Dữ liệu gửi lên không hợp lệ"}), 400
            
        plan_id = data.get("plan_id")
        day_of_week = data.get("day_of_week")
        workout_id = data.get("workout_id")
        meal_id = data.get("meal_id")
        exercise_name = data.get("exercise_name")  # 🆕 Cho phép custom exercise
        food_name = data.get("food_name")  # 🆕 Cho phép custom food
        sets = data.get("sets")
        reps = data.get("reps")
        duration = data.get("duration")
        calories = data.get("calories")
        notes = data.get("notes")

        if not plan_id or not day_of_week:
            return jsonify({"error": "Thiếu plan_id hoặc day_of_week"}), 400

        # Validate day_of_week
        day_mapping = {
            'Monday': 'Mon', 'Mon': 'Mon',
            'Tuesday': 'Tue', 'Tue': 'Tue', 
            'Wednesday': 'Wed', 'Wed': 'Wed',
            'Thursday': 'Thu', 'Thu': 'Thu',
            'Friday': 'Fri', 'Fri': 'Fri',
            'Saturday': 'Sat', 'Sat': 'Sat',
            'Sunday': 'Sun', 'Sun': 'Sun'
        }

        if day_of_week not in day_mapping:
            return jsonify({"error": f"Ngày trong tuần không hợp lệ. Chọn: {', '.join(day_mapping.keys())}"}), 400

        normalized_day = day_mapping[day_of_week]

        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor()
        
        # 🆕 KIỂM TRA: User có quyền thêm vào plan này không
        cursor.execute("SELECT user_id FROM plans WHERE plan_id = %s", (plan_id,))
        plan_owner = cursor.fetchone()
        
        if not plan_owner or plan_owner[0] != user_id:
            return jsonify({"error": "Không có quyền thêm vào kế hoạch này"}), 403

        cursor.execute("""
            INSERT INTO plan_details (plan_id, user_id, day_of_week, workout_id, meal_id, 
                                   exercise_name, food_name, sets, reps, duration, calories, notes, is_completed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
        """, (plan_id, user_id, normalized_day, workout_id, meal_id, exercise_name, food_name, 
              sets, reps, duration, calories, notes))
        conn.commit()

        detail_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Đã thêm vào kế hoạch thành công",
            "detail_id": detail_id
        }), 201

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 3️⃣ ĐÁNH DẤU HOÀN THÀNH THÔNG MINH =====================
@plan_bp.route("/plans/details/<int:detail_id>", methods=["PUT"])
@jwt_required()
def update_completion(detail_id):
    """
    Đánh dấu 1 chi tiết trong kế hoạch là hoàn thành - Phiên bản thông minh
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        completed = data.get("is_completed", True)
        actual_sets = data.get("actual_sets")
        actual_reps = data.get("actual_reps")
        actual_duration = data.get("actual_duration")
        notes = data.get("notes")

        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 LẤY THÔNG TIN CHI TIẾT TRƯỚC KHI UPDATE
        cursor.execute("""
            SELECT pd.*, p.plan_name 
            FROM plan_details pd
            JOIN plans p ON pd.plan_id = p.plan_id
            WHERE pd.detail_id = %s AND pd.user_id = %s
        """, (detail_id, user_id))
        
        detail = cursor.fetchone()
        
        if not detail:
            return jsonify({"error": "Không tìm thấy chi tiết kế hoạch"}), 404

        # 🆕 CẬP NHẬT THÔNG MINH
        update_fields = []
        update_values = []
        
        update_fields.append("is_completed = %s")
        update_values.append(1 if completed else 0)
        
        if actual_sets is not None:
            update_fields.append("actual_sets = %s")
            update_values.append(actual_sets)
            
        if actual_reps is not None:
            update_fields.append("actual_reps = %s")
            update_values.append(actual_reps)
            
        if actual_duration is not None:
            update_fields.append("actual_duration = %s")
            update_values.append(actual_duration)
        
        # Cập nhật notes
        new_note = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Đã hoàn thành: {notes}" if notes else f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Đã hoàn thành"
        update_fields.append("notes = CONCAT(IFNULL(notes,''), %s)")
        update_values.append(new_note)
        
        update_values.extend([detail_id, user_id])
        
        update_query = f"UPDATE plan_details SET {', '.join(update_fields)} WHERE detail_id = %s AND user_id = %s"
        cursor.execute(update_query, update_values)
        conn.commit()
        
        # 🆕 TẠO NOTIFICATION KHI HOÀN THÀNH
        if completed:
            try:
                activity_type = "bài tập" if detail['workout_id'] or detail['exercise_name'] else "bữa ăn"
                cursor.execute("""
                    INSERT INTO notifications (user_id, type, message, is_read)
                    VALUES (%s, 'achievement', %s, 0)
                """, (user_id, f"🎉 Chúc mừng! Bạn đã hoàn thành {activity_type} trong kế hoạch '{detail['plan_name']}'"))
                conn.commit()
            except:
                pass

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Đã cập nhật trạng thái thành công",
            "detail_id": detail_id,
            "completed": bool(completed)
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 4️⃣ XEM DANH SÁCH KẾ HOẠCH NÂNG CAO =====================
@plan_bp.route("/plans/user", methods=["GET"])
@jwt_required()
def get_user_plans():
    """
    Lấy danh sách kế hoạch của user - Phiên bản nâng cao với phân trang và filter
    """
    try:
        user_id = int(get_jwt_identity())
        
        # 🆕 THAM SỐ PHÂN TRANG VÀ FILTER
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        plan_type = request.args.get('type')
        goal = request.args.get('goal')
        status = request.args.get('status', 'active')  # active, completed, all
        
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 BUILD DYNAMIC QUERY
        where_conditions = ["p.user_id = %s"]
        query_params = [user_id]
        
        if plan_type:
            where_conditions.append("plan_type = %s")
            query_params.append(plan_type)
            
        if goal:
            where_conditions.append("goal = %s")
            query_params.append(goal)
        
        # Base query
        base_query = """
            SELECT p.plan_id, p.plan_name, p.plan_type, p.goal, p.rec_type, p.content,
                   p.created_at,
                   COUNT(pd.detail_id) as total_items,
                   SUM(CASE WHEN pd.is_completed = 1 THEN 1 ELSE 0 END) as completed_items
            FROM plans p
            LEFT JOIN plan_details pd ON p.plan_id = pd.plan_id
            WHERE """ + " AND ".join(where_conditions) + """
            GROUP BY p.plan_id
            ORDER BY p.created_at DESC
            LIMIT %s OFFSET %s
        """
        
        query_params.extend([limit, offset])
        cursor.execute(base_query, query_params)
        plans = cursor.fetchall()
        
        # 🆕 TÍNH TOÁN PHẦN TRĂM HOÀN THÀNH
        for plan in plans:
            total = plan['total_items'] or 0
            completed = plan['completed_items'] or 0
            plan['completion_rate'] = round((completed / total * 100), 1) if total > 0 else 0
            plan['status'] = 'completed' if plan['completion_rate'] == 100 else 'active'
            
            # Parse content nếu có
            if plan['content']:
                try:
                    plan['parsed_content'] = json.loads(plan['content'])
                except:
                    plan['parsed_content'] = None
        
        # 🆕 ĐẾM TỔNG SỐ PLANS CHO PHÂN TRANG
        count_query = "SELECT COUNT(*) as total FROM plans p WHERE " + " AND ".join(where_conditions)
        cursor.execute(count_query, query_params[:-2])  # Remove limit, offset
        total_count = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()

        return jsonify({
            "plans": plans,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            },
            "filters": {
                "type": plan_type,
                "goal": goal,
                "status": status
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 5️⃣ XEM CHI TIẾT KẾ HOẠCH HOÀN CHỈNH =====================
@plan_bp.route("/plans/<int:plan_id>/details", methods=["GET"])
@jwt_required()
def get_plan_details(plan_id):
    """
    Xem chi tiết kế hoạch (bài tập & bữa ăn) theo ngày - Phiên bản hoàn chỉnh
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 KIỂM TRA QUYỀN TRUY CẬP
        cursor.execute("SELECT user_id, plan_name FROM plans WHERE plan_id = %s", (plan_id,))
        plan = cursor.fetchone()
        
        if not plan:
            return jsonify({"error": "Không tìm thấy kế hoạch"}), 404
            
        if plan['user_id'] != user_id:
            return jsonify({"error": "Không có quyền truy cập kế hoạch này"}), 403

        # 🆕 LẤY CHI TIẾT THEO NGÀY
        cursor.execute("""
            SELECT pd.detail_id, pd.day_of_week, pd.is_completed,
                   pd.workout_id, pd.meal_id,
                   pd.exercise_name, pd.food_name,
                   pd.sets, pd.reps, pd.duration, pd.calories,
                   pd.actual_sets, pd.actual_reps, pd.actual_duration,
                   pd.notes,
                   e.name AS exercise_name_db,
                   e.body_part, 
                   e.equipment, 
                   e.target, 
                   e.secondary_muscles, 
                   e.video_path, 
                   e.level, 
                   f.name AS food_name_db,
                   f.calories AS food_calories_db, f.protein, f.carbs, f.fat, f.goal, f.category
            FROM plan_details pd
            LEFT JOIN exercises e ON pd.workout_id = e.exercise_id
            LEFT JOIN meals m ON pd.meal_id = m.meal_id
            LEFT JOIN meal_details md ON m.meal_id = md.meal_id
            LEFT JOIN foods f ON md.food_id = f.food_id
            WHERE pd.plan_id = %s AND pd.user_id = %s
            ORDER BY FIELD(pd.day_of_week, 'Mon','Tue','Wed','Thu','Fri','Sat','Sun'),
                     pd.detail_id
        """, (plan_id, user_id))
        
        details = cursor.fetchall()
        
        # 🆕 NHÓM CHI TIẾT THEO NGÀY
        daily_plan = {}
        for detail in details:
            day = detail['day_of_week']
            if day not in daily_plan:
                daily_plan[day] = {
                    "workouts": [],
                    "meals": [],
                    "completed_workouts": 0,
                    "completed_meals": 0,
                    "total_calories": 0
                }
            
            # Phân loại workout hoặc meal
            if detail['workout_id'] or detail['exercise_name']:
                workout_data = {
                    "detail_id": detail['detail_id'],
                    "exercise_id": detail['workout_id'],
                    "exercise_name": detail['exercise_name'] or detail['exercise_name_db'],
                    "body_part": detail['body_part'],
                    "equipment": detail['equipment'],
                    "target": detail['target'],
                    "secondary_muscles": detail['secondary_muscles'],
                    "video_path": detail['video_path'],
                    "level": detail['level'],
                    # Thông tin tập luyện
                    "sets": detail['sets'],
                    "reps": detail['reps'],
                    "duration": detail['duration'],
                    "calories": detail['calories'],
                    "actual_sets": detail['actual_sets'],
                    "actual_reps": detail['actual_reps'],
                    "actual_duration": detail['actual_duration'],
                    "is_completed": bool(detail['is_completed']),
                    "notes": detail['notes'],
                    "type": "workout"
                }
                daily_plan[day]['workouts'].append(workout_data)
                if detail['is_completed']:
                    daily_plan[day]['completed_workouts'] += 1
                    
            elif detail['meal_id'] or detail['food_name']:
                meal_data = {
                    "detail_id": detail['detail_id'],
                    "meal_id": detail['meal_id'],
                    "food_name": detail['food_name'] or detail['food_name_db'],
                    "calories": detail['calories'] or detail['food_calories_db'],
                    "protein": detail['protein'],
                    "carbs": detail['carbs'],
                    "fat": detail['fat'],
                    "goal": detail['goal'],
                    "category": detail['category'],
                    "is_completed": bool(detail['is_completed']),
                    "notes": detail['notes'],
                    "type": "meal"
                }
                daily_plan[day]['meals'].append(meal_data)
                if detail['is_completed']:
                    daily_plan[day]['completed_meals'] += 1
                
            # Tính tổng calories
            if detail['calories']:
                daily_plan[day]['total_calories'] += (detail['calories'] or 0)

        cursor.close()
        conn.close()

        return jsonify({
            "plan_id": plan_id,
            "plan_name": plan['plan_name'],
            "daily_plan": daily_plan,
            "summary": {
                "total_days": len(daily_plan),
                "total_workouts": sum(len(day['workouts']) for day in daily_plan.values()),
                "total_meals": sum(len(day['meals']) for day in daily_plan.values()),
                "completed_workouts": sum(day['completed_workouts'] for day in daily_plan.values()),
                "completed_meals": sum(day['completed_meals'] for day in daily_plan.values())
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 6️⃣ TẠO KẾ HOẠCH TỰ ĐỘNG THÔNG MINH =====================
@plan_bp.route("/plans/auto", methods=["POST"])
@jwt_required()
def create_auto_plan():
    """
    Tạo kế hoạch tự động dựa trên user preferences và goals - Phiên bản thông minh
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        goal = data.get("goal")
        plan_type = data.get("plan_type", "weekly")
        plan_name = data.get("plan_name", "Kế hoạch AI Recommendation")

        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)

        # 🆕 LẤY USER PREFERENCES ĐỂ CÁ NHÂN HÓA
        cursor.execute("""
            SELECT diet_type, activity_level, preferred_exercises, health_conditions
            FROM user_preferences 
            WHERE user_id = %s
        """, (user_id,))
        user_prefs = cursor.fetchone()
        
        # Nếu không có goal từ request, lấy từ preferences
        if not goal and user_prefs:
            # Map diet_type to goal
            goal_map = {
                'keto': 'weight_loss',
                'low_carb': 'weight_loss', 
                'high_protein': 'muscle_gain',
                'balanced': 'maintenance'
            }
            goal = goal_map.get(user_prefs['diet_type'], 'maintenance')

        # 🆕 TẠO PLAN CƠ BẢN
        cursor.execute("""
            INSERT INTO plans (user_id, plan_name, plan_type, goal, rec_type, content, created_at)
            VALUES (%s, %s, %s, %s, 'daily_plan', %s, NOW())
        """, (user_id, plan_name, plan_type, goal, json.dumps({
            "generated_by": "ai_system",
            "user_preferences": user_prefs,
            "goal": goal,
            "created_at": datetime.now().isoformat()
        })))
        
        plan_id = cursor.lastrowid
        conn.commit()

        # 🆕 TẠO NOTIFICATION
        try:
            cursor.execute("""
                INSERT INTO notifications (user_id, type, message, is_read)
                VALUES (%s, 'system', %s, 0)
            """, (user_id, f"🤖 AI đã tạo kế hoạch '{plan_name}' dựa trên mục tiêu {goal} của bạn!"))
            conn.commit()
        except:
            pass

        cursor.close()
        conn.close()

        return jsonify({
            "message": "AI đã tạo kế hoạch cá nhân hóa thành công",
            "plan_id": plan_id,
            "plan_name": plan_name,
            "goal": goal,
            "plan_type": plan_type,
            "rec_type": "daily_plan",
            "note": "Hãy thêm chi tiết bài tập và bữa ăn vào kế hoạch"
        }), 201

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 7️⃣ TÍNH % HOÀN THÀNH KẾ HOẠCH CHI TIẾT =====================
@plan_bp.route("/plans/<int:plan_id>/progress", methods=["GET"])
@jwt_required()
def get_plan_progress(plan_id):
    """
    Tính phần trăm hoàn thành kế hoạch chi tiết - Phiên bản analytics
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)

        # 🆕 KIỂM TRA QUYỀN TRUY CẬP
        cursor.execute("SELECT plan_name FROM plans WHERE plan_id = %s AND user_id = %s", (plan_id, user_id))
        plan = cursor.fetchone()
        
        if not plan:
            return jsonify({"error": "Không tìm thấy kế hoạch"}), 404

        # 🆕 THỐNG KÊ CHI TIẾT
        cursor.execute("""
            SELECT 
                COUNT(*) AS total_items,
                SUM(CASE WHEN is_completed = 1 THEN 1 ELSE 0 END) AS completed_items,
                SUM(CASE WHEN workout_id IS NOT NULL OR exercise_name IS NOT NULL THEN 1 ELSE 0 END) AS total_workouts,
                SUM(CASE WHEN (workout_id IS NOT NULL OR exercise_name IS NOT NULL) AND is_completed = 1 THEN 1 ELSE 0 END) AS completed_workouts,
                SUM(CASE WHEN meal_id IS NOT NULL OR food_name IS NOT NULL THEN 1 ELSE 0 END) AS total_meals,
                SUM(CASE WHEN (meal_id IS NOT NULL OR food_name IS NOT NULL) AND is_completed = 1 THEN 1 ELSE 0 END) AS completed_meals,
                AVG(CASE WHEN is_completed = 1 THEN calories ELSE 0 END) AS avg_calories_per_activity
            FROM plan_details
            WHERE plan_id = %s AND user_id = %s
        """, (plan_id, user_id))
        
        stats = cursor.fetchone()
        
        # 🆕 THỐNG KÊ THEO NGÀY
        cursor.execute("""
            SELECT day_of_week,
                   COUNT(*) as total_day_items,
                   SUM(is_completed) as completed_day_items,
                   ROUND(SUM(is_completed) / COUNT(*) * 100, 1) as day_completion_rate
            FROM plan_details
            WHERE plan_id = %s AND user_id = %s
            GROUP BY day_of_week
            ORDER BY FIELD(day_of_week, 'Mon','Tue','Wed','Thu','Fri','Sat','Sun')
        """, (plan_id, user_id))
        
        daily_stats = cursor.fetchall()
        
        cursor.close()
        conn.close()

        total = stats["total_items"] or 0
        completed = stats["completed_items"] or 0
        percent = round((completed / total * 100), 1) if total > 0 else 0
        
        # 🆕 XÁC ĐỊNH TRẠNG THÁI
        if percent == 0:
            status = "not_started"
            status_message = "Chưa bắt đầu"
        elif percent == 100:
            status = "completed"
            status_message = "Đã hoàn thành"
        elif percent >= 70:
            status = "almost_done"
            status_message = "Sắp hoàn thành"
        else:
            status = "in_progress"
            status_message = "Đang thực hiện"

        return jsonify({
            "plan_id": plan_id,
            "plan_name": plan["plan_name"],
            "overall_progress": {
                "completed_percent": percent,
                "status": status,
                "status_message": status_message,
                "total_items": total,
                "completed_items": completed,
                "remaining_items": total - completed
            },
            "breakdown": {
                "workouts": {
                    "total": stats["total_workouts"] or 0,
                    "completed": stats["completed_workouts"] or 0,
                    "completion_rate": round((stats["completed_workouts"] or 0) / (stats["total_workouts"] or 1) * 100, 1)
                },
                "meals": {
                    "total": stats["total_meals"] or 0,
                    "completed": stats["completed_meals"] or 0,
                    "completion_rate": round((stats["completed_meals"] or 0) / (stats["total_meals"] or 1) * 100, 1)
                }
            },
            "daily_progress": daily_stats,
            "insights": {
                "avg_calories_per_activity": round(stats["avg_calories_per_activity"] or 0, 1),
                "estimated_total_calories": round((stats["avg_calories_per_activity"] or 0) * completed, 1)
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 8️⃣ XOÁ KẾ HOẠCH AN TOÀN =====================
@plan_bp.route("/plans/<int:plan_id>", methods=["DELETE"])
@jwt_required()
def delete_plan(plan_id):
    """
    Xoá kế hoạch và chi tiết liên quan - Phiên bản an toàn
    """
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🆕 KIỂM TRA QUYỀN VÀ LẤY THÔNG TIN PLAN TRƯỚC KHI XÓA
        cursor.execute("SELECT plan_name FROM plans WHERE plan_id = %s AND user_id = %s", (plan_id, user_id))
        plan = cursor.fetchone()
        
        if not plan:
            return jsonify({"error": "Không tìm thấy kế hoạch hoặc không có quyền xóa"}), 404

        # 🆕 XÓA TRONG TRANSACTION ĐỂ ĐẢM BẢO TÍNH TOÀN VẸN
        cursor.execute("DELETE FROM plan_details WHERE plan_id = %s AND user_id = %s", (plan_id, user_id))
        cursor.execute("DELETE FROM plans WHERE plan_id = %s AND user_id = %s", (plan_id, user_id))
        conn.commit()

        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"Đã xoá kế hoạch '{plan['plan_name']}' thành công",
            "plan_id": plan_id
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 9️⃣ API MỚI: SAO CHÉP KẾ HOẠCH =====================
@plan_bp.route("/plans/<int:plan_id>/copy", methods=["POST"])
@jwt_required()
def copy_plan(plan_id):
    """
    Sao chép kế hoạch hiện có để tạo bản mới
    """
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json() or {}
        new_plan_name = data.get("new_plan_name", f"Bản sao kế hoạch {plan_id}")
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # Lấy thông tin plan gốc
        cursor.execute("""
            SELECT plan_name, plan_type, goal, rec_type, content
            FROM plans WHERE plan_id = %s AND user_id = %s
        """, (plan_id, user_id))
        
        original_plan = cursor.fetchone()
        if not original_plan:
            return jsonify({"error": "Không tìm thấy kế hoạch gốc"}), 404
        
        # Tạo plan mới
        cursor.execute("""
            INSERT INTO plans (user_id, plan_name, plan_type, goal, rec_type, content, created_at)
            VALUES (%s, %s, %s, %s, %s,'daily_plan, %s, NOW())
        """, (user_id, new_plan_name, original_plan['plan_type'], original_plan['goal'], 
               original_plan['content']))
        
        new_plan_id = cursor.lastrowid
        
        # Sao chép chi tiết plan
        cursor.execute("""
            INSERT INTO plan_details (plan_id, user_id, day_of_week, workout_id, meal_id,
                                   exercise_name, food_name, sets, reps, duration, calories, notes, is_completed)
            SELECT %s, %s, day_of_week, workout_id, meal_id,
                   exercise_name, food_name, sets, reps, duration, calories, 
                   CONCAT('Sao chép từ: ', IFNULL(notes, '')), 0
            FROM plan_details
            WHERE plan_id = %s AND user_id = %s
        """, (new_plan_id, user_id, plan_id, user_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": f"Đã sao chép kế hoạch thành công",
            "original_plan_id": plan_id,
            "new_plan_id": new_plan_id,
            "new_plan_name": new_plan_name,
            "rec_type": "daily_plan"
        }), 201
        
    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500
    # ===================== 🔟 API MỚI: LẤY DANH SÁCH EXERCISES =====================
@plan_bp.route("/exercises", methods=["GET"])
@jwt_required()
def get_exercises():
    """
    Lấy danh sách exercises để chọn cho kế hoạch
    """
    try:
        # Tham số filter
        body_part = request.args.get('body_part')
        equipment = request.args.get('equipment')
        target = request.args.get('target')
        level = request.args.get('level')
        search = request.args.get('search')
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # Build dynamic query
        where_conditions = ["is_active = 1"]
        query_params = []
        
        if body_part:
            where_conditions.append("body_part = %s")
            query_params.append(body_part)
            
        if equipment:
            where_conditions.append("equipment = %s")
            query_params.append(equipment)
            
        if target:
            where_conditions.append("target = %s")
            query_params.append(target)
            
        if level:
            where_conditions.append("level = %s")
            query_params.append(level)
            
        if search:
            where_conditions.append("(name LIKE %s OR body_part LIKE %s OR target LIKE %s)")
            query_params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        
        # Base query
        base_query = """
            SELECT exercise_id, name, body_part, equipment, target, 
                   secondary_muscles, video_path, level
            FROM exercises 
            WHERE """ + " AND ".join(where_conditions) + """
            ORDER BY name
            LIMIT %s OFFSET %s
        """
        
        query_params.extend([limit, offset])
        cursor.execute(base_query, query_params)
        exercises = cursor.fetchall()
        
        # Đếm tổng
        count_query = "SELECT COUNT(*) as total FROM exercises WHERE " + " AND ".join(where_conditions)
        cursor.execute(count_query, query_params[:-2])  # Remove limit, offset
        total_count = cursor.fetchone()['total']
        
        # Lấy các filter options
        cursor.execute("SELECT DISTINCT body_part FROM exercises WHERE is_active = 1 AND body_part IS NOT NULL ORDER BY body_part")
        body_parts = [row['body_part'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT equipment FROM exercises WHERE is_active = 1 AND equipment IS NOT NULL ORDER BY equipment")
        equipments = [row['equipment'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT target FROM exercises WHERE is_active = 1 AND target IS NOT NULL ORDER BY target")
        targets = [row['target'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT level FROM exercises WHERE is_active = 1 AND level IS NOT NULL ORDER BY level")
        levels = [row['level'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()

        return jsonify({
            "exercises": exercises,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            },
            "filters": {
                "body_parts": body_parts,
                "equipments": equipments,
                "targets": targets,
                "levels": levels
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 1️⃣1️⃣ API MỚI: LẤY DANH SÁCH FOODS =====================
@plan_bp.route("/foods", methods=["GET"])
@jwt_required()
def get_foods():
    """
    Lấy danh sách foods để chọn cho kế hoạch dinh dưỡng
    """
    try:
        # Tham số filter
        category = request.args.get('category')
        goal = request.args.get('goal')
        search = request.args.get('search')
        min_calories = request.args.get('min_calories')
        max_calories = request.args.get('max_calories')
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # Build dynamic query
        where_conditions = ["1=1"]  # Always true để dễ build query
        query_params = []
        
        if category:
            where_conditions.append("category = %s")
            query_params.append(category)
            
        if goal:
            where_conditions.append("goal = %s")
            query_params.append(goal)
            
        if search:
            where_conditions.append("name LIKE %s")
            query_params.append(f"%{search}%")
            
        if min_calories:
            where_conditions.append("calories >= %s")
            query_params.append(float(min_calories))
            
        if max_calories:
            where_conditions.append("calories <= %s")
            query_params.append(float(max_calories))
        
        # Base query
        base_query = """
            SELECT food_id, name, calories, protein, carbs, fat, goal, category
            FROM foods 
            WHERE """ + " AND ".join(where_conditions) + """
            ORDER BY name
            LIMIT %s OFFSET %s
        """
        
        query_params.extend([limit, offset])
        cursor.execute(base_query, query_params)
        foods = cursor.fetchall()
        
        # Đếm tổng
        count_query = "SELECT COUNT(*) as total FROM foods WHERE " + " AND ".join(where_conditions)
        cursor.execute(count_query, query_params[:-2])  # Remove limit, offset
        total_count = cursor.fetchone()['total']
        
        # Lấy các filter options
        cursor.execute("SELECT DISTINCT category FROM foods WHERE category IS NOT NULL ORDER BY category")
        categories = [row['category'] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT goal FROM foods WHERE goal IS NOT NULL ORDER BY goal")
        goals = [row['goal'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()

        return jsonify({
            "foods": foods,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            },
            "filters": {
                "categories": categories,
                "goals": goals
            }
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500


# ===================== 1️⃣2️⃣ API MỚI: LẤY CHI TIẾT EXERCISE =====================
@plan_bp.route("/exercises/<int:exercise_id>", methods=["GET"])
@jwt_required()
def get_exercise_detail(exercise_id):
    """
    Lấy chi tiết một exercise cụ thể
    """
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT exercise_id, name, body_part, equipment, target, 
                   secondary_muscles, video_path, level
            FROM exercises 
            WHERE exercise_id = %s AND is_active = 1
        """, (exercise_id,))
        
        exercise = cursor.fetchone()
        
        if not exercise:
            return jsonify({"error": "Không tìm thấy bài tập"}), 404
            
        cursor.close()
        conn.close()

        return jsonify({
            "exercise": exercise
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500
# ===================== 1️⃣3️⃣ API MỚI: LẤY CHI TIẾT FOOD =====================
@plan_bp.route("/foods/<int:food_id>", methods=["GET"])
@jwt_required()
def get_food_detail(food_id):
    """
    Lấy chi tiết một food cụ thể
    """
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Kết nối database thất bại"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT food_id, name, calories, protein, carbs, fat, goal, category
            FROM foods 
            WHERE food_id = %s
        """, (food_id,))
        
        food = cursor.fetchone()
        
        if not food:
            return jsonify({"error": "Không tìm thấy thực phẩm"}), 404
            
        cursor.close()
        conn.close()

        return jsonify({
            "food": food
        }), 200

    except Exception as e:
        return jsonify({"error": f"Lỗi server: {str(e)}"}), 500