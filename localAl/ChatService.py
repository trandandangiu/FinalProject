# ChatService.py - PERSONAL COACH EDITION
from flask import Blueprint, request, jsonify
from dbconnect import get_db_connection
import requests
import unicodedata
import re
import socket
import logging
import time
import datetime
import json
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date, timedelta
from typing import Dict, List, Optional, Any

chat_bp = Blueprint("chat", __name__)

# ===================== CONFIG =====================
def get_ollama_url():
    """Tự phát hiện URL Ollama"""
    try:
        socket.gethostbyname("ollama")
        return "http://ollama:11434"
    except socket.error:
        return "http://localhost:11434"

OLLAMA_URL = get_ollama_url()
OLLAMA_MODEL = "llama3:8b"

# Base URLs cho tất cả service
FOODS_BASE_URL = "http://localhost:5000/api"
PROGRESS_BASE_URL = "http://localhost:5000/api" 
WORKOUT_BASE_URL = "http://localhost:5000/api"
RECOMMEND_BASE_URL = "http://localhost:5000/api"
ANALYTICS_BASE_URL = "http://localhost:5000/api"
ADAPTIVE_BASE_URL = "http://localhost:5000/api"
PREFERENCE_BASE_URL = "http://localhost:5000/api"
USER_BASE_URL = "http://localhost:5000/api"

