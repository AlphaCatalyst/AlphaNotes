"""Excel version of the 2027 scenario model with live formulas (openpyxl).

Selector cells on sheet Paths: path index (1-5) and case (1 bear / 2 base / 3 bull).
Everything on Quarterly / Summary / Decomposition / Sensitivity is formula-driven from Paths + Company.
"""
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from common import PROC, ROOT
import model_2027 as M

OUT = ROOT / "model.xlsx"
OUT.parent.mkdir(exist_ok=True)

inp = pd.read_csv(PROC / "model_company_inputs.csv", dtype={"code": str})
paths = pd.read_csv(PROC / "model_price_paths.csv", index_col=0)
sc = pd.read_csv(PROC / "screen_snapshot.csv", dtype={"code": str})
dec = pd.read_csv(PROC / "model_decomposition.csv", dtype={"code": str})
hpe = pd.read_csv(PROC / "hist_peak_pe.csv")

HEAD = Font(bold=True)
INPUT = PatternFill("solid", fgColor="FFF2CC")   # editable assumptions
FACT = PatternFill("solid", fgColor="E2EFDA")    # disclosed data
wb = Workbook()


def header(ws, row, cols):
    for j, c in enumerate(cols, 1):
        ws.cell(row=row, column=j, value=c).font = HEAD
        ws.cell(row=row, column=j).alignment = Alignment(wrap_text=True, vertical="top")


def key(code):
    return ("SH" if code.startswith("6") else "SZ") + code


def widths(ws, w):
    for j, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(j)].width = x


# ------------------------------------------------------------------ README
ws = wb.active
ws.title = "README"
readme = [
    "2027年猪周期情景模型（前提：2027年全国生猪均价18元/公斤，为给定前提而非预测）",
    "快照：股价2026-10-08收盘；资产负债表2026-06-30；经营数据截至2026年8-9月简报。",
    "切换：Paths!B12 价格路径（1-5），Paths!B13 情景（1熊/2基准/3牛）。其余表全部由公式驱动。",
    "颜色：黄色=研究假设（可改）；绿色=公司披露事实或管理层目标（来源见Company表basis列与Screening表）。",
    "利润链条：每公斤毛利=全国价×(1+区域溢价)+渠道溢价−完全成本；养殖利润=育肥头数×出栏重×每公斤毛利；",
    "  归母利润≈(养殖利润+仔猪利润)×归属比例 + 其他业务（未建模=0：温氏黄羽鸡、新希望/大北农/唐人神饲料、华统屠宰等）。",
    "  养殖价差≠归母净利润（少数股东、其他业务、减值、所得税豁免外业务）；情景市盈率≠目标价；归母利润≠股价涨幅。",
    "成本未披露的公司（华统、新五丰、正邦）不计算情景利润，只给“当前市值=8倍情景利润”所需的成本门槛。",
    "成本季度路径：从最新披露成本线性滑向2027年假设值，全年均值=假设值（权重见Paths!B31:E31）。",
    "东瑞售价=全国价×(1+内销溢价d)+出口重量占比s×出口价差e（Paths!B19:D21）。",
    "历史校准：Hist_PE表为三轮周期市值峰值/峰值年度归母利润，供判断市场在周期高点愿付的倍数。",
    "数据与脚本：scripts/model_2027.py（Python版，结果与本表一致，见QA表）。",
]
for i, t in enumerate(readme, 1):
    ws.cell(row=i, column=1, value=t)
ws.column_dimensions["A"].width = 140

# ------------------------------------------------------------------ Paths
ws = wb.create_sheet("Paths")
ws["A1"] = "全国生猪均价季度路径（元/公斤）"; ws["A1"].font = HEAD
header(ws, 3, ["路径", "Q1", "Q2", "Q3", "Q4", "年均"])
pnames = list(M.PATHS.keys())
for i, name in enumerate(pnames):
    r = 4 + i
    ws.cell(row=r, column=1, value=name)
    for q in range(4):
        c = ws.cell(row=r, column=2 + q, value=round(float(M.PATHS[name][q]), 4)); c.fill = INPUT
    ws.cell(row=r, column=6, value=f"=AVERAGE(B{r}:E{r})")
r = 4 + len(pnames)
ws.cell(row=r, column=1, value="参考：期货曲线原值（2026-10-08结算；Q4=Q3×1.02假设）")
for q in range(4):
    ws.cell(row=r, column=2 + q, value=round(float(M.curve[q]), 4)).fill = FACT
