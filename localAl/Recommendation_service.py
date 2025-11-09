from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, date, timedelta
import json
import math
from collections import defaultdict
import logging

recommendation_bp = Blueprint('recommendation', __name__)

# ===================== CORE RECOMMENDATION ENGINE =====================

class SmartRecommendationEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_exercise_affinity(self, user_prefs, exercise, workout_history):
        """Tính điểm tương thích bài tập với user"""
        score = 0
        reasons = []
        
        # 🎯 Priority 1: Preferred exercises
        preferred_exercises = user_prefs.get('preferred_exercises', [])
        if exercise['name'] in preferred_exercises:
            score += 30
            reasons.append("Bài tập yêu thích")
        
        # 🎯 Priority 2: Body part focus
        user_goals = user_prefs.get('goal', '').lower()
        body_part = exercise.get('body_part', '').lower()
        
        goal_body_mapping = {
            'weight_loss': ['cardio', 'fullbody', 'core'],
            'muscle_gain': ['chest', 'back', 'arms', 'shoulders', 'legs'],
            'endurance': ['cardio', 'fullbody'],
            'flexibility': ['stretch', 'yoga', 'core']
        }
        
        if user_goals in goal_body_mapping:
            if body_part in goal_body_mapping[user_goals]:
                score += 25
                reasons.append(f"Phù hợp mục tiêu {user_goals}")
        
        # 🎯 Priority 3: Equipment availability
        user_equipment = user_prefs.get('available_equipment', ['bodyweight'])
        exercise_equipment = exercise.get('equipment', 'bodyweight').lower()
        
        if exercise_equipment in user_equipment or exercise_equipment == 'bodyweight':
            score += 20
            reasons.append("Phù hợp thiết bị có sẵn")
        else:
            score -= 15
            reasons.append("Cần thiết bị đặc biệt")
        
        # 🎯 Priority 4: Experience level matching
        user_level = user_prefs.get('experience_level', 'beginner')
        exercise_level = exercise.get('level', 'beginner')
        
        level_weights = {'beginner': 1, 'intermediate': 2, 'advanced': 3}
        user_level_num = level_weights.get(user_level, 1)
        exercise_level_num = level_weights.get(exercise_level, 1)
        
        level_diff = abs(user_level_num - exercise_level_num)
        if level_diff == 0:
            score += 15
            reasons.append("Phù hợp trình độ")
        elif level_diff == 1:
            score += 5
            reasons.append("Hơi khó/dễ so với trình độ")
        else:
            score -= 10
            reasons.append("Không phù hợp trình độ")
        
        # 🎯 Priority 5: Recent performance
        recent_performance = self.analyze_recent_performance(workout_history, exercise['exercise_id'])
        score += recent_performance.get('performance_boost', 0)
        if recent_performance.get('reason'):
            reasons.append(recent_performance['reason'])
        
        # 🎯 Priority 6: Variety factor (avoid repetition)
        variety_penalty = self.calculate_variety_penalty(workout_history, exercise['exercise_id'])
        score -= variety_penalty
        
        return max(0, min(100, score)), reasons
    
    def analyze_recent_performance(self, workout_history, exercise_id):
        """Phân tích hiệu suất gần đây của bài tập"""
        recent_sessions = [s for s in workout_history if s['exercise_id'] == exercise_id][-3:]
        
        if not recent_sessions:
            return {'performance_boost': 10, 'reason': 'Bài tập mới'}
        
        # Tính progress
        if len(recent_sessions) >= 2:
            first_session = recent_sessions[0]
            last_session = recent_sessions[-1]
            
            # Check improvement in sets/reps
            if (last_session.get('sets', 0) > first_session.get('sets', 0) or
                last_session.get('reps', 0) > first_session.get('reps', 0)):
                return {'performance_boost': 15, 'reason': 'Đang cải thiện tốt'}
            else:
                return {'performance_boost': -5, 'reason': 'Cần thay đổi bài tập'}
        
        return {'performance_boost': 0, 'reason': ''}
    
    def calculate_variety_penalty(self, workout_history, exercise_id):
        """Tính penalty cho bài tập lặp lại quá nhiều"""
        recent_workouts = workout_history[-10:]  # 10 buổi gần nhất
        exercise_count = sum(1 for w in recent_workouts if w['exercise_id'] == exercise_id)
        
        if exercise_count >= 5:
            return 20  # High penalty for too much repetition
        elif exercise_count >= 3:
            return 10
        else:
            return 0
    
    def calculate_nutrition_affinity(self, user_prefs, food, nutrition_history):
        """Tính điểm tương thích thực phẩm với user"""
        score = 0
        reasons = []
        
        # 🎯 Priority 1: Diet type compatibility
        diet_type = user_prefs.get('diet_type', 'balanced')
        food_goal = food.get('goal', '').lower()
        
        diet_goal_mapping = {
            'keto': ['low_carb', 'high_fat'],
            'high_protein': ['muscle_gain', 'high_protein'],
            'low_carb': ['weight_loss', 'low_carb'],
            'balanced': ['maintenance', 'balanced'],
            'vegan': ['plant_based', 'vegan'],
            'vegetarian': ['plant_based', 'vegetarian']
        }
        
        if diet_type in diet_goal_mapping:
            if any(goal in food_goal for goal in diet_goal_mapping[diet_type]):
                score += 30
                reasons.append(f"Phù hợp chế độ ăn {diet_type}")
        
        # 🎯 Priority 2: Calorie target alignment
        user_calorie_target = user_prefs.get('daily_calorie_target', 2000)
        food_calories = food.get('calories', 0)
        
        # Ideal meal calories (assuming 3 main meals)
        ideal_meal_calories = user_calorie_target / 3
        
        calorie_diff = abs(food_calories - ideal_meal_calories)
        if calorie_diff <= 100:
            score += 25
            reasons.append("Lượng calorie phù hợp")
        elif calorie_diff <= 200:
            score += 15
            reasons.append("Lượng calorie khá phù hợp")
        else:
            score -= 10
        
        # 🎯 Priority 3: Macronutrient balance
        protein = food.get('protein', 0)
        carbs = food.get('carbs', 0)
        fat = food.get('fat', 0)
        
        # Tính macronutrient score
        macro_score = self.calculate_macro_score(user_prefs, protein, carbs, fat)
        score += macro_score
        if macro_score > 0:
            reasons.append("Cân bằng dinh dưỡng tốt")
        
        # 🎯 Priority 4: Food preferences and restrictions
        disliked_foods = user_prefs.get('disliked_foods', [])
        food_name = food.get('name', '').lower()
        
        if any(disliked in food_name for disliked in disliked_foods):
            score -= 30
            reasons.append("Thực phẩm không thích")
        
        # 🎯 Priority 5: Recent consumption frequency
        recent_penalty = self.calculate_food_variety_penalty(nutrition_history, food['food_id'])
        score -= recent_penalty
        
        return max(0, min(100, score)), reasons
    
    def calculate_macro_score(self, user_prefs, protein, carbs, fat):
        """Tính điểm cân bằng dinh dưỡng"""
        goal = user_prefs.get('goal', 'maintenance')
        
        macro_targets = {
            'weight_loss': {'protein': 0.4, 'carbs': 0.3, 'fat': 0.3},
            'muscle_gain': {'protein': 0.35, 'carbs': 0.45, 'fat': 0.2},
            'maintenance': {'protein': 0.3, 'carbs': 0.4, 'fat': 0.3},
            'endurance': {'protein': 0.25, 'carbs': 0.55, 'fat': 0.2}
        }
        
        target = macro_targets.get(goal, macro_targets['maintenance'])
        
        total = protein + carbs + fat
        if total == 0:
            return 0
        
        actual_protein_ratio = protein / total
        actual_carbs_ratio = carbs / total
        actual_fat_ratio = fat / total
        
        # Tính deviation từ target
        deviation = (abs(actual_protein_ratio - target['protein']) +
                    abs(actual_carbs_ratio - target['carbs']) +
                    abs(actual_fat_ratio - target['fat']))
        
        # Chuyển deviation thành score (0-20)
        macro_score = max(0, 20 - (deviation * 100))
        return macro_score
    
    def calculate_food_variety_penalty(self, nutrition_history, food_id):
        """Tính penalty cho thực phẩm ăn quá thường xuyên"""
        recent_meals = nutrition_history[-20:]  # 20 bữa gần nhất
        food_count = sum(1 for m in recent_meals if m['food_id'] == food_id)
        
        if food_count >= 8:
            return 20
        elif food_count >= 5:
            return 10
        elif food_count >= 3:
            return 5
        else:
            return 0

