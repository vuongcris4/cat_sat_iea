from django.shortcuts import render
from django.http import JsonResponse
import json
import sys
import asyncio
import time

from channels.layers import get_channel_layer
from iea_project.consumers import LOG_HISTORY
from .forms import OptimizationForm
from .optimization_logic import get_or_calculate_patterns, solve_phase2, find_optimal_stock_length

class TeeStream:
    def __init__(self, websocket_room):
        self.websocket_room = websocket_room
        LOG_HISTORY[self.websocket_room] = []

    async def send_message_to_websocket(self, message):
        LOG_HISTORY[self.websocket_room].append(message)
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            self.websocket_room,
            {"type": "chat.message", "message": message},
        )

    def write(self, message):
        if message.strip():
            asyncio.run(self.send_message_to_websocket(message))

    def flush(self):
        pass

def index(request):
    form = OptimizationForm()
    context = {'form': form}
    return render(request, 'cat_laser_roi/index.html', context)

def run_optimization(request):
    if request.method == 'POST':
        original_stdout = sys.stdout
        room_name = "log_gurobi_solver_cat_laser_roi"
        try:
            sys.stdout = TeeStream(room_name)
            
            data = json.loads(request.body)
            stock_length = data.get('stock_length')
            max_waste_percentage = float(data.get('max_waste_percentage', 1.0)) / 100  # Convert percentage to decimal
            max_surplus = data.get('max_surplus')
            use_priority_constraint = data.get('use_priority_constraint')
            optimize_stock_length = data.get('optimize_stock_length', False)
            # use_combined_mode = data.get('use_combined_mode')
            time_limit_minutes = data.get('time_limit_minutes')
            pieces_data = data.get('pieces_data')


            if not pieces_data:  # FIXED: Added check for empty pieces_data to prevent index errors downstream.
                print("❌ Không có dữ liệu đoạn cắt được cung cấp.<br>")
                return JsonResponse({'status': 'error', 'message': 'Không có dữ liệu đoạn cắt.'}, status=400)

            # Filter ra các hàng hợp lệ (có đủ cột tên, chiều dài, số lượng)
            valid_rows = [
                item for item in pieces_data 
                if item and len(item) >= 3 
                and item[0] is not None and item[0] != ''
                and item[1] is not None and item[1] != ''
                and item[2] is not None and item[2] != ''
            ]
            
            if not valid_rows:
                print("❌ Không có dữ liệu hợp lệ. Vui lòng kiểm tra lại bảng dữ liệu.<br>")
                return JsonResponse({'status': 'error', 'message': 'Không có dữ liệu đoạn cắt hợp lệ.'}, status=400)
            
            # Parse dữ liệu từ các hàng hợp lệ
            piece_names = [str(row[0]) for row in valid_rows]
            piece_lengths = [float(row[1]) for row in valid_rows]
            demands_list = [int(row[2]) for row in valid_rows]
            priorities_list = [int(row[3]) if len(row) > 3 and row[3] is not None else 0 for row in valid_rows]
            is_doan_cuoi = [bool(row[4]) if len(row) > 4 and row[4] is not None else False for row in valid_rows]


            # Nếu bật tính năng tối ưu chiều dài cây sắt
            if optimize_stock_length:
                optimal_length, optimal_waste_pct, patterns_data = find_optimal_stock_length(
                    piece_lengths=piece_lengths,
                    demands_list=demands_list,
                    kerf_width=1,
                    max_waste_percentage=max_waste_percentage,
                    min_length=5000,
                    max_length=6000,
                    step=10,
                    trim_start=10,
                    doan_thua_cat_tay=0
                )
                
                if optimal_length is None:
                    print("❌ Không tìm thấy chiều dài tối ưu. Sử dụng chiều dài mặc định.<br>")
                    stock_length = stock_length  # Giữ nguyên giá trị người dùng nhập
                    patterns_data = get_or_calculate_patterns(
                        stock_length, piece_lengths, 1, max_waste_percentage, 10, 0
                    )
                else:
                    stock_length = optimal_length  # Sử dụng chiều dài tối ưu
            else:
                patterns_data = get_or_calculate_patterns(
                    stock_length, piece_lengths, 1, max_waste_percentage, 10, 0
                )
            
            if patterns_data is not None and not patterns_data.empty:
                solve_phase2(
                    stock_length,
                    patterns_data,
                    piece_names,
                    piece_lengths,
                    demands_list,
                    priorities_list,
                    max_surplus,
                    use_priority_constraint=use_priority_constraint,
                    is_doan_cuoi=is_doan_cuoi,
                    time_limit_seconds=time_limit_minutes * 60
                )
            
            return JsonResponse({'status': 'success', 'message': 'Optimization process finished.'})

        except Exception as e:
            error_message = f"Đã xảy ra lỗi trong view: {e}"
            print(error_message)
            return JsonResponse({'status': 'error', 'message': error_message}, status=500)
        finally:
            sys.stdout = original_stdout
    return JsonResponse({'error': 'Invalid request method'}, status=400)