ws.cell(row=r, column=6, value=f"=AVERAGE(B{r}:E{r})")

ws["A12"], ws["B12"] = "选定路径（1-5）", 1
ws["A13"], ws["B13"] = "选定情景（1熊/2基准/3牛）", 2
for a in ("B12", "B13"):
    ws[a].fill = INPUT
dv1 = DataValidation(type="whole", operator="between", formula1="1", formula2="5"); ws.add_data_validation(dv1); dv1.add("B12")
dv2 = DataValidation(type="whole", operator="between", formula1="1", formula2="3"); ws.add_data_validation(dv2); dv2.add("B13")
ws["C12"] = "=INDEX(A4:A8,B12)"
header(ws, 15, ["参数", "熊", "基准", "牛", "选定"])
ws["A16"] = "仔猪毛利（元/头）"
for j, k in enumerate(["bear", "base", "bull"]):
    ws.cell(row=16, column=2 + j, value=M.PIGLET_MARGIN[k]).fill = INPUT
ws["E16"] = "=INDEX(B16:D16,$B$13)"
labels = {"d": "东瑞内销溢价d（相对全国均价）", "s": "东瑞出口重量占比s", "e": "东瑞出口−内销价差e（元/公斤）"}
for i, par in enumerate(["d", "s", "e"]):
    r = 19 + i
    ws.cell(row=r, column=1, value=labels[par])
    for j, k in enumerate(["bear", "base", "bull"]):
        ws.cell(row=r, column=2 + j, value=M.DONGRUI[k][par]).fill = INPUT
    ws.cell(row=r, column=5, value=f"=INDEX(B{r}:D{r},$B$13)")
ws["A24"], ws["B24"] = "“正常年份”全国均价（用于18元超额利润，元/公斤）", 14.0
ws["A25"], ws["B25"] = "估值倍数1（隐含价格）", 10
ws["A26"], ws["B26"] = "估值倍数2（隐含价格）", 15
ws["A27"], ws["B27"] = "成本门槛倍数", 8
for a in ("B24", "B25", "B26", "B27"):
    ws[a].fill = INPUT
header(ws, 28, ["选定路径全国价", "Q1", "Q2", "Q3", "Q4", "年均"])
for q in range(4):
    col = get_column_letter(2 + q)
    ws.cell(row=29, column=2 + q, value=f"=INDEX({col}4:{col}8,$B$12)")
ws["F29"] = "=AVERAGE(B29:E29)"
ws["A31"] = "成本滑行权重（成本_q=C2027+w_q×(C最新−C2027)）"
for q, w in enumerate([0.375, 0.125, -0.125, -0.375]):
    ws.cell(row=31, column=2 + q, value=w)
widths(ws, [44, 10, 10, 10, 10, 10])

# ------------------------------------------------------------------ Company
ws = wb.create_sheet("Company")
cols = ["code", "公司", "市值(亿元,2026-10-08)", "育肥量熊(万头)", "育肥量基准", "育肥量牛", "出栏重(kg)", "仔猪(万头)",
        "最新成本(元/kg)", "2027成本熊", "2027成本基准", "2027成本牛", "区域溢价(相对全国)", "归属比例",
        "季节权重Q1", "Q2", "Q3", "Q4", "东瑞=1", "选定育肥量", "选定成本", "依据（事实/目标/假设）", "归属比例来源", "最新成本口径"]
header(ws, 4, cols)
ws["A1"] = "公司输入（黄色=研究假设，绿色=披露数据）"; ws["A1"].font = HEAD
crow = {}
for i, (_, c) in enumerate(inp.iterrows()):
    r = 5 + i
    crow[c["code"]] = r
    season = [float(x) for x in c["season_q"].split(",")]
    vals = [key(c["code"]), c["name"], round(c["mcap_yi"], 2), c["V_bear"], c["V_base"], c["V_bull"], c["W"], c["piglets"],
            None if pd.isna(c["cost_latest"]) else c["cost_latest"],
            None if pd.isna(c["C_bear"]) else c["C_bear"], None if pd.isna(c["C_base"]) else c["C_base"],
            None if pd.isna(c["C_bull"]) else c["C_bull"], round(c["regional_premium"], 4), round(c["parent_share"], 4)] + season
    for j, v in enumerate(vals, 1):
        cell = ws.cell(row=r, column=j, value=v)
        if j in (3, 9):
            cell.fill = FACT
        elif j >= 4:
            cell.fill = INPUT
    ws.cell(row=r, column=19, value=1 if c["code"] == "001201" else 0)
    ws.cell(row=r, column=20, value=f"=INDEX(D{r}:F{r},Paths!$B$13)")
    ws.cell(row=r, column=21, value=f'=IF(COUNT(J{r}:L{r})=3,INDEX(J{r}:L{r},Paths!$B$13),"")')
    ws.cell(row=r, column=22, value=c["basis"])
    ws.cell(row=r, column=23, value=c["parent_share_source"])
    ws.cell(row=r, column=24, value=c["cost_latest_basis"])
