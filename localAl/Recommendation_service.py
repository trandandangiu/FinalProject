from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
import math
from datetime import datetime, timedelta

recommendation_bp = Blueprint("recommendation", __name__)

# ===================== CONSTANTS & CONFIG =====================
GOAL_WEIGHTS = {
    "giảm cân": {"cardio": 0.6, "strength": 0.3, "flexibility": 0.1},
    "tăng cơ": {"cardio": 0.2, "strength": 0.7, "flexibility": 0.1},
    "duy trì": {"cardio": 0.4, "strength": 0.4, "flexibility": 0.2},
    "tăng sức bền": {"cardio": 0.7, "strength": 0.2, "flexibility": 0.1}
}

EXERCISE_INTENSITY = {
    "beginner": {"sets": 2, "reps": 8, "duration": 15},
    "intermediate": {"sets": 3, "reps": 10, "duration": 25},
    "advanced": {"sets": 4, "reps": 12, "duration": 35}
}

# ===================== UTILITY FUNCTIONS =====================
def calculate_user_level(workout_history_count, consistency_rate):
    """Xác định trình độ người dùng dựa trên lịch sử tập luyện"""
    if workout_history_count < 10 or consistency_rate < 0.3:
        return "beginner"
    elif workout_history_count < 30 or consistency_rate < 0.6:
        return "intermediate"
    else:
        return "advanced"

def get_user_profile(user_id):
    """Lấy thông tin profile người dùng"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT p.goal, p.weight, p.height, p.gender, p.dob,
               TIMESTAMPDIFF(YEAR, p.dob, CURDATE()) as age
        FROM profiles p 
        WHERE p.user_id = %s
    """, (user_id,))
    
    profile = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return profile

def get_workout_history_stats(user_id):
    """Thống kê lịch sử tập luyện"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy số buổi tập trong 30 ngày gần nhất
    cursor.execute("""
        SELECT COUNT(*) as session_count,
               COUNT(DISTINCT DATE(date)) as active_days
        FROM sessions 
        WHERE user_id = %s AND date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
    """, (user_id,))
    
    stats = cursor.fetchone()
    
    # Lấy nhóm cơ tập nhiều nhất
    cursor.execute("""
        SELECT e.body_part, COUNT(*) as count
        FROM session_details sd
        JOIN exercises e ON sd.exercise_id = e.exercise_id
        JOIN sessions s ON sd.session_id = s.session_id
        WHERE s.user_id = %s AND s.date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY e.body_part
        ORDER BY count DESC
        LIMIT 3
    """, (user_id,))
    
    favorite_body_parts = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return {
        "session_count": stats["session_count"] if stats else 0,
        "active_days": stats["active_days"] if stats else 0,
        "favorite_body_parts": [bp["body_part"] for bp in favorite_body_parts],
        "consistency_rate": stats["active_days"] / 30 if stats and stats["active_days"] else 0
    }

def get_meal_preferences(user_id):
    """Phân tích sở thích ăn uống từ lịch sử"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT f.name, f.category, COUNT(*) as frequency,
               AVG(md.quantity) as avg_quantity
        FROM meal_details md
        JOIN meals m ON md.meal_id = m.meal_id
        JOIN foods f ON md.food_id = f.food_id
        WHERE m.user_id = %s AND m.date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY f.food_id, f.name, f.category
        ORDER BY frequency DESC
        LIMIT 10
    """, (user_id,))
    
    preferences = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return preferences

# ===================== RECOMMENDATION ALGORITHMS =====================
def recommend_workouts(user_id, goal, user_level, favorite_body_parts, limit=5):
    """Đề xuất bài tập dựa trên mục tiêu và sở thích"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Lấy trọng số cho các loại bài tập dựa trên mục tiêu
    goal_weights = GOAL_WEIGHTS.get(goal, GOAL_WEIGHTS["duy trì"])
    
    # Xây dựng query
    query = """
        SELECT e.exercise_id, e.name, e.body_part, e.equipment, e.target, 
               e.secondary_muscles, e.video_url,
               CASE 
                   WHEN e.body_part IN ({placeholders}) THEN 2.0
                   WHEN e.target LIKE %s THEN 1.5
                   ELSE 1.0
               END as relevance_score
        FROM exercises e
        WHERE 1=1
    """
    params = []

    if favorite_body_parts:
        # tạo placeholders động cho số nhóm cơ
        placeholders = ",".join(["%s"] * len(favorite_body_parts))
        query = query.format(placeholders=placeholders)
        query += f" AND (e.body_part IN ({placeholders}) OR e.target LIKE %s)"
        params.extend(favorite_body_parts)
        params.append(f"%{favorite_body_parts[0]}%")
    else:
        # fallback nếu không có dữ liệu
        query = query.format(placeholders="'chest','legs','back'")
        query += " AND e.body_part IN ('chest','legs','back')"
        params.append("%chest%")  # để khớp với %s trong e.target LIKE
    
    query += " ORDER BY relevance_score DESC, RAND() LIMIT %s"
    params.append(limit)

    cursor.execute(query, tuple(params))
    exercises = cursor.fetchall()
    
    # Thêm thông số tập luyện dựa trên level
    intensity = EXERCISE_INTENSITY[user_level]
    for exercise in exercises:
        exercise.update(intensity)
    
    cursor.close()
    conn.close()
    
    return exercises

