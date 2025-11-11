from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import json
from .forms import OptimizationForm
# --- THAY ĐỔI: Import thêm SolverTimer ---
from .optimization_logic import SteelCuttingOptimizer, SolverTimer
import asyncio
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import os
import sys
# import signal # <-- Đã bỏ

class TeeStream:
    def __init__(self, websocket_room):
        self.websocket_room = websocket_room
        self.channel_layer = get_channel_layer()

    def write(self, message):
        if message.strip():
            async_to_sync(self.channel_layer.group_send)(
                f"{self.websocket_room}",
                {"type": "chat.message", "message": message}
            )

    def flush(self):
        pass

def index(request):
    form = OptimizationForm()
    return render(request, 'cat_sat/index.html', {'form': form})  

# --- BỎ VIEW NÀY ---
# def stop_server(request): ...

def optimize(request):
    if request.method == 'POST':
        original_stdout = sys.stdout
        try:
            sys.stdout = TeeStream("log_gurobi_solver_cat_sat") # Chuyển print cmd tới WebSocket

            data = json.loads(request.body) # lấy nội dung từ fetch post html: JSON.stringify(data)

            # --- THAY ĐỔI: Lấy time limit và khởi tạo Timer ---
            time_limit_minutes = data.get('time_limit_minutes', 2) # Lấy từ data, mặc định 2 phút
            time_limit_seconds = int(time_limit_minutes) * 60
            
            # --- THAY ĐỔI: Khai báo timer nhưng chưa start ---
            # Timer chỉ dùng cho GĐ 2, và chỉ cần chạy trong time_limit_seconds
            timer = SolverTimer(time_limit_seconds) 
            
            try: # <-- Thêm try...finally bên trong để đảm bảo timer được stop
                optimizer = SteelCuttingOptimizer(
                    length = int(data['length']),
                    te_dau_sat = int(data['te_dau_sat']),
                    segment_sizes = list(map(float, data['segment_sizes'])),
                    demands = list(map(int, data['demands'])),
                    blade_width = float(data['blade_width']),
                    factors = list(map(int, data['factors'])),
                    max_manual_cuts = int(data['max_manual_cuts']),
                    max_stock_over = int(data['max_stock_over']),
                    time_limit_seconds = time_limit_seconds # <-- Truyền time limit vào
                )

                # --- Giai đoạn 1 chạy trước, không có timer ---
                # Các lệnh print() bên trong sẽ được TeeStream đẩy ra log
                solutions = optimizer.optimize_cutting()    # tìm nghiệm từng cây sắt
                
                # --- BỎ DÒNG NÀY ---
                # print("!XONGBUOC1!")
                
                # --- Giai đoạn 2: Bắt đầu timer và chạy ---
                timer.start() # <-- BẮT ĐẦU TIMER NGAY TRƯỚC GĐ 2
                distribution = optimizer.optimize_distribution()    # số bó

                return JsonResponse({
                    "status": "success",
                    "solutions": solutions, # solutions là list of tuples, không cần tolist()
                    "distribution": distribution.tolist()
                }, status=200)
            
            finally: # <-- Đảm bảo timer dừng
                timer.stop() # Dừng timer (nếu nó đã chạy)
                
                # --- SỬA ĐỔI Ở ĐÂY ---
                # Chỉ join() nếu thread đã thực sự được start()
                if timer.is_alive():
                    timer.join()
                # --- KẾT THÚC SỬA ĐỔI ---
        
        except Exception as e:
            print(f"Đã xảy ra lỗi: {e}") # In lỗi ra websocket
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
        finally:
            sys.stdout = sys.__stdout__ # <-- Khôi phục stdout gốc

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=400)