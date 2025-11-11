import os
import json
import pickle
import hashlib
from pathlib import Path
import numpy as np
from collections import Counter
import time
import threading  # <-- Đã có

# OR-Tools CP-SAT
from ortools.sat.python import cp_model


# ===================================================================
# Lớp Timer (Copy từ cat_laser_roi)
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
            # In ra thông điệp chuẩn để frontend bắt
            print(f"TIMER_UPDATE::{elapsed}::{int(self.total_time)}")
            time.sleep(1)

    def stop(self):
        self.stop_event.set()

# ===================================================================
# Lớp Tối Ưu Hóa
# ===================================================================
class SteelCuttingOptimizer:
    # ... ( __init__ giữ nguyên, vẫn nhận time_limit_seconds ) ...
    def __init__(self, length, te_dau_sat, segment_sizes, demands, blade_width, factors, max_manual_cuts, max_stock_over, time_limit_seconds=30.0): # <-- THÊM time_limit_seconds
        self.length = length
        self.te_dau_sat = te_dau_sat
        self.segment_sizes = np.array(segment_sizes)
        self.demands = np.array(demands)
        self.blade_width = blade_width
        # đảm bảo factors có [1, 0] để khống chế cắt tay và chọn 0
        self.factors = sorted(factors, reverse=True) + [1, 0]
        self.max_manual_cuts = max_manual_cuts
        self.max_stock_over = max_stock_over
        self.time_limit_seconds = time_limit_seconds  # <-- THÊM MỚI

        self.solutions = []
        self.solution_matrix = None

        # ---- Pickle cache setup: pattern_cache nằm cùng cấp project folder ----
        self.BASE_DIR = Path(__file__).resolve().parents[1]  # .../cat_sat_iea
        self.CACHE_DIR = self.BASE_DIR / "pattern_cache"
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    # ... (Các hàm cache _cache_key, _cache_path, save_solution_to_pickle, cut_list, load_solution_from_pickle giữ nguyên) ...
    def _cache_key(self):
        payload = {
            "length": int(self.length),
            "segment_sizes": list(map(float, self.segment_sizes.tolist())),
            "blade_width": float(self.blade_width),
        }
        s = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _cache_path(self):
        key = self._cache_key()
        return self.CACHE_DIR / f"patterns_{key}.pkl"

    def save_solution_to_pickle(self):
        """Lưu list[(obj_value, solution)] vào file pickle."""
        path = self._cache_path()
        tmp = str(path) + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(self.solutions, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)

    def cut_list(self, lst, x, length):   # list_solutions, te_dau_sat, length
        for i, (obj_value, solution) in enumerate(lst):
            if obj_value + x <= length:
                return lst[i:]
        return []

    def load_solution_from_pickle(self):
        path = self._cache_path()
        if not path.exists():
            return []

        try:
            list_solutions = pickle.load(f) if False else None  # silence linter
            with open(path, "rb") as f:
                list_solutions = pickle.load(f)  # [(obj_value, [x_i,...]), ...]
        except Exception:
            # Hỏng file cache => bỏ qua
            return []

        print("------------------------------------------------<br>")
        print(f"ĐÃ CÓ {len(list_solutions)} NGHIỆM TRONG CACHE<br>")
        print("------------------------------------------------<br>")

        # Áp tề đầu
        list_solutions = self.cut_list(list_solutions, self.te_dau_sat, self.length)

        # VÌ MCTD CHỈ NHẬP TỐI ĐA 5 INPUT
        # Lọc theo tiêu chí <=5 loại đoạn khác 0 khi có >5 size (giống bản cũ)
        if len(self.segment_sizes) > 5:
            filtered = [
                (obj_value, solution) for obj_value, solution in list_solutions
                if sum(1 for x in solution if x != 0) <= 5
            ]
            return filtered
        else:
            return list_solutions

