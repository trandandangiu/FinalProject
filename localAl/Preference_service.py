from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
import datetime
import json

preference_bp = Blueprint('preference', __name__)

def format_list_field(field_data):
    """Chuyển list thành string format phù hợp - ĐẶT NGOÀI HÀM"""
    if not field_data:
        return None
    if isinstance(field_data, list):
        # Lưu dạng JSON string để dễ parse
        return json.dumps(field_data, ensure_ascii=False)
    return str(field_data)

def parse_list_field(field_value):
    """Parse dữ liệu từ string sang list"""
    if not field_value:
        return []
    try:
        # Giả sử dữ liệu được lưu dạng JSON string hoặc comma-separated
        if field_value.startswith('['):
            return json.loads(field_value)
        else:
            return [item.strip() for item in field_value.split(',') if item.strip()]
    except:
        return [field_value]

@preference_bp.route('/preferences', methods=['GET'])
@jwt_required()
def get_user_preferences():
    """Lấy toàn bộ thông tin cá nhân hóa của người dùng"""
    user_id = get_jwt_identity()
    conn = get_db_connection()
    
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                diet_type,
                disliked_foods,
                preferred_exercises, 
                disliked_exercises,
                injuries,
                activity_level,
                health_conditions,
                updated_at
            FROM user_preferences 
            WHERE user_id = %s
        """, (user_id,))
        
        preferences = cursor.fetchone()
        
        if not preferences:
            return jsonify({
                "diet_type": "balanced",  # 🆕 Mặc định là 'balanced'
                "disliked_foods": [],
                "preferred_exercises": [],
                "disliked_exercises": [],
                "injuries": [],
                "activity_level": "moderate",
                "health_conditions": [],
                "updated_at": None
            }), 200
        
        response_data = {
            "diet_type": preferences['diet_type'],
            "disliked_foods": parse_list_field(preferences['disliked_foods']),
            "preferred_exercises": parse_list_field(preferences['preferred_exercises']),
            "disliked_exercises": parse_list_field(preferences['disliked_exercises']),
            "injuries": parse_list_field(preferences['injuries']),
            "activity_level": preferences['activity_level'],
            "health_conditions": parse_list_field(preferences['health_conditions']),
            "updated_at": preferences['updated_at'].isoformat() if preferences['updated_at'] else None
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@preference_bp.route('/preferences', methods=['POST'])
@jwt_required()
def create_or_update_preferences():
    """Tạo mới hoặc cập nhật toàn bộ thông tin cá nhân hóa"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data:
        return jsonify({"message": "Dữ liệu gửi lên không hợp lệ"}), 400
    
    # 🆕 CẬP NHẬT: Dùng đúng ENUM values từ database
    valid_activity_levels = ['sedentary', 'light', 'moderate', 'active', 'very_active', 'low', 'medium', 'high']
    activity_level = data.get('activity_level', 'moderate')
    
    # 🆕 CẬP NHẬT: Dùng CHÍNH XÁC các giá trị ENUM từ database
    valid_diet_types = [
        'balanced',    # ✅ Giá trị mặc định
        'keto',        # ✅ 
        'vegan',       # ✅
        'low_carb',    # ✅
        'high_protein', # ✅
        'vegetarian',  # ✅
        'gluten_free', # ✅
        'dairy_free',  # ✅
        'paleo',       # ✅
        'mediterranean' # ✅
    ]
    
    diet_type = data.get('diet_type', 'balanced')  # 🆕 Mặc định là 'balanced'
    
    # Validate diet_type
    if diet_type not in valid_diet_types:
        return jsonify({
            "message": f"Loại chế độ ăn '{diet_type}' không hợp lệ. Các giá trị hợp lệ: {', '.join(valid_diet_types)}",
            "valid_diet_types": valid_diet_types
        }), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        
        # Kiểm tra xem user đã có preferences chưa
        cursor.execute("SELECT user_id FROM user_preferences WHERE user_id = %s", (user_id,))
        existing_preferences = cursor.fetchone()
        
        update_data = {
            'diet_type': diet_type,
            'disliked_foods': format_list_field(data.get('disliked_foods', [])),
            'preferred_exercises': format_list_field(data.get('preferred_exercises', [])),
            'disliked_exercises': format_list_field(data.get('disliked_exercises', [])),
            'injuries': format_list_field(data.get('injuries', [])),
            'activity_level': activity_level,
            'health_conditions': format_list_field(data.get('health_conditions', [])),
            'updated_at': datetime.datetime.now()
        }
        
        if existing_preferences:
            # UPDATE existing preferences
            cursor.execute("""
                UPDATE user_preferences 
                SET diet_type = %s,
                    disliked_foods = %s,
                    preferred_exercises = %s,
                    disliked_exercises = %s,
                    injuries = %s,
                    activity_level = %s,
                    health_conditions = %s,
                    updated_at = %s
                WHERE user_id = %s
            """, (
                update_data['diet_type'],
                update_data['disliked_foods'],
                update_data['preferred_exercises'],
                update_data['disliked_exercises'],
                update_data['injuries'],
                update_data['activity_level'],
                update_data['health_conditions'],
                update_data['updated_at'],
                user_id
            ))
            action = "updated"
        else:
            # INSERT new preferences
            cursor.execute("""
                INSERT INTO user_preferences (
                    user_id, diet_type, disliked_foods, preferred_exercises,
                    disliked_exercises, injuries, activity_level, health_conditions, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                update_data['diet_type'],
                update_data['disliked_foods'],
                update_data['preferred_exercises'],
                update_data['disliked_exercises'],
                update_data['injuries'],
                update_data['activity_level'],
                update_data['health_conditions'],
                update_data['updated_at']
            ))
            action = "created"
        
        conn.commit()
        
        return jsonify({
            "message": f"Preferences {action} successfully",
            "user_id": user_id,
            "data": {
                "diet_type": diet_type,
                "disliked_foods": data.get('disliked_foods', []),
                "preferred_exercises": data.get('preferred_exercises', []),
                "disliked_exercises": data.get('disliked_exercises', []),
                "injuries": data.get('injuries', []),
                "activity_level": activity_level,
                "health_conditions": data.get('health_conditions', [])
            }
        }), 200 if action == "updated" else 201
        
    except Exception as e:
        conn.rollback()
        error_msg = str(e)
        if "Data truncated for column 'diet_type'" in error_msg:
            return jsonify({
                "message": f"Loại chế độ ăn không hợp lệ. Các giá trị hợp lệ: {', '.join(valid_diet_types)}",
                "valid_diet_types": valid_diet_types,
                "error_details": error_msg
            }), 400
        return jsonify({"message": f"Database error: {error_msg}"}), 500
    finally:
        if conn:
            conn.close()
            
@preference_bp.route('/preferences/partial', methods=['PATCH'])
@jwt_required()
def update_partial_preferences():
    """Cập nhật một phần thông tin cá nhân hóa"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data:
        return jsonify({"message": "Dữ liệu gửi lên không hợp lệ"}), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        
        # Kiểm tra user có preferences không
        cursor.execute("SELECT user_id FROM user_preferences WHERE user_id = %s", (user_id,))
        if not cursor.fetchone():
            return jsonify({"message": "User preferences not found. Please create full preferences first."}), 404
        
        # Build dynamic update query
        update_fields = []
        update_values = []
        
        valid_fields = [
            'diet_type', 'disliked_foods', 'preferred_exercises', 
            'disliked_exercises', 'injuries', 'activity_level', 'health_conditions'
        ]
        
        for field in valid_fields:
            if field in data:
                if field in ['disliked_foods', 'preferred_exercises', 'disliked_exercises', 'injuries', 'health_conditions']:
                    # Format list fields
                    update_values.append(format_list_field(data[field]))
                else:
                    update_values.append(data[field])
                update_fields.append(f"{field} = %s")
        
        if not update_fields:
            return jsonify({"message": "No valid fields to update"}), 400
        
        # Thêm updated_at và user_id
        update_fields.append("updated_at = %s")
        update_values.append(datetime.datetime.now())
        update_values.append(user_id)
        
        # Execute update
        update_query = f"UPDATE user_preferences SET {', '.join(update_fields)} WHERE user_id = %s"
        cursor.execute(update_query, update_values)
        
        conn.commit()
        
        return jsonify({
            "message": "Preferences updated successfully",
            "updated_fields": list(data.keys())
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@preference_bp.route('/preferences/recommendation-data', methods=['GET'])
@jwt_required()
def get_recommendation_data():
    """Lấy dữ liệu cá nhân hóa cho hệ thống recommendation"""
    user_id = get_jwt_identity()
    conn = get_db_connection()
    
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT 
                diet_type,
                disliked_foods,
                preferred_exercises,
                disliked_exercises,
                injuries,
                activity_level,
                health_conditions
            FROM user_preferences 
            WHERE user_id = %s
        """, (user_id,))
        
        preferences = cursor.fetchone()
        
        if not preferences:
            return jsonify({
                "message": "No preferences found",
                "recommendation_data": {
                    "diet_restrictions": [],
                    "exercise_preferences": [],
                    "health_considerations": [],
                    "activity_level": "moderate"
                }
            }), 200
        
        # Parse for recommendation system
        recommendation_data = {
            "diet_restrictions": [
                preferences['diet_type']
            ] if preferences['diet_type'] and preferences['diet_type'] != 'none' else [],
            "food_avoidances": parse_list_field(preferences['disliked_foods']),
            "exercise_preferences": parse_list_field(preferences['preferred_exercises']),
            "exercise_avoidances": parse_list_field(preferences['disliked_exercises']),
            "health_considerations": parse_list_field(preferences['injuries']) + parse_list_field(preferences['health_conditions']),
            "activity_level": preferences['activity_level'] or 'moderate'
        }
        
        # Lọc bỏ các giá trị None/empty
        recommendation_data = {k: v for k, v in recommendation_data.items() if v}
        
        return jsonify({
            "user_id": user_id,
            "recommendation_data": recommendation_data
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@preference_bp.route('/preferences/reset', methods=['DELETE'])
@jwt_required()
def reset_preferences():
    """Reset tất cả preferences về mặc định"""
    user_id = get_jwt_identity()
    conn = get_db_connection()
    
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
        changes = cursor.rowcount
        
        conn.commit()
        
        if changes == 0:
            return jsonify({"message": "No preferences found to reset"}), 404
            
        return jsonify({
            "message": "Preferences reset successfully",
            "default_preferences": {
                "diet_type": None,
                "disliked_foods": [],
                "preferred_exercises": [],
                "disliked_exercises": [],
                "injuries": [],
                "activity_level": "moderate",
                "health_conditions": []
            }
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()