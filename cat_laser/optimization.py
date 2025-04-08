from ortools.sat.python import cp_model
import numpy as np

def solve_cp_model(a, k, length):
    # Kiểm tra độ dài mảng a và k
    a = np.array(a)
    k = np.array(k)
    n = len(a)
    if len(k) != n:
        raise ValueError("Mảng k phải có cùng kích thước với mảng a")

    # Tạo mô hình
    model = cp_model.CpModel()

    # 1. Xác định các vị trí đặc biệt (k_i != 1)
    special_indices = [i for i in range(n) if k[i] != 1]

    # 2. Khai báo biến x_i
    x = []
    for i in range(n):
        # if k[i] == 1:
        #     x.append(model.NewIntVar(1, length, f'x_{i+1}'))  # x_i >= 1, giới hạn trên là length
        # else:
        x.append(model.NewIntVar(0, length, f'x_{i+1}')) # x_i >= 0, giới hạn trên là length

    # 3. Biến nhị phân b_i cho các vị trí đặc biệt
    b = [model.NewBoolVar(f'b_{i+1}') for i in special_indices]

    # 4. Ràng buộc giữa x_i và b_i
    M = length # Hằng số lớn được thay bằng length
    for idx, i in enumerate(special_indices):
        model.Add(x[i] <= M * b[idx]) # Nếu x_i > 0 thì b_i = 1
        model.Add(x[i] >= b[idx]) # Nếu b_i = 1 thì x_i >= 1

    # 5. Tính s: số biến khác 0 tại các vị trí đặc biệt
    s = model.NewIntVar(0, len(special_indices), 's')
    model.Add(s == sum(b))

    #       S LÀ SỐ LƯỢNG ĐOẠN CÓ LƯỠI MÀI KHÁC 1
    # 6. Phân loại trường hợp với biến nhị phân
    b0 = model.NewBoolVar('b0') # s = 0
    b1 = model.NewBoolVar('b1') # s = 1
    b2 = model.NewBoolVar('b2') # s >= 2

    # Ràng buộc cho b0, b1, b2
    model.Add(s == 0).OnlyEnforceIf(b0)
    model.Add(s != 0).OnlyEnforceIf(b0.Not())
    model.Add(s == 1).OnlyEnforceIf(b1)
    model.Add(s != 1).OnlyEnforceIf(b1.Not())
    model.Add(s >= 2).OnlyEnforceIf(b2)
    model.Add(s < 2).OnlyEnforceIf(b2.Not())

    # Chỉ một trường hợp xảy ra
    model.Add(b0 + b1 + b2 == 1)

    # 7. Tổng biểu thức: sum((a[i] + k[i]) * x[i])
    # Nhân tất cả các hệ số với 100 để biến thành số nguyên
    expr = sum(int(100 * (a[i] + k[i])) * x[i] for i in range(n))

    # 8. Ràng buộc bất đẳng thức dựa trên c
    # Nhân các giá trị bên phải với 100
    model.Add(expr <= int(100 * (length - 60))).OnlyEnforceIf(b0) 
    model.Add(expr <= int(100 * (length - 0))).OnlyEnforceIf(b1) 
    model.Add(expr <= int(100 * (length - 15))).OnlyEnforceIf(b2) # expr + 15 <= length => expr <= length - 15
    model.Add(int(100 * length * (1-0.015)) <= expr ) # Hao hụt 1%

    # 9. Lớp callback để thu thập nghiệm
    class SolutionPrinter(cp_model.CpSolverSolutionCallback):
        def __init__(self, variables, special_indices, b0, b1, b2):
            cp_model.CpSolverSolutionCallback.__init__(self)
            self.variables_ = variables
            self.special_indices_ = special_indices
            self.b0_ = b0
            self.b1_ = b1
            self.b2_ = b2
            self.solutions_ = []

        def OnSolutionCallback(self):
            solution = np.array([self.Value(v) for v in self.variables_])
            special_values = [self.Value(self.variables_[i]) for i in self.special_indices_]
            num_nonzero = sum(1 for val in special_values if val > 0)
            if num_nonzero == 0:
                c = 60
            elif num_nonzero == 1:
                c = 0
            else:
                c = 15
            tong_chieu_dai_cat_duoc = sum((a + k) * solution) # (kich_thuoc_doan + hao_hut) * so_luong_doan
            if 0 < tong_chieu_dai_cat_duoc + c <= length:
                # Xác định trường hợp b0, b1, b2
                if self.Value(self.b0_):
                    case = "c=60"
                elif self.Value(self.b1_):
                    case = "c=0"
                else:
                    case = "c=15"
                self.solutions_.append((tong_chieu_dai_cat_duoc, solution, case))

        def get_sorted_solutions(self):
            return sorted(self.solutions_, reverse=True, key=lambda s: s[0])

    # 10. Tìm tất cả nghiệm
    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = True # hiển thị log chi tiết

    solution_printer = SolutionPrinter(x, special_indices, b0, b1, b2)  # Truyền b0, b1, b2
    solver.SearchForAllSolutions(model, solution_printer)

    # 11. In kết quả
    # print(f"Tổng số nghiệm: {len(solution_printer.solutions_)}")
    # for i, sol in enumerate(solution_printer.solutions_, 1):
    #     print(f"Nghiệm {i}: {sol}")

    return solution_printer.get_sorted_solutions()



