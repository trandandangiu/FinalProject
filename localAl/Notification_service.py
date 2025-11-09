from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from dbconnect import get_db_connection
from datetime import datetime

notification_bp = Blueprint('notification', __name__)

@notification_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    """Lấy tất cả thông báo của người dùng hiện tại"""
    user_id = get_jwt_identity()
    conn = get_db_connection()
    
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor(dictionary=True)
        # 🆕 SỬA: Dùng đúng tên cột từ database
        cursor.execute(
            "SELECT noti_id, type, message, is_read, created_at FROM notifications WHERE user_id=%s ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cursor.fetchall()
        
        notifications = []
        for row in rows:
            notifications.append({
                "id": row["noti_id"], 
                "type": row["type"],
                "message": row["message"],
                "read": bool(row["is_read"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else None  
            })
        
        return jsonify({
            "notifications": notifications,
            "count": len(notifications),
            "unread_count": sum(1 for n in notifications if not n["read"])
        }), 200
        
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@notification_bp.route('/notifications', methods=['POST'])
@jwt_required()
def create_notification():
    """Tạo một thông báo mới cho user"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or "type" not in data or "message" not in data:
        return jsonify({"message": "Dữ liệu gửi lên không hợp lệ"}), 400
        
    noti_type = data["type"]
    message = data["message"]
    
    # Validate notification type
    valid_types = ['system', 'reminder', 'achievement', 'workout', 'meal', 'progress', 'adaptive']
    if noti_type not in valid_types:
        return jsonify({
            "message": f"Loại thông báo không hợp lệ. Các loại hợp lệ: {', '.join(valid_types)}"
        }), 400
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        # 🆕 SỬA: Dùng đúng tên cột từ database
        cursor.execute(
            "INSERT INTO notifications (user_id, type, message, is_read) VALUES (%s, %s, %s, %s)",
            (user_id, noti_type, message, 0)
        )
        conn.commit()
        new_id = cursor.lastrowid
        
        # Lấy thông tin thông báo vừa tạo
        cursor_dict = conn.cursor(dictionary=True)
        cursor_dict.execute(
            "SELECT noti_id, type, message, is_read, created_at FROM notifications WHERE noti_id=%s",
            (new_id,)
        )
        new_notification = cursor_dict.fetchone()
        
        return jsonify({
            "id": new_notification["noti_id"],
            "type": new_notification["type"],
            "message": new_notification["message"],
            "read": bool(new_notification["is_read"]),
            "created_at": new_notification["created_at"].isoformat() if new_notification["created_at"] else None,
            "status": "Thông báo đã được tạo thành công"
        }), 201
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@notification_bp.route('/notifications/<int:noti_id>', methods=['PUT'])
@jwt_required()
def mark_notification_read(noti_id):
    """Đánh dấu đã đọc hoặc cập nhật trạng thái đọc cho một thông báo"""
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    
    # Mặc định đánh dấu là đã đọc (True) nếu không chỉ định
    mark_read = data.get("read", True)
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        # 🆕 SỬA: Dùng đúng tên cột từ database
        cursor.execute(
            "UPDATE notifications SET is_read=%s WHERE noti_id=%s AND user_id=%s",
            (1 if mark_read else 0, noti_id, user_id)
        )
        changes = cursor.rowcount
        conn.commit()
        
        if changes == 0:
            return jsonify({"message": "Không tìm thấy thông báo hoặc không có quyền"}), 404
            
        return jsonify({
            "message": "Cập nhật trạng thái thông báo thành công",
            "noti_id": noti_id,
            "read": mark_read
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@notification_bp.route('/notifications/read-all', methods=['PUT'])
@jwt_required()
def mark_all_notifications_read():
    """Đánh dấu tất cả thông báo là đã đọc"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        # 🆕 SỬA: Dùng đúng tên cột từ database
        cursor.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=%s AND is_read=0",
            (user_id,)
        )
        updated_count = cursor.rowcount
        conn.commit()
        
        return jsonify({
            "message": f"Đã đánh dấu {updated_count} thông báo là đã đọc",
            "updated_count": updated_count
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()

@notification_bp.route('/notifications/<int:noti_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(noti_id):
    """Xóa một thông báo"""
    user_id = get_jwt_identity()
    
    conn = get_db_connection()
    if conn is None:
        return jsonify({"message": "Database connection failed"}), 500
        
    try:
        cursor = conn.cursor()
        # 🆕 SỬA: Dùng đúng tên cột từ database
        cursor.execute(
            "DELETE FROM notifications WHERE noti_id=%s AND user_id=%s",
            (noti_id, user_id)
        )
        changes = cursor.rowcount
        conn.commit()
        
        if changes == 0:
            return jsonify({"message": "Không tìm thấy thông báo hoặc không có quyền"}), 404
            
        return jsonify({
            "message": "Đã xóa thông báo thành công",
            "noti_id": noti_id
        }), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()