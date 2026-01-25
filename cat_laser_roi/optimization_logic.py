from ortools.sat.python import cp_model
import numpy as np
import pandas as pd
import os
import pickle
import hashlib
from datetime import datetime
import time
import threading
import math 

# HỆ SỐ ĐỂ NHÂN CÁC GIÁ TRỊ THẬP PHÂN THÀNH SỐ NGUYÊN
SCALING_FACTOR = 10
# GIỚI HẠN SỐ LƯỢNG PATTERN TỐI ĐA ĐỂ TÍNH TOÁN HOẶC TẢI LẠI
SOLUTION_LIMIT = 100000

# ===================================================================
# GIAI ĐOẠN 1
# ===================================================================
def find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay=0):
    """
    Tìm tất cả các cách cắt (pattern) khả thi từ một cây sắt tiêu chuẩn.
    Mỗi cách cắt phải thỏa mãn điều kiện về hao hụt tối đa cho phép.
    """
    print("⏳ Bắt đầu Giai đoạn 1: Tìm các phương án cắt hiệu quả...<br>")

    # --- BẮT ĐẦU SỬA LỖI: Chuyển đổi tất cả sang số nguyên ---
    stock_length_int = int(stock_length * SCALING_FACTOR)
    piece_lengths_int = [int(l * SCALING_FACTOR) for l in piece_lengths]    # KÍCH THƯỚC ĐOẠN
    kerf_width_int = int(kerf_width * SCALING_FACTOR)
    trim_start_int = int(trim_start * SCALING_FACTOR)
    # --- KẾT THÚC SỬA LỖI ---


    model = cp_model.CpModel()
    num_pieces = len(piece_lengths_int)
    counts = [model.NewIntVar(0, 30, f'segment_{i}') for i in range(num_pieces)]    # NGHIỆM THỨ 0, 1, 2, 3,... (tránh lỗi khi bị trùng kích thước)

    total_pieces_length = sum(counts[i] * piece_lengths_int[i] for i in range(num_pieces))

    total_kerf_loss = sum(counts) * kerf_width_int
    total_material_used = total_pieces_length + total_kerf_loss + trim_start_int    # tổng các đoạn + tổng lưỡi mài + tề đầu

    # cây sắt - cùi sắt
    model.Add(total_material_used <= stock_length_int)
    min_material_used = int(stock_length_int * (1 - max_waste_percentage))
    model.Add(min_material_used <= total_material_used)

    waste_var = model.NewIntVar(0, stock_length_int, 'waste')
    model.Add(waste_var == stock_length_int - total_material_used)  # Cui sat

    # Cach viet chon 1 trong 2 phuong an
    # Nhu phuong an cu la hao hut = 3 hoac >= 10, -> thi trim_start=3, doan_thua_cat_tay=7
    # Sau do sua lai hao hut luon >= 10, -> trim_start = 10, doan_thua_cat_tay =0
    # is_waste_zero = model.NewBoolVar('is_waste_zero') 
    # model.Add(waste_var == 0).OnlyEnforceIf(is_waste_zero) # Hao hut bang 0 vi da + trim start o material used
    # model.Add(waste_var >= doan_thua_cat_tay).OnlyEnforceIf(is_waste_zero.Not())    # tang buoc cui sat phai lon hon trim_start
    model.Add(waste_var >= 0)   # Vì đã cộng hao hụt tề đầu trim_start

    solver = cp_model.CpSolver()
    solver.log_search_progress = False
    
    # --- SỬA ĐỔI: Cập nhật lớp callback để dừng khi đạt giới hạn ---
    class SolutionAndLogCollector(cp_model.CpSolverSolutionCallback):
        def __init__(self, variables, limit):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.__variables = variables
            self.__solution_limit = limit
            self.solutions = []

        def on_solution_callback(self):
            # Dừng tìm kiếm nếu đã đạt giới hạn
            if len(self.solutions) >= self.__solution_limit:
                self.StopSearch()
                return
            
            solution = {v.Name(): self.Value(v) for v in self.__variables}
            self.solutions.append(solution)
            
    # --- SỬA ĐỔI: Truyền giới hạn vào khi khởi tạo ---
    solution_collector = SolutionAndLogCollector(counts, SOLUTION_LIMIT)
    solver.parameters.enumerate_all_solutions = True

    print(f"Vui lòng chờ, bộ giải đang tìm kiếm các pattern (tối đa {SOLUTION_LIMIT:,} phương án)... (GĐ 1)<br>")

    status = solver.Solve(model, solution_collector)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and solution_collector.solutions:
        print(f"✅ GĐ 1: Tính toán thành công, tìm thấy {len(solution_collector.solutions)} patterns hiệu quả.<br>")
        df_patterns = pd.DataFrame(solution_collector.solutions)
        
        segment_cols = [f'segment_{i}' for i in range(num_pieces)]  # HÀNG HEADER
        df_patterns['Tong_SL_Doan'] = df_patterns[segment_cols].sum(axis=1)    # TỔNG SỐ LƯỢNG ĐOẠN TỪNG HÀNG, để tính hao hụt tia laser
        
        df_patterns['Tong_Dai_Doan'] = 0
        for i in range(num_pieces):
            length = piece_lengths_int[i]
            df_patterns['Tong_Dai_Doan'] += df_patterns[f'segment_{i}'] * length

        df_patterns['Tong_Cat'] = df_patterns['Tong_Dai_Doan'] + (df_patterns['Tong_SL_Doan'] * kerf_width_int) + trim_start_int
        phoi_cuoi_cung = stock_length_int - df_patterns['Tong_Cat']
        df_patterns['Hao hụt (mm)'] = phoi_cuoi_cung + trim_start_int

        ordered_columns = segment_cols + ['Hao hụt (mm)']
        return df_patterns[ordered_columns].sort_values(by='Hao hụt (mm)')
    else:
        print("❌ GĐ 1: Không tìm thấy pattern nào phù hợp.<br>")
        return None

