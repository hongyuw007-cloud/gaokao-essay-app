"""Build the README-based experiment report DOCX with verified screenshots."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "高考满分作文智能应用_实验报告.docx"
BLACK = RGBColor(0, 0, 0)
DARK = "263238"
LIGHT_BLUE = "EAF2F8"
WHITE = "FFFFFF"
BORDER = "D9D9D9"


def set_cell_shading(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), color)


def set_cell_border(cell, color: str = BORDER, size: str = "6") -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.first_child_found_in("w:tcBorders")
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = f"w:{edge}"
        element = borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), size)
        element.set(qn("w:color"), color)


def set_cell_text(cell, text: str, *, bold: bool = False, color: str = "000000") -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_border(cell)


def mark_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    header = tr_pr.find(qn("w:tblHeader"))
    if header is None:
        header = OxmlElement("w:tblHeader")
        tr_pr.append(header)
    header.set(qn("w:val"), "true")


def add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, end])
    run.font.name = "Arial"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(90, 90, 90)


def add_caption(doc: Document, text: str) -> None:
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(8)
    paragraph.paragraph_format.space_after = Pt(12)
    run = paragraph.add_run(text)
    run.font.name = "Microsoft YaHei"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(80, 80, 80)


def set_image_alt(inline_shape, description: str) -> None:
    doc_pr = inline_shape._inline.docPr
    doc_pr.set("descr", description)
    doc_pr.set("title", description)


def add_screenshot(doc: Document, filename: str, caption: str, *, page_break: bool) -> None:
    if page_break:
        doc.add_page_break()
    paragraph = doc.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(0)
    shape = paragraph.add_run().add_picture(
        str(ROOT / "screenshots" / filename),
        width=Inches(6.35),
    )
    set_image_alt(shape, caption)
    add_caption(doc, caption)


def style_document(doc: Document) -> None:
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.orientation = WD_ORIENT.PORTRAIT
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.85)
    section.right_margin = Inches(0.85)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.45
    normal.paragraph_format.space_after = Pt(7)

    title = styles["Title"]
    title.font.name = "Microsoft YaHei"
    title._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    title.font.size = Pt(26)
    title.font.bold = True
    title.font.color.rgb = BLACK
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(10)

    for style_name, size, before, after in (
        ("Heading 1", 17, 18, 8),
        ("Heading 2", 13, 13, 6),
    ):
        style = styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = BLACK
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    footer = section.footer
    add_page_number(footer.paragraphs[0])


def add_heading(doc: Document, text: str, level: int = 1) -> None:
    paragraph = doc.add_paragraph(style=f"Heading {level}")
    run = paragraph.add_run(text)
    run.font.color.rgb = BLACK


def add_body(doc: Document, text: str, *, bold_lead: str | None = None) -> None:
    paragraph = doc.add_paragraph()
    if bold_lead and text.startswith(bold_lead):
        lead = paragraph.add_run(bold_lead)
        lead.bold = True
        paragraph.add_run(text[len(bold_lead) :])
    else:
        paragraph.add_run(text)
    paragraph.paragraph_format.first_line_indent = Inches(0.22)


def build_report() -> None:
    doc = Document()
    style_document(doc)

    doc.add_paragraph("高考满分作文智能应用实验报告", style="Title")
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT
    subtitle_run = subtitle.add_run("生成式人工智能课程实验1")
    subtitle_run.font.name = "Microsoft YaHei"
    subtitle_run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    subtitle_run.font.size = Pt(13)
    subtitle_run.font.color.rgb = RGBColor(70, 70, 70)
    subtitle.paragraph_format.space_after = Pt(18)

    metadata = [
        ("学生姓名", "王红玉"),
        ("班级", "网安242"),
        ("学号", "202301090163"),
        ("在线系统", "https://gaokao-essay-app.vercel.app"),
        ("GitHub 仓库", "https://github.com/hongyuw007-cloud/gaokao-essay-app"),
    ]
    table = doc.add_table(rows=len(metadata), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(1.35)
    table.columns[1].width = Inches(5.25)
    for row_idx, (label, value) in enumerate(metadata):
        row = table.rows[row_idx]
        for cell in row.cells:
            set_cell_border(cell)
        set_cell_text(row.cells[0], label, bold=True, color=WHITE)
        set_cell_shading(row.cells[0], DARK)
        set_cell_text(row.cells[1], value)
        set_cell_shading(row.cells[1], WHITE if row_idx % 2 == 0 else LIGHT_BLUE)
    mark_table_header(table.rows[0])

    intro = doc.add_paragraph()
    intro.paragraph_format.space_before = Pt(14)
    intro.add_run(
        "本报告说明高考满分作文智能应用的实现内容、运行方式与测试结果。"
        "系统采用提示工程控制 DeepSeek 生成约 800 字的高考作文，"
        "并通过 Supabase 实现多用户注册登录、数据隔离和作品管理。"
    )

    add_heading(doc, "1 项目概述")
    add_body(
        doc,
        "系统面向高考作文写作场景。用户登录后输入作文题目，后端调用 DeepSeek "
        "生成范文，并把作文自动保存到当前用户的历史记录。项目分析高考满分作文样例，"
        "归纳标题、开头、主体、结尾和立意方面的共性，再将这些规律写入系统提示词。",
    )

    add_heading(doc, "2 主要功能")
    functions = [
        "邮箱注册、登录、刷新登录状态和退出登录。",
        "每位用户独立保存、搜索、查看自己的作文，不同用户的数据相互隔离。",
        "编辑个人资料，并在首页显示姓名、班级和学号。",
        "收藏或取消收藏作文，复制和删除自己的作文。",
        "根据高考作文题目调用 DeepSeek 生成约 800 字范文并自动保存。",
        "提供响应式 Web 界面以及 Vercel Serverless 部署入口。",
    ]
    for item in functions:
        paragraph = doc.add_paragraph(item, style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(3)

    add_heading(doc, "3 技术架构")
    architecture = [
        ("前端", "原生 HTML、CSS、JavaScript；登录、作文生成、历史与个人资料界面"),
        ("后端", "FastAPI；提供认证、资料、作文生成和作品管理接口"),
        ("大模型", "DeepSeek deepseek-chat；使用 OpenAI SDK 调用"),
        ("数据与认证", "Supabase Auth 与 PostgreSQL/PostgREST；RLS 实现用户数据隔离"),
        ("部署", "Vercel 生产部署；Supabase 承担云端身份认证与数据库"),
    ]
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.columns[0].width = Inches(1.35)
    table.columns[1].width = Inches(5.25)
    for index, text in enumerate(("模块", "实现")):
        set_cell_text(table.rows[0].cells[index], text, bold=True, color=WHITE)
        set_cell_shading(table.rows[0].cells[index], DARK)
    mark_table_header(table.rows[0])
    for row_idx, (label, value) in enumerate(architecture, start=1):
        row = table.add_row()
        set_cell_text(row.cells[0], label, bold=True)
        set_cell_text(row.cells[1], value)
        fill = WHITE if row_idx % 2 else LIGHT_BLUE
        set_cell_shading(row.cells[0], fill)
        set_cell_shading(row.cells[1], fill)

    add_heading(doc, "4 使用与部署")
    add_body(
        doc,
        "本地运行时，先安装 requirements.txt 中的依赖，配置 DeepSeek 与 Supabase "
        "环境变量，再执行 uvicorn backend.main:app --reload --port 8001。"
        "线上版本由 Vercel 从 frontend 目录提供静态页面，并通过 FastAPI 入口处理 API 请求。"
        "Supabase 中的 essays 表启用了行级安全策略，用户只能访问自己的记录。",
    )
    add_body(
        doc,
        "Vercel 生产环境已配置 DEEPSEEK_API_KEY、SUPABASE_URL、SUPABASE_ANON_KEY "
        "等服务端变量。浏览器只持有 Supabase 登录后的短期访问凭证，不包含模型密钥。",
    )

    add_heading(doc, "5 功能运行截图")
    add_screenshot(doc, "login.png", "图1 登录与注册页面", page_break=False)
    add_body(
        doc,
        "登录页提供登录与注册两个入口。注册时需要填写姓名、班级、学号和邮箱，"
        "登录成功后才能使用作文生成和个人作品管理功能。",
    )
    add_screenshot(doc, "home.png", "图2 登录后的系统首页与个人信息", page_break=True)
    add_body(
        doc,
        "首页顶部固定显示学生姓名、班级和学号。登录区域展示当前账号资料，"
        "左侧保留个人作文列表，右侧用于输入题目并生成作文。",
    )
    add_screenshot(doc, "result.png", "图3 作文生成与自动保存结果", page_break=True)
    add_body(
        doc,
        "输入“论坚持与成长”后，系统调用 DeepSeek 生成作文并自动保存。"
        "结果区域展示标题、题目、字数、生成时间和全文，并提供收藏、复制与删除操作。",
    )
    add_screenshot(doc, "history.png", "图4 个人作文历史与收藏管理", page_break=True)
    add_body(
        doc,
        "历史区域支持按题目或标题搜索。每篇作文均有收藏入口，点击记录可以重新查看全文，"
        "删除操作仅影响当前用户自己的记录。",
    )

    add_heading(doc, "6 核心提示词")
    add_body(
        doc,
        "SYSTEM_PROMPT 将模型设定为具有三十年教学经验的高考语文特级教师和阅卷组组长。"
        "提示词要求内容切题深刻、结构完整、语言有文采、正文约 800 字，"
        "并约定由审题立意和谋篇布局进入最终成文。",
    )
    add_body(
        doc,
        "输出要求限定标题、开头、主体和结尾的组织方式；主体包含两到三个递进或并列分论点，"
        "事例必须服务论点，结尾需要回扣标题与中心思想。模型只输出最终作文，不展示内部构思过程。",
    )

    doc.add_page_break()
    add_heading(doc, "7 数据安全与验证")
    add_body(
        doc,
        "DeepSeek 和 Supabase 配置保存在服务端环境变量中。Supabase essays 表启用 RLS，"
        "并配置查询、插入、更新、删除四类用户隔离策略。浏览器端输出使用纯文本渲染，"
        "避免模型返回内容被当作 HTML 执行。",
    )
    add_body(
        doc,
        "部署完成后已执行真实端到端验证：临时用户登录成功，DeepSeek 生成作文并保存，"
        "历史查询、收藏和删除均正常；测试用户及其数据随后被清理。最新生产版本的首页、"
        "健康检查和配置接口均返回 HTTP 200，错误级运行日志为空。",
    )

    add_heading(doc, "8 项目提交信息")
    add_body(
        doc,
        "代码保存在私有 GitHub 仓库中。教师通过仓库协作者邀请访问源码、"
        "运行截图和本说明；在线应用无需 GitHub 账号即可访问。",
    )

    properties = doc.core_properties
    properties.title = "高考满分作文智能应用实验报告"
    properties.subject = "生成式人工智能课程实验1"
    properties.author = "王红玉"
    properties.comments = "README 转换文档"

    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build_report()
