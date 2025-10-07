# ChatService.py
from flask import Blueprint, request, jsonify
from dbconnect import get_db_connection
import requests
import unicodedata
import re
import socket
import logging
import time
import datetime
from flask_jwt_extended import jwt_required, get_jwt_identity

chat_bp = Blueprint("chat", __name__)

# ===================== CONFIG =====================
def get_ollama_url():
    """
    Tự phát hiện URL Ollama:
    - Nếu đang chạy trong Docker Compose và service name là 'ollama' -> http://ollama:11434
    - Ngược lại dùng localhost
    """
    try:
        socket.gethostbyname("ollama")
        return "http://ollama:11434"
    except socket.error:
        return "http://localhost:11434"

OLLAMA_URL = get_ollama_url()
OLLAMA_MODEL = "llama3:8b"

# Base URLs cho các service nội bộ
FOODS_BASE_URL = "http://localhost:5000/api"
PROGRESS_BASE_URL = "http://localhost:5000/api"
WORKOUT_BASE_URL = "http://localhost:5000/api"
RECOMMEND_BASE_URL = "http://localhost:5000/api"

# ===================== LOGGING =====================
logging.basicConfig(
    filename="chat.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8"
)

# ===================== UTILS =====================
def remove_accents(input_str):
    nfkd_form = unicodedata.normalize("NFKD", input_str)
    no_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return no_accents.replace("đ", "d").replace("Đ", "D")

def extract_muscle_group(msg_ascii: str):
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
    grams_match = re.search(r"(\d+)\s*g", msg_ascii)
    grams = int(grams_match.group(1)) if grams_match else 100
    food_name = re.sub(r"\d+\s*g", "", msg_ascii)
    food_name = food_name.replace("calo", "").replace("kcal", "").strip()
    return food_name, grams

def extract_foods_from_message(msg_ascii: str):
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
            # chỉ giữ unit nếu không phải 'g'
            if unit and unit.lower() != "g":
                name = f"{unit} {name}"
            items.append({"name": name, "quantity": qty})
        else:
            items.append({"name": part, "quantity": 1})
    return items
# ===================== OLLAMA FIXED =====================
def call_ollama_with_retry(payload, retries=2, delay=3):
    """Fixed version for Ollama API"""
    for i in range(retries):
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=payload,
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                # FIX: Ollama returns {"message": {"content": "...", "role": "assistant"}, ...}
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

