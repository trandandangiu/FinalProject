from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token, jwt_required, get_jwt_identity, get_jwt
)
import mysql.connector

# Blueprint cho User Service
user_bp = Blueprint("user", __name__)

# ===== BLACKLIST CHO TOKEN =====
blacklist = set()

# Hàm connect DB trực tiếp
def get_db_connection():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="241103",  # thay bằng mật khẩu của bạn
        database="fitai",
        port=3306
    )

# -------------------------------
# API ĐĂNG KÝ (REGISTER)
# -------------------------------
@user_bp.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    name = data.get("name")
    gender = data.get("gender")
    dob = data.get("dob")
    height = data.get("height")
    weight = data.get("weight")
    goal = data.get("goal")

    if not email or not password:
        return jsonify({"error": "Thiếu email hoặc password"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        hashed_pw = generate_password_hash(password)

        cursor.execute(
            "INSERT INTO users (email, password_hash, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
            (email, hashed_pw)
        )
        user_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO profiles (user_id, name, gender, dob, height, weight, goal) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, name, gender, dob, height, weight, goal)
        )

        conn.commit()
        return jsonify({"message": "Đăng ký thành công", "user_id": user_id}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400

    finally:
        cursor.close()
        conn.close()


# -------------------------------
# API ĐĂNG NHẬP (LOGIN)
# -------------------------------
@user_bp.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Thiếu email hoặc password"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and check_password_hash(user["password_hash"], password):
        # Tạo access_token để dùng cho API khác
        access_token = create_access_token(identity=str(user["user_id"]))  # ✅ để int
        return jsonify({
            "message": "Đăng nhập thành công",
            "access_token": access_token,
            "user_id": user["user_id"]
        }), 200
    else:
        return jsonify({"error": "Sai email hoặc mật khẩu"}), 401


# -------------------------------
# API ĐĂNG XUẤT (LOGOUT)
# -------------------------------
@user_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]  # lấy JWT ID
    blacklist.add(jti)      # thêm vào danh sách token đã thu hồi
    return jsonify({"message": "Đăng xuất thành công"}), 200


# -------------------------------
# API LẤY PROFILE
# -------------------------------
@user_bp.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())  # ✅ lấy từ token

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT u.user_id, u.email, p.name, p.gender, p.dob, 
               p.height, p.weight, p.goal, u.created_at
        FROM users u
        LEFT JOIN profiles p ON u.user_id = p.user_id
        WHERE u.user_id = %s
    """, (user_id,))
    profile = cursor.fetchone()

    cursor.close()
    conn.close()

    if profile:
        return jsonify(profile)
    else:
        return jsonify({"error": "Không tìm thấy profile"}), 404


# -------------------------------
# API CẬP NHẬT PROFILE
# -------------------------------
@user_bp.route("/profile", methods=["PUT"])  
@jwt_required()
def update_profile():
    user_id = int(get_jwt_identity())  # ✅ lấy từ token
    try:
        data = request.json
        required_fields = ["name", "gender", "dob", "height", "weight", "goal"]
        
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Thiếu trường {field}"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        existing_profile = cursor.fetchone()
        
        if existing_profile:
            cursor.execute("""
                UPDATE profiles 
                SET name=%s, gender=%s, dob=%s, height=%s, weight=%s, goal=%s 
                WHERE user_id=%s
            """, (data["name"], data["gender"], data["dob"], 
                 data["height"], data["weight"], data["goal"], user_id))
        else:
            cursor.execute("""
                INSERT INTO profiles (user_id, name, gender, dob, height, weight, goal)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, data["name"], data["gender"], data["dob"],
                 data["height"], data["weight"], data["goal"]))
        
        conn.commit()
        return jsonify({"message": "Cập nhật profile thành công"}), 200
        
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        conn.close()
