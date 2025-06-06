import os
import json
import numpy as np
import gurobipy as gp
from gurobipy import GRB
from collections import Counter
from django.db import models
from .models import Solution

class SteelCuttingOptimizer:
    def __init__(self, length, te_dau_sat, segment_sizes, demands, blade_width, factors, max_manual_cuts, max_stock_over):
        self.length = length
        self.te_dau_sat = te_dau_sat
        self.segment_sizes = np.array(segment_sizes)
        self.demands = np.array(demands)
        self.blade_width = blade_width
        self.factors = sorted(factors, reverse=True) + [1, 0]  # Ensure proper factor ordering
        self.max_manual_cuts = max_manual_cuts
        self.max_stock_over = max_stock_over
        self.solutions = []
        self.solution_matrix = None

    def save_solution_to_model(self):
        for obj_value, solution in self.solutions:
            if not Solution.objects.filter(length=self.length, segment_sizes=self.segment_sizes.tolist(), blade_width=self.blade_width, solution=solution).exists():
                Solution.objects.create(
                    length=self.length,
                    segment_sizes=self.segment_sizes.tolist(),
                    blade_width=self.blade_width,
                    obj_value=obj_value,
                    solution=solution
                )
    
    def cut_list(self, lst, x, length):   # Tề đầu
        # Tìm vị trí đầu tiên thỏa mãn điều kiện obj_value + x <= length
        for i, (obj_value, solution) in enumerate(lst):
            if obj_value + x <= length:
                return lst[i:]  # Cắt từ vị trí này trở đi
        return []  # Trả về danh sách rỗng nếu không có phần tử nào thỏa mãn


    def load_solution_from_model(self):
        # solutions = Solution.objects.filter(length=self.length, segment_sizes=self.segment_sizes.tolist(), blade_width=self.blade_width)
        # return [(s.obj_value, s.solution) for s in solutions]
        solutions = Solution.objects.filter(
            length=self.length,
            segment_sizes=self.segment_sizes.tolist(),
            blade_width=self.blade_width
        )

        if 0 < solutions.count() < 10:
            print("DANH SÁCH NGHIỆM QUÁ NHỎ, ĐANG GIẢI LẠI!!!!")
            solutions.delete()

        list_solutions = list(solutions.values_list('obj_value', 'solution'))

        print("------------------------------------------------<br>")
        print(f"ĐÃ CÓ {len(list_solutions)} NGHIỆM TRONG CSDL<br>")
        print("------------------------------------------------<br>")

        list_solutions = self.cut_list(list_solutions, self.te_dau_sat, self.length)    # Tăng độ hao hụt >= một số cho trước

        # CẬP NHẬT THÊM CHỖ MÁY CẮT TỰ ĐỘNG
        if len(self.segment_sizes) > 5:
            # MÁY CẮT TỰ ĐỘNG KHÔNG NHẬP QUÁ 5 LẦN

            filtered_solutions = [
                (obj_value, solution) for obj_value, solution in list_solutions
                if sum(1 for x in solution if x != 0) <= 5
            ]

            return filtered_solutions
        else:        
            return list_solutions

    def optimize_cutting(self):
        self.solutions = self.load_solution_from_model()

        # Tìm nghiệm cho 1 cây sắt
        if not self.solutions:
            print("Chưa có nghiệm trong CSDL, đang tìm nghiệm")
            model = gp.Model("Steel Cutting Optimization")
            model.setParam('OutputFlag', 0) # Tắt log mặc định ra CMD


            variables = []  # biến x1, x2, x3, x4
            # Ràng buộc 0<=x<=30
            for i in range(len(self.segment_sizes)):
                var = model.addVar(lb=0, ub=30, vtype=GRB.INTEGER, name=f"var_{i+1}")   # Ràng buộc cho từng biến xi
                variables.append(var)

            total_sum = gp.quicksum(variables)  # Tổng x + y + z + t
            objective = (
                gp.quicksum(self.segment_sizes[i] * variables[i] for i in range(len(variables))) +
                self.blade_width * total_sum
            )   # Hàm mục tiêu: vd: 500x + 255y + 600z + 615t + 2.5*(x+y+z+t)

            model.addConstr(objective <= self.length - 15, "UpperBound") # Ràng buộc <= 5850 (-15 TỀ ĐẦU)
            model.addConstr(objective >= self.length * (1 - 0.015), "LowerBound") # >= 5850*(1-0.01)

            model.setObjective(objective, GRB.MAXIMIZE) # Chạy tối ưu

            nghiem_thu_n = 1
            while True:
                model.optimize()    # Giải optimize model

                nghiem_thu_n +=1 
                if nghiem_thu_n >= 1000:    # Ràng buộc nhỏ hơn 1000 nghiệm
                    break

                if model.status == GRB.OPTIMAL:
                    # Lưu nghiệm hiện tại
                    solution = [int(var.x) for var in variables] # Lấy value của từng biến xi đã giải đc
                    obj_value = objective.getValue()
                    self.solutions.append((obj_value, solution))    # lưu vào ma trận solutions

                    model.addConstr(
                        gp.quicksum((variables[i] - solution[i]) * (variables[i] - solution[i]) for i in range(len(variables))) >= 1,
                        name=f"ExcludeSolution_{len(self.solutions)}"
                    )   # sum from 1 to 4 (xi - xio)^2 >= 1, loại bỏ nghiệm vừa tìm được

                    print(f"{solution}, Hao hụt {self.length-obj_value}/cây<br>")  # in nghiệm trong quá trình tìm được
                else:
                    break
                

            self.save_solution_to_model()

        self.solution_matrix = np.array([sol[1] for sol in self.solutions])
        print("------------------------------------------------<br>")
        print(f"THỰC TẾ LOAD {len(self.solution_matrix)} NGHIỆM<br>")
        print("------------------------------------------------<br>")

        # print("<br>Tất cả các nghiệm tìm được:<br>")
        # for obj_value, sol in self.solutions:
        #     print(f"Nghiệm: {sol}, f(x) = {obj_value}, Minimized length - objective = {self.length - obj_value}<br>")

        return self.solutions

    def optimize_distribution(self):
        if self.solution_matrix is None:
            raise ValueError("Run optimize_cutting first to generate solution matrix.")

        A = self.solution_matrix.T  # Ma trận nghiệm transpose
        L = np.array([self.length - sol[0] for sol in self.solutions])  # Loss vector

        m, n = A.shape
        k = 30  # Ma trận số bó sắt

        model = gp.Model("Matrix Optimization")
        # model.setParam('TimeLimit', 60)  # Stop after 60 seconds
        model.setParam('MIPGap', 0.025)  # Stop when relative gap is below 2.5%

        x = model.addVars(n, k, vtype=GRB.INTEGER, name="x")    # Biến quyết định: x_ij
        # Biến nhị phân z_ijr để chọn giá trị của x_ij từ factors
        z = model.addVars(n, k, len(self.factors), vtype=GRB.BINARY, name="z")

        # Ràng buộc: x_ij phải bằng một giá trị trong danh sách factors
        for i in range(n):
            for j in range(k):
                model.addConstr(x[i, j] == gp.quicksum(z[i, j, r] * self.factors[r] for r in range(len(self.factors))),
                                name=f"x_constraint_{i}_{j}")
                model.addConstr(gp.quicksum(z[i, j, r] for r in range(len(self.factors))) == 1,
                                name=f"z_one_hot_{i}_{j}")

        # Giới hạn số lượng cắt tay
        index_of_one = self.factors.index(1)
        total_ones = gp.quicksum(z[i, j, index_of_one] for i in range(n) for j in range(k))
        model.addConstr(total_ones <= self.max_manual_cuts, name="limit_ones")

        # Ràng buộc: 0 <= C - B <= 10
        C = model.addVars(m, vtype=GRB.INTEGER, name="C")   # Số lượng đoạn thực tế mỗi loại
        for i in range(m):
            # Tổng các hàng của ma trận A*x
            model.addConstr(C[i] == gp.quicksum(A[i, j] * x[j, col] for j in range(n) for col in range(k)),
                            name=f"C_calc_{i}")
            model.addConstr(C[i] - self.demands[i] >= 0, name=f"C_B_lower_{i}")
            model.addConstr(C[i] - self.demands[i] <= self.max_stock_over, name=f"C_B_upper_{i}")

        # Tối ưu hóa số lượng biến bằng 0 trong ma trận x
        # Hàm mục tiêu thứ hai: Số lượng biến bằng 0 trong ma trận x
        zero_vars = model.addVars(n, k, vtype=GRB.BINARY, name="zero_vars")

        M = 1e6  # Big-M, giá trị đủ lớn
        epsilon = 1e-6  # Giá trị nhỏ để đảm bảo x[i, j] > 0
        # Thêm ràng buộc để xác định zero_vars
        for i in range(n):
            for j in range(k):
                # Ràng buộc 1: x[i, j] <= M * (1 - zero_vars[i, j])
                # Nếu (x[i, j] == 0) -> (zero_vars[i, j] == 1)
                model.addConstr(x[i, j] <= M * (1 - zero_vars[i, j]), name=f"bigM_zero_var_1_{i}_{j}")

                # Ràng buộc 2: x[i, j] >= epsilon - M * zero_vars[i, j]
                # Nếu (x[i, j] > 0) -> (zero_vars[i, j] == 0)
                model.addConstr(x[i, j] >= epsilon - M * zero_vars[i, j], name=f"bigM_zero_var_2_{i}_{j}")

        # Hàm mục tiêu thứ nhất: Loss
        Loss = gp.quicksum(L[i] * x[i, j] for i in range(n) for j in range(k))
        # Hàm mục tiêu thứ hai: Tối đa hóa số lượng biến bằng 0
        num_zeros = gp.quicksum(zero_vars[i, j] for i in range(n) for j in range(k))

        # Sử dụng phương pháp mục tiêu đa mục tiêu
        model.setObjectiveN(Loss, index=0, priority=2, name="Minimize_Loss")
        model.setObjectiveN(num_zeros, index=1, priority=1, name="Maximize_Zeros")

        model.optimize()

        print("!CLEAR!")    # XÓA HẾT LOG TRƯỚC KHI PRINT KẾT QUẢ

        if model.status == GRB.OPTIMAL:
            x_optimal = np.array([[x[i, j].X for j in range(k)] for i in range(n)])

            print("Kích thước đoạn (mm): ")
            print(f"{self.segment_sizes}<br>")
            # Duyệt qua từng hàng
            tong_lan_cat = 0
            tong_cat_tay = 0
            for row_index, row in enumerate(x_optimal):
                non_zero_elements = row[row != 0]  # Lấy các phần tử khác 0
                if non_zero_elements.size > 0:
                    # Đếm số lượng mỗi loại số
                    counts = Counter(non_zero_elements)
                    print("Chọn: ",A[:,row_index], " Hao hụt: ", str(L[row_index])+" mm/cây<br>")

                    for num, count in counts.items():
                        print(f"\t{num} cây/bó: {count} lần<br>")
                        if num == 1:
                            tong_cat_tay += count
                        tong_lan_cat += count
            
            tong_sat = sum(sum(x_optimal))
            print("____<br>")
            print("Yêu cầu: <br>")
            print(f"{self.demands}<br>")
            print("Đã cắt được: <br>")
            print(f"{np.array([C[i].X for i in C])}<br>")    # {0: <gurobi.Var C[0] (value 788.0)>, 1: <gurobi.Var C[1] (value 1580.0)>, 2: <gurobi.Var C[2] (value 1508.0)>, 3: <gurobi.Var C[3] (value 1508.0)<br>>}
            print("____<br>")
            print(f"Tổng lần cắt: {tong_lan_cat}<br>")
            print("Trong đó: cắt máy: ", tong_sat-tong_cat_tay," cây, "," cắt tay: ", tong_cat_tay, " cây<br>")
            time_estimate = tong_cat_tay * 5 + (tong_lan_cat-tong_cat_tay) * 4 # cắt tay * x + cắt máy * y
            print("Thời gian ước tính: ", time_estimate // 60," giờ ",time_estimate % 60," phút<br>")
            print("____<br>")
            print("Tổng cây sắt cần: ", tong_sat, " cây<br>")
            print("Cắt được: ",(self.length * tong_sat - Loss.getValue())/1000,"m<br>")
            print("Hao hụt: ", Loss.getValue()/1000,"m<br>")
            print(f"Hao hụt: {(Loss.getValue() / (self.length * tong_sat))*100:.2f}%<br>")
            return x_optimal
        else:
            # print("ĐÃ STOP TIẾN TRÌNH!")
            print("Dui lòng tăng số đoạn cắt thủ công hoặc số tồn kho chứ VÔ NGHIỆM rùi!!!!")
            raise ValueError("No optimal solution found.")