# ===================== RECOMMENDATION API ENDPOINTS =====================

recommendation_engine = SmartRecommendationEngine()

@recommendation_bp.route('/recommend/exercises', methods=['GET'])
@jwt_required()
def recommend_exercises():
    """Recommend exercises thông minh dựa trên user profile và history"""
    try:
        user_id = int(get_jwt_identity())
        
        # Parameters
        limit = int(request.args.get('limit', 10))
        body_part = request.args.get('body_part')
        goal = request.args.get('goal')
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🎯 Lấy user preferences và data
        user_data = get_user_data(cursor, user_id)
        workout_history = get_workout_history(cursor, user_id)
        
        # 🎯 Lấy tất cả exercises
        exercise_query = "SELECT * FROM exercises WHERE is_active = 1"
        query_params = []
        
        if body_part:
            exercise_query += " AND body_part = %s"
            query_params.append(body_part)
        
        cursor.execute(exercise_query, query_params)
        all_exercises = cursor.fetchall()
        
        # 🎯 Tính điểm cho từng exercise
        scored_exercises = []
        for exercise in all_exercises:
            score, reasons = recommendation_engine.calculate_exercise_affinity(
                user_data['preferences'], 
                exercise, 
                workout_history
            )
            
            scored_exercises.append({
                'exercise_id': exercise['exercise_id'],
                'name': exercise['name'],
                'body_part': exercise['body_part'],
                'equipment': exercise['equipment'],
                'level': exercise['level'],
                'video_path': exercise.get('video_path'),
                'affinity_score': score,
                'reasons': reasons,
                'recommendation_confidence': get_confidence_level(score)
            })
        
        # 🎯 Sắp xếp và lọc
        scored_exercises.sort(key=lambda x: x['affinity_score'], reverse=True)
        recommended_exercises = scored_exercises[:limit]
        
        # 🎯 Phân loại theo nhóm cơ
        categorized = categorize_exercises(recommended_exercises)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user_id": user_id,
            "user_goal": user_data['preferences'].get('goal'),
            "recommendation_engine": "AI Smart Engine",
            "total_exercises_evaluated": len(all_exercises),
            "recommended_exercises": recommended_exercises,
            "categorized_exercises": categorized,
            "workout_insights": generate_workout_insights(user_data, workout_history)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@recommendation_bp.route('/recommend/foods', methods=['GET'])