widths(ws, [8, 10, 12] + [9] * 17 + [9, 9, 90, 28, 50])
last_c = 4 + len(inp)

# ------------------------------------------------------------------ Quarterly
ws = wb.create_sheet("Quarterly")
header(ws, 1, ["code", "公司", "季度", "全国价", "公司售价", "完全成本", "育肥量(万头)", "每公斤毛利", "养殖利润(亿元)"])
qr = 2
for code, r in crow.items():
    for q in range(4):
        qc = get_column_letter(2 + q)
        ws.cell(row=qr, column=1, value=key(code))
        ws.cell(row=qr, column=2, value=f"=Company!B{r}")
        ws.cell(row=qr, column=3, value=q + 1)
        ws.cell(row=qr, column=4, value=f"=Paths!{qc}$29")
        ws.cell(row=qr, column=5, value=f"=IF(Company!$S${r}=1,D{qr}*(1+Paths!$E$19)+Paths!$E$20*Paths!$E$21,D{qr}*(1+Company!$M${r}))")
        ws.cell(row=qr, column=6, value=f'=IF(Company!$U${r}="","",Company!$U${r}+Paths!{qc}$31*(IF(ISNUMBER(Company!$I${r}),Company!$I${r},Company!$U${r})-Company!$U${r}))')
        ws.cell(row=qr, column=7, value=f"=Company!$T${r}*Company!{get_column_letter(15 + q)}${r}")
        ws.cell(row=qr, column=8, value=f'=IF(F{qr}="",0,E{qr}-F{qr})')
        ws.cell(row=qr, column=9, value=f'=IF(F{qr}="",0,G{qr}*10000*Company!$G${r}*H{qr}/100000000)')
        qr += 1
widths(ws, [8, 10, 6, 9, 9, 9, 11, 10, 12])
last_q = qr - 1

# ------------------------------------------------------------------ Summary
ws = wb.create_sheet("Summary")
header(ws, 3, ["code", "公司", "市值(亿元)", "量加权售价", "2027成本(选定)", "每公斤毛利(量加权)", "养殖利润(亿元)", "仔猪利润(亿元)",
               "归属比例", "情景归母利润(亿元)", "情景市盈率(倍)", "利润/市值", "成本门槛(市值=8倍利润)",
               "每1元/kg对应归母利润(亿元)", "占市值", "隐含全国价@10倍", "隐含全国价@15倍", "18元相对14元的超额利润(亿元)", "占市值"])
