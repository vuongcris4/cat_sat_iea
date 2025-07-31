from ortools.sat.python import cp_model
import numpy as np
import pandas as pd
import os
import pickle
import hashlib
from datetime import datetime
import time
import threading

# ===================================================================
# GIAI ĐOẠN 1 (Không đổi)
# ===================================================================
def find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay=6):
    print("⏳ Bắt đầu Giai đoạn 1: Tìm các phương án cắt hiệu quả...<br>")
    model = cp_model.CpModel()
    num_pieces = len(piece_lengths)
    counts = [model.NewIntVar(0, 30, f'x_{i}') for i in range(num_pieces)]
    total_pieces_length = sum(counts[i] * length for i, length in enumerate(piece_lengths))
    total_kerf_loss = sum(counts) * kerf_width
    total_material_used = total_pieces_length + total_kerf_loss + trim_start
    model.Add(total_material_used <= stock_length)
    min_material_used = int(stock_length * (1 - max_waste_percentage))
    model.Add(min_material_used <= total_material_used)
    waste_var = model.NewIntVar(0, stock_length, 'waste')
    model.Add(waste_var == stock_length - total_material_used)
    is_waste_zero = model.NewBoolVar('is_waste_zero')
    model.Add(waste_var == 0).OnlyEnforceIf(is_waste_zero)
    model.Add(waste_var >= doan_thua_cat_tay).OnlyEnforceIf(is_waste_zero.Not())
    solver = cp_model.CpSolver()
    solver.log_search_progress = False
    class SolutionAndLogCollector(cp_model.CpSolverSolutionCallback):
        def __init__(self, variables):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.__variables = variables
            self.solutions = []
        def on_solution_callback(self):
            solution = {v.Name(): self.Value(v) for v in self.__variables}
            self.solutions.append(solution)
    solution_collector = SolutionAndLogCollector(counts)
    solver.parameters.enumerate_all_solutions = True
    print("Vui lòng chờ, bộ giải đang tìm kiếm các pattern... (GĐ 1)<br>")
    status = solver.Solve(model, solution_collector)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and solution_collector.solutions:
        print(f"✅ GĐ 1: Tính toán thành công, tìm thấy {len(solution_collector.solutions)} patterns hiệu quả.<br>")
        df_patterns = pd.DataFrame(solution_collector.solutions)
        column_names = {f'x_{i}': f'{length}mm' for i, length in enumerate(piece_lengths)}
        df_patterns = df_patterns.rename(columns=column_names)
        total_sl_cols = [f'{length}mm' for length in piece_lengths]
        df_patterns['Tong_SL_Doan'] = df_patterns[total_sl_cols].sum(axis=1)
        df_patterns['Tong_Dai_Doan'] = 0
        for i, length in enumerate(piece_lengths):
            df_patterns['Tong_Dai_Doan'] += df_patterns[f'{length}mm'] * length
        df_patterns['Tong_Cat'] = df_patterns['Tong_Dai_Doan'] + (df_patterns['Tong_SL_Doan'] * kerf_width) + trim_start
        phoi_cuoi_cung = stock_length - df_patterns['Tong_Cat']
        df_patterns['Hao hụt (mm)'] = phoi_cuoi_cung + trim_start
        ordered_columns = [f'{length}mm' for length in piece_lengths] + ['Hao hụt (mm)']
        return df_patterns[ordered_columns].sort_values(by='Hao hụt (mm)')
    else:
        print("❌ GĐ 1: Không tìm thấy pattern nào phù hợp.<br>")
        return None

def get_or_calculate_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay):
    cache_folder = "patterns_cache"
    os.makedirs(cache_folder, exist_ok=True)
    sorted_pieces = tuple(sorted(piece_lengths))
    params_string = f"{stock_length}-{sorted_pieces}-{kerf_width}-{max_waste_percentage}-{trim_start}"
    input_hash = hashlib.sha256(params_string.encode('utf-8')).hexdigest()[:16]
    filename = os.path.join(cache_folder, f"patterns_{input_hash}.pkl")
    if os.path.exists(filename):
        print(f"👍 GĐ 1: Đã tìm thấy file nghiệm '{filename}'. Đang tải lại...<br>")
        with open(filename, 'rb') as f:
            patterns = pickle.load(f)
        print(f"✅ GĐ 1: Tải lại thành công! Tìm thấy {len(patterns)} patterns đã lưu.<br>")
        return patterns
    else:
        patterns = find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay)
        if patterns is not None and not patterns.empty:
            with open(filename, 'wb') as f:
                pickle.dump(patterns, f)
            print(f"💾 GĐ 1: Đã lưu bộ nghiệm mới vào file: '{filename}'<br>")
        return patterns