# =========================================================
# GIAI ĐOẠN 1 MỚI: Thu thập nghiệm bằng SolutionCallback
# =========================================================
class SolutionAndLogCollector(cp_model.CpSolverSolutionCallback):
    # ... (Giữ nguyên) ...
    def __init__(self, vars_x, seg_scaled, blade_scaled, scale, length, te_dau_sat,
                 exclude_set, accept_at_most=1000, print_every=1):
        super().__init__()
        self._vars_x = vars_x
        self._seg_scaled = seg_scaled
        self._blade_scaled = blade_scaled
        self._scale = scale
        self._length = length
        self._te = te_dau_sat
        self._exclude = exclude_set  # set(tuple(x))
        self._seen = set()
        self._solutions = []         # list[(obj_value, [x_i,...])]
        self._accept_at_most = accept_at_most
        self._print_every = max(1, print_every)
        self._cnt = 0
        self._start = time.time()

    def on_solution_callback(self):
        # đọc nghiệm
        x = [int(self.Value(v)) for v in self._vars_x]
        key = tuple(x)

        # bỏ nghiệm trùng hoặc đã có trong cache
        if key in self._seen or key in self._exclude:
            return

        # tính objective ở thang float
        sum_x = sum(x)
        obj_scaled = sum(self._seg_scaled[i] * x[i] for i in range(len(x))) + self._blade_scaled * sum_x
        obj_value = obj_scaled / self._scale  # mm

        self._solutions.append((obj_value, x))
        self._seen.add(key)

        self._cnt += 1
        if self._cnt % self._print_every == 0:
            hao_hut = self._length - obj_value
            print(f"{x}, Hao hụt {hao_hut}/cây<br>")

        # dừng sớm khi đủ số nghiệm mong muốn
        if len(self._solutions) >= self._accept_at_most:
            self.StopSearch()

    @property
    def solutions(self):
        # sắp xếp theo obj_value giảm dần để ưu tiên phương án hao hụt nhỏ
        return sorted(self._solutions, key=lambda t: t[0], reverse=True)