ws["A1"] = "="'"情景汇总：路径 "&Paths!C12&"，情景 "&CHOOSE(Paths!B13,"熊","基准","牛")'
srow = {}
for i, (code, r) in enumerate(crow.items()):
    s = 4 + i
    srow[code] = s
    rng = lambda col: f"Quarterly!${col}$2:${col}${last_q}"
    ws.cell(row=s, column=1, value=key(code))
    ws.cell(row=s, column=2, value=f"=Company!B{r}")
    ws.cell(row=s, column=3, value=f"=Company!C{r}")
    ws.cell(row=s, column=4, value=f'=SUMPRODUCT(({rng("A")}=A{s})*{rng("E")}*{rng("G")})/SUMIF({rng("A")},A{s},{rng("G")})')
    ws.cell(row=s, column=5, value=f"=Company!U{r}")
    ws.cell(row=s, column=6, value=f'=IF(E{s}="","",SUMPRODUCT(({rng("A")}=A{s})*{rng("H")}*{rng("G")})/SUMIF({rng("A")},A{s},{rng("G")}))')
    ws.cell(row=s, column=7, value=f'=IF(E{s}="","",SUMIF({rng("A")},A{s},{rng("I")}))')
    ws.cell(row=s, column=8, value=f"=Company!H{r}*10000*Paths!$E$16/100000000")
    ws.cell(row=s, column=9, value=f"=Company!N{r}")
    ws.cell(row=s, column=10, value=f'=IF(G{s}="","",(G{s}+H{s})*I{s})')
    ws.cell(row=s, column=11, value=f'=IF(J{s}="","",IF(J{s}>0,C{s}/J{s},"亏损"))')
    ws.cell(row=s, column=12, value=f'=IF(J{s}="","",J{s}/C{s})')
    ws.cell(row=s, column=13, value=f"=D{s}-(C{s}/Paths!$B$27/I{s}-H{s})*100000000/(Company!T{r}*10000*Company!G{r})")
    ws.cell(row=s, column=14, value=f"=Company!E{r}*10000*Company!G{r}/100000000*I{s}")
    ws.cell(row=s, column=15, value=f"=N{s}/C{s}")
    for k, col in ((25, 16), (26, 17)):
        need = f"(C{s}/Paths!$B${k}/I{s}-Company!H{r}*10000*Paths!$C$16/100000000)/(Company!E{r}*10000*Company!G{r}/100000000)"
        ws.cell(row=s, column=col, value=f'=IF(Company!K{r}="","",IF(Company!S{r}=1,(Company!K{r}+{need}-Paths!$C$20*Paths!$C$21)/(1+Paths!$C$19),(Company!K{r}+{need})/(1+Company!M{r})))')
    ws.cell(row=s, column=18, value=f'=N{s}*(18-Paths!$B$24)*(1+IF(Company!S{r}=1,Paths!$C$19,Company!M{r}))')
    ws.cell(row=s, column=19, value=f"=R{s}/C{s}")
widths(ws, [8, 10] + [11] * 17)

# ------------------------------------------------------------------ Dongrui
ws = wb.create_sheet("Dongrui")
ws["A1"] = "东瑞股份：售价拆分与“价格优势是否大于成本差距”检验"; ws["A1"].font = HEAD
ws["A3"] = "一、出口重量占比估算（配额≠销量）"
rows = [("2026年供港配额（头，截至9-29）", 214484, "事实"), ("供澳配额（头）", 879, "事实"),
        ("配额外供货出口（头，参照2024年出口26.23万−配额完成22.07万）", 41600, "推断"),
        ("2027年育肥出栏（万头）", "=Company!E%d" % crow["001201"], "假设"),
        ("出口猪均重/内销猪均重之比", 0.95, "假设"),
        ("出口重量占比s（若配额与2026持平）", "=(B4+B5+B6)*B8/(B7*10000)", "推算")]
for i, (a, b, lab) in enumerate(rows):
    ws.cell(row=4 + i, column=1, value=a); c = ws.cell(row=4 + i, column=2, value=b); ws.cell(row=4 + i, column=3, value=lab)
    c.fill = INPUT if lab in ("假设", "推断") else FACT
ws["A11"] = "二、2027年售价矩阵（全国价×内销溢价+出口占比×出口价差），元/公斤"
header(ws, 12, ["全国均价", "熊(d1%,s12%,e1.1)", "基准(d3%,s16%,e2.5)", "牛(d8%,s22%,e4.0)", "牧原同期售价(区域溢价%s)" % round(inp.set_index("code").loc["002714", "regional_premium"], 3)])
for i, p in enumerate([12, 14, 16, 18, 20, 22]):
    r = 13 + i
    ws.cell(row=r, column=1, value=p)
    for j, col in enumerate(["B", "C", "D"]):
        ws.cell(row=r, column=2 + j, value=f"=A{r}*(1+Paths!{col}$19)+Paths!{col}$20*Paths!{col}$21")
    ws.cell(row=r, column=5, value=f"=A{r}*(1+Company!M{crow['002714']})")