# ===================== ENHANCED LOGGING =====================
logging.basicConfig(
    filename="coach_chat.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# ===================== CONTEXT MANAGER =====================
class UserContext:
    """Quản lý context và lịch sử hội thoại của user"""
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.conversation_history = []
        self.user_profile = {}
        self.user_preferences = {}
        self.recent_activities = []
        self.current_goals = {}
        self.health_metrics = {}
        self.last_interaction = datetime.datetime.now()
        self.conversation_mood = "neutral"  # neutral, happy, stressed, tired
    
    def add_message(self, user_msg, ai_msg, intent, mood_detected=None):
        """Thêm tin nhắn vào lịch sử với phân tích tâm trạng"""
        self.conversation_history.append({
            "timestamp": datetime.datetime.now(),
            "user": user_msg,
            "assistant": ai_msg,
            "intent": intent,
            "mood": mood_detected or self.detect_mood(user_msg)
        })
        
        # Giữ chỉ 20 tin nhắn gần nhất
        if len(self.conversation_history) > 20:
            self.conversation_history.pop(0)
            
        self.last_interaction = datetime.datetime.now()
    
    def detect_mood(self, message):
        """Phát hiện tâm trạng từ tin nhắn"""
        message_lower = message.lower()
        
        happy_keywords = ['tuyệt', 'vui', 'happy', 'good', 'tốt', 'xuất sắc', 'cảm ơn', 'thanks']
        stressed_keywords = ['mệt', 'stress', 'căng thẳng', 'khó khăn', 'vấn đề', 'lo lắng']
        tired_keywords = ['mệt', 'mỏi', 'kiệt sức', 'buồn ngủ', 'đuối']
        
        if any(keyword in message_lower for keyword in happy_keywords):
            return "happy"
        elif any(keyword in message_lower for keyword in stressed_keywords):
            return "stressed" 
        elif any(keyword in message_lower for keyword in tired_keywords):
            return "tired"
        else:
            return "neutral"
    
    def get_conversation_summary(self):
        """Tóm tắt cuộc hội thoại gần đây"""
        if not self.conversation_history:
            return "Chưa có lịch sử hội thoại"
        
        recent = self.conversation_history[-5:]  # 5 tin nhắn gần nhất
        summary = []
        for msg in recent:
            summary.append(f"User: {msg['user'][:50]}... -> Intent: {msg['intent']}")
        
        return " | ".join(summary)
    
    def update_user_data(self, profile_data, preference_data):
        """Cập nhật dữ liệu user từ các service"""
        self.user_profile = profile_data or {}
        self.user_preferences = preference_data or {}
        
        # Extract goals từ profile
        if 'goal' in self.user_profile:
            self.current_goals = {
                'main_goal': self.user_profile['goal'],
                'weight': self.user_profile.get('weight'),
                'height': self.user_profile.get('height')
            }

# Global context storage
user_contexts: Dict[int, UserContext] = {}

def get_user_context(user_id: int) -> UserContext:
    """Lấy hoặc tạo user context"""
    if user_id not in user_contexts:
        user_contexts[user_id] = UserContext(user_id)
    return user_contexts[user_id]

# ===================== ENHANCED UTILS =====================
def remove_accents(input_str):
    """Chuẩn hóa văn bản tiếng Việt"""
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    no_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return no_accents.replace("đ", "d").replace("Đ", "D")

def extract_muscle_group(msg_ascii: str):
    """Trích xuất nhóm cơ từ tin nhắn"""
    mapping = {
        "bung": "abdominals", "eo": "abdominals", "abs": "abdominals", "bụng": "abdominals",
        "tay": "arms", "arm": "arms", "cánh tay": "arms", "bắp tay": "arms",
        "chan": "legs", "leg": "legs", "chân": "legs", "đùi": "legs", "bắp chân": "legs",
        "lung": "back", "back": "back", "lưng": "back",
        "nguc": "chest", "chest": "chest", "ngực": "chest",
        "vai": "shoulders", "shoulder": "shoulders",
        "mong": "glutes", "glute": "glutes", "mông": "glutes"
    }
    for k, v in mapping.items():
        if k in msg_ascii:
            return v
    m = re.search(r"nhom co\s+([a-z]+)", msg_ascii)
    if m:
        return mapping.get(m.group(1), None)
    return None

def extract_food_and_grams(msg_ascii: str):
    """Trích xuất thông tin thực phẩm và khối lượng"""
    grams_match = re.search(r"(\d+)\s*g", msg_ascii)
    grams = int(grams_match.group(1)) if grams_match else 100
    food_name = re.sub(r"\d+\s*g", "", msg_ascii)
    food_name = food_name.replace("calo", "").replace("kcal", "").strip()
    return food_name, grams

def extract_foods_from_message(msg_ascii: str):
    """Trích xuất danh sách thực phẩm từ tin nhắn"""
    items = []
    parts = re.split(r",|\s+và\s+", msg_ascii)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(\d+)\s*(g|bát|quả|ly)?\s*(.+)", part)
        if m:
            qty = int(m.group(1))
            unit = m.group(2) or ""
            name = m.group(3).strip()
            if unit and unit.lower() != "g":
                name = f"{unit} {name}"
            items.append({"name": name, "quantity": qty})
        else:
            items.append({"name": part, "quantity": 1})
    return items

# ===================== SMART INTENT DETECTION =====================
def detect_intent_advanced(user_message_ascii: str, intent_list: List[str], user_context: UserContext) -> str:
    """
    Phát hiện intent thông minh với context awareness
    """
    message = user_message_ascii.lower().strip()
    
    # Enhanced keyword mapping với priority
    intent_keywords = {
        "progress_check": [
            "tiến độ", "progress", "giảm cân", "tăng cân", "trong tháng", "trong tuần",
            "tập luyện", "kết quả", "theo dõi", "cân nặng", "body fat", "bodyfat",
            "xem tiến độ", "tiến độ tập", "kết quả tập", "theo dõi cân", "bao nhiêu cân"
        ],
        "recommendation": [
            "recommend", "recommendation", "đề xuất", "cá nhân hóa", "ca nhan hoa",
            "kế hoạch tuần", "ke hoach tuan", "weekly plan", "tip nhanh", "quick tip",
            "gợi ý cá nhân", "goi y ca nhan", "gợi ý ăn", "goi y an", "nên làm gì"
        ],
        "workout_suggestion": [
            "bài tập", "workout", "tập luyện", "nhóm cơ", "cơ bụng", "cơ ngực",
            "cơ tay", "cơ chân", "tập cho", "exercise", "tập", "bụng", "tay",
            "chân", "ngực", "lưng", "vai", "mông", "đùi", "bắp tay", "bắp chân"
        ],
        "meal_suggestion": [
            "thực phẩm", "ăn gì", "meal", "món ăn", "bữa ăn", "thức ăn",
            "đồ ăn", "bữa sáng", "bữa trưa", "bữa tối", "suggest",
            "nên ăn", "thực đơn", "menu", "món healthy", "ăn gì để"
        ],
        "add_meal": [
            "tôi vừa ăn", "ghi lại", "lưu bữa ăn", "đã ăn", "vừa ăn", "ate",
            "mới ăn", "vua an", "ghi lai", "thêm bữa ăn", "log meal", "log food"
        ],
        "food_lookup": [
            "calo", "kcal", "protein", "carb", "fat", "gram", "gam",
            "bao nhiêu calo", "bao nhiêu protein", "nutrition facts"
        ],
        "meal_history": [
            "lịch sử ăn", "hôm qua ăn", "bữa trước", "meal history", "đã ăn gì",
            "ăn gì hôm qua", "history", "lịch sử", "hôm qua", "hôm kia"
        ],
        "analytics_check": [
            "phân tích", "analytics", "thống kê", "số liệu", "báo cáo",
            "tổng quan", "overview", "thống kê tuần", "phân tích hiệu suất"
        ],
        "adaptive_suggestion": [
            "điều chỉnh", "adaptive", "thích ứng", "thay đổi", "cập nhật",
            "gợi ý thông minh", "smart suggestion", "tối ưu"
        ],
        "preference_update": [
            "cập nhật sở thích", "thay đổi mục tiêu", "đổi chế độ ăn",
            "preference", "sở thích", "không thích", "thích ăn"
        ],
        "general_health": [
            "bmi", "bmr", "sức khỏe", "tình trạng", "health", "chỉ số",
            "sức khoẻ", "suc khoe", "tình trạng sức khỏe"
        ],
        "daily_summary": [
            "hôm nay", "tóm tắt", "summary", "nạp vào", "tiêu hao",
            "calo hôm nay", "hôm nay ăn", "tổng kết hôm nay"
        ]
    }
    
    # Rule-based detection với priority
    for intent, keywords in intent_keywords.items():
        if intent in intent_list and any(kw in message for kw in keywords):
            logging.info(f"[RULE] Intent '{intent}' detected")
            return intent
    
    # Context-aware fallback: Dựa vào lịch sử hội thoại
    if user_context.conversation_history:
        last_intent = user_context.conversation_history[-1].get('intent')
        if last_intent in ['meal_suggestion', 'workout_suggestion'] and 'tiếp theo' in message:
            return last_intent
    
    # LLM fallback với context enhancement
    try:
        context_summary = user_context.get_conversation_summary()
        prompt = f"""
Bạn là bộ phân loại intent cho hệ thống GymLife Coach.

CONTEXT HIỆN TẠI:
- Lịch sử hội thoại: {context_summary}
- Mục tiêu user: {user_context.current_goals.get('main_goal', 'unknown')}
- Tâm trạng: {user_context.conversation_mood}

NGƯỜI DÙNG NHẮN: "{message}"

CÁC INTENT HỢP LỆ: {intent_list}

Phân tích intent phù hợp nhất dựa trên context và tin nhắn.
Trả về DUY NHẤT tên intent.
"""
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": False
            },
            timeout=60,
        )
        if response.status_code == 200:
            data = response.json()
            intent = data.get("message", {}).get("content", "").strip().lower()
            if intent in intent_list:
                logging.info(f"[LLM] Intent '{intent}' detected with context")
                return intent
    except Exception as e:
        logging.error(f"[LLM] Fallback failed: {e}")
    
    return "general_chat"

