import mysql.connector

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host='localhost',           # ✅ Kết nối đến MySQL trên Windows
            user='root',                # ✅ Username MySQL của bạn
            password='241103',          # ✅ Password MySQL của bạn (đổi thành password thật)
            database='fitai',      # ✅ Tên database
            port=3306,                  # ✅ Port mặc định của MySQL
            auth_plugin='mysql_native_password'  # ✅ Quan trọng: thêm dòng này
        )
        print("✅ Kết nối database thành công!")
        return conn
    except Exception as e:
        print(f"❌ Lỗi kết nối database: {e}")
        return None