class SteelCuttingOptimizer(SteelCuttingOptimizer):  # extend class ở trên để gom file một chỗ
    # -----------------------------
    # Batch tìm nghiệm dùng callback
    # -----------------------------
    def _solve_single_bar_batch(self, max_solutions=1000, time_limit_sec=None): # <-- Sửa: bỏ giá trị time_limit_sec
        """
        Tạo mô hình thỏa mãn với ràng buộc:
          - length*(1-0.01) <= sum(seg[i]*x_i) + blade_width * sum(x_i) <= length - te_dau_sat
          - 0 <= x_i <= 30, integer
        Dùng CpSolverSolutionCallback để duyệt nghiệm nhanh, lọc trùng bằng set.
        Trả về list[(obj_value_mm, [x_i,...])], đã sort theo obj_value giảm dần.
        """
        # --- THÊM MỚI: Log ---
        print(f"Bắt đầu GĐ 1: Tìm các pattern (tối đa {max_solutions:,} phương án). Vui lòng chờ...<br>")
        model = cp_model.CpModel()

        n = len(self.segment_sizes)
        vars_x = [model.NewIntVar(0, 30, f"x_{i}") for i in range(n)]
        sum_x = cp_model.LinearExpr.Sum(vars_x)

        # scale integer hóa
        scale = 10
        seg_scaled = [int(round(s * scale)) for s in self.segment_sizes.tolist()]
        blade_scaled = int(round(self.blade_width * scale))
        length_scaled = int(round(self.length * scale))
        te_scaled = int(round(self.te_dau_sat * scale))

        objective_scaled = cp_model.LinearExpr.Sum(
            [seg_scaled[i] * vars_x[i] for i in range(n)]
        ) + blade_scaled * sum_x

        # ràng buộc cửa sổ hao hụt (giữ như cũ, 1% hao hụt tối thiểu)
        lower = int(round(length_scaled * (1 - 0.01)))
        upper = int(round(length_scaled))   # ---------------------- KHÔNG LẤY te_scaled nữa, B1 vẫn giải full, tới lúc load mới lấy từ tề đầu trở đi
        model.Add(objective_scaled >= lower)
        model.Add(objective_scaled <= upper)

        # Bật enumerate all solutions (bài toán thỏa mãn)
        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.log_search_progress = True
        
        # --- THAY ĐỔI: Bỏ time limit ---
        # solver.parameters.max_time_in_seconds = float(self.time_limit_seconds) # <-- BỎ DÒNG NÀY
        
        solver.parameters.num_search_workers = 1

        # chuẩn bị exclude từ cache hiện có (nếu có)
        exclude_set = set()
        for _, sol in self.solutions:
            exclude_set.add(tuple(int(v) for v in sol))

        collector = SolutionAndLogCollector(
            vars_x=vars_x,
            seg_scaled=seg_scaled,
            blade_scaled=blade_scaled,
            scale=scale,
            length=self.length,
            te_dau_sat=self.te_dau_sat,
            exclude_set=exclude_set,
            accept_at_most=max_solutions, # <-- Sẽ được set là 100,000 từ optimize_cutting
            print_every=100 # <-- In ít lại
        )

        # chạy tìm tất cả nghiệm (giới hạn bởi solution_limit)
        solver.SearchForAllSolutions(model, collector)

        # --- THÊM MỚI: Log ---
        print(f"GĐ 1: Tìm thấy {len(collector.solutions)} patterns.<br>")
        return collector.solutions

    def optimize_cutting(self):
        # Ưu tiên dùng nghiệm cache (sau khi lọc theo tề đầu)
        self.solutions = self.load_solution_from_pickle()

        if not self.solutions:
            print("Chưa có nghiệm trong CACHE, đang tìm nghiệm<br>")
        elif 0 < len(self.solutions) < 10:
            print("DANH SÁCH NGHIỆM QUÁ NHỎ, ĐANG GIẢI LẠI!!!!<br>")
            self.solutions = []

        # Nếu cache chưa đủ, dùng batch callback để lấy nhanh nghiệm mới
        if not self.solutions:
            # --- THAY ĐỔI: Giống cat_laser_roi ---
            MAX_SOLUTIONS = 100000 
            # TIME_LIMIT_SEC = 5.0 (Không dùng nữa)

            batch = self._solve_single_bar_batch(
                max_solutions=MAX_SOLUTIONS,
                time_limit_sec=None # <-- Không dùng nữa
            )
            if not batch:
                # <-- Lỗi này vẫn có thể xảy ra nếu không tìm thấy gì
                raise ValueError("Không tìm được nghiệm phù hợp cho 1 cây sắt (GĐ 1).")

            self.solutions = batch
            # Lưu cache
            self.save_solution_to_pickle()

        self.solution_matrix = np.array([sol[1] for sol in self.solutions], dtype=int)
        print("------------------------------------------------<br>")
        print(f"THỰC TẾ LOAD {len(self.solution_matrix)} NGHIỆM<br>")
        print("------------------------------------------------<br>")
        return self.solutions

    # -----------------------------
    # Giai đoạn 2: Phân phối số bó (CP-SAT)
    # -----------------------------
    def optimize_distribution(self):
        # --- THÊM MỚI: Log ---
        print("<br>Bắt đầu GĐ 2: Phân phối bó...<br>")
        if self.solution_matrix is None:
            raise ValueError("Run optimize_cutting first to generate solution matrix.")

        A = self.solution_matrix.T               # m x n
        L = np.array([self.length - sol[0] for sol in self.solutions], dtype=int)

        m, n = A.shape
        k = 30  # số cột bó sắt

        model = cp_model.CpModel()

        R = len(self.factors)
        z = [[[model.NewBoolVar(f"z_{i}_{j}_{r}") for r in range(R)] for j in range(k)] for i in range(n)]
        max_factor = max(self.factors)
        x = [[model.NewIntVar(0, max_factor, f"x_{i}_{j}") for j in range(k)] for i in range(n)]

        for i in range(n):
            for j in range(k):
                model.Add(sum(z[i][j][r] for r in range(R)) == 1)
                model.Add(x[i][j] == sum(self.factors[r] * z[i][j][r] for r in range(R)))

        index_of_one = self.factors.index(1)
        model.Add(
            sum(z[i][j][index_of_one] for i in range(n) for j in range(k)) <= self.max_manual_cuts
        )

        C = [model.NewIntVar(0, 10**9, f"C_{i}") for i in range(A.shape[0])]
        for i_row in range(A.shape[0]):
            expr = []
            for j_col in range(n):
                coeff = int(A[i_row, j_col])
                if coeff != 0:
                    for col in range(k):
                        expr.append(coeff * x[j_col][col])
            model.Add(C[i_row] == (sum(expr) if expr else 0))
            model.Add(C[i_row] - int(self.demands[i_row]) >= 0)
            model.Add(C[i_row] - int(self.demands[i_row]) <= int(self.max_stock_over))

        Loss_terms = []
        for j_col in range(n):
            if int(L[j_col]) != 0:
                Loss_terms.append(int(L[j_col]) * sum(x[j_col][col] for col in range(k)))
        Loss_expr = sum(Loss_terms) if Loss_terms else 0

        index_of_zero = self.factors.index(0)
        num_zeros_expr = sum(z[i][j][index_of_zero] for i in range(n) for j in range(k))

        W1 = 10**6
        W2 = 1
        model.Minimize(Loss_expr * W1 - num_zeros_expr * W2)

        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = False
        # --- CHỖ NÀY ĐÃ ĐÚNG: GĐ 2 dùng time limit ---
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)

        print("!CLEAR!")  # XÓA LOG TRƯỚC KHI IN KẾT QUẢ

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("Dui lòng tăng số đoạn cắt thủ công hoặc số tồn kho chứ VÔ NGHIỆM rùi!!!!")
            # --- Sửa thông báo lỗi ---
            raise ValueError("Không tìm được nghiệm tối ưu (GĐ 2) trong thời gian giới hạn.")

        x_optimal = np.array([[solver.Value(x[i][j]) for j in range(k)] for i in range(n)])

        print("Kích thước đoạn (mm): ")
        print(f"{self.segment_sizes}<br>")

        tong_lan_cat = 0
        tong_cat_tay = 0

        for row_index in range(n):
            row = x_optimal[row_index, :]
            non_zero = row[row != 0]
            if non_zero.size > 0:
                counts = Counter(non_zero)
                print("Chọn: ", A[:, row_index], " Hao hụt: ", str(L[row_index]) + " mm/cây<br>")
                for num, count in counts.items():
                    print(f"\t{num} cây/bó: {count} lần<br>")
                    if num == 1:
                        tong_cat_tay += count
                    tong_lan_cat += count

        tong_sat = int(x_optimal.sum())
        C_vals = np.array([solver.Value(C[i]) for i in range(m)])

        print("____<br>")
        print("Yêu cầu: <br>")
        print(f"{self.demands}<br>")
        print("Đã cắt được: <br>")
        print(f"{C_vals}<br>")
        print("____<br>")
        print(f"Tổng lần cắt: {tong_lan_cat}<br>")
        print("Trong đó: cắt máy: ", tong_sat - tong_cat_tay, " cây, ", " cắt tay: ", tong_cat_tay, " cây<br>")

        time_estimate = tong_cat_tay * 5 + (tong_lan_cat - tong_cat_tay) * 4
        print("Thời gian ước tính: ", time_estimate // 60, " giờ ", time_estimate % 60, " phút<br>")
        print("____<br>")
        print("Tổng cây sắt cần: ", tong_sat, " cây<br>")

        Loss_value = 0
        for j_col in range(n):
            count_j = sum(solver.Value(x[j_col][col]) for col in range(k))
            Loss_value += int(L[j_col]) * count_j

        print("Cắt được: ", (self.length * tong_sat - Loss_value) / 1000, "m<br>")
        print("Hao hụt: ", Loss_value / 1000, "m<br>")
        if self.length * tong_sat > 0:
            print(f"Hao hụt: {(Loss_value / (self.length * tong_sat)) * 100:.2f}%<br>")

        return x_optimal