@jwt_required()
def recommend_foods():
    """Recommend foods thông minh dựa trên user profile và nutrition history"""
    try:
        user_id = int(get_jwt_identity())
        
        # Parameters
        limit = int(request.args.get('limit', 15))
        category = request.args.get('category')
        max_calories = request.args.get('max_calories', type=float)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🎯 Lấy user data
        user_data = get_user_data(cursor, user_id)
        nutrition_history = get_nutrition_history(cursor, user_id)
        
        # 🎯 Lấy tất cả foods
        food_query = "SELECT * FROM foods WHERE 1=1"
        query_params = []
        
        if category:
            food_query += " AND category = %s"
            query_params.append(category)
        
        if max_calories:
            food_query += " AND calories <= %s"
            query_params.append(max_calories)
        
        cursor.execute(food_query, query_params)
        all_foods = cursor.fetchall()
        
        # 🎯 Tính điểm cho từng food
        scored_foods = []
        for food in all_foods:
            score, reasons = recommendation_engine.calculate_nutrition_affinity(
                user_data['preferences'],
                food,
                nutrition_history
            )
            
            scored_foods.append({
                'food_id': food['food_id'],
                'name': food['name'],
                'calories': food['calories'],
                'protein': food['protein'],
                'carbs': food['carbs'],
                'fat': food['fat'],
                'category': food['category'],
                'goal': food['goal'],
                'affinity_score': score,
                'reasons': reasons,
                'recommendation_confidence': get_confidence_level(score)
            })
        
        # 🎯 Sắp xếp và lọc
        scored_foods.sort(key=lambda x: x['affinity_score'], reverse=True)
        recommended_foods = scored_foods[:limit]
        
        # 🎯 Phân loại theo bữa ăn
        meal_recommendations = generate_meal_recommendations(recommended_foods, user_data)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user_id": user_id,
            "diet_type": user_data['preferences'].get('diet_type'),
            "recommendation_engine": "AI Nutrition Engine",
            "total_foods_evaluated": len(all_foods),
            "recommended_foods": recommended_foods,
            "meal_suggestions": meal_recommendations,
            "nutrition_insights": generate_nutrition_insights(user_data, nutrition_history)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@recommendation_bp.route('/recommend/workout-plan', methods=['GET'])