def get_or_calculate_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay):
    """
    Kiểm tra xem có file cache cho bộ tham số này không.
    Nếu có, tải lại. Nếu không, chạy Giai đoạn 1 để tính toán và lưu lại.
    """
    cache_folder = "patterns_cache"
    os.makedirs(cache_folder, exist_ok=True)
    # Cache key phụ thuộc vào thứ tự và giá trị của các đoạn cắt

    params_string = f"{stock_length}-{tuple(piece_lengths)}-{kerf_width}-{max_waste_percentage}-{trim_start}"
    input_hash = hashlib.sha256(params_string.encode('utf-8')).hexdigest()[:16]
    
    filename = os.path.join(cache_folder, f"patterns_{input_hash}.pkl")
    if os.path.exists(filename):
        print(f"👍 GĐ 1: Đã tìm thấy file nghiệm '{filename}'. Đang tải lại...<br>")
        with open(filename, 'rb') as f:
            patterns = pickle.load(f)
        # --- THÊM BƯỚC LỌC TẠI ĐÂY ---
        # Lọc kết quả từ file cache nếu nó lớn hơn giới hạn cho phép
        if len(patterns) > SOLUTION_LIMIT:
            original_count = len(patterns)
            # Vì các patterns đã được sắp xếp theo hao hụt khi lưu,
            # lấy N hàng đầu tiên chính là lấy N patterns tốt nhất.
            patterns = patterns.head(SOLUTION_LIMIT)
            print(f"⚠️ File cache chứa {original_count:,} patterns, đã được lọc lại còn **{len(patterns):,} patterns tốt nhất**.<br>")
        
        print(f"✅ GĐ 1: Tải lại thành công! Sử dụng {len(patterns):,} patterns đã lưu.<br>")

        return patterns
    else:
        patterns = find_efficient_cutting_patterns(stock_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay)
        if patterns is not None and not patterns.empty:
            with open(filename, 'wb') as f:
                pickle.dump(patterns, f)
            print(f"💾 GĐ 1: Đã lưu bộ nghiệm mới vào file: '{filename}'<br>")
        return patterns


