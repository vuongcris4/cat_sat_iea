import os
import json
import pickle
import hashlib
from pathlib import Path
import numpy as np
from collections import Counter
import time
import threading

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
# Lớp Tối Ưu Hóa (Phần 1: cache + tìm pattern)
# ===================================================================
class SteelCuttingOptimizer:
    # __init__ vẫn nhận time_limit_seconds
    def __init__(
        self,
        length,
        te_dau_sat,
        segment_sizes,
        demands,
        blade_width,
        factors,
        max_manual_cuts,
        max_stock_over,
        time_limit_seconds=30.0,
    ):
        self.length = length
        self.te_dau_sat = te_dau_sat
        self.segment_sizes = np.array(segment_sizes)
        self.demands = np.array(demands)
        self.blade_width = blade_width
        # đảm bảo factors có [1, 0] để khống chế cắt tay và “không chọn”
        # (GĐ2 sẽ tự lọc factor==0 để tránh biến vô nghĩa)
        self.factors = sorted(factors, reverse=True) + [1, 0]
        self.max_manual_cuts = max_manual_cuts
        self.max_stock_over = max_stock_over
        self.time_limit_seconds = time_limit_seconds

        self.solutions = []
        self.solution_matrix = None

        # ---- Pickle cache setup: pattern_cache nằm cùng cấp project folder ----
        self.BASE_DIR = Path(__file__).resolve().parents[1]  # .../cat_sat_iea
        self.CACHE_DIR = self.BASE_DIR / "pattern_cache"
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # -------------- Cache helpers --------------
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

    def cut_list(self, lst, x, length):
        """Áp tề đầu: bỏ các pattern có obj_value + te_dau > length."""
        for i, (obj_value, solution) in enumerate(lst):
            if obj_value + x <= length:
                return lst[i:]
        return []

    def load_solution_from_pickle(self):
        path = self._cache_path()
        if not path.exists():
            return []
        try:
            list_solutions = None
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
        # Lọc theo tiêu chí <=5 loại đoạn khác 0 khi có >5 size
        if len(self.segment_sizes) > 5:
            filtered = [
                (obj_value, solution)
                for obj_value, solution in list_solutions
                if sum(1 for x in solution if x != 0) <= 5
            ]
            return filtered
        else:
            return list_solutions