# ===================================================================
# Lớp Timer cho Giai đoạn 2
# ===================================================================
class SolverTimer(threading.Thread):
    def __init__(self, total_time):
        super().__init__()
        self.total_time = total_time
        self.stop_event = threading.Event()
        self.start_time = None
        self.daemon = True

    def run(self):
        self.start_time = time.time()
        while not self.stop_event.is_set():
            elapsed = int(time.time() - self.start_time)
            if elapsed > self.total_time:
                break
            print(f"TIMER_UPDATE::{elapsed}::{int(self.total_time)}")
            time.sleep(1)

    def stop(self):
        self.stop_event.set()

# ===================================================================
# GIAI ĐOẠN 2
# ===================================================================
def solve_phase2(raw_stock_length, patterns_df, piece_names, piece_lengths, demands_list, priorities_list,
                 max_surplus, use_priority_constraint=False, time_limit_seconds=120.0):
    print("!CLEAR!")
    print("🚀 Bắt đầu Giai đoạn 2: Tối ưu hóa kế hoạch cắt sắt...<br>")
    if use_priority_constraint:
        print("--- Chế độ ưu tiên đang BẬT ---<br>")
        long_piece_cols = [f'{length}mm' for length in piece_lengths if length >= 60]
        original_pattern_count = len(patterns_df)
        patterns_df = patterns_df[patterns_df[long_piece_cols].sum(axis=1) > 0].copy()
        print(f"Lọc pattern: Giữ lại {len(patterns_df)}/{original_pattern_count} patterns hợp lệ (có đoạn >= 60mm).<br>")
        priority_map = dict(zip(piece_lengths, priorities_list))
        def calculate_priority_score(row):
            min_priority = float('inf')
            for length, priority in priority_map.items():
                if row[f'{length}mm'] > 0 and priority < min_priority:
                    min_priority = priority
            return min_priority
        patterns_df['Priority_Score'] = patterns_df.apply(calculate_priority_score, axis=1)
    else:
        print("--- Chế độ ưu tiên đang TẮT (chỉ tối ưu hao hụt và tồn kho) ---<br>")
        print(f"Sử dụng toàn bộ {len(patterns_df)} patterns đã tìm thấy.<br>")
    if len(patterns_df) == 0:
        print("❌ GĐ 2: Không có pattern nào để xử lý sau khi lọc.<br>")
        return
    model = cp_model.CpModel()
    x = [model.NewIntVar(0, sum(demands_list) * 2, f'x_{j}') for j in range(len(patterns_df))]
    surplus_vars = {}
    for i, length in enumerate(piece_lengths):
        produced = sum(x[j] * patterns_df.iloc[j][f'{length}mm'] for j in range(len(patterns_df)))
        model.Add(produced >= demands_list[i])
        s = model.NewIntVar(0, sum(demands_list), f'surplus_{length}')
        model.Add(s == produced - demands_list[i])
        surplus_vars[length] = s
        model.Add(s <= max_surplus)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.log_search_progress = False
    status = cp_model.UNKNOWN
    
    # --- Khởi tạo và chạy Timer duy nhất ---
    total_time_for_all_steps = time_limit_seconds * 3
    timer = SolverTimer(total_time_for_all_steps)
    timer.start()
    
    try:
        print("<br>--- ƯU TIÊN 1: Tối thiểu hóa Hao hụt ---<br>")
        model.Minimize(sum(x[j] * patterns_df.iloc[j]['Hao hụt (mm)'] for j in range(len(patterns_df))))
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            min_waste_found = int(solver.ObjectiveValue())
            print(f"✅ Mức hao hụt tối thiểu: {min_waste_found:,.0f} mm<br>")
            model.Add(sum(x[j] * patterns_df.iloc[j]['Hao hụt (mm)'] for j in range(len(patterns_df))) == min_waste_found)
        else:
            print("...Không tìm thấy lời giải cho Ưu tiên 1, dừng lại.<br>")
            return # Dừng nếu bước đầu tiên thất bại
        
        print("<br>--- ƯU TIÊN 2: Tối thiểu hóa Tồn kho ---<br>")
        model.Minimize(sum(surplus_vars.values()))
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            min_surplus_found = int(solver.ObjectiveValue())
            print(f"✅ Mức tồn kho tối thiểu: {min_surplus_found:,.0f} đoạn<br>")
            model.Add(sum(surplus_vars.values()) == min_surplus_found)
        else:
            print("...Không tìm thấy lời giải cho Ưu tiên 2, dừng lại.<br>")
            return

        if use_priority_constraint:
            print("<br>--- ƯU TIÊN 3: Tối ưu theo Độ ưu tiên ---<br>")
            model.Minimize(sum(x[j] * patterns_df.iloc[j]['Priority_Score'] for j in range(len(patterns_df))))
            status = solver.Solve(model)

    finally:
        # Dừng timer sau khi tất cả các bước giải đã xong
        timer.stop()
        timer.join()

    # ... (Phần in kết quả không đổi) ...
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("!CLEAR!")
        now = datetime.now()
        print(f"<b>Thời gian: {now.strftime('%d/%m/%Y %H:%M:%S')}</b><br>")
        print(f"<b>Chiều dài cây sắt thô:</b> {raw_stock_length}mm<br>")
        plan_indices = [j for j in range(len(patterns_df)) if solver.Value(x[j]) > 0]
        plan_counts = [solver.Value(x[j]) for j in plan_indices]
        production_plan = patterns_df.iloc[plan_indices].copy()
        production_plan['SL cây sắt'] = plan_counts
        print("<h4>TỔNG KẾT</h4>")
        summary = []
        length_to_name_map = dict(zip(piece_lengths, piece_names))
        for i, length in enumerate(piece_lengths):
            produced = (production_plan[f'{length}mm'] * production_plan['SL cây sắt']).sum()
            summary.append({"Tên sắt": length_to_name_map.get(length, ""),"Đoạn (mm)": length, "SL cần (đoạn)": demands_list[i], "SL cắt (đoạn)": produced, "Tồn kho (đoạn)": produced - demands_list[i]})
        summary_df = pd.DataFrame(summary)
        summary_styler = summary_df.style.set_properties(**{'text-align': 'center'}).hide(axis="index")
        print(summary_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))
        total_bars_used = production_plan['SL cây sắt'].sum()
        final_waste = (production_plan['Hao hụt (mm)'] * production_plan['SL cây sắt']).sum()
        print("<hr>")
        print(f"<b>Tổng số cây sắt cần dùng:</b> {total_bars_used} cây<br>")
        print(f"<b>Tổng hao hụt dài:</b> {final_waste/1000:,.2f}m<br>")
        if total_bars_used > 0:
            print(f"<b>Hao hụt:</b> {final_waste/(raw_stock_length*total_bars_used)*100:.2f}%")
        if use_priority_constraint:
            production_plan = production_plan.sort_values(by=['Priority_Score', 'SL cây sắt'], ascending=[True, True])
            print_plan = production_plan.drop(columns=['Priority_Score'])
        else:
            production_plan = production_plan.sort_values(by='SL cây sắt', ascending=True)
            print_plan = production_plan
        print_plan.insert(0, 'STT', np.arange(1, len(print_plan) + 1))
        cols = [col for col in print_plan.columns if col != 'SL cây sắt'] + ['SL cây sắt']
        print_plan = print_plan[cols]
        print(f"<h4>KẾ HOẠCH CẮT CHI TIẾT ({len(print_plan)} loại)</h4>")
        bold_cols = [col for col in print_plan.columns if 'mm' in col and 'Hao hụt' not in col] + ['SL cây sắt']
        plan_styler = print_plan.style.set_properties(**{'text-align': 'center'})
        plan_styler.set_properties(**{'font-weight': 'bold'}, subset=bold_cols)
        plan_styler.hide(axis="index")
        print(plan_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))
    else:
        print("<br>❌ Rất tiếc, không thể tìm ra kế hoạch sản xuất phù hợp.")