def find_optimal_stock_length(piece_names, piece_lengths, demands_list, priorities_list, is_doan_cuoi,
                               max_surplus, use_priority_constraint, time_limit_seconds,
                               kerf_width=1, max_waste_percentage=0.01,
                               min_length=5000, max_length=6000, step=10, trim_start=10, doan_thua_cat_tay=0,
                               max_total_surplus=None):
    """
    Tìm chiều dài cây sắt tối ưu bằng cách chạy ĐẦY ĐỦ Phase 2 optimization cho mỗi chiều dài.
    
    Args:
        piece_names: Tên các đoạn sắt
        piece_lengths: Danh sách chiều dài các đoạn cắt
        demands_list: Danh sách nhu cầu số lượng từng đoạn
        priorities_list: Danh sách độ ưu tiên
        is_doan_cuoi: Danh sách đánh dấu đoạn cuối
        max_surplus: Số lượng tồn kho tối đa mỗi loại
        use_priority_constraint: Có sử dụng ràng buộc ưu tiên không
        time_limit_seconds: Thời gian giới hạn cho Phase 2
        kerf_width: Độ rộng lưỡi cắt (mặc định 1mm)
        max_waste_percentage: Phần trăm hao hụt tối đa cho mỗi pattern (mặc định 1%)
        min_length: Chiều dài tối thiểu để thử (mặc định 5000mm)
        max_length: Chiều dài tối đa để thử (mặc định 6000mm)
        step: Bước nhảy giữa các chiều dài (mặc định 10mm)
        trim_start: Hao hụt tề đầu
        doan_thua_cat_tay: Đoạn thừa cắt tay
        max_total_surplus: Tổng tồn kho tối đa cho tất cả các loại (None = không giới hạn)
    
    Returns:
        tuple: (optimal_length, min_waste_percentage, best_result_dict)
    """
    print("<br>=== BẮT ĐẦU TÌM CHIỀU DÀI CÂY SẮT TỐI ƯU (CHẾ ĐỘ ĐẦY ĐỦ) ===<br>")
    print(f"Khoảng tìm kiếm: {min_length}mm - {max_length}mm (bước nhảy {step}mm)<br>")
    total_tests = (max_length - min_length) // step + 1
    print(f"<b>⚠️ CẢNH BÁO:</b> Sẽ chạy {total_tests} tests đầy đủ. Ước tính thời gian: ~{total_tests * time_limit_seconds * 3 / 3600:.1f} giờ<br>")
    if max_total_surplus:
        print(f"<b>📊 Ràng buộc:</b> Tổng tồn kho tối đa = {max_total_surplus} đoạn<br><br>")
    else:
        print(f"<b>📊 Ràng buộc:</b> Không giới hạn tổng tồn kho<br><br>")
    
    best_length = None
    best_waste_percentage = float('inf')
    best_total_surplus = float('inf')
    best_total_bars = float('inf')
    best_result_dict = None
    
    results_summary = []
    test_count = 0
    
    # Duyệt qua các chiều dài
    for test_length in range(min_length, max_length + 1, step):
        test_count += 1
        
        # Broadcast chiều dài đang test
        print(f"TESTING_LENGTH::{test_length}")
        
        try:
            # Hiển thị tiến trình
            print(f"🔍 <b>Test {test_count}/{total_tests}</b>: Đang kiểm tra chiều dài {test_length}mm...<br>")
            
            # Tính toán patterns cho chiều dài này
            patterns_data = get_or_calculate_patterns(
                test_length, piece_lengths, kerf_width, max_waste_percentage, trim_start, doan_thua_cat_tay
            )
            
            if patterns_data is None or patterns_data.empty:
                print(f"  ⚠️ Không tìm thấy pattern phù hợp cho {test_length}mm<br>")
                continue
            
            # Chạy ĐẦY ĐỦ Phase 2 và nhận kết quả trực tiếp
            result = solve_phase2(
                test_length,
                patterns_data,
                piece_names,
                piece_lengths,
                demands_list,
                priorities_list,
                max_surplus,
                use_priority_constraint=use_priority_constraint,
                is_doan_cuoi=is_doan_cuoi,
                time_limit_seconds=time_limit_seconds,
                optimal_stock_info=None
            )
            
            if result is None:
                print(f"  ⚠️ Không tìm thấy giải pháp khả thi cho {test_length}mm<br>")
                continue
            
            # Kiểm tra ràng buộc tổng tồn kho
            if max_total_surplus is not None and result['total_surplus'] > max_total_surplus:
                print(f"  ⚠️ Tồn kho vượt quá giới hạn ({result['total_surplus']} > {max_total_surplus})<br>")
                continue
            
            # Lưu kết quả
            print(f"  ✅ Kết quả: {result['total_bars']} cây, hao hụt {result['waste_percentage']:.2f}%, tồn kho {result['total_surplus']} đoạn<br>")
            
            results_summary.append({
                'length': test_length,
                'bars': result['total_bars'],
                'waste_pct': result['waste_percentage'],
                'total_surplus': result['total_surplus'],
                'result': result
            })
            
            # So sánh và cập nhật giải pháp tốt nhất
            # Priority 1: Waste percentage (với tolerance 0.01%)
            # Priority 2: Total surplus (khi waste tương đương)
            # Priority 3: Total bars (tie-breaker cuối cùng)
            is_better = False
            
            if result['waste_percentage'] < best_waste_percentage - 0.01:
                # Hao hụt tốt hơn rõ rệt
                is_better = True
            elif abs(result['waste_percentage'] - best_waste_percentage) < 0.01:
                # Hao hụt tương đương, so sánh tồn kho
                if result['total_surplus'] < best_total_surplus:
                    is_better = True
                elif result['total_surplus'] == best_total_surplus:
                    # Tồn kho bằng nhau, so sánh số cây
                    if result['total_bars'] < best_total_bars:
                        is_better = True
            
            if is_better:
                best_length = test_length
                best_waste_percentage = result['waste_percentage']
                best_total_surplus = result['total_surplus']
                best_total_bars = result['total_bars']
                best_result_dict = {
                    'length': test_length,
                    'bars': result['total_bars'],
                    'waste_pct': result['waste_percentage'],
                    'total_surplus': result['total_surplus'],
                    'result': result
                }
                print(f"  ✨ <b>Tìm thấy chiều dài tốt hơn: {best_length}mm (hao hụt: {best_waste_percentage:.2f}%, tồn kho: {best_total_surplus}, {best_total_bars} cây)</b><br>")
                
        except Exception as e:
            print(f"  ❌ Lỗi khi kiểm tra {test_length}mm: {str(e)}<br>")
            continue
    
    print(f"<br>✅ Hoàn thành tìm kiếm! Đã kiểm tra {test_count} chiều dài, tìm thấy {len(results_summary)} kết quả khả thi.<br><br>")
    
    if best_length is not None and len(results_summary) > 0:
        print("📊 KẾT QUẢ TÌM KIẾM (10 kết quả tốt nhất):<br>")
        
        # Sắp xếp theo thứ tự ưu tiên: waste_pct -> total_surplus -> bars
        results_summary.sort(key=lambda x: (x['waste_pct'], x['total_surplus'], x['bars']))
        
        # Hiển thị top 10
        display_count = min(10, len(results_summary))
        results_df = pd.DataFrame(results_summary[:display_count])
        results_df = results_df[['length', 'bars', 'waste_pct', 'total_surplus']]
        results_df.columns = ['Chiều dài (mm)', 'Số cây sắt', 'Hao hụt (%)', 'Tồn kho (đoạn)']
        
        # Highlight hàng tốt nhất
        def highlight_best(row):
            if row['Chiều dài (mm)'] == best_length:
                return ['background-color: #d4f1d4; font-weight: bold'] * len(row)
            return [''] * len(row)
        
        styler = results_df.style.apply(highlight_best, axis=1)
        styler = styler.set_properties(**{'text-align': 'center'}).hide(axis="index")
        styler = styler.format({
            'Chiều dài (mm)': '{:.0f}',
            'Số cây sắt': '{:.0f}',
            'Hao hụt (%)': '{:.2f}',
            'Tồn kho (đoạn)': '{:.0f}'
        })
        
        print(styler.to_html(classes='table table-sm table-bordered table-striped', border=0))
        
        print(f"<br>✅ <b>CHIỀU DÀI TỐI ƯU: {best_length}mm</b><br>")
        print(f"   - Số lượng cây sắt cần: {best_total_bars} cây<br>")
        print(f"   - Hao hụt: {best_waste_percentage:.2f}%<br>")
        print(f"   - Tổng tồn kho: {best_total_surplus} đoạn<br><br>")
        
        # Broadcast chiều dài tối ưu
        print(f"OPTIMAL_LENGTH::{best_length}")
        
        return best_length, best_waste_percentage, best_result_dict
    else:
        print("❌ Không tìm thấy chiều dài phù hợp trong khoảng cho phép.<br>")
        return None, None, None






