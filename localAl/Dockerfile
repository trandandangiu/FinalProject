# Sử dụng image Python chính thức
FROM python:3.9-slim

# Thiết lập thư mục làm việc trong container
WORKDIR /app

# Sao chép file requirements.txt vào container
COPY requirements.txt .

# Cài đặt các dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép toàn bộ source code vào container
COPY . .

# Expose port mà ứng dụng chạy trên
EXPOSE 5000

# Chạy ứng dụng Flask
CMD ["python", "app.py"]s