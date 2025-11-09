from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import date, datetime, timedelta

metrics_bp = Blueprint('metrics', __name__)

@metrics_bp.route('/metrics', methods=['GET'])
@jwt_required()
def get_metrics():
    """Lấy dữ liệu health metrics theo ngày, tuần hoặc tất cả"""
    user_id = get_jwt_identity()
    
    # Lấy tham số truy vấn
    date_str = request.args.get('date')
    week_str = request.args.get('week')
    year_str = request.args.get('year')
    days_str = request.args.get('days', '7')  # Mặc định 7 ngày
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        if date_str:
            # 📅 Dữ liệu một ngày cụ thể từ bảng user_metrics
            cursor.execute("""
                SELECT date, heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps
                FROM user_metrics 
                WHERE user_id=%s AND date=%s
            """, (user_id, date_str))
            row = cursor.fetchone()
            
            if row is None:
                return jsonify({"message": "Không có dữ liệu cho ngày này"}), 404
            
            data = {
                "date": row["date"].isoformat() if isinstance(row["date"], date) else row["date"],
                "heart_rate": row["heart_rate"],
                "sleep_hours": row["sleep_hours"],
                "mood_score": row["mood_score"],
                "hydration_level": row["hydration_level"],
                "stress_level": row["stress_level"],
                "steps": row["steps"]
            }
            return jsonify(data), 200
            
        elif week_str:
            # 📊 Dữ liệu theo tuần
            try:
                if '-' in week_str:
                    year, week_num = map(int, week_str.split('-'))
                else:
                    week_num = int(week_str)
                    year = int(year_str) if year_str else date.today().isocalendar()[0]
            except ValueError:
                return jsonify({"message": "Tham số tuần không hợp lệ"}), 400
            
            try:
                monday_date = date.fromisocalendar(year, week_num, 1)
                sunday_date = date.fromisocalendar(year, week_num, 7)
            except Exception:
                return jsonify({"message": "Tuần hoặc năm không hợp lệ"}), 400
            
            monday_str = monday_date.isoformat()
            sunday_str = sunday_date.isoformat()
            
            cursor.execute("""
                SELECT date, heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps
                FROM user_metrics 
                WHERE user_id=%s AND date BETWEEN %s AND %s 
                ORDER BY date
            """, (user_id, monday_str, sunday_str))
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "date": row["date"].isoformat() if isinstance(row["date"], date) else row["date"],
                    "heart_rate": row["heart_rate"],
                    "sleep_hours": row["sleep_hours"],
                    "mood_score": row["mood_score"],
                    "hydration_level": row["hydration_level"],
                    "stress_level": row["stress_level"],
                    "steps": row["steps"]
                })
            
            return jsonify({
                "period": {
                    "week": week_num,
                    "year": year,
                    "start_date": monday_str,
                    "end_date": sunday_str
                },
                "metrics": result,
                "count": len(result)
            }), 200
            
        else:
            # 📈 Dữ liệu theo số ngày (mặc định 7 ngày gần nhất)
            try:
                days = int(days_str)
                start_date = (date.today() - timedelta(days=days)).isoformat()
            except ValueError:
                return jsonify({"message": "Tham số days không hợp lệ"}), 400
            
            cursor.execute("""
                SELECT date, heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps
                FROM user_metrics 
                WHERE user_id=%s AND date >= %s 
                ORDER BY date DESC
            """, (user_id, start_date))
            rows = cursor.fetchall()
            
            # Tính các giá trị trung bình
            if rows:
                avg_heart_rate = sum(r['heart_rate'] or 0 for r in rows) / len(rows)
                avg_sleep = sum(r['sleep_hours'] or 0 for r in rows) / len(rows)
                avg_mood = sum(r['mood_score'] or 0 for r in rows) / len(rows)
                avg_hydration = sum(r['hydration_level'] or 0 for r in rows) / len(rows)
                total_steps = sum(r['steps'] or 0 for r in rows)
            else:
                avg_heart_rate = avg_sleep = avg_mood = avg_hydration = total_steps = 0
            
            result = []
            for row in rows:
                result.append({
                    "date": row["date"].isoformat() if isinstance(row["date"], date) else row["date"],
                    "heart_rate": row["heart_rate"],
                    "sleep_hours": row["sleep_hours"],
                    "mood_score": row["mood_score"],
                    "hydration_level": row["hydration_level"],
                    "stress_level": row["stress_level"],
                    "steps": row["steps"]
                })
            
            return jsonify({
                "period": {
                    "days": days,
                    "start_date": start_date,
                    "end_date": date.today().isoformat()
                },
                "summary": {
                    "total_entries": len(rows),
                    "average_heart_rate": round(avg_heart_rate, 1),
                    "average_sleep_hours": round(avg_sleep, 1),
                    "average_mood_score": round(avg_mood, 1),
                    "average_hydration": round(avg_hydration, 1),
                    "total_steps": total_steps
                },
                "metrics": result
            }), 200
            
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@metrics_bp.route('/metrics', methods=['POST'])
@jwt_required()
def create_metric():
    """Ghi nhận dữ liệu health metrics mới"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data:
        return jsonify({"message": "Dữ liệu gửi lên không hợp lệ"}), 400
    
    # Lấy các trường từ JSON
    heart_rate = data.get("heart_rate")
    sleep_hours = data.get("sleep_hours")
    mood_score = data.get("mood_score")
    hydration_level = data.get("hydration_level")
    stress_level = data.get("stress_level")
    steps = data.get("steps")
    metric_date = data.get("date")
    
    # Validate required fields
    if heart_rate is None or sleep_hours is None or mood_score is None:
        return jsonify({"message": "Thiếu trường dữ liệu bắt buộc: heart_rate, sleep_hours, mood_score"}), 400
    
    # Nếu không chỉ định ngày, sử dụng ngày hôm nay
    if not metric_date:
        metric_date = date.today().isoformat()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        
        # Kiểm tra xem đã có dữ liệu cho ngày này chưa
        cursor.execute("SELECT metric_id FROM user_metrics WHERE user_id=%s AND date=%s", 
                      (user_id, metric_date))
        existing_metric = cursor.fetchone()
        
        if existing_metric:
            # UPDATE existing metric
            cursor.execute("""
                UPDATE user_metrics 
                SET heart_rate=%s, sleep_hours=%s, mood_score=%s, hydration_level=%s, 
                    stress_level=%s, steps=%s, created_at=NOW()
                WHERE user_id=%s AND date=%s
            """, (heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps, 
                  user_id, metric_date))
            action = "updated"
        else:
            # INSERT new metric
            cursor.execute("""
                INSERT INTO user_metrics 
                (user_id, date, heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, metric_date, heart_rate, sleep_hours, mood_score, 
                  hydration_level, stress_level, steps))
            action = "created"
        
        conn.commit()
        
        # Lấy dữ liệu vừa tạo/cập nhật
        cursor_dict = conn.cursor(dictionary=True)
        cursor_dict.execute("""
            SELECT metric_id, date, heart_rate, sleep_hours, mood_score, hydration_level, stress_level, steps
            FROM user_metrics 
            WHERE user_id=%s AND date=%s
        """, (user_id, metric_date))
        new_metric = cursor_dict.fetchone()
        
        return jsonify({
            "message": f"Metric {action} successfully",
            "metric": {
                "id": new_metric["metric_id"],
                "date": new_metric["date"].isoformat() if isinstance(new_metric["date"], date) else new_metric["date"],
                "heart_rate": new_metric["heart_rate"],
                "sleep_hours": new_metric["sleep_hours"],
                "mood_score": new_metric["mood_score"],
                "hydration_level": new_metric["hydration_level"],
                "stress_level": new_metric["stress_level"],
                "steps": new_metric["steps"]
            }
        }), 201 if action == "created" else 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@metrics_bp.route('/metrics/summary', methods=['GET'])
