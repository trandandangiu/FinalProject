# test_chat_service.py
import pytest
import requests
import json
import time
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Thêm thư mục gốc vào path để import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Base URL cho testing
BASE_URL = "http://localhost:5000"
CHAT_URL = f"{BASE_URL}/api/chat"

# Mock JWT token cho testing
TEST_TOKEN = "Bearer mock_jwt_token_12345"
TEST_USER_ID = 1

class TestChatService:
    """Test suite toàn diện cho ChatService"""
    
    def setup_method(self):
        """Setup trước mỗi test"""
        self.headers = {"Authorization": TEST_TOKEN}
        self.test_user_id = TEST_USER_ID
        
    def test_health_check(self):
        """Test health check endpoint"""
        response = requests.get(f"{BASE_URL}/api/chat/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['status'] == 'healthy'
        assert data['service'] == 'Personal_Coach_Chat_Service'
        assert 'active_users' in data
        assert 'services_status' in data
        assert 'ollama_status' in data
        assert 'features' in data
        
        print("✓ Health check passed")

    def test_chat_endpoint_authentication(self):
        """Test authentication requirement"""
        # Test không có token
        response = requests.post(CHAT_URL, json={"message": "test"})
        assert response.status_code == 401
        
        print("✓ Authentication test passed")

    @patch('requests.get')
    def test_chat_general_conversation(self, mock_requests):
        """Test hội thoại chung"""
        # Mock responses từ các service
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User",
                "goal": "giảm cân", 
                "height": 170,
                "weight": 70
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={
                "diet_type": "balanced",
                "preferred_exercises": ["chạy bộ", "yoga"]
            })),
            # Database response for intents
            Mock(status_code=200, json=Mock(return_value=[]))
        ]
        
        test_message = "Xin chào, tôi mới bắt đầu tập gym"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'response' in data
        assert 'intent' in data
        assert 'user_id' in data
        assert 'mood' in data
        assert data['user_id'] == self.test_user_id
        
        print("✓ General conversation test passed")

    @patch('requests.get')
    def test_chat_progress_check(self, mock_requests):
        """Test kiểm tra tiến độ"""
        # Mock responses
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User",
                "goal": "giảm cân",
                "height": 170,
                "weight": 70
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={
                "diet_type": "balanced"
            })),
            # Progress data
            Mock(status_code=200, json=Mock(return_value={
                "progress": [
                    {
                        "date": "2024-01-15",
                        "weight": 68.5,
                        "bmi": 23.7,
                        "bmi_category": "Bình thường",
                        "body_fat_pct": 18.5,
                        "calories_in": 1800,
                        "calories_out": 2200
                    }
                ]
            })),
            # Analytics data
            Mock(status_code=200, json=Mock(return_value={
                "analytics": {
                    "weight_trend": [
                        {"avg_weight": 70.0},
                        {"avg_weight": 68.5}
                    ]
                }
            }))
        ]
        
        test_message = "Tôi muốn xem tiến độ giảm cân của mình"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['intent'] == 'progress_check'
        assert 'response' in data
        assert 'tiến độ' in data['response'].lower() or 'progress' in data['response'].lower()
        
        print("✓ Progress check test passed")

    @patch('requests.get')
    def test_chat_workout_suggestion(self, mock_requests):
        """Test gợi ý bài tập"""
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User",
                "goal": "tăng cơ"
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={
                "preferred_exercises": ["tạ tay", "hít đất"]
            })),
            # Exercise recommendation
            Mock(status_code=200, json=Mock(return_value={
                "exercises": [
                    {"name": "Push-up", "muscle_group": "chest"},
                    {"name": "Dumbbell Curl", "muscle_group": "arms"}
                ]
            }))
        ]
        
        test_message = "Gợi ý cho tôi bài tập cho cơ tay"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Có thể là workout_suggestion hoặc recommendation
        assert data['intent'] in ['workout_suggestion', 'recommendation']
        assert 'response' in data
        
        print("✓ Workout suggestion test passed")

    @patch('requests.get')
    def test_chat_meal_suggestion(self, mock_requests):
        """Test gợi ý bữa ăn"""
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User", 
                "goal": "giảm cân"
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={
                "diet_type": "low_carb"
            })),
            # Food recommendation
            Mock(status_code=200, json=Mock(return_value={
                "foods": [
                    {"name": "Ức gà", "calories": 165},
                    {"name": "Rau xà lách", "calories": 15}
                ]
            }))
        ]
        
        test_message = "Tôi nên ăn gì cho bữa trưa?"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['intent'] in ['meal_suggestion', 'recommendation']
        assert 'response' in data
        
        print("✓ Meal suggestion test passed")

    @patch('requests.get')
    def test_chat_analytics_check(self, mock_requests):
        """Test kiểm tra analytics"""
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User"
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={})),
            # Analytics data
            Mock(status_code=200, json=Mock(return_value={
                "overview": {
                    "total_workouts": 5,
                    "total_meals": 21,
                    "average_daily_calories": 1850,
                    "consistency_rate": 85
                },
                "daily_completion": {
                    "2024-01-15": {"completion_rate": 90},
                    "2024-01-14": {"completion_rate": 80}
                }
            }))
        ]
        
        test_message = "Cho tôi xem phân tích hoạt động tuần qua"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['intent'] == 'analytics_check'
        assert 'phân tích' in data['response'].lower() or 'analytics' in data['response'].lower()
        
        print("✓ Analytics check test passed")

    @patch('requests.get')
    def test_chat_adaptive_suggestion(self, mock_requests):
        """Test gợi ý thích ứng"""
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User"
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={})),
            # Adaptive recommendations
            Mock(status_code=200, json=Mock(return_value={
                "adaptive_analysis": {
                    "main_suggestion": "Tăng cường độ tập cardio"
                },
                "performance_summary": {
                    "performance_score": 75,
                    "total_workouts": 4,
                    "target_workouts": 5,
                    "total_calories_burned": 1800,
                    "target_calories_burn": 2000
                }
            }))
        ]
        
        test_message = "Gợi ý thông minh cho tôi"
        
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": test_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data['intent'] == 'adaptive_suggestion'
        assert 'gợi ý' in data['response'].lower() or 'suggestion' in data['response'].lower()
        
        print("✓ Adaptive suggestion test passed")

    def test_context_management(self):
        """Test quản lý context"""
        # Test get context info
        response = requests.get(
            f"{BASE_URL}/api/chat/context/info",
            headers=self.headers
        )
        
        assert response.status_code == 200
        context_info = response.json()
        
        assert context_info['user_id'] == self.test_user_id
        assert 'conversation_count' in context_info
        assert 'current_mood' in context_info
        assert 'last_interaction' in context_info
        
        # Test clear context
        response = requests.post(
            f"{BASE_URL}/api/chat/context/clear",
            headers=self.headers
        )
        
        assert response.status_code == 200
        assert 'cleared' in response.json()['message'].lower()
        
        print("✓ Context management test passed")

    @patch('requests.get')
    def test_mood_detection(self, mock_requests):
        """Test phát hiện tâm trạng"""
        mock_requests.side_effect = [
            # User profile
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User"
            })),
            # User preferences
            Mock(status_code=200, json=Mock(return_value={}))
        ]
        
        # Test tin nhắn vui vẻ
        happy_message = "Hôm nay tôi cảm thấy rất tuyệt!"
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": happy_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['mood'] == 'happy'
        
        # Test tin nhắn căng thẳng
        stressed_message = "Tôi đang rất căng thẳng với công việc"
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": stressed_message}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['mood'] == 'stressed'
        
        print("✓ Mood detection test passed")

    @patch('requests.get')
    def test_conversation_flow(self, mock_requests):
        """Test luồng hội thoại liên tục"""
        # Mock data cho multiple calls
        mock_responses = [
            # Call 1: User profile + preferences
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User",
                "goal": "giảm cân",
                "height": 170,
                "weight": 70
            })),
            Mock(status_code=200, json=Mock(return_value={
                "diet_type": "balanced"
            })),
            # Call 2: User profile + preferences
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User",
                "goal": "giảm cân"
            })),
            Mock(status_code=200, json=Mock(return_value={
                "diet_type": "balanced"
            })),
            # Call 3: User profile + preferences
            Mock(status_code=200, json=Mock(return_value={
                "name": "Test User"
            })),
            Mock(status_code=200, json=Mock(return_value={}))
        ]
        
        mock_requests.side_effect = mock_responses
        
        # Thực hiện chuỗi hội thoại
        messages = [
            "Xin chào coach!",
            "Tôi muốn xem tiến độ của mình",
            "Gợi ý cho tôi bài tập ngày hôm nay"
        ]
        
        for i, message in enumerate(messages):
            response = requests.post(
                CHAT_URL,
                headers=self.headers,
                json={"message": message}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert 'response' in data
            assert 'intent' in data
            
            print(f"✓ Conversation step {i+1} passed")
        
        # Kiểm tra context được duy trì
        context_response = requests.get(
            f"{BASE_URL}/api/chat/context/info",
            headers=self.headers
        )
        
        context_info = context_response.json()
        assert context_info['conversation_count'] >= len(messages)
        
        print("✓ Conversation flow test passed")

    @patch('requests.get')
    def test_error_handling(self, mock_requests):
        """Test xử lý lỗi"""
        # Mock service failure
        mock_requests.side_effect = [
            Exception("Service unavailable"),
            Exception("Service unavailable")
        ]
        
        # Test vẫn hoạt động khi service lỗi
        response = requests.post(
            CHAT_URL,
            headers=self.headers,
            json={"message": "Xin chào"}
        )
        
        # Vẫn nên nhận được response (fallback to Ollama)
        assert response.status_code == 200
        data = response.json()
        assert 'response' in data
        
        print("✓ Error handling test passed")

    def test_intent_detection_edge_cases(self):
        """Test các trường hợp biên của intent detection"""
        test_cases = [
            # (message, expected_intent_pattern)
            ("", "general_chat"),
            ("123456", "general_chat"),
            ("!!!@#$%", "general_chat"),
            ("calo trong 100g thịt gà", "food_lookup"),
            ("tôi vừa ăn phở", "add_meal"),
            ("bmi của tôi là bao nhiêu", "general_health"),
            ("hôm nay tóm tắt", "daily_summary"),
        ]
        
        print("✓ Intent detection edge cases defined")

    @patch('requests.get')
    def test_performance(self, mock_requests):
        """Test hiệu năng"""
        # Mock nhanh các service
        mock_requests.return_value = Mock(
            status_code=200, 
            json=Mock(return_value={})
        )
        
        start_time = time.time()
        
        # Thực hiện multiple requests
        for i in range(3):
            response = requests.post(
                CHAT_URL,
                headers=self.headers,
                json={"message": f"Test message {i}"}
            )
            assert response.status_code == 200
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Mỗi request nên dưới 5 giây
        assert total_time < 15, f"Performance test failed: {total_time}s for 3 requests"
        
        print(f"✓ Performance test passed: {total_time:.2f}s for 3 requests")

def run_all_tests():
    """Chạy tất cả tests"""
    test_suite = TestChatService()
    
    print("🚀 BẮT ĐẦU TEST CHAT SERVICE")
    print("=" * 50)
    
    tests = [
        test_suite.test_health_check,
        test_suite.test_chat_endpoint_authentication,
        test_suite.test_chat_general_conversation,
        test_suite.test_chat_progress_check,
        test_suite.test_chat_workout_suggestion,
        test_suite.test_chat_meal_suggestion,
        test_suite.test_chat_analytics_check,
        test_suite.test_chat_adaptive_suggestion,
        test_suite.test_context_management,
        test_suite.test_mood_detection,
        test_suite.test_conversation_flow,
        test_suite.test_error_handling,
        test_suite.test_intent_detection_edge_cases,
        test_suite.test_performance,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test_suite.setup_method()
            test()
            passed += 1
            print(f"✅ {test.__name__} - PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__} - FAILED: {str(e)}")
        print("-" * 30)
    
    print("=" * 50)
    print(f"🎯 KẾT QUẢ TEST: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 TẤT CẢ TEST ĐÃ PASSED!")
    else:
        print(f"⚠️  CÓ {failed} TEST FAILED, cần kiểm tra lại")
    
    return failed == 0

if __name__ == "__main__":
    # Chạy tests
    success = run_all_tests()
    
    # Exit code cho CI/CD
    sys.exit(0 if success else 1)