# =========================================================
# GIAI ĐOẠN 1: Thu thập nghiệm bằng SolutionCallback
# =========================================================
class SolutionAndLogCollector(cp_model.CpSolverSolutionCallback):
    def __init__(
        self,
        vars_x,
        seg_scaled,
        blade_scaled,
        scale,
        length,
        te_dau_sat,
        exclude_set,
        accept_at_most=1000,
        print_every=100,
    ):
        super().__init__()
        self._vars_x = vars_x
        self._seg_scaled = seg_scaled
        self._blade_scaled = blade_scaled
        self._scale = scale
        self._length = length
        self._te = te_dau_sat
        self._exclude = exclude_set  # set(tuple(x))
        self._seen = set()
        self._solutions = []  # list[(obj_value, [x_i,...])]
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
    def _solve_single_bar_batch(self, max_solutions=1000, time_limit_sec=None):
        """
        Tạo mô hình thỏa mãn với ràng buộc:
          - length*(1-0.01) <= sum(seg[i]*x_i) + blade_width * sum(x_i) <= length
          - 0 <= x_i <= 30, integer
        Dùng CpSolverSolutionCallback để duyệt nghiệm nhanh, lọc trùng bằng set.
        Trả về list[(obj_value_mm, [x_i,...])], đã sort theo obj_value giảm dần.
        """
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
        te_scaled = int(round(self.te_dau_sat * scale))  # giữ để tham khảo, B1 không dùng

        objective_scaled = cp_model.LinearExpr.Sum(
            [seg_scaled[i] * vars_x[i] for i in range(n)]
        ) + blade_scaled * sum_x

        # ràng buộc cửa sổ hao hụt (1% hao hụt tối thiểu)
        lower = int(round(length_scaled * (1 - 0.01)))
        upper = int(round(length_scaled))  # B1 giải full cây; tề đầu áp khi load cache
        model.Add(objective_scaled >= lower)
        model.Add(objective_scaled <= upper)

        # Bật enumerate all solutions (bài toán thỏa mãn)
        solver = cp_model.CpSolver()
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.log_search_progress = True

        # KHÔNG dùng time limit cho GĐ1 (đã bỏ)
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
            accept_at_most=max_solutions,
            print_every=100,
        )

        # chạy tìm tất cả nghiệm (giới hạn bởi solution_limit)
        solver.SearchForAllSolutions(model, collector)

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
            MAX_SOLUTIONS = 100000
            batch = self._solve_single_bar_batch(
                max_solutions=MAX_SOLUTIONS,
                time_limit_sec=None
            )
            if not batch:
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
    # Giai đoạn 2: Phân phối số bó (CP-SAT gọn O(n·R))
    # -----------------------------
    def optimize_distribution(self):
        print("<br>Bắt đầu GĐ 2: Đang tính toán bó sắt...<br>")
        if self.solution_matrix is None:
            raise ValueError("Run optimize_cutting first to generate solution matrix.")

        # A: m x n (m = số loại đoạn, n = số pattern)
        A = self.solution_matrix.T
        L = np.array([self.length - sol[0] for sol in self.solutions], dtype=int)  # hao hụt / cây cho pattern j
        m, n = A.shape

        # Chỉ dùng các factor > 0 (0 nghĩa là không chọn)
        pos_factors = [f for f in self.factors if f > 0]
        idx_one = None
        if 1 in pos_factors:
            idx_one = pos_factors.index(1)

        model = cp_model.CpModel()

        # Upper bound chặt cho từng (j,r) để thu gọn không gian nghiệm
        def safe_div_ceil(a, b):
            return (a + b - 1) // b

        # UB[j] = min_i ceil((demands_i + max_stock_over)/A[i,j]) với a_ij>0
        UB = []
        for j in range(n):
            caps = []
            for i in range(m):
                aij = int(A[i, j])
                if aij > 0:
                    caps.append(safe_div_ceil(int(self.demands[i]) + int(self.max_stock_over), aij))
            if caps:
                UB.append(min(caps))
            else:
                UB.append(0)  # pattern không tạo ra đoạn nào

        # Biến b[j][r] = số bó pattern j với hệ số fr (fr ∈ pos_factors)
        b = []
        for j in range(n):
            row = []
            for fr in pos_factors:
                ub = safe_div_ceil(UB[j], fr) if UB[j] > 0 else 0
                row.append(model.NewIntVar(0, max(0, ub), f"b_{j}_{fr}"))
            b.append(row)

        # Tổng số cây sắt theo pattern j: sum_r fr * b[j][r]
        def bars_of_pattern(j):
            terms = []
            for r, fr in enumerate(pos_factors):
                if fr != 0:
                    terms.append(fr * b[j][r])
            return sum(terms) if terms else 0

        # Nhu cầu từng loại đoạn (khoảng [demands, demands+max_stock_over])
        C = []
        for i in range(m):
            contrib = []
            for j in range(n):
                aij = int(A[i, j])
                if aij != 0:
                    contrib.append(aij * bars_of_pattern(j))
            Ci = model.NewIntVar(0, 10**12, f"C_{i}")
            model.Add(Ci == (sum(contrib) if contrib else 0))
            model.Add(Ci >= int(self.demands[i]))
            model.Add(Ci <= int(self.demands[i]) + int(self.max_stock_over))
            C.append(Ci)

        # Giới hạn số lần cắt tay (factor == 1)
        if idx_one is not None:
            manual_cuts = sum(b[j][idx_one] for j in range(n))
            model.Add(manual_cuts <= int(self.max_manual_cuts))

        # Mục tiêu: minimize hao hụt tổng + tie-break nhỏ cho số bó
        loss_terms = []
        bundle_terms = []
        for j in range(n):
            bj = bars_of_pattern(j)
            loss_terms.append(int(L[j]) * bj)
            for r in range(len(pos_factors)):
                bundle_terms.append(b[j][r])

        Loss_expr = sum(loss_terms) if loss_terms else 0
        Bundles_expr = sum(bundle_terms) if bundle_terms else 0

        # W1 lớn để ưu tiên hao hụt; W2 nhỏ để giảm số bó khi bằng điểm
        W1 = 10**6
        W2 = 1
        model.Minimize(Loss_expr * W1 + Bundles_expr * W2)

        # Giải
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = False
        solver.parameters.max_time_in_seconds = float(self.time_limit_seconds)
        solver.parameters.num_search_workers = 8

        status = solver.Solve(model)

        print("!CLEAR!")  # Xóa log trước khi in kết quả

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("Vô nghiệm / hết thời gian trong GĐ 2 — hãy tăng cắt tay hoặc tồn kho tối đa!")
            raise ValueError("Không tìm được nghiệm tối ưu (GĐ 2) trong thời gian giới hạn.")

        # Thu kết quả (n x |pos_factors|): số bó theo từng pattern & factor
        b_opt = np.zeros((n, len(pos_factors)), dtype=int)
        for j in range(n):
            for r in range(len(pos_factors)):
                b_opt[j, r] = int(solver.Value(b[j][r]))

        # In báo cáo giống logic cũ
        print("Kích thước đoạn (mm): ")
        print(f"{self.segment_sizes}<br>")

        tong_lan_cat = int(b_opt.sum())  # tổng số bó
        tong_cat_tay = 0
        total_bars = 0

        for j in range(n):
            counts = {pos_factors[r]: b_opt[j, r] for r in range(len(pos_factors)) if b_opt[j, r] > 0}
            if counts:
                print("Chọn: ", A[:, j], " Hao hụt: ", str(int(L[j])) + " mm/cây<br>")
                for fr, cnt in counts.items():
                    print(f"\t{fr} cây/bó: {cnt} lần<br>")
                    total_bars += fr * cnt
                    if fr == 1:
                        tong_cat_tay += cnt

        C_vals = np.array([int(solver.Value(C[i])) for i in range(m)], dtype=int)

        print("____<br>")
        print("Yêu cầu: <br>")
        print(f"{self.demands}<br>")
        print("Đã cắt được: <br>")
        print(f"{C_vals}<br>")
        print("____<br>")
        print(f"Tổng lần cắt (số bó): {tong_lan_cat}<br>")
        print("Trong đó: cắt máy: ", total_bars - tong_cat_tay, " cây, ", " cắt tay: ", tong_cat_tay, " cây<br>")

        time_estimate = tong_cat_tay * 5 + (tong_lan_cat - tong_cat_tay) * 4
        print("Thời gian ước tính: ", time_estimate // 60, " giờ ", time_estimate % 60, " phút<br>")
        print("____<br>")
        print("Tổng cây sắt cần: ", total_bars, " cây<br>")

        Loss_value = 0
        for j in range(n):
            count_j = sum(pos_factors[r] * b_opt[j, r] for r in range(len(pos_factors)))
            Loss_value += int(L[j]) * count_j

        print("Cắt được: ", (self.length * total_bars - Loss_value) / 1000, "m<br>")
        print("Hao hụt: ", Loss_value / 1000, "m<br>")
        if self.length * total_bars > 0:
            print(f"Hao hụt: {(Loss_value / (self.length * total_bars)) * 100:.2f}%<br>")

        # Trả về ma trận (n x |pos_factors|) để views.py .tolist() gửi ra client
        return b_opt