ws["A20"] = "三、18元下：东瑞相对牧原的价格优势 vs 成本差距（元/公斤）"
header(ws, 21, ["情景", "东瑞售价", "牧原售价", "价格优势", "东瑞成本", "牧原成本", "成本差距", "优势−差距（>0才说明价格优势覆盖成本劣势）"])
dr, mr = crow["001201"], crow["002714"]
for i, (nm, col, ccol) in enumerate([("熊", "B", "J"), ("基准", "C", "K"), ("牛", "D", "L")]):
    r = 22 + i
    ws.cell(row=r, column=1, value=nm)
    ws.cell(row=r, column=2, value=f"=18*(1+Paths!{col}$19)+Paths!{col}$20*Paths!{col}$21")
    ws.cell(row=r, column=3, value=f"=18*(1+Company!M{mr})")
    ws.cell(row=r, column=4, value=f"=B{r}-C{r}")
    ws.cell(row=r, column=5, value=f"=Company!{ccol}{dr}")
    ws.cell(row=r, column=6, value=f"=Company!{ccol}{mr}")
    ws.cell(row=r, column=7, value=f"=E{r}-F{r}")
    ws.cell(row=r, column=8, value=f"=D{r}-G{r}")
ws["A26"] = "四、历史：东瑞与牧原的售价差与成本差（事实/推算，元/公斤）"
header(ws, 27, ["年份", "东瑞商品猪均价", "牧原商品猪均价", "价格优势", "东瑞完全成本", "牧原完全成本（约）", "成本差距", "优势−差距", "出口重量占比", "来源/说明"])
hist = [(2022, 23.68, 18.16, 18.1, 15.7, 0.60, "东瑞售价=招股/问询回复表；成本2021末18.6、2022Q1 17.8、Q3 18.4取约18.1。牧原成本：2023-05-17业绩说明会“2022全年平均商品猪完全成本15.7元/kg左右”"),
        (2023, 17.13, 14.42, 17.8, 15.0, 0.50, "东瑞2023完全成本17.8（正常场口径，2024-03-01纪要）；牧原2024-05-17业绩说明会“2023年…15.0元/kg左右”"),
        (2024, 18.16, 16.45, 16.67, 14.0, 0.48, "东瑞16.67（2025-01-20纪要）；牧原2025-03-20“全年平均成本在14元/kg左右”"),
        (2025, 14.66, 13.48, 14.6, 12.0, 0.286, "东瑞H1 15.0、9月14.4、12月13.93，全年取约14.6（推算）；牧原2026-03-28“全年平均成本降至12元/kg左右”"),
        ("2026H1", 11.41, 10.48, 13.95, 11.7, 0.19, "东瑞H1售价11.41（2026-08-28纪要）、成本13.95（2026-07-14纪要）；牧原1-2月约12、3月11.6、7月11.5，H1取约11.7（推算）")]
for i, h in enumerate(hist):
    r = 28 + i
    ws.cell(row=r, column=1, value=h[0]); ws.cell(row=r, column=2, value=h[1]); ws.cell(row=r, column=3, value=h[2])
    ws.cell(row=r, column=4, value=f"=B{r}-C{r}")
    ws.cell(row=r, column=5, value=h[3]); ws.cell(row=r, column=6, value=h[4])
    ws.cell(row=r, column=7, value=f"=E{r}-F{r}"); ws.cell(row=r, column=8, value=f"=D{r}-G{r}")
    ws.cell(row=r, column=9, value=h[5]); ws.cell(row=r, column=10, value=h[6])
widths(ws, [52, 16, 16, 16, 14, 16, 12, 30, 12, 60])

# ------------------------------------------------------------------ Decomposition
ws = wb.create_sheet("Decomposition")
ws["A1"] = "2026年当前状态→2027年18元基准：利润变化的中点拆分（Δ(V·m)=ΔV·m̄+V̄·Δm）"; ws["A1"].font = HEAD
ws["A2"] = "2026状态：最近年化育肥量、2026年7-9月新牧网全国均价、最新披露成本；2027：全国18元、基准育肥量与成本。融资影响见利息/公斤列（集团口径，饲料型公司偏高）。"
cols = ["code", "公司", "V2026", "V2027", "全国价2026", "全国价2027", "区域溢价r或东瑞d", "渠道溢价s×e", "成本2026", "成本2027", "出栏重",
        "毛利2026(元/kg)", "毛利2027", "养殖利润2026(亿)", "养殖利润2027(亿)", "量贡献", "全国价贡献", "区域溢价贡献", "渠道溢价贡献", "成本贡献", "合计校验", "利息/公斤(2026H1年化)"]