@jwt_required()
def recommend_workout_plan():
    """Recommend workout plan tuần thông minh"""
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🎯 Lấy user data
        user_data = get_user_data(cursor, user_id)
        workout_history = get_workout_history(cursor, user_id)
        
        # 🎯 Generate weekly plan
        weekly_plan = generate_weekly_workout_plan(user_data, workout_history)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user_id": user_id,
            "plan_type": "weekly_workout_plan",
            "generated_at": datetime.now().isoformat(),
            "user_goal": user_data['preferences'].get('goal'),
            "fitness_level": user_data['preferences'].get('experience_level', 'beginner'),
            "weekly_plan": weekly_plan,
            "plan_insights": generate_plan_insights(user_data, weekly_plan)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@recommendation_bp.route('/recommend/nutrition-plan', methods=['GET'])
@jwt_required()
def recommend_nutrition_plan():
    """Recommend nutrition plan hàng ngày thông minh"""
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🎯 Lấy user data
        user_data = get_user_data(cursor, user_id)
        nutrition_history = get_nutrition_history(cursor, user_id)
        
        # 🎯 Generate daily nutrition plan
        daily_plan = generate_daily_nutrition_plan(user_data, nutrition_history)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user_id": user_id,
            "plan_type": "daily_nutrition_plan",
            "generated_at": datetime.now().isoformat(),
            "diet_type": user_data['preferences'].get('diet_type'),
            "calorie_target": user_data['preferences'].get('daily_calorie_target', 2000),
            "daily_plan": daily_plan,
            "shopping_list": generate_shopping_list(daily_plan)
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@recommendation_bp.route('/recommend/adaptive', methods=['GET'])
@jwt_required()
def adaptive_recommendations():
    """Adaptive recommendations dựa trên real-time data"""
    try:
        user_id = int(get_jwt_identity())
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"error": "Database connection failed"}), 500
            
        cursor = conn.cursor(dictionary=True)
        
        # 🎯 Lấy comprehensive user data
        user_data = get_comprehensive_user_data(cursor, user_id)
        
        # 🎯 Generate adaptive recommendations
        adaptive_recs = generate_adaptive_recommendations(user_data)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user_id": user_id,
            "recommendation_type": "adaptive_ai",
            "timestamp": datetime.now().isoformat(),
            "user_context": {
                "goal": user_data['preferences'].get('goal'),
                "current_mood": user_data.get('current_mood'),
                "recent_performance": user_data.get('recent_performance'),
                "sleep_quality": user_data.get('sleep_quality')
            },
            "adaptive_recommendations": adaptive_recs
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

# ===================== HELPER FUNCTIONS =====================

def get_user_data(cursor, user_id):
    """Lấy comprehensive user data"""
    # User preferences
    cursor.execute("SELECT * FROM user_preferences WHERE user_id = %s", (user_id,))
    preferences = cursor.fetchone() or {}
    
    # User profile
    cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
    profile = cursor.fetchone() or {}
    
    # User goals từ profile
    if profile and 'goal' in profile:
        preferences['goal'] = profile['goal']
    
    return {
        'preferences': preferences,
        'profile': profile
    }

def get_workout_history(cursor, user_id, days=30):
    """Lấy workout history"""
    start_date = (datetime.now() - timedelta(days=days)).date()
    
    cursor.execute("""
        SELECT sd.exercise_id, e.name, sd.sets, sd.reps, sd.calories_burned, s.date
        FROM session_details sd
        JOIN sessions s ON sd.session_id = s.session_id
        JOIN exercises e ON sd.exercise_id = e.exercise_id
        WHERE s.user_id = %s AND s.date >= %s
        ORDER BY s.date DESC
    """, (user_id, start_date))
    
    return cursor.fetchall()

