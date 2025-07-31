from django.shortcuts import render
from django.http import JsonResponse
import json
import sys
import asyncio
from channels.layers import get_channel_layer
from iea_project.consumers import LOG_HISTORY

from .forms import OptimizationForm
from .optimization_logic import get_or_calculate_patterns, solve_phase2

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
            max_surplus = data.get('max_surplus')
            use_priority_constraint = data.get('use_priority_constraint')
            time_limit_minutes = data.get('time_limit_minutes')
            pieces_data = data.get('pieces_data')

            piece_names = [str(item[0]) for item in pieces_data if item and item[0] is not None]
            piece_lengths = [int(item[1]) for item in pieces_data if item and item[1] is not None]
            demands_list = [int(item[2]) for item in pieces_data if item and item[2] is not None]
            priorities_list = [int(item[3]) for item in pieces_data if item and item[3] is not None]

            patterns_data = get_or_calculate_patterns(
                stock_length, piece_lengths, 1, 0.015, 3, 7
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