# ===================== SERVICE INTEGRATION HELPERS =====================
def get_user_profile_data(user_id: int, auth_header: str) -> Dict:
    """Lấy thông tin profile từ User Service"""
    try:
        response = requests.get(
            f"{USER_BASE_URL}/profile",
            headers={"Authorization": auth_header},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to get user profile: {e}")
    return {}

def get_user_preferences_data(user_id: int, auth_header: str) -> Dict:
    """Lấy preferences từ Preference Service"""
    try:
        response = requests.get(
            f"{PREFERENCE_BASE_URL}/preferences",
            headers={"Authorization": auth_header},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to get user preferences: {e}")
    return {}

def get_analytics_data(user_id: int, auth_header: str, period: str = "7") -> Dict:
    """Lấy analytics data"""
    try:
        response = requests.get(
            f"{ANALYTICS_BASE_URL}/analytics",
            headers={"Authorization": auth_header},
            params={"days": period},
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to get analytics: {e}")
    return {}

def get_adaptive_recommendations(user_id: int, auth_header: str) -> Dict:
    """Lấy adaptive recommendations"""
    try:
        response = requests.get(
            f"{ADAPTIVE_BASE_URL}/adaptive",
            headers={"Authorization": auth_header},
            timeout=15
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logging.error(f"Failed to get adaptive recommendations: {e}")
    return {}

# ===================== SMART RESPONSE GENERATION =====================
def generate_coach_response(intent: str, data: Dict, user_context: UserContext, user_message: str = "") -> str:
    """
    Tạo response thông minh với personality của coach
    """
    coach_personality = {
        "tone": "supportive",
        "style": "encouraging", 
        "emotion": "empathetic",
        "knowledge_level": "expert"
    }
    
    # Xác định tone dựa trên tâm trạng user
    mood = user_context.conversation_mood
    if mood == "stressed":
        coach_personality["tone"] = "calming"
        coach_personality["style"] = "reassuring"
    elif mood == "tired":
        coach_personality["tone"] = "energizing" 
        coach_personality["style"] = "motivating"
    elif mood == "happy":
        coach_personality["tone"] = "celebratory"
        coach_personality["style"] = "enthusiastic"
    
    base_responses = {
        "progress_check": "📊 **PHÂN TÍCH TIẾN ĐỘ CỦA BẠN:**\n",
        "workout_suggestion": "💪 **GỢI Ý TẬP LUYỆN THÔNG MINH:**\n",
        "meal_suggestion": "🥗 **ĐỀ XUẤT DINH DƯỠNG:**\n", 
        "analytics_check": "📈 **BÁO CÁO PHÂN TÍCH:**\n",
        "adaptive_suggestion": "🎯 **GỢI Ý THÍCH ỨNG:**\n",
        "recommendation": "🌟 **ĐỀ XUẤT CÁ NHÂN HÓA:**\n"
    }
    
    response_template = base_responses.get(intent, "🤖 **COACH PHẢN HỒI:**\n")
    
    # Generate content based on intent và data
    content = generate_intent_content(intent, data, user_context)
    
    # Thêm motivational elements
    motivation = add_motivational_element(intent, user_context)
    
    # Thêm proactive suggestions
    proactive = add_proactive_suggestion(intent, user_context)
    
    full_response = f"{response_template}{content}"
    if motivation:
        full_response += f"\n\n✨ {motivation}"
    if proactive:
        full_response += f"\n\n🔮 {proactive}"
        
    return full_response

def generate_intent_content(intent: str, data: Dict, user_context: UserContext) -> str:
    """Tạo nội dung cụ thể cho từng intent"""
    
    if intent == "progress_check":
        if not data.get('progress'):
            return "📝 Hãy bắt đầu ghi lại tiến độ đầu tiên của bạn!"
        
        progress = data['progress']
        latest = progress[0] if progress else {}
        
        content = f"""
📅 **Cập nhật mới nhất:** {latest.get('date', 'N/A')}
⚖️ **Cân nặng:** {latest.get('weight', 'N/A')}kg
📊 **BMI:** {latest.get('bmi', 'N/A')} ({latest.get('bmi_category', 'N/A')})
💪 **Mỡ cơ thể:** {latest.get('body_fat_pct', 'N/A')}%
🔥 **Calo nạp/tiêu:** {latest.get('calories_in', 0)}/{latest.get('calories_out', 0)} kcal
"""
        # Thêm insights từ analytics nếu có
        if data.get('analytics'):
            analytics = data['analytics']
            if analytics.get('weight_trend'):
                trend = analytics['weight_trend']
                if len(trend) >= 2:
                    change = trend[0]['avg_weight'] - trend[-1]['avg_weight']
                    if change < 0:
                        content += f"📉 Xu hướng: Giảm {abs(change):.1f}kg trong {len(trend)} ngày qua"
                    elif change > 0:
                        content += f"📈 Xu hướng: Tăng {change:.1f}kg trong {len(trend)} ngày qua"
                    else:
                        content += "➡️ Cân nặng ổn định"
        
        return content
    
    elif intent == "analytics_check":
        if not data:
            return "Chưa có đủ dữ liệu để phân tích. Hãy ghi lại vài ngày tập luyện và ăn uống!"
        
        overview = data.get('overview', {})
        daily_stats = data.get('daily_completion', {})
        
        content = f"""
📅 **TỔNG QUAN 7 NGÀY:**
🏋️ **Số buổi tập:** {overview.get('total_workouts', 0)}
🥗 **Số bữa ăn:** {overview.get('total_meals', 0)}
🔥 **Calo trung bình/ngày:** {overview.get('average_daily_calories', 0)}
📊 **Tỷ lệ duy trì:** {overview.get('consistency_rate', 0)}%

📈 **HIỆU SUẤT THEO NGÀY:**
"""
        for date_str, stats in list(daily_stats.items())[:3]:  # 3 ngày gần nhất
            content += f"• {date_str}: {stats.get('completion_rate', 0)}% completion\n"
            
        return content
    
    elif intent == "adaptive_suggestion":
        if not data:
            return "Hệ thống đang phân tích thói quen của bạn để đưa ra gợi ý tối ưu..."
        
        analysis = data.get('adaptive_analysis', {})
        performance = data.get('performance_summary', {})
        
        content = f"""
🎯 **PHÂN TÍCH HIỆU SUẤT:**
📊 Điểm hiệu suất: {performance.get('performance_score', 0)}%
💪 Số buổi tập: {performance.get('total_workouts', 0)}/{performance.get('target_workouts', 0)}
🔥 Calo đốt: {performance.get('total_calories_burned', 0)}/{performance.get('target_calories_burn', 0)}

💡 **GỢI Ý THÍCH ỨNG:**
{analysis.get('main_suggestion', 'Tiếp tục duy trì lịch tập hiện tại')}
"""
        return content
    
    # Các intent khác...
    return str(data) if data else "Tôi cần thêm thông tin để giúp bạn tốt hơn."

def add_motivational_element(intent: str, user_context: UserContext) -> str:
    """Thêm câu động viên phù hợp"""
    
    motivations = {
        "progress_check": [
            "Mỗi bước nhỏ đều đáng giá!",
            "Tiến bộ của bạn thật đáng kinh ngạc!",
            "Hãy tự hào về những gì bạn đã đạt được!"
        ],
        "workout_suggestion": [
            "Cơ thể mạnh mẽ, tâm trí mạnh mẽ!",
            "Hôm nay là ngày hoàn hảo để thử thách bản thân!",
            "Mỗi giọt mồ hôi đều xứng đáng!"
        ],
        "meal_suggestion": [
            "Dinh dưỡng tốt là nền tảng của thành công!",
            "Mỗi bữa ăn lành mạnh là một bước gần hơn đến mục tiêu!",
            "Cơ thể bạn sẽ cảm ơn bạn vì những lựa chọn thông minh!"
        ],
        "general": [
            "Bạn đang làm rất tốt!",
            "Tiếp tục phát huy nhé!",
            "Tôi tin vào bạn!"
        ]
    }
    
    import random
    key = intent if intent in motivations else "general"
    return random.choice(motivations[key])

def add_proactive_suggestion(intent: str, user_context: UserContext) -> str:
    """Đề xuất chủ động dựa trên context"""
    
    # Phân tích lịch sử để đưa ra đề xuất thông minh
    recent_intents = [msg['intent'] for msg in user_context.conversation_history[-3:]]
    
    if "progress_check" in recent_intents and "meal_suggestion" not in recent_intents:
        return "Bạn muốn tôi gợi ý thực đơn phù hợp với tiến độ hiện tại không?"
    
    if "workout_suggestion" in recent_intents and "progress_check" not in recent_intents:
        return "Hãy ghi lại kết quả tập luyện để tôi theo dõi tiến độ giúp bạn!"
    
    if len(user_context.conversation_history) > 5 and "analytics_check" not in recent_intents:
        return "Bạn có muốn xem báo cáo tổng quan về hoạt động gần đây không?"
    
    return ""

# ===================== OLLAMA ENHANCED =====================
def call_ollama_with_retry(payload, retries=2, delay=3):
    """Enhanced Ollama call với context"""
    for i in range(retries):
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                if "message" in data and "content" in data["message"]:
                    return {"choices": [{"message": {"content": data["message"]["content"]}}]}
                else:
                    logging.error(f"Ollama response missing message content: {data}")
                    return None
            else:
                logging.error(f"Ollama status {resp.status_code}: {resp.text}")
        except Exception as e:
            logging.error(f"Ollama request failed (try {i+1}): {e}")
            time.sleep(delay)
    return None

def call_ollama_coach(user_message: str, user_context: UserContext, intent: str) -> str:
    """Gọi Ollama với personality của coach"""
    
    context = user_context.get_conversation_summary()
    profile = user_context.user_profile
    preferences = user_context.user_preferences
    
    system_prompt = f"""
Bạn là Coach AI - một huấn luyện viên cá nhân thông minh, nhiệt tình và tận tâm.

THÔNG TIN USER:
- Tên: {profile.get('name', 'bạn')}
- Mục tiêu: {profile.get('goal', 'chưa xác định')}
- Chiều cao: {profile.get('height', 'N/A')}cm | Cân nặng: {profile.get('weight', 'N/A')}kg
- Sở thích: {preferences.get('preferred_exercises', 'chưa có')}
- Chế độ ăn: {preferences.get('diet_type', 'balanced')}

CONTEXT HỘI THOẠI:
{context}

INTENT HIỆN TẠI: {intent}

HÃY TRẢ LỜI:
- Bằng TIẾNG VIỆT tự nhiên, thân thiện
- Ngắn gọn nhưng đầy đủ thông tin
- Động viên, tích cực
- Cá nhân hóa dựa trên thông tin user
- Kèm emoji phù hợp
"""
    
    response = call_ollama_with_retry({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "stream": False
    })
    
    if response and "choices" in response:
        return response["choices"][0]["message"]["content"]
    else:
        return "Xin lỗi, hiện tôi không thể kết nối đến hệ thống AI. Vui lòng thử lại sau!"

# ===================== MAIN CHAT ENHANCED =====================
@chat_bp.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    """Enhanced chat endpoint với Personal Coach AI"""
    try:
        data = request.get_json(force=True)
        user_message = data.get("message", "")
        user_id = int(get_jwt_identity())
        auth_header = request.headers.get("Authorization")

        # Khởi tạo context
        user_context = get_user_context(user_id)
        
        # Lấy dữ liệu user từ các service
        profile_data = get_user_profile_data(user_id, auth_header)
        preference_data = get_user_preferences_data(user_id, auth_header)
        user_context.update_user_data(profile_data, preference_data)

        # Lưu tin nhắn user
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chats (user_id, message, is_user, timestamp) VALUES (%s,%s,%s,NOW())",
            (user_id, user_message, 1)
        )
        conn.commit()

        user_message_ascii = remove_accents(user_message.lower())

        # Lấy intent list từ DB
        cursor.execute("SELECT intent, description, sql_template FROM intent_mapping")
        all_intents = cursor.fetchall()
        intent_list = [row[0] for row in all_intents]

        # Phát hiện intent thông minh
        detected_intent = detect_intent_advanced(user_message_ascii, intent_list, user_context)
        sql_template = None
        for intent, desc, sql in all_intents:
            if intent == detected_intent:
                sql_template = sql
                break

        ai_response = None
        service_data = {}

        # ===== SMART SERVICE INTEGRATION =====
        if detected_intent == "progress_check":
            # Lấy progress + analytics
            progress_data = get_progress_from_service(user_id, auth_header)
            analytics_data = get_analytics_data(user_id, auth_header, "7")
            service_data = {
                "progress": progress_data,
                "analytics": analytics_data.get('analytics', {}) if analytics_data else {}
            }
            ai_response = generate_coach_response(detected_intent, service_data, user_context)

        elif detected_intent == "analytics_check":
            analytics_data = get_analytics_data(user_id, auth_header, "7")
            ai_response = generate_coach_response(detected_intent, analytics_data, user_context)

        elif detected_intent == "adaptive_suggestion":
            adaptive_data = get_adaptive_recommendations(user_id, auth_header)
            ai_response = generate_coach_response(detected_intent, adaptive_data, user_context)

        elif detected_intent == "recommendation":
            # Smart recommendation routing
            if 'tập' in user_message_ascii or 'workout' in user_message_ascii:
                try:
                    rec_response = requests.get(
                        f"{RECOMMEND_BASE_URL}/recommend/exercises",
                        headers={"Authorization": auth_header},
                        timeout=15
                    )
                    if rec_response.status_code == 200:
                        rec_data = rec_response.json()
                        ai_response = generate_coach_response("workout_suggestion", rec_data, user_context)
                except Exception as e:
                    logging.error(f"Exercise recommendation failed: {e}")
            
            elif 'ăn' in user_message_ascii or 'food' in user_message_ascii or 'meal' in user_message_ascii:
                try:
                    rec_response = requests.get(
                        f"{RECOMMEND_BASE_URL}/recommend/foods", 
                        headers={"Authorization": auth_header},
                        timeout=15
                    )
                    if rec_response.status_code == 200:
                        rec_data = rec_response.json()
                        ai_response = generate_coach_response("meal_suggestion", rec_data, user_context)
                except Exception as e:
                    logging.error(f"Food recommendation failed: {e}")
            
            else:
                # General recommendation
                ai_response = "Tôi có thể giúp bạn với:\n• 🏋️ Gợi ý bài tập\n• 🥗 Đề xuất thực đơn\n• 📊 Kế hoạch tuần\n\nBạn muốn tập trung vào điều gì?"

        # ===== FALLBACK TO SMART OLLAMA =====
        if not ai_response:
            ai_response = call_ollama_coach(user_message, user_context, detected_intent)

        # Cập nhật context với tin nhắn mới
        mood_detected = user_context.detect_mood(user_message)
        user_context.add_message(user_message, ai_response, detected_intent, mood_detected)

        # Lưu bot message
        cursor.execute(
            "INSERT INTO chats (user_id, message, is_user, timestamp) VALUES (%s,%s,%s,NOW())",
            (user_id, ai_response, 0)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "response": ai_response,
            "intent": detected_intent,
            "user_id": user_id,
            "mood": mood_detected,
            "context_id": id(user_context)
        })

    except Exception as e:
        logging.error(f"Unexpected error in chat route: {e}")
        return jsonify({"error": str(e)}), 500

# ===================== PROGRESS SERVICE HELPER =====================
def get_progress_from_service(user_id, auth_header):
    """Lấy progress data từ service"""
    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        progress_url = f"{PROGRESS_BASE_URL}/progress"
        response = requests.get(progress_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get("progress", [])
        elif response.status_code == 404:
            return []
        else:
            return None
    except Exception:
        return None

# ===================== HEALTH CHECK =====================
@chat_bp.route("/health", methods=["GET"])
def health_check():
    """Health check với thông tin service"""
    services_status = {}
    
    # Kiểm tra kết nối đến các service
    services = {
        "foods": FOODS_BASE_URL,
        "progress": PROGRESS_BASE_URL,
        "analytics": ANALYTICS_BASE_URL,
        "adaptive": ADAPTIVE_BASE_URL,
        "recommendation": RECOMMEND_BASE_URL,
        "preference": PREFERENCE_BASE_URL
    }
    
    for service_name, url in services.items():
        try:
            response = requests.get(f"{url}/health", timeout=5)
            services_status[service_name] = "healthy" if response.status_code == 200 else "unhealthy"
        except:
            services_status[service_name] = "unreachable"
    
    # Kiểm tra Ollama
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        ollama_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        ollama_status = "unreachable"
    
    return jsonify({
        'status': 'healthy',
        'service': 'Personal_Coach_Chat_Service',
        'version': '4.0.0',
        'timestamp': datetime.datetime.now().isoformat(),
        'services_status': services_status,
        'ollama_status': ollama_status,
        'active_users': len(user_contexts),
        'features': [
            'Context-Aware Conversations',
            'Multi-Service Integration', 
            'Personalized Coaching',
            'Mood Detection',
            'Proactive Suggestions',
            'Smart Intent Detection'
        ]
    })

# ===================== CONTEXT MANAGEMENT =====================
@chat_bp.route("/context/clear", methods=["POST"])
@jwt_required()
def clear_context():
    """Xóa context của user"""
    user_id = int(get_jwt_identity())
    if user_id in user_contexts:
        del user_contexts[user_id]
    return jsonify({"message": "Context cleared successfully"})

@chat_bp.route("/context/info", methods=["GET"])
@jwt_required()
def get_context_info():
    """Lấy thông tin context của user"""
    user_id = int(get_jwt_identity())
    user_context = get_user_context(user_id)
    
    return jsonify({
        "user_id": user_id,
        "conversation_count": len(user_context.conversation_history),
        "current_mood": user_context.conversation_mood,
        "last_interaction": user_context.last_interaction.isoformat(),
        "goals": user_context.current_goals,
        "recent_intents": [msg['intent'] for msg in user_context.conversation_history[-3:]]
    })