def get_nutrition_history(cursor, user_id, days=30):
    """Lấy nutrition history"""
    start_date = (datetime.now() - timedelta(days=days)).date()
    
    cursor.execute("""
        SELECT md.food_id, f.name, md.quantity, md.calories, m.date
        FROM meal_details md
        JOIN meals m ON md.meal_id = m.meal_id
        JOIN foods f ON md.food_id = f.food_id
        WHERE m.user_id = %s AND m.date >= %s
        ORDER BY m.date DESC
    """, (user_id, start_date))
    
    return cursor.fetchall()

def get_comprehensive_user_data(cursor, user_id):
    """Lấy comprehensive data cho adaptive recommendations"""
    base_data = get_user_data(cursor, user_id)
    
    # Recent health metrics
    cursor.execute("""
        SELECT mood_score, stress_level, sleep_hours, heart_rate
        FROM user_metrics 
        WHERE user_id = %s 
        ORDER BY date DESC LIMIT 1
    """, (user_id,))
    health_metrics = cursor.fetchone() or {}
    
    # Recent progress
    cursor.execute("""
        SELECT weight, bmi, calories_in, calories_out
        FROM progress 
        WHERE user_id = %s 
        ORDER BY date DESC LIMIT 1
    """, (user_id,))
    progress = cursor.fetchone() or {}
    
    base_data.update({
        'current_mood': health_metrics.get('mood_score'),
        'stress_level': health_metrics.get('stress_level'),
        'sleep_quality': health_metrics.get('sleep_hours'),
        'recent_weight': progress.get('weight'),
        'calorie_balance': (progress.get('calories_in', 0) - progress.get('calories_out', 0))
    })
    
    return base_data

def get_confidence_level(score):
    """Xác định confidence level dựa trên score"""
    if score >= 80:
        return "very_high"
    elif score >= 60:
        return "high"
    elif score >= 40:
        return "medium"
    elif score >= 20:
        return "low"
    else:
        return "very_low"

def categorize_exercises(exercises):
    """Phân loại exercises theo nhóm cơ"""
    categorized = defaultdict(list)
    for exercise in exercises:
        body_part = exercise.get('body_part', 'other')
        categorized[body_part].append(exercise)
    return dict(categorized)

def generate_workout_insights(user_data, workout_history):
    """Tạo insights từ workout history"""
    insights = []
    
    if not workout_history:
        insights.append("Bắt đầu với các bài tập cơ bản phù hợp với mục tiêu của bạn")
        return insights
    
    # Phân tích frequency
    recent_workouts = [w for w in workout_history if w['date'] >= (datetime.now() - timedelta(days=7)).date()]
    if len(recent_workouts) < 3:
        insights.append("Tăng tần suất tập luyện để đạt kết quả tốt hơn")
    
    # Phân tích body part focus
    body_part_count = defaultdict(int)
    for workout in workout_history[:10]:  # 10 buổi gần nhất
        body_part_count[workout.get('body_part', 'unknown')] += 1
    
    if body_part_count:
        most_trained = max(body_part_count.items(), key=lambda x: x[1])
        least_trained = min(body_part_count.items(), key=lambda x: x[1])
        
        insights.append(f"Bạn tập {most_trained[0]} nhiều nhất")
        insights.append(f"Cân nhắc tập thêm {least_trained[0]} để cân bằng")
    
    return insights

def generate_nutrition_insights(user_data, nutrition_history):
    """Tạo insights từ nutrition history"""
    insights = []
    
    if not nutrition_history:
        insights.append("Bắt đầu ghi lại bữa ăn để nhận đề xuất chính xác hơn")
        return insights
    
    # Phân tích calorie intake
    recent_nutrition = nutrition_history[:7]  # 7 bữa gần nhất
    total_calories = sum(n['calories'] for n in recent_nutrition if n['calories'])
    avg_daily_calories = total_calories / min(len(recent_nutrition), 7)
    
    target_calories = user_data['preferences'].get('daily_calorie_target', 2000)
    
    if avg_daily_calories > target_calories + 300:
        insights.append("Lượng calorie nạp vào đang cao hơn mục tiêu")
    elif avg_daily_calories < target_calories - 300:
        insights.append("Lượng calorie nạp vào đang thấp hơn mục tiêu")
    else:
        insights.append("Lượng calorie đang phù hợp với mục tiêu")
    
    return insights

