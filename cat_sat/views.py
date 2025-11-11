from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import json
from .forms import OptimizationForm
from .optimization_logic import SteelCuttingOptimizer, SolverTimer
import asyncio
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import os
import sys

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

def optimize(request):
    if request.method == 'POST':
        original_stdout = sys.stdout
        try:
            sys.stdout = TeeStream("log_gurobi_solver_cat_sat")
            data = json.loads(request.body)

            time_limit_minutes = data.get('time_limit_minutes', 2)
            time_limit_seconds = int(time_limit_minutes) * 60
            timer = SolverTimer(time_limit_seconds)

            try:
                # === THAY ĐỔI LOGIC LẤY DỮ LIỆU ===
                pieces_data = data.get('pieces_data')
                if not pieces_data:
                    print("❌ Không có dữ liệu đoạn cắt được cung cấp.<br>")
                    return JsonResponse({'status': 'error', 'message': 'Không có dữ liệu đoạn cắt.'}, status=400)

                # Lọc các hàng rỗng từ handsontable
                valid_pieces = [row for row in pieces_data if row and row[0] is not None and row[1] is not None]
                
                if not valid_pieces:
                    print("❌ Dữ liệu đoạn cắt rỗng.<br>")
                    return JsonResponse({'status': 'error', 'message': 'Dữ liệu đoạn cắt rỗng.'}, status=400)

                # Tách dữ liệu từ bảng
                segment_sizes = [float(item[0]) for item in valid_pieces]
                demands = [int(item[1]) for item in valid_pieces]

                # Lấy factors (dạng string) và chuyển thành list int
                factors_str = data.get('factors', "")
                factors = [int(f) for f in factors_str.replace('.', ' ').replace(',', ' ').split() if f.isdigit()]
                if not factors: # Nếu rỗng, mặc định là [1]
                    factors = [1] 
                # === KẾT THÚC THAY ĐỔI ===

                optimizer = SteelCuttingOptimizer(
                    length=int(data['length']),
                    te_dau_sat=int(data['te_dau_sat']),
                    segment_sizes=segment_sizes, # Truyền list đã tách
                    demands=demands,           # Truyền list đã tách
                    blade_width=float(data['blade_width']),
                    factors=factors,           # Truyền list int
                    max_manual_cuts=int(data['max_manual_cuts']),
                    max_stock_over=int(data['max_stock_over']),
                    time_limit_seconds=time_limit_seconds
                )

                solutions = optimizer.optimize_cutting()
                
                timer.start()
                distribution = optimizer.optimize_distribution()

                return JsonResponse({
                    "status": "success",
                    "solutions": solutions,
                    "distribution": distribution.tolist()
                }, status=200)
            
            finally:
                timer.stop()
                if timer.is_alive():
                    timer.join()
        
        except Exception as e:
            print(f"Đã xảy ra lỗi: {e}")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
        finally:
            sys.stdout = sys.__stdout__ # <-- Sửa lại thành __stdout__

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=400)
   