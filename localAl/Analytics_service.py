from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import date, timedelta, datetime
import json

analytics_bp = Blueprint('analytics', __name__)

def parse_json_field(field_value):
    """Parse JSON field từ database"""
    if not field_value:
        return []
    try:
        if isinstance(field_value, str) and field_value.startswith('['):
            return json.loads(field_value)
        return [field_value]
    except:
        return []

@analytics_bp.route('/analytics', methods=['GET'])
@jwt_required()
def get_analytics():
    """Tổng hợp dữ liệu analytics: calories, workouts, progress"""
    user_id = get_jwt_identity()
    
    # Đọc tham số tuần (week và year)
    week_str = request.args.get('week')
    year_str = request.args.get('year')
    
    if week_str:
        try:
            if '-' in week_str:
                year = int(week_str.split('-')[0])
                week_num = int(week_str.split('-')[1])
            else:
                week_num = int(week_str)
                year = int(year_str) if year_str else date.today().isocalendar()[0]
        except ValueError:
            return jsonify({"message": "Tham số tuần không hợp lệ"}), 400
    else:
        # Mặc định dùng tuần hiện tại
        iso = date.today().isocalendar()
        year = iso[0]
        week_num = iso[1]
    
    # Xác định khoảng thời gian tuần (Monday -> Sunday)
    try:
        monday_date = date.fromisocalendar(year, week_num, 1)
        sunday_date = date.fromisocalendar(year, week_num, 7)
    except Exception:
        return jsonify({"message": "Tuần hoặc năm không hợp lệ"}), 400
    
    monday_str = monday_date.isoformat()
    sunday_str = sunday_date.isoformat()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. 📊 TÍNH CALORIES TỪ MEALS VÀ SESSIONS
        # Calories nạp từ meals (dùng total_calories từ bảng meals)
        cursor.execute("""
            SELECT SUM(total_calories) as total_intake
            FROM meals 
            WHERE user_id = %s AND date BETWEEN %s AND %s
        """, (user_id, monday_str, sunday_str))
        intake_result = cursor.fetchone()
        total_intake = intake_result['total_intake'] or 0
        
        # Calories đốt từ sessions (dùng total_calories từ bảng sessions)
        cursor.execute("""
            SELECT SUM(total_calories) as total_burned
            FROM sessions 
            WHERE user_id = %s AND date BETWEEN %s AND %s
        """, (user_id, monday_str, sunday_str))
        burned_result = cursor.fetchone()
        total_burned = burned_result['total_burned'] or 0
        
        # 2. 🏋️ DỮ LIỆU WORKOUT THEO NGÀY (từ sessions)
        cursor.execute("""
            SELECT date, 
                   total_calories as daily_burned,
                   duration_min as total_duration
            FROM sessions 
            WHERE user_id = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """, (user_id, monday_str, sunday_str))
        daily_workouts = cursor.fetchall()
        
        # 3. 🥗 DỮ LIỆU NUTRITION THEO NGÀY (từ meals)
        cursor.execute("""
            SELECT date, 
                   SUM(total_calories) as daily_intake,
                   COUNT(meal_id) as meals_count
            FROM meals 
            WHERE user_id = %s AND date BETWEEN %s AND %s
            GROUP BY date
            ORDER BY date
        """, (user_id, monday_str, sunday_str))
        daily_nutrition = cursor.fetchall()
        
        # 4. 📈 PROGRESS TRACKING (từ progress)
        cursor.execute("""
            SELECT date, weight, body_fat_pct, calories_in, calories_out
            FROM progress 
            WHERE user_id = %s AND date BETWEEN %s AND %s
            ORDER BY date
        """, (user_id, monday_str, sunday_str))
        progress_data = cursor.fetchall()
        
        # 5. 🎯 GOAL & TARGETS TỪ USER_PREFERENCES
        cursor.execute("""
            SELECT diet_type, activity_level, preferred_exercises, health_conditions
            FROM user_preferences 
            WHERE user_id = %s
        """, (user_id,))
        user_prefs = cursor.fetchone()
        
        # Tính target calories dựa trên diet_type và activity_level
        target_intake = 2000  # Mặc định
        target_burn = 450     # Mặc định
        
        if user_prefs:
            # Điều chỉnh target intake theo diet_type
            if user_prefs['diet_type'] == 'keto':
                target_intake = 1800
                target_burn = 500
            elif user_prefs['diet_type'] == 'high_protein':
                target_intake = 2200
                target_burn = 400
            elif user_prefs['diet_type'] == 'low_carb':
                target_intake = 1700
                target_burn = 480
            
            # Điều chỉnh theo activity_level
            if user_prefs['activity_level'] == 'high':
                target_intake += 300
                target_burn += 100
            elif user_prefs['activity_level'] == 'low':
                target_intake -= 300
                target_burn -= 100
        
        # 6. 📅 TÍNH COMPLETION RATE THEO NGÀY
        daily_completion = {}
        current_date = monday_date
        
        while current_date <= sunday_date:
            date_str = current_date.isoformat()
            
            # Tìm workout data cho ngày này
            workout_today = next((w for w in daily_workouts if w['date'].isoformat() == date_str), None)
            nutrition_today = next((n for n in daily_nutrition if n['date'].isoformat() == date_str), None)
            
            # Tính completion rate
            workout_score = 1 if workout_today and workout_today['daily_burned'] and workout_today['daily_burned'] > 0 else 0
            nutrition_score = 1 if nutrition_today and nutrition_today['daily_intake'] and nutrition_today['daily_intake'] > 0 else 0
            
            completion_rate = ((workout_score + nutrition_score) / 2) * 100
            
            daily_completion[date_str] = {
                "completion_rate": round(completion_rate, 1),
                "workout_done": bool(workout_score),
                "nutrition_logged": bool(nutrition_score),
                "calories_burned": float(workout_today['daily_burned']) if workout_today else 0,
                "calories_intake": float(nutrition_today['daily_intake']) if nutrition_today else 0,
                "workout_duration": workout_today['total_duration'] if workout_today else 0,
                "meals_count": nutrition_today['meals_count'] if nutrition_today else 0
            }
            
            current_date += timedelta(days=1)
        
        # 7. 📊 TỔNG HỢP KẾT QUẢ
        result = {
            "period": {
                "week": week_num,
                "year": year,
                "start_date": monday_str,
                "end_date": sunday_str
            },
            "summary": {
                "total_calories_intake": float(total_intake),
                "total_calories_burned": float(total_burned),
                "net_calories": float(total_intake - total_burned),
                "workout_sessions": len(daily_workouts),
                "nutrition_days": len(daily_nutrition),
                "progress_entries": len(progress_data)
            },
            "targets": {
                "daily_calorie_intake": target_intake,
                "daily_calorie_burn": target_burn,
                "weekly_workout_goal": 5,
                "achieved_workouts": len(daily_workouts)
            },
            "user_preferences": {
                "diet_type": user_prefs['diet_type'] if user_prefs else None,
                "activity_level": user_prefs['activity_level'] if user_prefs else None,
                "preferred_exercises": parse_json_field(user_prefs['preferred_exercises']) if user_prefs else [],
                "health_conditions": parse_json_field(user_prefs['health_conditions']) if user_prefs else []
            } if user_prefs else {},
            "daily_completion": daily_completion,
            "workout_analytics": [
                {
                    "date": w['date'].isoformat() if isinstance(w['date'], date) else w['date'],
                    "calories_burned": float(w['daily_burned'] or 0),
                    "duration_minutes": w['total_duration'] or 0
                } for w in daily_workouts
            ],
            "nutrition_analytics": [
                {
                    "date": n['date'].isoformat() if isinstance(n['date'], date) else n['date'],
                    "calories": float(n['daily_intake'] or 0),
                    "meals_count": n['meals_count'] or 0
                } for n in daily_nutrition
            ],
            "progress_analytics": [
                {
                    "date": p['date'].isoformat() if isinstance(p['date'], date) else p['date'],
                    "weight": float(p['weight'] or 0),
                    "body_fat_pct": float(p['body_fat_pct'] or 0),
                    "calories_in": float(p['calories_in'] or 0),
                    "calories_out": float(p['calories_out'] or 0)
                } for p in progress_data
            ]
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@analytics_bp.route('/analytics/overview', methods=['GET'])
@jwt_required()
def get_analytics_overview():
    """Lấy tổng quan analytics (30 ngày gần nhất)"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Tính ngày bắt đầu (30 ngày trước)
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # 📊 TỔNG HỢP 30 NGÀY
        # Total workouts từ sessions
        cursor.execute("""
            SELECT COUNT(session_id) as total_workouts,
                   SUM(duration_min) as total_workout_minutes,
                   SUM(total_calories) as total_calories_burned
            FROM sessions 
            WHERE user_id = %s AND date BETWEEN %s AND %s
        """, (user_id, start_date, end_date))
        workout_summary = cursor.fetchone()
        
        # Total nutrition từ meals
        cursor.execute("""
            SELECT COUNT(meal_id) as total_meals,
                   SUM(total_calories) as total_calories_intake
            FROM meals 
            WHERE user_id = %s AND date BETWEEN %s AND %s
        """, (user_id, start_date, end_date))
        nutrition_summary = cursor.fetchone()
        
        # Progress changes từ progress
        cursor.execute("""
            SELECT 
                (SELECT weight FROM progress WHERE user_id = %s AND date <= %s ORDER BY date DESC LIMIT 1) as latest_weight,
                (SELECT weight FROM progress WHERE user_id = %s AND date >= %s ORDER BY date ASC LIMIT 1) as start_weight
        """, (user_id, end_date, user_id, start_date))
        progress_summary = cursor.fetchone()
        
        weight_change = 0
        if progress_summary and progress_summary['latest_weight'] and progress_summary['start_weight']:
            weight_change = progress_summary['latest_weight'] - progress_summary['start_weight']
        
        # Activity consistency
        cursor.execute("""
            SELECT COUNT(DISTINCT date) as active_days
            FROM (
                SELECT date FROM sessions WHERE user_id = %s AND date BETWEEN %s AND %s
                UNION 
                SELECT date FROM meals WHERE user_id = %s AND date BETWEEN %s AND %s
            ) AS combined_activities
        """, (user_id, start_date, end_date, user_id, start_date, end_date))
        activity_result = cursor.fetchone()
        active_days = activity_result['active_days'] if activity_result else 0
        
        result = {
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": 30
            },
            "overview": {
                "total_workouts": workout_summary['total_workouts'] or 0,
                "total_workout_minutes": workout_summary['total_workout_minutes'] or 0,
                "total_calories_burned": float(workout_summary['total_calories_burned'] or 0),
                "total_meals_logged": nutrition_summary['total_meals'] or 0,
                "total_calories_intake": float(nutrition_summary['total_calories_intake'] or 0),
                "weight_change": float(weight_change),
                "active_days": active_days,
                "consistency_rate": round((active_days / 30) * 100, 1),
                "average_daily_calories": round(float((nutrition_summary['total_calories_intake'] or 0) / 30), 1),
                "workout_frequency": round((workout_summary['total_workouts'] or 0) / 30 * 7, 1)
            }
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@analytics_bp.route('/analytics/health-metrics', methods=['GET'])
@jwt_required()
def get_health_metrics():
    """Lấy health metrics từ bảng progress"""
    user_id = get_jwt_identity()
    
    # Tham số số ngày (mặc định 7 ngày)
    days = int(request.args.get('days', 7))
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        start_date = date.today() - timedelta(days=days)
        
        cursor.execute("""
            SELECT date, weight, body_fat_pct, calories_in, calories_out, bmi
            FROM progress 
            WHERE user_id = %s AND date >= %s
            ORDER BY date DESC
        """, (user_id, start_date))
        
        health_data = cursor.fetchall()
        
        result = {
            "period_days": days,
            "health_metrics": [
                {
                    "date": h['date'].isoformat() if isinstance(h['date'], date) else h['date'],
                    "weight": float(h['weight'] or 0),
                    "body_fat_pct": float(h['body_fat_pct'] or 0),
                    "calories_in": float(h['calories_in'] or 0),
                    "calories_out": float(h['calories_out'] or 0),
                    "bmi": float(h['bmi'] or 0)
                } for h in health_data
            ],
            "summary": {
                "entries_count": len(health_data),
                "latest_weight": float(health_data[0]['weight']) if health_data else 0,
                "latest_bmi": float(health_data[0]['bmi']) if health_data else 0
            }
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()