header(ws, 4, cols)
for i, (_, d) in enumerate(dec.iterrows()):
    r = 5 + i
    is_dr = d["code"] == "001201"
    vals = [key(d["code"]), d["name"], round(d["V_2026"], 2), d["V_2027"], round(M.NAT_NOW, 4), 18.0,
            M.DONGRUI["base"]["d"] if is_dr else round(inp.set_index("code").loc[d["code"], "regional_premium"], 4),
            M.DONGRUI["base"]["s"] * M.DONGRUI["base"]["e"] if is_dr else 0.0, d["cost_2026"], d["cost_2027"],
            float(inp.set_index("code").loc[d["code"], "W"])]
    for j, v in enumerate(vals, 1):
        ws.cell(row=r, column=j, value=v)
    ws.cell(row=r, column=12, value=f"=E{r}*(1+G{r})+H{r}-I{r}")
    ws.cell(row=r, column=13, value=f"=F{r}*(1+G{r})+H{r}-J{r}")
    k = f"10000*K{r}/100000000"
    ws.cell(row=r, column=14, value=f"=C{r}*L{r}*{k}")
    ws.cell(row=r, column=15, value=f"=D{r}*M{r}*{k}")
    ws.cell(row=r, column=16, value=f"=(D{r}-C{r})*(L{r}+M{r})/2*{k}")
    ws.cell(row=r, column=17, value=f"=(C{r}+D{r})/2*(F{r}-E{r})*{k}")
    ws.cell(row=r, column=18, value=f"=(C{r}+D{r})/2*(F{r}-E{r})*G{r}*{k}")
    ws.cell(row=r, column=19, value=0)
    ws.cell(row=r, column=20, value=f"=(C{r}+D{r})/2*(I{r}-J{r})*{k}")
    ws.cell(row=r, column=21, value=f"=SUM(P{r}:T{r})-(O{r}-N{r})")
    ws.cell(row=r, column=22, value=None if pd.isna(d["interest_per_kg"]) else round(d["interest_per_kg"], 3))
widths(ws, [8, 10] + [10] * 20)

# ------------------------------------------------------------------ Screening (snapshot values + formulas)
ws = wb.create_sheet("Screening")
ws["A1"] = "筛选快照（市值2026-10-08；资产负债2026-06-30；能繁/成本日期见列）"; ws["A1"].font = HEAD
cols = ["code", "公司", "池", "市值(亿)", "有息负债(亿)", "现金(亿)", "EV(亿)", "资产负债率", "现金/短债", "H1经营现金流(亿)", "H1资本开支(亿)", "H1归母净利(亿)",
        "能繁(万头)", "能繁日期", "2027育肥基准(万头)", "市值/能繁(万元/头)", "EV/能繁(万元/头)", "市值/2027育肥(元/头)", "EV/2027育肥(元/头)",
        "最新售价", "售价月份", "同月全国均价", "售价溢价", "最新成本", "成本日期", "成本口径", "可转债余额(亿)", "转股价", "风险标记"]
header(ws, 3, cols)
for i, (_, x) in enumerate(sc.iterrows()):
    r = 4 + i
    vb = f"=Company!E{crow[x['code']]}" if x["code"] in crow else None
    vals = [key(x["code"]), x["name"], x["pool"], round(x["mcap_yi"], 2), round(x["ib_debt_yi"], 2), round(x["cash_yi"], 2), f"=D{r}+E{r}-F{r}",
            round(x["debt_ratio"], 4), round(x["cash_to_st_debt"], 3), round(x["ocf_h1_yi"], 2), round(x["capex_h1_yi"], 2), round(x["np_h1_yi"], 2),
            None if pd.isna(x["sows_wan"]) else x["sows_wan"], x["sows_date"] if pd.notna(x["sows_date"]) else None, vb,
            f'=IF(M{r}="","",D{r}*10000/M{r}/10000)', f'=IF(M{r}="","",G{r}*10000/M{r}/10000)',
            f'=IF(O{r}="","",D{r}*100000000/(O{r}*10000))', f'=IF(O{r}="","",G{r}*100000000/(O{r}*10000))',
            None if pd.isna(x["last_price"]) else x["last_price"], x["price_month"] if pd.notna(x["price_month"]) else None,
            None if pd.isna(x["national_avg_same_month"]) else round(x["national_avg_same_month"], 3),
            f'=IF(OR(T{r}="",V{r}=""),"",T{r}/V{r}-1)',
            None if pd.isna(x["cost_latest_kg"]) else x["cost_latest_kg"], x["cost_date"] if pd.notna(x["cost_date"]) else None,
            x["cost_def"] if pd.notna(x["cost_def"]) else None,
            None if pd.isna(x["cb_outstanding_yi"]) else x["cb_outstanding_yi"], None if pd.isna(x["cb_conv_price"]) else x["cb_conv_price"],
            x["flags"] if pd.notna(x["flags"]) else None]
    for j, v in enumerate(vals, 1):
        ws.cell(row=r, column=j, value=v)
