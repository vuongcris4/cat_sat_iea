from django.shortcuts import render
from django.http import JsonResponse
import json
import numpy as np
from ortools.sat.python import cp_model
from .forms import OptimizationLaserForm

def index(request):
    form = OptimizationLaserForm()
    return render(request, 'cat_laser/index.html', {'form': form})

def optimize(request):
    if request.method == 'POST':
        data = request.POST
        length = int(data['length'])
        segment_sizes = list(map(float, data['segment_sizes'].split(',')))
        demands = list(map(int, data['demands'].split(',')))
        blade_width_mctd = int(data['blade_width_mctd'])
        max_stock_over = int(data['max_stock_over'])
        blade_types = list(map(int, data['blade_types'].split(',')))

        # Xử lý tối ưu hóa OR-Tools
        solutions, optimal_x = optimize_cutting(length, segment_sizes, demands, blade_types, max_stock_over)

        if solutions:
            return JsonResponse({"status": "success", "message": format_solutions(solutions, optimal_x)})
        else:
            return JsonResponse({"status": "error", "message": "Không tìm thấy giải pháp tối ưu."})
    return JsonResponse({"status": "error", "message": "Phương thức không hợp lệ."}, status=400)

def optimize_cutting(length, segment_sizes, demands, blade_types, max_stock_over):
    model = cp_model.CpModel()
    scaled_length = length * 10
    scaled_segments = [int(size * 10) for size in segment_sizes]
    scaled_blade = [int(bt * 10) for bt in blade_types]

    x = [model.NewIntVar(0, length // min(segment_sizes), f'x_{i}') for i in range(len(segment_sizes))]
    total_length_used = sum(x[i] * (scaled_segments[i] + scaled_blade[i]) for i in range(len(segment_sizes)))

    model.Add(total_length_used >= int(scaled_length * 0.985))
    model.Add(total_length_used <= scaled_length - 150)

    solver = cp_model.CpSolver()
    solver.parameters.enumerate_all_solutions = True

    class SolutionCollector(cp_model.CpSolverSolutionCallback):
        def __init__(self, x_vars):
            super().__init__()
            self._x_vars = x_vars
            self.solutions = []

        def on_solution_callback(self):
            solution = [self.Value(var) for var in self._x_vars]
            total_used = self.Value(total_length_used) / 10
            self.solutions.append((total_used, solution))

        def get_solutions(self):
            return sorted(self.solutions, reverse=True, key=lambda s: s[0])

    collector = SolutionCollector(x)
    solver.Solve(model, collector)
    return collector.get_solutions(), None

def format_solutions(solutions, optimal_x):
    result = f"🔹 Tổng số nghiệm tìm được: {len(solutions)}<br>"
    for i, (total_used, solution) in enumerate(solutions[:5], start=1):
        result += f"🔸 Nghiệm {i}: (Tổng dài dùng: {total_used} mm)<br>"
        for size, count in zip(segment_sizes, solution):
            if count > 0:
                result += f"- {size} mm: {count} lần cắt<br>"
        result += "-" * 40 + "<br>"
    return result
