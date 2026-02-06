from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
import json
import logging
from .forms import OptimizationForm
from .optimization_logic import SteelCuttingOptimizer, SolverTimer
import asyncio
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import os
import sys
import traceback
from datetime import datetime

# Configure logging
logger = logging.getLogger('cat_sat')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [CAT_SAT] %(levelname)s: %(message)s'))
logger.addHandler(handler)

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

@login_required
def index(request):
    form = OptimizationForm()
    return render(request, 'cat_sat/index.html', {'form': form})

@login_required
def optimize(request):
    if request.method == 'POST':
        original_stdout = sys.stdout
        try:
            sys.stdout = TeeStream("log_gurobi_solver_cat_sat")
            
            # === LOGGING USER REQUEST ===
            logger.info("="*60)
            logger.info(f"NEW OPTIMIZATION REQUEST at {datetime.now().isoformat()}")
            logger.info(f"User: {request.user.username}")
            logger.info("="*60)
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

                # Lọc các hàng rỗng từ handsontable (hàng phải có cả 3 cột)
                valid_pieces = [row for row in pieces_data if row and row[0] is not None and row[1] is not None and row[2] is not None]
                
                if not valid_pieces:
                    print("❌ Dữ liệu đoạn cắt rỗng.<br>")
                    return JsonResponse({'status': 'error', 'message': 'Dữ liệu đoạn cắt rỗng.'}, status=400)

                # Tách dữ liệu từ bảng (3 cột)
                piece_names = [str(item[0]) for item in valid_pieces]
                segment_sizes = [float(item[1]) for item in valid_pieces]
                demands = [int(item[2]) for item in valid_pieces]

                # Lấy factors (dạng string) và chuyển thành list int
                factors_str = data.get('factors', "")
                factors = [int(f) for f in factors_str.replace('.', ' ').replace(',', ' ').split() if f.isdigit()]
                if not factors: # Nếu rỗng, mặc định là [1]
                    factors = [1] 
                # === KẾT THÚC THAY ĐỔI ===

                # === LOGGING INPUT PARAMETERS ===
                logger.info(f"Stock Length: {data['length']}mm")
                logger.info(f"Te Dau Sat: {data['te_dau_sat']}mm")
                logger.info(f"Blade Width: {data['blade_width']}mm")
                logger.info(f"Max Manual Cuts: {data['max_manual_cuts']}")
                logger.info(f"Max Stock Over: {data['max_stock_over']}")
                logger.info(f"Time Limit: {time_limit_seconds}s")
                logger.info(f"Factors: {factors}")
                logger.info(f"Number of piece types: {len(piece_names)}")
                for i, (name, size, demand) in enumerate(zip(piece_names, segment_sizes, demands)):
                    logger.info(f"  [{i+1}] {name}: {size}mm x {demand} pcs")
                logger.info("-"*60)

                optimizer = SteelCuttingOptimizer(
                    length=int(data['length']),
                    te_dau_sat=int(data['te_dau_sat']),
                    piece_names=piece_names,       # Thêm Tên sắt
                    segment_sizes=segment_sizes, # Truyền list đã tách
                    demands=demands,           # Truyền list đã tách
                    blade_width=float(data['blade_width']),
                    factors=factors,           # Truyền list int
                    max_manual_cuts=int(data['max_manual_cuts']),
                    max_stock_over=int(data['max_stock_over']),
                    time_limit_seconds=time_limit_seconds
                )

                logger.info("Starting Phase 1: Pattern Generation...")
                solutions = optimizer.optimize_cutting()
                logger.info(f"Phase 1 complete. Found {len(solutions) if solutions else 0} patterns.")
                
                logger.info("Starting Phase 2: Distribution Optimization...")
                timer.start()
                distribution = optimizer.optimize_distribution()
                logger.info("Phase 2 complete.")

                logger.info("="*60)
                logger.info("OPTIMIZATION COMPLETE")
                logger.info("="*60)
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
            # Lấy chi tiết toàn bộ traceback_message
            traceback_message = traceback.format_exc() 
            
            # In ra WebSocket (vì stdout đang bị TeeStream bắt)
            print("!CLEAR!") # Xóa log cũ
            print("❌ ĐÃ XẢY RA LỖI NGHIÊM TRỌNG (GĐ 2) ❌<br>")
            print("<pre style='color:red; font-family: monospace;'>")
            print(traceback_message)
            print("</pre>")

            return JsonResponse({"status": "error", "message": str(e)}, status=500)
        
        finally:
            sys.stdout = original_stdout # <-- Sửa lại thành __stdout__

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=400)