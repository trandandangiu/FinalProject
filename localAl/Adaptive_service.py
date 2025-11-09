from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime, date, timedelta
import json

adaptive_bp = Blueprint('adaptive', __name__)

@adaptive_bp.route('/adaptive', methods=['GET'])
@jwt_required()
def check_adaptive():
    """Kiểm tra hiệu suất tập luyện và đưa ra gợi ý thích ứng"""
    user_id = get_jwt_identity()
    
    # Xác định tuần hiện tại
    today = date.today()
    iso_year, iso_week, iso_weekday = today.isocalendar()
    
    # Xác định ngày đầu tuần (thứ 2) và cuối tuần (CN)
    week_start_date = date.fromisocalendar(iso_year, iso_week, 1)  # Monday
    week_end_date = date.fromisocalendar(iso_year, iso_week, 7)    # Sunday
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # 1. 📊 LẤY DỮ LIỆU WORKOUTS TRONG TUẦN (từ sessions)
        cursor.execute("""
            SELECT date, total_calories as daily_burned, duration_min
            FROM sessions 
            WHERE user_id=%s AND date BETWEEN %s AND %s
            ORDER BY date
        """, (user_id, week_start_date, week_end_date))
        workout_data = cursor.fetchall()
        
        # 2. 🎯 LẤY MỤC TIÊU & PREFERENCES CỦA USER
        cursor.execute("""
            SELECT diet_type, activity_level, preferred_exercises, health_conditions
            FROM user_preferences 
            WHERE user_id=%s
        """, (user_id,))
        user_prefs = cursor.fetchone()
        
        # 3. 📈 LẤY DỮ LIỆU PROGRESS GẦN ĐÂY
        cursor.execute("""
            SELECT date, weight, calories_in, calories_out
            FROM progress 
            WHERE user_id=%s AND date >= %s
            ORDER BY date DESC
            LIMIT 7
        """, (user_id, (today - timedelta(days=30)).isoformat()))
        progress_data = cursor.fetchall()
        
        # 4. 🏥 LẤY HEALTH METRICS GẦN ĐÂY
        cursor.execute("""
            SELECT date, mood_score, stress_level, sleep_hours
            FROM user_metrics 
            WHERE user_id=%s AND date >= %s
            ORDER BY date DESC
            LIMIT 7
        """, (user_id, (today - timedelta(days=14)).isoformat()))
        health_data = cursor.fetchall()
        
        # 5. 🗓️ LẤY PLAN HIỆN TẠI - SỬA: Dùng cấu trúc thực tế của bảng plans
        cursor.execute("""
            SELECT plan_id, plan_name, plan_type, goal, rec_type, content, created_at
            FROM plans 
            WHERE user_id=%s
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        current_plan = cursor.fetchone()
        
        # 6. 🎯 THIẾT LẬP TARGETS DỰA TRÊN USER PREFERENCES
        if user_prefs:
            if user_prefs['diet_type'] == 'keto':
                target_calories_burn = 500
                target_workouts = 5
            elif user_prefs['diet_type'] == 'high_protein':
                target_calories_burn = 400
                target_workouts = 4
            elif user_prefs['diet_type'] == 'low_carb':
                target_calories_burn = 480
                target_workouts = 5
            else:  # balanced
                target_calories_burn = 450
                target_workouts = 4
            
            # Điều chỉnh theo activity_level
            if user_prefs['activity_level'] == 'high':
                target_calories_burn += 100
                target_workouts += 1
            elif user_prefs['activity_level'] == 'low':
                target_calories_burn -= 100
                target_workouts -= 1
        else:
            target_calories_burn = 450
            target_workouts = 4
        
        # 7. 📊 TÍNH TOÁN HIỆU SUẤT
        total_calories_burned = sum(w['daily_burned'] or 0 for w in workout_data)
        total_workouts = len(workout_data)
        total_workout_minutes = sum(w['duration_min'] or 0 for w in workout_data)
        
        # Tính completion rate theo ngày
        daily_completion = {}
        current_date = week_start_date
        
        while current_date <= week_end_date:
            date_str = current_date.isoformat()
            # Sửa: Convert cả workout date thành string để so sánh
            workout_today = next((w for w in workout_data if str(w['date']) == date_str), None)
            
            if workout_today and workout_today['daily_burned']:
                completion_rate = min((workout_today['daily_burned'] / target_calories_burn) * 100, 100)
            else:
                completion_rate = 0
            
            daily_completion[date_str] = {
                "completion_rate": round(completion_rate, 1),
                "workout_done": bool(workout_today),
                "calories_burned": workout_today['daily_burned'] if workout_today else 0,
                "duration_minutes": workout_today['duration_min'] if workout_today else 0
            }
            
            current_date += timedelta(days=1)
        
        # Tính trung bình completion rate (performance score)
        active_days = sum(1 for day in daily_completion.values() if day['workout_done'])
        avg_completion_rate = sum(day['completion_rate'] for day in daily_completion.values()) / 7
        
        # Khởi tạo các biến health metrics
        avg_mood = avg_stress = avg_sleep = 0
        
        if health_data:
            avg_mood = sum(h['mood_score'] or 0 for h in health_data) / len(health_data)
            avg_stress = sum(h['stress_level'] or 0 for h in health_data) / len(health_data)
            avg_sleep = sum(h['sleep_hours'] or 0 for h in health_data) / len(health_data)
        
        # 8. 🧠 PHÂN TÍCH & ĐƯA RA GỢI Ý
        suggestions = []
        change_reasons = []
        ai_decisions = []
        adaptive_action = "maintain"  # Mặc định: duy trì
        
        # Phân tích hiệu suất workout
        if avg_completion_rate < 50:
            change_reasons.append(f"low performance ({avg_completion_rate:.1f}%)")
            suggestions.append(f"Hiệu suất tập luyện tuần này thấp ({avg_completion_rate:.1f}%). Cân nhắc giảm cường độ hoặc tăng tần suất.")
            ai_decisions.append("Reduced intensity")
            adaptive_action = "reduce_intensity"
        elif avg_completion_rate > 120:
            change_reasons.append(f"high performance ({avg_completion_rate:.1f}%)")
            suggestions.append(f"Bạn đang tập luyện rất tích cực ({avg_completion_rate:.1f}%). Có thể tăng cường độ nhẹ cho tuần tới.")
            ai_decisions.append("Increased intensity")
            adaptive_action = "increase_intensity"
        
        # Phân tích dựa trên số buổi tập
        if total_workouts < target_workouts - 2:
            change_reasons.append(f"missed {target_workouts - total_workouts} sessions")
            suggestions.append(f"Bạn mới tập {total_workouts}/{target_workouts} buổi. Cố gắng duy trì đều đặn hơn.")
            ai_decisions.append("Adjusted frequency")
        elif total_workouts >= target_workouts:
            suggestions.append(f"Xuất sắc! Bạn đã hoàn thành {total_workouts} buổi tập.")
        
        # Phân tích health metrics
        if health_data:
            if avg_mood < 5:
                change_reasons.append("low mood")
                suggestions.append("Tâm trạng có vẻ thấp. Thử các bài tập nhẹ nhàng như yoga hoặc đi bộ.")
                ai_decisions.append("Added low-intensity workouts")
            if avg_stress > 6:
                change_reasons.append("high stress")
                suggestions.append("Mức độ stress cao. Cân nhắc các bài tập giảm stress như thiền ho stretching.")
                ai_decisions.append("Added stress-reduction exercises")
            if avg_sleep < 6:
                change_reasons.append("insufficient sleep")
                suggestions.append("Ngủ không đủ giấc có thể ảnh hưởng đến hiệu suất tập luyện.")
                ai_decisions.append("Adjusted recovery time")
        
        # Phân tích progress
        if len(progress_data) >= 2:
            latest_weight = progress_data[0]['weight'] or 0
            previous_weight = progress_data[-1]['weight'] or 0
            
            if latest_weight > 0 and previous_weight > 0:
                weight_change = latest_weight - previous_weight
                if weight_change > 2:  # Tăng 2kg
                    change_reasons.append("significant weight gain")
                    suggestions.append("Cân nặng tăng đáng kể. Cân nhắc tăng cường độ cardio.")
                    ai_decisions.append("Increased cardio intensity")
                elif weight_change < -2:  # Giảm 2kg
                    change_reasons.append("significant weight loss")
                    suggestions.append("Cân nặng giảm nhiều. Đảm bảo dinh dưỡng đầy đủ để duy trì năng lượng.")
                    ai_decisions.append("Adjusted nutrition plan")
        
        # 9. 💾 LƯU ADAPTIVE LOG VỚI CẤU TRÚC DB THỰC TẾ
        main_suggestion = " ".join(suggestions) if suggestions else f"Duy trì hiện tại. Hiệu suất: {avg_completion_rate:.1f}%"
        change_reason_text = ", ".join(change_reasons) if change_reasons else "No significant changes needed"
        ai_decision_text = ", ".join(ai_decisions) if ai_decisions else "Maintain current plan"
        
        # Kiểm tra xem đã có log cho tuần này chưa
        cursor.execute("""
            SELECT log_id FROM adaptive_logs 
            WHERE user_id=%s AND week_start=%s
        """, (user_id, week_start_date))
        existing_log = cursor.fetchone()
        
        old_plan_id = current_plan['plan_id'] if current_plan else None
        
        if existing_log:
            # Update existing log
            cursor.execute("""
                UPDATE adaptive_logs 
                SET change_reason=%s, performance_score=%s, ai_decision=%s
                WHERE user_id=%s AND week_start=%s
            """, (change_reason_text, round(avg_completion_rate, 1), ai_decision_text, 
                  user_id, week_start_date))
        else:
            # Insert new log
            cursor.execute("""
                INSERT INTO adaptive_logs 
                (user_id, week_start, old_plan_id, change_reason, performance_score, ai_decision)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, week_start_date, old_plan_id, change_reason_text, 
                  round(avg_completion_rate, 1), ai_decision_text))
        
        conn.commit()
        
        # 10. 📋 TẠO RESPONSE
        result = {
            "period": {
                "week": iso_week,
                "year": iso_year,
                "week_start": week_start_date.isoformat(),
                "week_end": week_end_date.isoformat()
            },
            "performance_summary": {
                "total_workouts": total_workouts,
                "total_calories_burned": float(total_calories_burned),
                "total_workout_minutes": total_workout_minutes,
                "active_days": active_days,
                "performance_score": round(avg_completion_rate, 1),
                "target_workouts": target_workouts,
                "target_calories_burn": target_calories_burn
            },
            "adaptive_analysis": {
                "adaptive_action": adaptive_action,
                "main_suggestion": main_suggestion,
                "change_reasons": change_reasons,
                "ai_decisions": ai_decisions,
                "health_considerations": {
                    "avg_mood_score": round(avg_mood, 1) if health_data else "N/A",
                    "avg_stress_level": round(avg_stress, 1) if health_data else "N/A", 
                    "avg_sleep_hours": round(avg_sleep, 1) if health_data else "N/A"
                }
            },
            "current_plan": {
                "plan_id": current_plan['plan_id'] if current_plan else None,
                "plan_name": current_plan['plan_name'] if current_plan else "No active plan",
                "plan_type": current_plan['plan_type'] if current_plan else None,
                "goal": current_plan['goal'] if current_plan else None,
                "rec_type": current_plan['rec_type'] if current_plan else None
            },
            "daily_completion": daily_completion
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@adaptive_bp.route('/adaptive/logs', methods=['GET'])
@jwt_required()
def get_adaptive_logs():
    """Lấy danh sách các gợi ý thích ứng trước đây"""
    user_id = get_jwt_identity()
    
    # Tham số phân trang
    limit = int(request.args.get('limit', 10))
    offset = int(request.args.get('offset', 0))
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT log_id, week_start, old_plan_id, new_plan_id, change_reason, 
                   performance_score, ai_decision, created_at
            FROM adaptive_logs 
            WHERE user_id=%s 
            ORDER BY week_start DESC
            LIMIT %s OFFSET %s
        """, (user_id, limit, offset))
        
        logs = cursor.fetchall()
        
        # Đếm tổng số logs
        cursor.execute("SELECT COUNT(*) as total FROM adaptive_logs WHERE user_id=%s", (user_id,))
        total_count = cursor.fetchone()['total']
        
        return jsonify({
            "logs": [
                {
                    "id": log["log_id"],
                    "week_start": log["week_start"].isoformat() if isinstance(log["week_start"], date) else log["week_start"],
                    "old_plan_id": log["old_plan_id"],
                    "new_plan_id": log["new_plan_id"],
                    "change_reason": log["change_reason"],
                    "performance_score": float(log["performance_score"]) if log["performance_score"] else None,
                    "ai_decision": log["ai_decision"],
                    "created_at": log["created_at"].isoformat() if isinstance(log["created_at"], datetime) else log["created_at"]
                } for log in logs
            ],
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + len(logs)) < total_count
            }
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@adaptive_bp.route('/adaptive/insights', methods=['GET'])
@jwt_required()
def get_adaptive_insights():
    """Lấy insights và trends từ adaptive logs"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Lấy logs 8 tuần gần nhất
        cursor.execute("""
            SELECT week_start, change_reason, performance_score, ai_decision, created_at
            FROM adaptive_logs 
            WHERE user_id=%s 
            ORDER BY week_start DESC
            LIMIT 8
        """, (user_id,))
        
        recent_logs = cursor.fetchall()
        
        if not recent_logs:
            return jsonify({"message": "Chưa có đủ dữ liệu để phân tích"}), 404
        
        # Tính toán insights
        performance_scores = [log['performance_score'] or 0 for log in recent_logs]
        avg_performance = sum(performance_scores) / len(performance_scores)
        
        # Phân tích reasons
        all_reasons = []
        for log in recent_logs:
            if log['change_reason']:
                reasons = [r.strip() for r in log['change_reason'].split(',')]
                all_reasons.extend(reasons)
        
        reason_counts = {}
        for reason in all_reasons:
            if reason and reason != "No significant changes needed":
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        # Xác định trend
        if len(recent_logs) >= 2:
            current_perf = recent_logs[0]['performance_score'] or 0
            previous_perf = recent_logs[1]['performance_score'] or 0
            performance_trend = "improving" if current_perf > previous_perf else "declining" if current_perf < previous_perf else "stable"
        else:
            performance_trend = "insufficient_data"
        
        # Gợi ý dựa trên insights
        insights = []
        if avg_performance < 60:
            insights.append("Hiệu suất trung bình thấp. Cân nhắc điều chỉnh lịch tập hoặc mục tiêu.")
        elif avg_performance > 100:
            insights.append("Hiệu suất xuất sắc! Bạn có thể thử thách bản thân với mục tiêu cao hơn.")
        
        if reason_counts.get('low performance', 0) >= 3:
            insights.append("Thường xuyên có hiệu suất thấp. Cân nhắc đánh giá lại kế hoạch tập luyện.")
        
        if reason_counts.get('high stress', 0) >= 2:
            insights.append("Stress thường xuyên cao. Cân nhắc thêm các bài tập giảm stress.")
        
        result = {
            "analysis_period": f"{len(recent_logs)} tuần gần nhất",
            "performance_insights": {
                "average_performance_score": round(avg_performance, 1),
                "performance_trend": performance_trend,
                "best_week": max(performance_scores),
                "worst_week": min(performance_scores)
            },
            "common_issues": {
                "most_common_reason": max(reason_counts, key=reason_counts.get) if reason_counts else "No issues",
                "issue_distribution": reason_counts
            },
            "recommendations": insights,
            "recent_weeks": [
                {
                    "week_start": log['week_start'].isoformat() if isinstance(log['week_start'], date) else log['week_start'],
                    "performance_score": float(log['performance_score']) if log['performance_score'] else 0,
                    "change_reason": log['change_reason'],
                    "ai_decision": log['ai_decision']
                } for log in recent_logs
            ]
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()