@jwt_required()
def get_metrics_summary():
    """Lấy tổng quan health metrics (7 ngày gần nhất)"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        start_date = (date.today() - timedelta(days=7)).isoformat()
        
        cursor.execute("""
            SELECT 
                AVG(heart_rate) as avg_heart_rate,
                AVG(sleep_hours) as avg_sleep_hours,
                AVG(mood_score) as avg_mood_score,
                AVG(hydration_level) as avg_hydration,
                AVG(stress_level) as avg_stress_level,
                SUM(steps) as total_steps,
                COUNT(*) as entries_count
            FROM user_metrics 
            WHERE user_id=%s AND date >= %s
        """, (user_id, start_date))
        
        summary = cursor.fetchone()
        
        # Lấy dữ liệu trend (so sánh với tuần trước)
        previous_start_date = (date.today() - timedelta(days=14)).isoformat()
        previous_end_date = (date.today() - timedelta(days=8)).isoformat()
        
        cursor.execute("""
            SELECT 
                AVG(heart_rate) as prev_heart_rate,
                AVG(sleep_hours) as prev_sleep_hours,
                AVG(mood_score) as prev_mood_score
            FROM user_metrics 
            WHERE user_id=%s AND date BETWEEN %s AND %s
        """, (user_id, previous_start_date, previous_end_date))
        
        previous_summary = cursor.fetchone()
        
        # Tính trends
        def calculate_trend(current, previous):
            if not previous or previous == 0:
                return 0
            return round(((current - previous) / previous) * 100, 1)
        
        # 🆕 SỬA LỖI: Dùng biến và toán tử so sánh thay vì between
        avg_heart_rate = summary['avg_heart_rate'] or 0
        avg_sleep_hours = summary['avg_sleep_hours'] or 0
        avg_mood_score = summary['avg_mood_score'] or 0
        avg_hydration = summary['avg_hydration'] or 0
        avg_stress_level = summary['avg_stress_level'] or 0
        
        result = {
            "period": {
                "days": 7,
                "start_date": start_date,
                "end_date": date.today().isoformat()
            },
            "current_metrics": {
                "average_heart_rate": round(avg_heart_rate, 1),
                "average_sleep_hours": round(avg_sleep_hours, 1),
                "average_mood_score": round(avg_mood_score, 1),
                "average_hydration": round(avg_hydration, 1),
                "average_stress_level": round(avg_stress_level, 1),
                "total_steps": summary['total_steps'] or 0,
                "entries_count": summary['entries_count'] or 0
            },
            "trends": {
                "heart_rate_trend": calculate_trend(avg_heart_rate, previous_summary['prev_heart_rate'] or 0),
                "sleep_trend": calculate_trend(avg_sleep_hours, previous_summary['prev_sleep_hours'] or 0),
                "mood_trend": calculate_trend(avg_mood_score, previous_summary['prev_mood_score'] or 0)
            },
            "health_status": {
                # 🆕 SỬA: Dùng toán tử so sánh thay vì between
                "heart_rate_status": "optimal" if 60 <= avg_heart_rate <= 100 else "monitor",
                "sleep_status": "optimal" if avg_sleep_hours >= 7 else "improve",
                "mood_status": "good" if avg_mood_score >= 7 else "needs_attention",
                "hydration_status": "optimal" if avg_hydration >= 7 else "improve",
                "stress_status": "low" if avg_stress_level <= 4 else "monitor"
            }
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@metrics_bp.route('/metrics/<string:metric_date>', methods=['DELETE'])
@jwt_required()
def delete_metric(metric_date):
    """Xóa dữ liệu metrics của một ngày cụ thể"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM user_metrics WHERE user_id=%s AND date=%s", 
                      (user_id, metric_date))
        changes = cursor.rowcount
        conn.commit()
        
        if changes == 0:
            return jsonify({"message": "Không tìm thấy dữ liệu metrics để xóa"}), 404
            
        return jsonify({
            "message": "Đã xóa dữ liệu metrics thành công",
            "date": metric_date
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()