# ===================================================================
# Lớp Timer cho Giai đoạn 2
# ===================================================================
class SolverTimer(threading.Thread):
    """Lớp đếm thời gian chạy cho bộ giải và gửi cập nhật ra frontend."""
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
                 max_surplus, use_priority_constraint=False, is_doan_cuoi=None, time_limit_seconds=120.0, optimal_stock_info=None):
    """
    Từ các pattern đã tìm thấy, xác định số lần thực hiện mỗi pattern
    để đáp ứng nhu cầu sản xuất và tối ưu hóa theo các mục tiêu.
    """
    print("!CLEAR!")
    print("🚀 Bắt đầu Giai đoạn 2: Tối ưu hóa kế hoạch cắt sắt...<br>")
    if use_priority_constraint:
        print("--- Chế độ ưu tiên đang BẬT ---<br>")
        # Lọc ra tên cột >= 60
        long_piece_indices = [i for i, length in enumerate(piece_lengths) if length >= 60]
        long_piece_cols = [f'segment_{i}' for i in long_piece_indices]
        
        original_pattern_count = len(patterns_df)
        patterns_df = patterns_df[patterns_df[long_piece_cols].sum(axis=1) > 0].copy()
        print(f"Lọc pattern: Giữ lại {len(patterns_df)}/{original_pattern_count} patterns hợp lệ (có đoạn >= 60mm).<br>")

        # Tính điểm ưu tiên cho mỗi pattern
        priority_map_by_index = dict(enumerate(priorities_list))
        def calculate_priority_score(row):
            min_priority = float('inf')
            for i, priority in priority_map_by_index.items():
                if row[f'segment_{i}'] > 0 and priority < min_priority:
                    min_priority = priority
            return min_priority if min_priority != float('inf') else 9999
        # Trả về cột Priority_Score với giá trị min_priority của mỗi patterns.
        patterns_df['Priority_Score'] = patterns_df.apply(calculate_priority_score, axis=1)
    else:
        print("--- Chế độ ưu tiên đang TẮT (chỉ tối ưu hao hụt và tồn kho) ---<br>")
        print(f"Sử dụng toàn bộ {len(patterns_df)} patterns đã tìm thấy.<br>")

    # LOẠI BỎ CÁC PATTERNS KHÔNG THOẢ ĐIỀU KIỆN CẮT KẾT HỢP CẮT LASER VÀ TỰ ĐỘNG
    if any(is_doan_cuoi):   # NẾU CÓ ÍT NHẤT MỘT DẤU TICK
        """
        Chỉ giữ lại các patterns thoả mãn một trong 3 điều kiện sau: 
        - CÁC ĐOẠN ĐƯỢC TICK:
            + TH kích thước đoạn >= 60: -> Có ít nhất một đoạn có nghiệm >= 1
            + TH kích thước đoạn < 60: -> Có ít nhất một nghiệm >= trunc(60 / KÍCH THƯỚC ĐOẠN) + 1
        - NẾU 2 ĐIỀU KIỆN TRÊN KHÔNG THOẢ MÃN THÌ:
            + Hao hụt ít nhất 60mm
        """
        print("--- Chế độ cắt kết hợp Laser + Tự động đang BẬT ---<br>")
        
        selected_indices = [i for i, sel in enumerate(is_doan_cuoi) if sel]    # Lấy vị trí các segment được tick
        long_ticked = [i for i in selected_indices if piece_lengths[i] >= 60] # 
        short_ticked = [(i, math.trunc(60 / piece_lengths[i]) + 1) for i in selected_indices if piece_lengths[i] < 60]  # (Vị trí segment<60 , giới hạn dưới cần ít nhất bao nhiêu đoạn)
        
        original_pattern_count = len(patterns_df)
        
        def filter_combined(row):
            has_long = any(row[f'segment_{i}'] >= 1 for i in long_ticked)   # CÁC THÍCH THƯỚC ĐOẠN DÀI CÓ ÍT NHẤT 1 đoạn có nghiệm >= 1 là ok
            if has_long:
                return True
            has_short_double = any(row[f'segment_{i}'] >= lower_bound for (i, lower_bound) in short_ticked)   # CÁC THÍCH THƯỚC ĐOẠN NGẮN CÓ ÍT NHẤT 1 đoạn có nghiệm >= 2 là ok
            if has_short_double:
                return True
            return row['Hao hụt (mm)'] >= (60 * SCALING_FACTOR)
        
        patterns_df = patterns_df[patterns_df.apply(filter_combined, axis=1)].copy()  # ÁP DỤNG ĐIỀU KIỆN CHO TỪNG HÀNG
        print(f"Lọc pattern: Giữ lại {len(patterns_df)}/{original_pattern_count} patterns hợp lệ cho chế độ kết hợp.<br>")

    if len(patterns_df) == 0:
        print("❌ GĐ 2: Không có pattern nào để xử lý sau khi lọc.<br>")
        return

    # Khai báo mô hình tối ưu hóa
    model = cp_model.CpModel()
    x = [model.NewIntVar(0, sum(demands_list) * 2, f'x_{j}') for j in range(len(patterns_df))]
    
    # Ràng buộc về nhu cầu sản xuất và hàng tồn kho
    surplus_vars = {}
    for i in range(len(piece_lengths)):
        produced = sum(x[j] * patterns_df.iloc[j][f'segment_{i}'] for j in range(len(patterns_df))) # sumproduct(segment{i}, x{i})
        model.Add(produced >= demands_list[i])

        s = model.NewIntVar(0, sum(demands_list), f'surplus_{i}')
        
        model.Add(s == produced - demands_list[i])
        surplus_vars[i] = s
        model.Add(s <= max_surplus)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.log_search_progress = False
    status = cp_model.UNKNOWN
    
    total_time_for_all_steps = time_limit_seconds * 3
    timer = SolverTimer(total_time_for_all_steps)
    timer.start()
    
    try:
        print("<br>--- ƯU TIÊN 1: Tối thiểu hóa Hao hụt ---<br>")
        print("Vui lòng chờ......<br>")
        model.Minimize(sum(x[j] * patterns_df.iloc[j]['Hao hụt (mm)'] for j in range(len(patterns_df))))
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            min_waste_found = int(solver.ObjectiveValue())
            print(f"✅ Mức hao hụt tối thiểu: {min_waste_found / SCALING_FACTOR:,.2f} mm<br>")
            model.Add(sum(x[j] * patterns_df.iloc[j]['Hao hụt (mm)'] for j in range(len(patterns_df))) == min_waste_found)
        else:
            print("...Không tìm thấy lời giải cho Ưu tiên 1, dừng lại.<br>")
            return
        
        print("<br>--- ƯU TIÊN 2: Tối thiểu hóa Tồn kho ---<br>")
        print("Vui lòng chờ......<br>")
        model.Minimize(sum(surplus_vars.values()))
        status = solver.Solve(model)
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            min_surplus_found = int(solver.ObjectiveValue())
            print(f"✅ Mức tồn kho tối thiểu: {min_surplus_found:,.0f} đoạn<br>")
            model.Add(sum(surplus_vars.values()) == min_surplus_found)
        else:
            print("...Không tìm thấy lời giải cho Ưu tiên 2, dừng lại.<br>")
            return

        # Mục tiêu 3 (tùy chọn): Tối ưu theo độ ưu tiên
        if use_priority_constraint:
            print("<br>--- ƯU TIÊN 3: Tối ưu theo Độ ưu tiên ---<br>")
            print("Vui lòng chờ......<br>")
            model.Minimize(sum(x[j] * patterns_df.iloc[j]['Priority_Score'] for j in range(len(patterns_df))))
            status = solver.Solve(model)
    finally:
        timer.stop()
        timer.join()

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("!CLEAR!")
        now = datetime.now()
        print(f"<b>Thời gian: {now.strftime('%d/%m/%Y %H:%M:%S')}</b><br>")
        
        # Hiển thị thông tin chiều dài tối ưu nếu có
        if optimal_stock_info:
            print(f"<div style='background-color: #d4edda; padding: 10px; margin: 10px 0; border-left: 4px solid #28a745;'>")
            print(f"<b>🎯 ĐÃ TÌM THẤY CHIỀU DÀI TỐI ƯU:</b> {optimal_stock_info['length']}mm<br>")
            print(f"   - Hao hụt: {optimal_stock_info['waste_pct']:.2f}%<br>")
            print(f"   - Số lượng cây sắt: {optimal_stock_info['total_bars']} cây<br>")
            print(f"   - Đã kiểm tra {optimal_stock_info['tests_count']} chiều dài (5000-6000mm, bước 10mm)")
            print(f"</div><br>")
        
        print(f"<b>Chiều dài cây sắt:</b> {raw_stock_length}mm<br>")
        
        plan_indices = [j for j in range(len(patterns_df)) if solver.Value(x[j]) > 0]   # Chi in nhung pattern co SL cay sat > 0, tim vi tri
        plan_counts = [solver.Value(x[j]) for j in plan_indices]    #Lay mang SL cay sat
        production_plan = patterns_df.iloc[plan_indices].copy() # Lay cac pattern SL cay sat > 0

        production_plan['SL cây sắt'] = plan_counts

        print("<h4>TỔNG KẾT CẮT LASER</h4>")
        
        custom_formatter_int = lambda x: f"{int(x)}" if x == int(x) else f"{x:.1f}" # Dinh dang so nguyen hoac so thap phan 1 chu so

        summary = []
        for i, length in enumerate(piece_lengths):
            produced = (production_plan[f'segment_{i}'] * production_plan['SL cây sắt']).sum()
            summary.append({
                "Tên sắt": piece_names[i],
                "Đoạn (mm)": length, 
                "SL cần (đoạn)": demands_list[i], 
                "SL cắt (đoạn)": produced, 
                "Tồn kho (đoạn)": produced - demands_list[i]
            })
        summary_df = pd.DataFrame(summary)
        summary_styler = summary_df.style.set_properties(**{'text-align': 'center'}).hide(axis="index")
        summary_styler.format({"Đoạn (mm)": custom_formatter_int}) # Dinh dang so nguyen hoac so thap phan 1 chu so

        print(summary_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))
        
        # --- SỬA LỖI: Chia lại hệ số khi tính toán và hiển thị hao hụt cuối cùng ---
        # Thông số tổng hợp
        total_bars_used = production_plan['SL cây sắt'].sum()
        production_plan['Hao hụt (mm)'] = production_plan['Hao hụt (mm)'] / SCALING_FACTOR
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
        
        # Đổi tên cột từ 'segment_i' sang tên dễ đọc để hiển thị
        rename_map = {f'segment_{i}': f'{piece_names[i]} <br>({custom_formatter_int(piece_lengths[i])}mm)' for i in range(len(piece_names))}
        print_plan.rename(columns=rename_map, inplace=True)

        # --- SỬA LỖI: Chia lại cột hao hụt trước khi hiển thị ---
        # print_plan['Hao hụt (mm)'] = print_plan['Hao hụt (mm)'] / SCALING_FACTOR

        # Thay thế các giá trị 0 bằng chuỗi rỗng cho các cột sản phẩm 
        for col in rename_map.values():
            print_plan[col] = print_plan[col].apply(lambda x: '' if x == 0 else x)

        # Chỉ hiển thị các cột sản phẩm có số lượng cắt > 0
        # cols_to_show = [col for col in rename_map.values() if print_plan[col].sum() > 0]
        other_cols = ['Hao hụt (mm)', 'SL cây sắt']
        final_cols = ['STT'] + list(rename_map.values()) + other_cols

        print_plan.insert(0, 'STT', np.arange(1, len(print_plan) + 1))
        print_plan = print_plan[final_cols]
        
        print(f"<h4>KẾ HOẠCH CẮT CHI TIẾT ({len(print_plan)} loại)</h4>")
        
        bold_cols = [col for col in print_plan.columns if 'mm' in col and 'Hao hụt' not in col] + ['SL cây sắt']
        
        plan_styler = print_plan.style.set_properties(**{'text-align': 'center'})
        plan_styler.format({'Hao hụt (mm)': custom_formatter_int})
        plan_styler.set_properties(**{'font-weight': 'bold'}, subset=bold_cols)
        plan_styler.hide(axis="index")

        # Thêm viền đậm bao quanh
        piece_size_cols = [col for col in print_plan.columns if 'mm' in col and 'Hao hụt' not in col]
        # # Giới hạn độ rộng các cột kích thước để in vừa A4
        plan_styler.set_properties(**{'width': '65px', 'max-width': '65px'}, subset=piece_size_cols)
        if piece_size_cols:
            first_col_idx = print_plan.columns.get_loc(piece_size_cols[0])
            last_col_idx = print_plan.columns.get_loc(piece_size_cols[-1])
            border_style = '2px solid black'
            
            table_styles = [
                {'selector': f'th.col{first_col_idx}, td.col{first_col_idx}', 'props': [('border-left', border_style)]},
                {'selector': f'th.col{last_col_idx}, td.col{last_col_idx}', 'props': [('border-right', border_style)]},
                {'selector': ', '.join([f'th.col{print_plan.columns.get_loc(c)}' for c in piece_size_cols]), 'props': [('border-top', border_style)]},
                {'selector': ', '.join([f'tbody tr:last-child td.col{print_plan.columns.get_loc(c)}' for c in piece_size_cols]), 'props': [('border-bottom', border_style)]}
            ]
            plan_styler.set_table_styles(table_styles)
        
        print(plan_styler.to_html(classes='table table-sm table-bordered table-striped', border=0))
        
        # Return structured data for programmatic use
        result = {
            'total_bars': int(total_bars_used),
            'total_waste_mm': float(final_waste),
            'waste_percentage': float(final_waste/(raw_stock_length*total_bars_used)*100) if total_bars_used > 0 else 0,
            'total_surplus': int(sum(solver.Value(surplus_vars[i]) for i in range(len(piece_lengths)))),
            'production_plan': production_plan,
            'summary_df': summary_df
        }
        return result
    else:
        print("<br>❌ Rất tiếc, không thể tìm ra kế hoạch sản xuất phù hợp.")
        return None