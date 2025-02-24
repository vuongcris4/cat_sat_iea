from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
import json
from .forms import OptimizationForm
from .optimization_logic import SteelCuttingOptimizer
import asyncio
from channels.layers import get_channel_layer
import sys
import os
import signal

class TeeStream:
    # Redirect stdout to WebSocket
    def __init__(self, websocket_room):
        self.websocket_room = websocket_room

    async def send_message_to_websocket(self, message):
        channel_layer = get_channel_layer()  # Lấy channel layer
        await channel_layer.group_send(
            f"{self.websocket_room}",  # Group WebSocket (phải trùng với group trong consumer)
            {
                "type": "chat.message",  # Tên handler trong consumer
                "message": message,      # Dữ liệu gửi tới trình duyệt
            },
        )

    def write(self, message):
        # Ghi vào bộ nhớ đệm và gửi tới WebSocket
        if message.strip(): # Ignore empty lines
            asyncio.run(self.send_message_to_websocket(message))

    def flush(self):
        pass
    #     self.original_stream.flush()    # Ensure all data in the buffer is written to the original stream

def index(request):
    form = OptimizationForm()
    return render(request, 'cat_sat/index.html', {'form': form})  

def stop_server(request):
    os.kill(os.getpid(), signal.SIGINT)  # Gửi tín hiệu dừng server
    return HttpResponse("Server is stopping...")

def optimize(request):
    if request.method == 'POST':
        try:
            sys.stdout = TeeStream("log_gurobi_solver") # Chuyển print cmd tới WebSocket

            data = json.loads(request.body) # lấy nội dung từ fetch post html: JSON.stringify(data)

            optimizer = SteelCuttingOptimizer(
                length = int(data['length']),
                segment_sizes = list(map(float, data['segment_sizes'])),
                demands = list(map(int, data['demands'])),
                blade_width = float(data['blade_width']),
                factors = list(map(int, data['factors'])),
                max_manual_cuts = int(data['max_manual_cuts']),
                max_stock_over = int(data['max_stock_over'])
            )

            solutions = optimizer.optimize_cutting()    # tìm nghiệm từng cây sắt
            # print("!CLEAR!")
            print("!XONGBUOC1!")    # Gwủi xong bước 1 để hiện nút stop tiến trình đang giải
            distribution = optimizer.optimize_distribution()    # số bó

            return JsonResponse({
                "status": "success",
                "solutions": solutions,
                "distribution": distribution.tolist()
            }, status=200)

        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
        finally:
            sys.stdout = sys.__stdout__

    return JsonResponse({"status": "error", "message": "Invalid request method"}, status=400)