def recommend_meals(user_id, goal, preferences, limit=3):
    """Đề xuất bữa ăn dựa trên mục tiêu và sở thích"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    calorie_targets = {
        "giảm cân": 1500,
        "tăng cơ": 2500,
        "duy trì": 2000,
        "tăng sức bền": 2200
    }
    target_calories = calorie_targets.get(goal, 2000)

    query = """
        SELECT f.food_id, f.name, f.calories, f.protein, f.carbs, f.fat, 
               f.category, f.goal,
               CASE 
                   WHEN f.name IN ({food_ph}) THEN 2.0
                   ELSE 1.0
               END as preference_score
        FROM foods f
        WHERE (f.goal LIKE %s OR f.goal = 'all')
    """

    params = []

    if preferences:
        favorite_foods = [pref["name"] for pref in preferences[:3]]
        food_ph = ",".join(["%s"] * len(favorite_foods))
        query = query.format(food_ph=food_ph)
        params.extend(favorite_foods)
    else:
        # fallback: không có sở thích → placeholder giả
        query = query.format(food_ph="%s")
        params.append("default")

    query += " ORDER BY preference_score DESC, RAND() LIMIT %s"
    params.append(f"%{goal}%")
    params.append(limit)

    cursor.execute(query, tuple(params))
    foods = cursor.fetchall()

    cursor.close()
    conn.close()
    return foods

def generate_weekly_plan(user_id, goal, user_level, preferences, workout_stats):
    """Tạo kế hoạch tập luyện và dinh dưỡng hàng tuần"""
    
    # Đề xuất bài tập
    recommended_workouts = recommend_workouts(
        user_id, goal, user_level, 
        workout_stats["favorite_body_parts"], 
        limit=10
    )
    
    # Đề xuất món ăn
    recommended_meals = recommend_meals(user_id, goal, preferences, limit=15)
    
    # Phân bổ bài tập theo ngày
    weekly_schedule = {
        "Thứ 2": {"focus": "chest", "workouts": [], "meals": []},
        "Thứ 3": {"focus": "back", "workouts": [], "meals": []},
        "Thứ 4": {"focus": "legs", "workouts": [], "meals": []},
        "Thứ 5": {"focus": "shoulders", "workouts": [], "meals": []},
        "Thứ 6": {"focus": "arms", "workouts": [], "meals": []},
        "Thứ 7": {"focus": "cardio", "workouts": [], "meals": []},
        "Chủ nhật": {"focus": "rest", "workouts": [], "meals": []}
    }
    
    # Phân phối bài tập theo nhóm cơ
    for workout in recommended_workouts:
        for day, schedule in weekly_schedule.items():
            if schedule["focus"] in workout["body_part"].lower():
                if len(schedule["workouts"]) < 2:  # Tối đa 2 bài/ngày
                    schedule["workouts"].append(workout)
                    break
    
    # Phân phối món ăn ngẫu nhiên
    import random
    meal_types = ["breakfast", "lunch", "dinner"]
    
    for day in weekly_schedule:
        if day != "Chủ nhật":  # Chủ nhật nghỉ ngơi
            daily_meals = random.sample(recommended_meals, min(3, len(recommended_meals)))
            weekly_schedule[day]["meals"] = [
                {"meal_type": meal_type, "food": food} 
                for meal_type, food in zip(meal_types, daily_meals)
            ]
    
    return weekly_schedule

# ===================== API ENDPOINTS =====================
@recommendation_bp.route("/recommendations/workouts", methods=["GET"])
@jwt_required()
def get_workout_recommendations():
    """API đề xuất bài tập cá nhân hóa"""
    try:
        user_id = int(get_jwt_identity())
        
        # Lấy thông tin người dùng
        profile = get_user_profile(user_id)
        if not profile:
            return jsonify({"error": "User profile not found"}), 404
        
        workout_stats = get_workout_history_stats(user_id)
        user_level = calculate_user_level(
            workout_stats["session_count"], 
            workout_stats["consistency_rate"]
        )
        
        # Đề xuất bài tập
        workouts = recommend_workouts(
            user_id, 
            profile["goal"], 
            user_level, 
            workout_stats["favorite_body_parts"]
        )
        
        return jsonify({
            "user_level": user_level,
            "goal": profile["goal"],
            "recommended_workouts": workouts,
            "stats": workout_stats
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@recommendation_bp.route("/recommendations/meals", methods=["GET"])
@jwt_required()
def get_meal_recommendations():
    """API đề xuất bữa ăn cá nhân hóa"""
    try:
        user_id = int(get_jwt_identity())
        
        profile = get_user_profile(user_id)
        if not profile:
            return jsonify({"error": "User profile not found"}), 404
        
        preferences = get_meal_preferences(user_id)
        meals = recommend_meals(user_id, profile["goal"], preferences)
        
        return jsonify({
            "goal": profile["goal"],
            "recommended_meals": meals,
            "preferences_analyzed": len(preferences) > 0
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@recommendation_bp.route("/recommendations/weekly-plan", methods=["GET"])
@jwt_required()
def get_weekly_plan():
    """API đề xuất kế hoạch tuần đầy đủ"""
    try:
        user_id = int(get_jwt_identity())
        
        profile = get_user_profile(user_id)
        if not profile:
            return jsonify({"error": "User profile not found"}), 404
        
        workout_stats = get_workout_history_stats(user_id)
        user_level = calculate_user_level(
            workout_stats["session_count"], 
            workout_stats["consistency_rate"]
        )
        
        preferences = get_meal_preferences(user_id)
        
        weekly_plan = generate_weekly_plan(
            user_id, profile["goal"], user_level, preferences, workout_stats
        )
        
        return jsonify({
            "user_level": user_level,
            "goal": profile["goal"],
            "weekly_plan": weekly_plan,
            "generated_date": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@recommendation_bp.route("/recommendations/quick-tip", methods=["GET"])
@jwt_required()
def get_quick_tip():
    """API đề xuất mẹo nhanh dựa trên hoạt động gần đây"""
    try:
        user_id = int(get_jwt_identity())
        
        profile = get_user_profile(user_id)
        workout_stats = get_workout_history_stats(user_id)
        
        tips = []
        
        # Phân tích và đưa ra gợi ý
        if workout_stats["consistency_rate"] < 0.5:
            tips.append("💡 Bạn nên tập luyện đều đặn hơn để đạt mục tiêu " + profile["goal"])
        
        if workout_stats["session_count"] == 0:
            tips.append("🎯 Hãy bắt đầu với các bài tập cơ bản phù hợp với người mới!")
        elif len(workout_stats["favorite_body_parts"]) > 0:
            tips.append(f"🌟 Bạn tập {workout_stats['favorite_body_parts'][0]} nhiều nhất. Hãy thử thêm bài tập cho nhóm cơ đối kháng!")
        
        # Gợi ý dựa trên mục tiêu
        goal_tips = {
            "giảm cân": "🔥 Kết hợp cardio và strength training để đốt calo hiệu quả",
            "tăng cơ": "💪 Tập trung vào compound exercises và đảm bảo đủ protein",
            "duy trì": "⚖️ Duy trì cân bằng giữa các nhóm cơ và chế độ ăn",
            "tăng sức bền": "🏃‍♂️ Tăng dần cường độ và thời gian tập luyện"
        }
        
        tips.append(goal_tips.get(profile["goal"], "🎉 Bạn đang trên đà tiến bộ!"))

        return jsonify({
            "tips": tips,
            "consistency_rate": workout_stats["consistency_rate"],
            "active_days": workout_stats["active_days"]
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@recommendation_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Recommendation Service",
        "timestamp": datetime.now().isoformat()
    })