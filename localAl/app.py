import os
import datetime
import logging 
logging.basicConfig(level=logging.DEBUG)
from flask import Flask, render_template, send_from_directory, jsonify
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from User_service import user_bp, blacklist   
from ChatService import chat_bp   
from Workout_service import workout_bp  
from Foods_service import Foods_bp 
from Progress_service import progress_bp  
from Recommendation_service import recommendation_bp  
from Plan_service import plan_bp  
from Preference_service import preference_bp
from Notification_service import notification_bp
from Analytics_service import analytics_bp
from Metrics_service import metrics_bp
from Adaptive_service import adaptive_bp
app = Flask(__name__,
    static_folder='C:/Users/trant/OneDrive/Desktop/FinalProject/frontend',
    template_folder='C:/Users/trant/OneDrive/Desktop/FinalProject/frontend'
)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.info("CORS enabled for all /api/* routes")


# 🔑 CẤU HÌNH JWT
app.config['JWT_SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = datetime.timedelta(hours=24)
app.config['JWT_BLACKLIST_ENABLED'] = True   # ⚡ bật blacklist
jwt = JWTManager(app)

# ✅ HÀM KIỂM TRA TOKEN CÓ BỊ THU HỒI KHÔNG
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    return jti in blacklist

# ✅ ĐĂNG KÝ CÁC BLUEPRINT
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(chat_bp, url_prefix='/api')
app.register_blueprint(workout_bp, url_prefix='/api')
app.register_blueprint(Foods_bp, url_prefix='/api')
app.register_blueprint(progress_bp, url_prefix='/api')
app.register_blueprint(recommendation_bp, url_prefix='/api')
app.register_blueprint(plan_bp, url_prefix="/api")
app.register_blueprint(preference_bp, url_prefix="/api")
app.register_blueprint(notification_bp, url_prefix="/api") 
app.register_blueprint(analytics_bp, url_prefix="/api")
app.register_blueprint(metrics_bp, url_prefix="/api")
app.register_blueprint(adaptive_bp, url_prefix="/api")  
# ✅ CÁC ROUTE CỦA ỨNG DỤNG CHÍNH
@app.route('/')
def serve_home():
    return render_template('Login.html')

@app.route('/index.html')
def serve_login():
    return render_template('index.html')

@app.route('/register.html')
def serve_register():
    return render_template('Register.html')

@app.route('/profile.html')
def serve_profile():
    return render_template('Profiles.html')

@app.route('/<string:page_name>.html')
def serve_html_page(page_name):
    template_path = f"{page_name}.html"
    if not os.path.exists(os.path.join(app.template_folder, template_path)):
        return jsonify({"error": "Page not found", "path": template_path}), 404
    return render_template(template_path)

@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy", "message": "Server is running perfectly!"})

@app.route('/<path:subpath>')
def serve_static_resources(subpath):
    full_path = os.path.join(app.static_folder, subpath)
    if os.path.isfile(full_path):
        return send_from_directory(app.static_folder, subpath)
    else:
        return jsonify({"error": "Page not found", "path": subpath}), 404

@app.route('/user.html')
def serve_user():
    return render_template('Users.html')

# 🎯 CHẠY ỨNG DỤNG
if __name__ == '__main__':
    print("🔥 Starting GymLife Server...")
    print("📍 Frontend path:", app.static_folder)
    print("📁 Template path:", app.template_folder)
    
    if os.path.exists(app.template_folder):
        print("✅ Template folder exists")
        html_files = [f for f in os.listdir(app.template_folder) if f.endswith('.html')]
        print("📄 HTML files found:", html_files)
    else:
        print("❌ Template folder does NOT exist!")
    
    print("🌐 Server URL: http://localhost:5000")
    print("✅ Health check: http://localhost:5000/api/health")
    print("👤 Register API: http://localhost:5000/api/register")
    print("📝 Login page: http://localhost:5000/login.html")
    print("📝 Register page: http://localhost:5000/register.html")

    app.run(debug=True, host='0.0.0.0', port=5000)