# Ví dụ sử dụng
KICH_THUOC_DOAN = [2360.8, 1684.8, 1289.2, 1162.2, 565, 46]
k = [1, 1, 1, 1, 3, 3] # Các vị trí có k_i != 1 là x5, x6
LENGTH = 5850 # Giả định length = 100, bạn có thể thay đổi giá trị này
SL_CAT = [600, 1200, 1200, 600, 1200, 1200]



# KICH_THUOC_DOAN = [2680.8, 2360.8, 2360.8, 1886.8, 1796.8, 1770.8, 1684.8, 1680.8, 1289.2, 1289.2, 1186.6, 1162.2, 645, 323, 565, 46]
# k = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 3]
# LENGTH = 5850  # Chiều dài thanh sắt
# SL_CAT = [300, 300, 300, 600, 600, 600, 300, 600, 300, 600, 300, 300, 600, 300, 300, 1200]


solutions = solve_cp_model(KICH_THUOC_DOAN, k, LENGTH)

# ------------------------------ BƯỚC 2 ------------------------------

# Trích xuất ma trận từ danh sách solutions
def extract_solution_matrix(solutions, num_sol=-1):
    """Trích xuất ma trận từ danh sách solutions."""
    solution_matrix = np.array([list(solution[1]) for solution in solutions[:num_sol]])
    return solution_matrix.T


# Chuyển danh sách solutions thành ma trận
patterns = extract_solution_matrix(solutions)
hao_hut = np.array([LENGTH - solution[0] for solution in solutions])


SO_LUONG_TON_KHO = 20

# Khởi tạo mô hình tối ưu
model = cp_model.CpModel()

m, n = patterns.shape # Số pattern (hàng) và số đoạn (cột)

# Tạo biến x[i] là số lần sử dụng mỗi pattern
x_cay_sat = [model.NewIntVar(0, max(SL_CAT), f'x_{i}') for i in range(n)]

# Ràng buộc: 0 <= (patterns * x - SL_CAT) <= SO_LUONG_TON_KHO (đảm bảo đủ số đoạn cần thiết)
for i in range(m):
    model.Add((sum(patterns[i, j] * x_cay_sat[j] for j in range(n)) - SL_CAT[i]) >= 0)
    model.Add((sum(patterns[i, j] * x_cay_sat[j] for j in range(n)) - SL_CAT[i]) <= SO_LUONG_TON_KHO)

# Hàm mục tiêu: Minimize tổng hao hụt

tong_so_patterns = model.NewIntVar(0, n, "tong_so_patterns")
bool_vars = [model.NewBoolVar(f'b_{i}') for i in range(n)]
for i in range(n):
    model.Add(x_cay_sat[i] > 0).OnlyEnforceIf(bool_vars[i])
    model.Add(x_cay_sat[i] == 0).OnlyEnforceIf(bool_vars[i].Not())
model.Add(tong_so_patterns == sum(bool_vars))

tong_hao_hut = sum(hao_hut[i] * x_cay_sat[i] for i in range(n))
# model.Minimize(tong_so_patterns + tong_hao_hut)
model.Minimize(tong_hao_hut)

# Giải bài toán
solver = cp_model.CpSolver()
solver.parameters.log_search_progress = True # hiển thị log chi tiết
solver.parameters.max_time_in_seconds = 60 # Dừng sau 60 giây
status = solver.Solve(model)

# Kiểm tra kết quả tối ưu
if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    optimal_x = [solver.Value(x_var) for x_var in x_cay_sat] # Số lượng cây sắt cho từng pattern

    # Nhân ma trận patterns với vector optimal_x
    result_matrix = np.dot(patterns, optimal_x)

    # In kết quả
    print("Kích thước đoạn:")
    print(KICH_THUOC_DOAN)

    print("Số lượng cần:")
    print(SL_CAT)

    print("🔹 Đã cắt:")
    print(result_matrix)

    so_lan_cat = 0
    tong_hao_hut_sat = 0
    print("-"*40)
    print("Các bước cắt:")
    for solution, count in zip(solutions, optimal_x):
        if count > 0:
            so_lan_cat += 1
            print(f"Lần cắt thứ {so_lan_cat} || Hao hụt: {LENGTH-solution[0]:.1f}mm || Cắt {count} cây sắt || {solution[2]}")
            tong_hao_hut_sat += (LENGTH-solution[0])*count
            # print(f"{solution}: {count}")
            for size, so_nhat in zip(KICH_THUOC_DOAN, solution[1]):
                if so_nhat > 0:
                    print(f"({size}mm: {so_nhat} nhát)", end=", ")
            print("\n")

    print("-"*40)
    so_cay_sat = sum(optimal_x)
    print(f"Cần {so_cay_sat} cây sắt")
    print(f"Hao hụt: {tong_hao_hut_sat / (LENGTH*so_cay_sat) * 100:.2f}%")

else:
    print("❌ Không tìm thấy giải pháp tối ưu.")