def generate_weekly_workout_plan(user_data, workout_history):
    """Tạo weekly workout plan"""
    goal = user_data['preferences'].get('goal', 'maintenance')
    level = user_data['preferences'].get('experience_level', 'beginner')
    
    # Workout templates cho các goal khác nhau
    workout_templates = {
        'weight_loss': {
            'frequency': 5,
            'focus': ['cardio', 'fullbody', 'hiit'],
            'rest_days': [2, 6]  # Wednesday, Sunday
        },
        'muscle_gain': {
            'frequency': 4,
            'focus': ['strength', 'hypertrophy'],
            'split': ['push', 'pull', 'legs', 'upper']
        },
        'maintenance': {
            'frequency': 3,
            'focus': ['balanced', 'flexibility'],
            'rest_days': [1, 3, 5, 6]
        }
    }
    
    template = workout_templates.get(goal, workout_templates['maintenance'])
    
    # Generate days
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    weekly_plan = {}
    
    for i, day in enumerate(days):
        day_number = i + 1
        
        if day_number in template.get('rest_days', []):
            weekly_plan[day] = {
                'type': 'rest',
                'description': 'Ngày nghỉ phục hồi',
                'activities': ['Nghỉ ngơi', 'Giãn cơ nhẹ', 'Đi bộ']
            }
        else:
            # Tạo workout cho ngày tập
            workout_focus = get_workout_focus_for_day(day_number, template)
            weekly_plan[day] = {
                'type': 'workout',
                'focus': workout_focus,
                'duration_minutes': 60,
                'intensity': get_intensity_level(level, goal),
                'recommended_exercises': get_recommended_exercises_for_focus(workout_focus, user_data)
            }
    
    return weekly_plan

def generate_daily_nutrition_plan(user_data, nutrition_history):
    """Tạo daily nutrition plan"""
    diet_type = user_data['preferences'].get('diet_type', 'balanced')
    calorie_target = user_data['preferences'].get('daily_calorie_target', 2000)
    
    meal_distribution = {
        'breakfast': 0.25,
        'lunch': 0.35,
        'dinner': 0.30,
        'snacks': 0.10
    }
    
    daily_plan = {}
    for meal, ratio in meal_distribution.items():
        meal_calories = calorie_target * ratio
        
        daily_plan[meal] = {
            'target_calories': round(meal_calories),
            'description': get_meal_description(meal, diet_type),
            'food_suggestions': get_food_suggestions_for_meal(meal, diet_type, meal_calories),
            'timing_recommendation': get_meal_timing(meal)
        }
    
    return daily_plan

def generate_adaptive_recommendations(user_data):
    """Tạo adaptive recommendations dựa trên real-time context"""
    recommendations = []
    
    # Dựa trên mood và energy
    current_mood = user_data.get('current_mood')
    sleep_quality = user_data.get('sleep_quality')
    stress_level = user_data.get('stress_level')
    
    if current_mood and current_mood < 5:
        recommendations.append({
            'type': 'workout_adjustment',
            'message': 'Tâm trạng thấp, đề xuất tập nhẹ hoặc yoga',
            'priority': 'high',
            'action': 'Giảm cường độ tập, tập trung vào các bài tập giảm stress'
        })
    
    if sleep_quality and sleep_quality < 6:
        recommendations.append({
            'type': 'recovery',
            'message': 'Ngủ không đủ giấc, cần chú ý phục hồi',
            'priority': 'medium',
            'action': 'Tập nhẹ, bổ sung thực phẩm hỗ trợ giấc ngủ'
        })
    
    if stress_level and stress_level > 7:
        recommendations.append({
            'type': 'stress_management',
            'message': 'Mức độ stress cao',
            'priority': 'high',
            'action': 'Tập meditation, đi bộ, tránh tập nặng'
        })
    
    # Dựa trên calorie balance
    calorie_balance = user_data.get('calorie_balance', 0)
    if calorie_balance > 500:
        recommendations.append({
            'type': 'nutrition_adjustment',
            'message': 'Calorie nạp vào đang cao',
            'priority': 'medium',
            'action': 'Điều chỉnh khẩu phần ăn, tăng cường rau xanh'
        })
    
    return recommendations