widths(ws, [8, 10, 12] + [10] * 22 + [40, 10, 10, 60])

# ------------------------------------------------------------------ Sensitivity
ws = wb.create_sheet("Sensitivity")
ws["A1"] = "情景归母利润敏感性（亿元）：全年全国均价 × 2027完全成本（基准育肥量、基准仔猪毛利；东瑞用基准d/s/e）"; ws["A1"].font = HEAD
r0 = 3
for code in ["002714", "300498", "001201", "603477", "002567", "002100"]:
    cr = crow[code]
    ws.cell(row=r0, column=1, value=f"=Company!B{cr}").font = HEAD
    ws.cell(row=r0, column=2, value="成本→")
    costs = [round(float(inp.set_index("code").loc[code, "C_base"]) + d, 2) for d in (-1.0, -0.5, 0, 0.5, 1.0)]
    for j, cst in enumerate(costs):
        ws.cell(row=r0, column=3 + j, value=cst)
    for i, p in enumerate([12, 14, 16, 18, 20, 22]):
        rr = r0 + 1 + i
        ws.cell(row=rr, column=2, value=p)
        for j in range(5):
            cc = f"{get_column_letter(3 + j)}${r0}"
            px = f"($B{rr}*(1+Paths!$C$19)+Paths!$C$20*Paths!$C$21)" if code == "001201" else f"($B{rr}*(1+Company!$M${cr}))"
            ws.cell(row=rr, column=3 + j, value=f"=(({px}-{cc})*Company!$E${cr}*10000*Company!$G${cr}/100000000+Company!$H${cr}*10000*Paths!$C$16/100000000)*Company!$N${cr}")
    ws.cell(row=r0 + 7, column=2, value="当前市值")
    ws.cell(row=r0 + 7, column=3, value=f"=Company!C{cr}")
    r0 += 10
widths(ws, [12, 10, 10, 10, 10, 10, 10])

# ------------------------------------------------------------------ Hist_PE
ws = wb.create_sheet("Hist_PE")
ws["A1"] = "历史校准：市值峰值 / 峰值年度归母净利润（窗口：非瘟2018-07~2021-12；2022轮2022-01~2023-06；2024轮2024-01~2025-06）"; ws["A1"].font = HEAD
header(ws, 3, list(hpe.columns))
for i, row in enumerate(hpe.itertuples(index=False)):
    for j, v in enumerate(row, 1):
        ws.cell(row=4 + i, column=j, value=None if (isinstance(v, float) and np.isnan(v)) else v)
widths(ws, [8, 8, 12, 10, 12, 14, 10, 10, 10, 10, 10])

# ------------------------------------------------------------------ QA (python reference values)
ws = wb.create_sheet("QA")
ws["A1"] = "Python参考值（路径P1、情景基准），用于核对公式结果"; ws["A1"].font = HEAD
res = pd.read_csv(PROC / "model_results.csv", dtype={"code": str})
ref = res[(res["path"] == "P1 全年持平") & (res["case"] == "base")]
header(ws, 3, ["code", "公司", "Python归母利润", "Excel归母利润", "差异", "Python成本门槛", "Excel成本门槛"])
for i, (_, x) in enumerate(ref.iterrows()):
    r = 4 + i
    s = srow[x["code"]]
    ws.cell(row=r, column=1, value=key(x["code"])); ws.cell(row=r, column=2, value=x["name"])
    ws.cell(row=r, column=3, value=None if pd.isna(x["parent_earnings_yi"]) else round(x["parent_earnings_yi"], 4))
    ws.cell(row=r, column=4, value=f"=Summary!J{s}")
    ws.cell(row=r, column=5, value=f'=IF(OR(C{r}="",D{r}=""),"",D{r}-C{r})')
    ws.cell(row=r, column=6, value=round(x["cost_hurdle_8x"], 4))
    ws.cell(row=r, column=7, value=f"=Summary!M{s}")

wb.save(OUT)
print("saved", OUT)