# ===================== INTENT DETECTION =====================
def detect_intent(user_message_ascii: str, intent_list):
    """
    Hybrid intent detection:
    - Ưu tiên rule-based với keyword.
    - Nếu không match thì fallback sang LLM (Ollama).
    """
    message = user_message_ascii.lower().strip()

    # 1) progress_check
    progress_keywords = [
        "tiến độ", "progress", "giảm cân", "tăng cân", "trong tháng", "trong tuần",
        "tập luyện", "kết quả", "theo dõi", "cân nặng", "body fat", "bodyfat",
        "xem tiến độ", "tiến độ tập", "tiến độ giảm", "kết quả tập", "theo dõi cân",
        "bao nhiêu cân", "cân nặng hiện", "chỉ số hiện", "số đo", "vòng bụng",
        "mỡ cơ thể", "phần trăm mỡ", "kết quả giảm cân", "thành tích"
    ]
    if any(kw in message for kw in progress_keywords):
        return "progress_check"

    # 2) recommendation (ưu tiên trước meal_suggestion để tránh đè)
    recom_keywords = [
        "recommend", "recommendation", "đề xuất", "cá nhân hóa", "ca nhan hoa",
        "kế hoạch tuần", "ke hoach tuan", "weekly plan", "tip nhanh", "quick tip",
        "gợi ý cá nhân", "goi y ca nhan", "gợi ý ăn", "goi y an"
    ]
    if any(kw in message for kw in recom_keywords):
        return "recommendation"

    # 3) workout_suggestion
    workout_keywords = [
        "bài tập", "workout", "tập luyện", "nhóm cơ", "cơ bụng", "cơ ngực",
        "cơ tay", "cơ chân", "tập cho", "exercise", "tập", "bụng", "tay",
        "chân", "ngực", "lưng", "vai", "mông", "đùi", "bắp tay", "bắp chân",
        "gợi ý tập", "goi y tap","nên tập gì", "tập gì cho", "bài tập cho", "exercise for",
        "workout cho", "tập cơ", "phát triển cơ", "tăng cơ", "giảm mỡ"
    ]
    if any(kw in message for kw in workout_keywords):
        return "workout_suggestion"

    # 4) meal_suggestion
    meal_keywords = [
        "thực phẩm", "ăn gì", "meal", "món ăn", "bữa ăn", "thức ăn",
        "đồ ăn", "bữa sáng", "bữa trưa", "bữa tối", "suggest",
        "nên ăn", "thực đơn", "menu", "món healthy", "ăn gì để", "thực phẩm nào"
    ]
    if any(kw in message for kw in meal_keywords):
        return "meal_suggestion"

    # 5) add_meal
    add_meal_keywords = [
        "tôi vừa ăn", "ghi lại", "lưu bữa ăn", "đã ăn", "vừa ăn", "ate",
        "mới ăn", "vua an", "ghi lai", "thêm bữa ăn", "log meal", "log food",
        "ăn xong", "vừa ăn xong", "tôi mới ăn", "đã dùng bữa", "vừa dùng bữa",
        "ăn sáng xong", "ăn trưa xong", "ăn tối xong", "bữa ăn vừa xong"
    ]
    if any(kw in message for kw in add_meal_keywords):
        return "add_meal"

    # 6) food_lookup (chỉ khi không trùng các intent khác)
    food_keywords = [
        "calo", "kcal", "protein", "carb", "fat", "gram", "gam",
        "bao nhiêu calo", "bao nhiêu protein", "nutrition facts", "giá trị dinh dưỡng"
    ]
    if (
        any(kw in message for kw in food_keywords)
        and not any(kw in message for kw in meal_keywords)
        and not any(kw in message for kw in add_meal_keywords)
        and not any(kw in message for kw in progress_keywords)
        and not any(kw in message for kw in workout_keywords)
        and not any(kw in message for kw in recom_keywords)
    ):
        return "food_lookup"

    # 7) meal_history
    history_keywords = [
        "lịch sử ăn", "hôm qua ăn", "bữa trước", "meal history", "đã ăn gì",
        "ăn gì hôm qua", "history", "lịch sử", "hôm qua", "hôm kia", "tuần trước",
        "tháng trước", "các bữa ăn trước", "bữa ăn đã qua", "đã ăn những gì",
        "ăn gì những hôm trước", "lịch sử bữa ăn", "meal log", "nhật ký ăn uống"
    ]
    if any(kw in message for kw in history_keywords):
        return "meal_history"

    # 8) plan_overview
    plan_keywords = [
        "kế hoạch", "plan", "tuần này", "tuần tới", "lịch tập", "lịch ăn",
        "kế hoạch tuần", "lịch trình", "schedule", "lịch", "kế hoạch tập",
        "kế hoạch ăn", "lịch tập luyện", "lịch ăn uống", "kế hoạch hàng tuần",
        "lịch trình tuần", "plan for week", "weekly plan overview"
    ]
    if any(kw in message for kw in plan_keywords):
        return "plan_overview"

    # 9) daily_summary
    daily_keywords = [
        "hôm nay", "tóm tắt", "summary", "in/out", "nạp vào", "tiêu hao",
        "calo hôm nay", "hôm nay ăn", "tổng kết hôm nay", "hôm nay thế nào",
        "kết quả hôm nay", "today", "hôm nay tập", "hôm nay đốt", "calories today",
        "hôm nay nạp", "hôm nay tiêu", "tổng hợp hôm nay", "daily summary"
    ]
    if any(kw in message for kw in daily_keywords):
        return "daily_summary"

    # 10) general_health
    health_keywords = [
        "bmi", "bmr", "sức khỏe", "tình trạng", "health", "chỉ số", "sức khoẻ",
        "suc khoe", "tình trạng sức khỏe", "chỉ số sức khỏe", "health status",
        "tình hình sức khỏe", "kiểm tra sức khỏe", "đánh giá sức khỏe",
        "chỉ số cơ thể", "body metrics", "health metrics", "tính bmi", "tính bmr"
    ]
    if any(kw in message for kw in health_keywords):
        return "general_health"

    # 11) fallback to LLM (chỉ trả về intent name)
    try:
        prompt = f"""
Bạn là bộ phân loại intent cho hệ thống GymLife.
Người dùng nhắn: "{message}"
Các intent hợp lệ: {intent_list}
Trả về DUY NHẤT tên intent trong danh sách.
"""
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": False  # FIX: đúng parameter
            },
            timeout=60,
        )
        if response.status_code == 200:
            data = response.json()
            intent = data.get("message", {}).get("content", "").strip().lower()  # FIX: đúng cấu trúc
            if intent in intent_list:
                logging.info(f"[LLM] Intent '{intent}' detected")
                return intent
            else:
                logging.warning(f"[LLM] Invalid intent returned: {intent}")
    except Exception as e:
        logging.error(f"[LLM] Fallback failed: {e}")

    return None