def get_workout_focus_for_day(day_number, template):
    """Xác định focus cho từng ngày tập"""
    focuses = template.get('focus', ['fullbody'])
    return focuses[day_number % len(focuses)]

def get_intensity_level(experience_level, goal):
    """Xác định intensity level"""
    base_intensity = {'beginner': 'low', 'intermediate': 'medium', 'advanced': 'high'}
    intensity_boost = {'weight_loss': 1, 'muscle_gain': 1, 'maintenance': 0}
    
    level_score = ['low', 'medium', 'high'].index(base_intensity.get(experience_level, 'low'))
    boosted_score = min(2, level_score + intensity_boost.get(goal, 0))
    
    return ['low', 'medium', 'high'][boosted_score]

def get_recommended_exercises_for_focus(focus, user_data):
    """Lấy exercises recommendation cho focus cụ thể"""
    # Placeholder - trong thực tế sẽ query database
    focus_exercises = {
        'cardio': ['Chạy bộ', 'Nhảy dây', 'Burpees'],
        'strength': ['Squat', 'Deadlift', 'Bench Press'],
        'hiit': ['Mountain Climbers', 'Jump Squats', 'High Knees']
    }
    return focus_exercises.get(focus, ['Full Body Workout'])

def get_meal_description(meal, diet_type):
    """Mô tả bữa ăn"""
    descriptions = {
        'breakfast': f'Bữa sáng {diet_type} giàu năng lượng',
        'lunch': f'Bữa trưa {diet_type} cân bằng dinh dưỡng',
        'dinner': f'Bữa tối {diet_type} nhẹ nhàng',
        'snacks': f'Đồ ăn nhẹ {diet_type} lành mạnh'
    }
    return descriptions.get(meal, 'Bữa ăn cân bằng')

def get_food_suggestions_for_meal(meal, diet_type, target_calories):
    """Đề xuất thực phẩm cho bữa ăn"""
    # Placeholder - trong thực tế sẽ query database
    meal_suggestions = {
        'breakfast': ['Yến mạch', 'Trứng', 'Sữa chua Hy Lạp'],
        'lunch': ['Ức gà', 'Gạo lứt', 'Rau xanh'],
        'dinner': ['Cá hồi', 'Rau củ hấp', 'Quả bơ'],
        'snacks': ['Hạt dinh dưỡng', 'Trái cây', 'Protein shake']
    }
    return meal_suggestions.get(meal, ['Thực phẩm lành mạnh'])

def get_meal_timing(meal):
    """Đề xuất thời gian ăn"""
    timings = {
        'breakfast': '7:00 - 8:00 AM',
        'lunch': '12:00 - 1:00 PM',
        'dinner': '6:00 - 7:00 PM',
        'snacks': '10:00 AM & 4:00 PM'
    }
    return timings.get(meal, 'Theo lịch trình phù hợp')

def generate_shopping_list(daily_plan):
    """Tạo shopping list từ nutrition plan"""
    shopping_items = set()
    
    for meal in daily_plan.values():
        for suggestion in meal.get('food_suggestions', []):
            shopping_items.add(suggestion)
    
    return list(shopping_items)

def generate_plan_insights(user_data, weekly_plan):
    """Tạo insights cho workout plan"""
    insights = []
    
    workout_days = sum(1 for day in weekly_plan.values() if day['type'] == 'workout')
    insights.append(f"Kế hoạch {workout_days} ngày tập/tuần phù hợp với mục tiêu {user_data['preferences'].get('goal')}")
    
    if workout_days >= 5:
        insights.append("Lịch tập dày đảm bảo đủ ngày nghỉ để phục hồi")
    elif workout_days <= 2:
        insights.append("Có thể tăng thêm ngày tập để đạt kết quả tốt hơn")
    
    return insights

# ===================== HEALTH CHECK =====================
@recommendation_bp.route('/recommend/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'Advanced_Recommendation_Service',
        'version': '3.0.0',
        'features': [
            'AI Exercise Recommendations',
            'Smart Nutrition Planning', 
            'Adaptive Workout Plans',
            'Real-time Personalization',
            'Comprehensive Analytics'
        ],
        'timestamp': datetime.now().isoformat()
    })