# ===================== PROGRESS SERVICE =====================
def get_progress_from_service(user_id, auth_header):
    try:
        headers = {"Authorization": auth_header} if auth_header else {}
        progress_url = f"{PROGRESS_BASE_URL}/progress"
        response = requests.get(progress_url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("progress", [])
        elif response.status_code == 404:
            return []
        else:
            return None
    except Exception:
        return None

def format_progress_response(progress_data):
    if not progress_data:
        return "📊 Hiện chưa có dữ liệu tiến độ nào được ghi lại."
    sorted_progress = sorted(progress_data, key=lambda x: x.get('date', ''), reverse=True)
    response_lines = ["📈 **TIẾN ĐỘ CỦA BẠN:**"]
    for progress in sorted_progress[:5]:
        date = progress.get('date', 'Unknown date')
        weight = progress.get('weight', 'N/A')
        bmi = progress.get('bmi')
        body_fat_pct = progress.get('body_fat_pct')
        calories_in = progress.get('calories_in', 0)
        calories_out = progress.get('calories_out', 0)
        line = f"\n📅 **{date}:**"
        line += f"\n   • ⚖️ Cân nặng: {weight}kg"
        line += f"\n   • 📊 BMI: {bmi:.1f}" if isinstance(bmi, (int, float)) else "\n   • 📊 BMI: N/A"
        line += f"\n   • 💪 Mỡ cơ thể: {body_fat_pct}%" if isinstance(body_fat_pct, (int, float)) else "\n   • 💪 Mỡ cơ thể: N/A"
        line += f"\n   • 🔥 Calo nạp/tiêu: {calories_in}/{calories_out} kcal"
        response_lines.append(line)
    if len(sorted_progress) > 5:
        response_lines.append(f"\nℹ️ Hiển thị 5/{len(sorted_progress)} bản ghi mới nhất.")
    return "\n".join(response_lines)

# ===================== FORMATTER =====================
def format_response(intent, rows, extra=None):
    if not rows:
        return None
    if intent == "workout_suggestion":
        workout_list = [r[0] for r in rows]
        return f"💪 Gợi ý bài tập cho nhóm cơ {extra.get('muscle','')}: " + ", ".join(workout_list)
    elif intent == "general_health":
        bmi, bmr = rows[0]
        return f"📊 Chỉ số sức khỏe:\n- BMI: {bmi:.2f}\n- BMR: {bmr:.0f} kcal/ngày"
    elif intent == "daily_summary":
        return "\n".join([f"📅 {d}: Nạp {ci} kcal | Tiêu hao {co} kcal | Cân bằng: {ci - co} kcal" for d, ci, co in rows])
    elif intent == "plan_overview":
        return "🗓️ Kế hoạch tuần của bạn:\n" + "\n".join([f"- {r[1]}: {r[2]}" for r in rows])
    elif intent == "progress_check":
        return None
    return None

# ===================== RECOMMENDATION HELPERS =====================
def format_recommendation_response(intent_hint: str, data: dict) -> str:
    """
    Làm gọn response từ Recommendation_service.
    """
    try:
        if "weekly" in intent_hint:
            plan = data.get("weekly_plan", {})
            lines = [f"🗓️ Kế hoạch tuần (mục tiêu: {data.get('goal','?')}, level: {data.get('user_level','?')}):"]
            for day, detail in plan.items():
                focus = detail.get("focus", "")
                w = ", ".join([x.get("name","") for x in detail.get("workouts", [])]) or "Nghỉ"
                m = ", ".join([f"{x['meal_type']}: {x['food']['name']}" for x in detail.get("meals", [])]) if detail.get("meals") else "—"
                lines.append(f"• {day} ({focus}): 🏋️ {w} | 🍽️ {m}")
            return "\n".join(lines) if lines else "Không tạo được kế hoạch tuần."
        if "quick" in intent_hint or "tip" in intent_hint:
            tips = data.get("tips", [])
            if not tips:
                return "Hôm nay chưa có mẹo nào."
            return "⚡ Mẹo nhanh hôm nay:\n- " + "\n- ".join(tips)
        if "meals" in intent_hint:
            meals = data.get("recommended_meals", [])
            if not meals:
                return "Chưa có gợi ý bữa ăn phù hợp."
            top = meals[:5]
            lines = [f"🥗 Gợi ý bữa ăn (goal: {data.get('goal','?')}):"]
            for f in top:
                lines.append(f"- {f['name']} ({f['calories']} kcal, P:{f['protein']}g C:{f['carbs']}g F:{f['fat']}g)")
            return "\n".join(lines)
        # workouts default
        workouts = data.get("recommended_workouts", [])
        if not workouts:
            return "Chưa có gợi ý bài tập phù hợp."
        top = workouts[:6]
        lines = [f"💪 Gợi ý bài tập (goal: {data.get('goal','?')}, level: {data.get('user_level','?')}):"]
        for w in top:
            lines.append(f"- {w['name']} ({w['body_part']}) • {w['sets']}x{w['reps']} hoặc {w['duration']}′")
        return "\n".join(lines)
    except Exception:
        return "🤖 Gợi ý cá nhân hóa:\n" + str(data)

# ===================== MAIN CHAT =====================
@chat_bp.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "")
        user_id = int(get_jwt_identity())
        auth_header = request.headers.get("Authorization")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chats (user_id, message, is_user, timestamp) VALUES (%s,%s,%s,NOW())",
                       (user_id, user_message, 1))
        conn.commit()

        user_message_ascii = remove_accents(user_message.lower())

        # lấy intent list từ DB
        cursor.execute("SELECT intent, description, sql_template FROM intent_mapping")
        all_intents = cursor.fetchall()
        intent_list = [row[0] for row in all_intents]

        detected_intent = detect_intent(user_message_ascii, intent_list)
        sql_template = None
        for intent, desc, sql in all_intents:
            if intent == detected_intent:
                sql_template = sql
                break

        ai_response = None

        # ===== progress_check =====
        if detected_intent == "progress_check":
            progress_data = get_progress_from_service(user_id, auth_header)
            ai_response = format_progress_response(progress_data) if progress_data is not None else "❌ Lỗi kết nối dịch vụ tiến độ."

        # ===== food_lookup FIXED =====
        elif detected_intent == "food_lookup":
            food_name, grams = extract_food_and_grams(user_message_ascii)
            try:
                # FIX: Sử dụng endpoint chính xác từ kiểm tra
                r = requests.get(
                    f"{FOODS_BASE_URL}/foods", 
                    params={"q": food_name, "limit": 5},
                    headers={"Authorization": auth_header} if auth_header else {},
                    timeout=10
                )
                
                if r.status_code == 200:
                    dataf = r.json()
                    foods = dataf.get("foods", [])
                    
                    if foods:
                        # Tìm food name khớp nhất
                        matching_food = None
                        for food in foods:
                            if food_name.lower() in food.get('name', '').lower():
                                matching_food = food
                                break
                        
                        if not matching_food:
                            matching_food = foods[0]  # Lấy food đầu tiên nếu không khớp chính xác
                        
                        # FIX: Xử lý dữ liệu số đúng cách
                        calories = float(matching_food.get("calories", 0))
                        protein = float(matching_food.get("protein", 0))
                        carbs = float(matching_food.get("carbs", 0))
                        fat = float(matching_food.get("fat", 0))
                        
                        # Tính toán cho lượng grams cụ thể
                        cal_per_gram = calories * grams / 100
                        protein_per_gram = protein * grams / 100
                        carbs_per_gram = carbs * grams / 100
                        fat_per_gram = fat * grams / 100
                        
                        ai_response = f"🍚 {grams}g {matching_food['name']}: {cal_per_gram:.1f} kcal | P:{protein_per_gram:.1f}g C:{carbs_per_gram:.1f}g F:{fat_per_gram:.1f}g"
                    else:
                        ai_response = "Không tìm thấy món ăn trong cơ sở dữ liệu."
                else:
                    ai_response = "❌ Không thể kết nối đến dịch vụ thực phẩm."
                    
            except Exception as e:
                logging.error(f"Food lookup error: {e}")
                ai_response = "❌ Lỗi kết nối dịch vụ thực phẩm."

        # ===== meal_suggestion FIXED =====
        elif detected_intent == "meal_suggestion":
            goal = "tăng cơ" if "tang" in user_message_ascii or "tăng" in user_message_ascii else \
                   "giảm cân" if "giam" in user_message_ascii or "giảm" in user_message_ascii else "duy trì"
            try:
                # FIX: Sử dụng foods endpoint với filtering
                r = requests.get(
                    f"{FOODS_BASE_URL}/foods",
                    params={"limit": 3},
                    headers={"Authorization": auth_header} if auth_header else {},
                    timeout=10
                )
                
                if r.status_code == 200:
                    dataf = r.json()
                    foods = dataf.get("foods", [])
                    
                    # Lọc foods theo goal
                    filtered_foods = []
                    for food in foods:
                        food_goal = food.get("goal", "").lower()
                        if goal in food_goal or food_goal == "all" or not food_goal:
                            filtered_foods.append(food)
                        if len(filtered_foods) >= 3:
                            break
                    
                    if filtered_foods:
                        meals = []
                        for food in filtered_foods:
                            meals.append(f"- {food['name']} ({food.get('calories', '?')} kcal, P:{food.get('protein', '?')}g C:{food.get('carbs', '?')}g F:{food.get('fat', '?')}g)")
                        
                        ai_response = f"🥗 Gợi ý thực phẩm cho mục tiêu {goal}:\n" + "\n".join(meals)
                    else:
                        ai_response = f"Chưa có gợi ý thực phẩm cho mục tiêu {goal}."
                else:
                    ai_response = "❌ Không thể kết nối đến dịch vụ thực phẩm."
                    
            except Exception as e:
                logging.error(f"Meal suggestion error: {e}")
                ai_response = "❌ Lỗi kết nối dịch vụ gợi ý bữa ăn."

        # ===== meal_history =====
        elif detected_intent == "meal_history":
            try:
                r = requests.get(f"{FOODS_BASE_URL}/meals/history",
                                 headers={"Authorization": auth_header} if auth_header else {})
                if r.status_code == 200:
                    meals = r.json()
                    if meals:
                        latest = meals[0]
                        ai_response = f"📅 {latest['date']} ({latest['meal_type']}): {latest['total_calories']} kcal với {len(latest.get('foods', []))} món."
                    else:
                        ai_response = "Bạn chưa lưu bữa ăn nào."
                else:
                    ai_response = "❌ Không thể kết nối đến lịch sử bữa ăn."
            except Exception:
                ai_response = "❌ Lỗi kết nối lịch sử bữa ăn."

        # ===== add_meal FIXED =====
        elif detected_intent == "add_meal":
            items = extract_foods_from_message(user_message_ascii)
            if items:
                try:
                    # FIX: Chuẩn bị payload đúng cấu trúc
                    meal_items = []
                    for item in items:
                        meal_items.append({
                            "food_name": item["name"],
                            "quantity": item["quantity"]
                        })
                    
                    payload = {
                        "date": str(datetime.date.today()),
                        "meal_type": "other",
                        "items": meal_items
                    }
                    
                    # FIX: Thử các endpoint có thể có
                    headers = {"Authorization": auth_header, "Content-Type": "application/json"} if auth_header else {"Content-Type": "application/json"}
                    
                    r = requests.post(
                        f"{FOODS_BASE_URL}/meals",
                        json=payload,
                        headers=headers,
                        timeout=10
                    )
                    
                    if r.status_code in [200, 201]:
                        ai_response = "🍽️ Đã lưu bữa ăn thành công!"
                    else:
                        logging.error(f"Add meal failed: {r.status_code} - {r.text}")
                        ai_response = "⚠️ Không thể lưu bữa ăn. Có thể endpoint chưa được implement."
                        
                except Exception as e:
                    logging.error(f"Add meal error: {e}")
                    ai_response = "❌ Lỗi khi kết nối dịch vụ lưu bữa ăn."
            else:
                ai_response = "⚠️ Không thể nhận diện món ăn từ tin nhắn của bạn."

        # ===== recommendation =====
        elif detected_intent == "recommendation":
            try:
                # Chọn endpoint phù hợp theo câu hỏi
                if "tuan" in user_message_ascii or "tuần" in user_message_ascii or "weekly" in user_message_ascii:
                    ep = "weekly-plan"; hint = "weekly"
                elif "tip" in user_message_ascii or "meo" in user_message_ascii or "mẹo" in user_message_ascii or "quick" in user_message_ascii:
                    ep = "quick-tip"; hint = "quick"
                elif "an" in user_message_ascii or "ăn" in user_message_ascii or "meal" in user_message_ascii:
                    ep = "meals"; hint = "meals"
                else:
                    ep = "workouts"; hint = "workouts"

                r = requests.get(
                    f"{RECOMMEND_BASE_URL}/recommendations/{ep}",
                    headers={"Authorization": auth_header} if auth_header else {},
                    timeout=15
                )
                if r.status_code == 200:
                    ai_response = format_recommendation_response(hint, r.json())
                elif r.status_code == 404:
                    ai_response = "Chưa đủ dữ liệu profile/lịch sử để gợi ý. Hãy cập nhật hồ sơ và ghi lại vài buổi tập/bữa ăn nhé!"
                else:
                    ai_response = "❌ Không thể kết nối đến Recommendation Service."
            except Exception:
                ai_response = "❌ Lỗi khi kết nối Recommendation Service."

        # ===== DB intents (giữ nguyên cơ chế) =====
        elif detected_intent and sql_template:
            try:
                if detected_intent == "workout_suggestion":
                    mg = extract_muscle_group(user_message_ascii)
                    if mg:
                        cursor.execute(sql_template, (mg,))
                        rows = cursor.fetchall()
                        ai_response = format_response(detected_intent, rows, {"muscle": mg})
                    else:
                        cursor.execute("SELECT name FROM exercises LIMIT 5")
                        rows = cursor.fetchall()
                        ai_response = "💪 Gợi ý bài tập phổ biến: " + ", ".join([r[0] for r in rows]) if rows else "🤔 Bạn muốn tập cho nhóm cơ nào?"
                else:
                    if "%s" in sql_template:
                        cursor.execute(sql_template, (user_id,))
                    else:
                        cursor.execute(sql_template)
                    rows = cursor.fetchall()
                    ai_response = format_response(detected_intent, rows)
            except Exception as e:
                ai_response = f"⚠️ Query failed ({detected_intent}): {str(e)}"

        # ===== fallback to Ollama FIXED =====
        if not ai_response:
            response_json = call_ollama_with_retry({
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": "Bạn là huấn luyện viên dinh dưỡng và tập luyện. Trả lời bằng TIẾNG VIỆT, ngắn gọn, rõ ràng, chính xác."},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0.4,
                "stream": False
            })
            
            # FIX: Xử lý response đúng cách
            if response_json and "choices" in response_json:
                ai_response = response_json["choices"][0]["message"]["content"]
            else:
                ai_response = "⚠️ Hiện không thể kết nối đến AI. Vui lòng thử lại sau."

        # Lưu bot message
        cursor.execute("INSERT INTO chats (user_id, message, is_user, timestamp) VALUES (%s,%s,%s,NOW())",
                       (user_id, ai_response, 0))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"response": ai_response or "không có dữ liệu", "intent": detected_intent, "user_id": user_id})

    except Exception as e:
        logging.error(f"Unexpected error in chat route: {e}")
        return jsonify({"error": str(e)}), 500