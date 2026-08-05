"""

pan-os-cli v2.5 [20260622]
pan-os-cli v2.4 [20260619]
pan-os-cli v2.3 [20260617]
pan-os-cli v2.2 [20260607]
pan-os_cli v2.1 [20260515]
pan-os_cli v2.0 [20250420]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli
https://pexpect.readthedocs.io/en/stable/index.html

"""

import json
import os
import re
import statistics
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymupdf
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm, Inches, Pt

from conf.cf_report import cf


ctx = {}

def init():
    ctx['verbose'] = cf['verbose']
    ctx['debug'] = cf['debug']

    ctx['prs'] = Presentation(cf['template'])
    # ctx['last_slide'] = ctx['prs'].slides[-1]
    ctx['last_sldId'] = ctx['prs'].slides._sldIdLst[cf['sldId']['last']]
    ctx['cases'] = {}
    ctx['results'] = []

    ctx['ctx_file'] = Path(cf['report_dir']) / cf['ctx_file']

    top_dir = Path(cf['poc_dir'])

    subdirs = sorted(
        (p for p in top_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name.lower()
    )

    for prefixes in ('case_prefixes', 'other_prefixes'):
        folders = []
        for prefix in cf[prefixes]:
            prefix = prefix.casefold()
            folders.extend(
                d for d in subdirs
                if d.name.casefold().startswith(prefix)
            )
        folders_key = 'folders_' + prefixes.split('_')[0]
        ctx[folders_key] = folders
        if cf['verbose']:
            for folder in folders:
                print(folder.name)
            print()


def cleanup():
    ctx['prs'].save(Path(cf['report_dir']) / cf['report_file'])

    file = str(ctx['ctx_file'])
    for key, val in ctx.items():
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, set):
                    val[k] = list(v)
        elif isinstance(val, list):
            ctx[key] = [v.isoformat() if isinstance(v, datetime) else v for v in val]
        # elif isinstance(val, set): ctx[key] = list(val)
        elif isinstance(val, datetime):
            ctx[key] = val.isoformat()
    with open(file, "w", encoding="utf-8") as f:
        json.dump(ctx, f, indent=2,
            skipkeys=True,
            default=str,  # lambda o: '<not serializable>',
        )


def results_to_dataframe(results):
    df = pd.DataFrame(results)

    cols = [c for c in cf['result_columns'].keys() if c in df.columns]

    df = (
        df.reindex(columns=cols)
        .sort_values(by=["case", "job"])
        .reset_index(drop=True)
    )

    df['flow_ctrl'] = df['flow_ctrl'].map(lambda x: f"{x:.0f}%")
    df['throughput'] = df['throughput'].map(lambda x: "" if x == "" else f"{x / 1000:,.1f}")
    df['flow_rate'] = df['flow_rate'].map(lambda x: "" if x == "" else f"{float(x):,.0f}")
    for col in ('connectionRate', 'allocatedSessions', 'packetRate', 'supportedSessions'):
        df[col] = df[col].map(lambda x: f"{x:,.0f}")

    df = df.rename(columns=cf['result_columns'])

    print("\n", df.to_string(index=False))

    return df


def slide_cover():
    slide = ctx['prs'].slides[0]
    slide.placeholders[0].text = "\n".join([cf['cust_name'], cf['subject']])
    slide.placeholders[1].text = cf['poc_number']
    slide.placeholders[2].text = cf['author']


def slide_add_bullets(text_frame, items):
    text_frame.clear()

    first = True

    def walk(items, level):
        nonlocal first

        for item in items:
            if isinstance(item, str):
                if first:
                    p = text_frame.paragraphs[0]
                    first = False
                else:
                    p = text_frame.add_paragraph()

                p.text = item
                p.level = level

            elif isinstance(item, list):
                walk(item, level + 1)

    walk(items, 0)


def slide_add_image(slide, placeholder, image_path, scale=1.1):
    left = placeholder.left
    top = placeholder.top
    box_w = placeholder.width
    box_h = placeholder.height + Cm(1.5)

    if ctx['debug']:
        print(f"slide_add_image: left {left}, top {top}, box_w {box_w}, box_h {box_h}")

    with Image.open(image_path) as img:
        img_w, img_h = img.size

    native_w = Inches(img_w / 96) * scale
    native_h = Inches(img_h / 96) * scale

    ratio = min(
        1.0,
        box_w / native_w,
        box_h / native_h,
    )

    new_w = int(native_w * ratio)
    new_h = int(native_h * ratio)

    left += int((box_w - new_w) / 2)  # center image
    top += int((box_h - new_h) / 2)

    element = placeholder._element
    element.getparent().remove(element)  # remove placeholder

    if ctx['debug']:
        print(f"slide_add_image: img_w {img_w}, img_h {img_h}")
        print(f"slide_add_image: image_path {str(image_path)}")
        print(f"slide_add_image: left {left}, top {top}, new_w {new_w}, new_h {new_h}\n")

    slide.shapes.add_picture(
        image_path,
        left,
        top,
        width=new_w,
        height=new_h
    )


def slide_add_table(slide, placeholder, table_size=(2, 2)):
    left = placeholder.left
    top = placeholder.top
    width = placeholder.width
    height = placeholder.height + Cm(1.5)

    if ctx['verbose']:
        print(f"slide_add_table: left {left}, top {top}, box_w {width}, box_h {height}")

    rows, cols = table_size

    table = slide.shapes.add_table(
        rows, cols,
        left, top,
        width, height
    ).table

    table.columns[0].width = Cm(5)
    table.columns[1].width = Cm(10)

    headers = [
        "Test Case ID",
        "Description",
        "Purpose",
        "Objective",
        "Comments",
        "Metrics",
        "Result",
    ]

    data = [
        ("",), ("",), ("",), ("",), ("",),
        ("",), ("",),
    ]

    for r, text in enumerate(headers):
        table.cell(r, 0).text = text

    for r, row in enumerate(data):
        for c, value in enumerate(row, start=1):
            table.cell(r, c).text = str(value)


def slide_fill_table(slide, df, header=True):
    table = None
    for shape in slide.shapes:
        if shape.has_table:
            table = shape.table
            break

    if table is None:
        return

    max_cols = min(len(df.columns), len(table.columns))
    max_rows = min(len(df), len(table.rows) - 1)

    if header:
        for c in range(max_cols):
            table.cell(0, c).text = str(df.columns[c])

    for r in range(max_rows):
        for c in range(max_cols):
            cell = table.cell(r + 1, c)
            cell.text = str(df.iat[r, c])

    for r in range(len(table.rows)):
        for c in range(len(table.columns)):
            cell = table.cell(r, c)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER
                for run in p.runs:
                    run.font.name = "Montserrat"
                    run.font.size = Pt(8)
                    if r == 0:
                        run.font.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)


def slide_add_with_images(idx, path, images_list, title=""):
    if images_list is None:
        return
    for images in images_list:
        if ctx['verbose']:
            print(f"slide_add_with_images: images {images}")
        for image_path in sorted(path.glob(images)):
            slide_add(idx, title=f"{title.format(image_path.stem)}", image=str(image_path))


def slide_add(idx=1, title="", text=None, image=None, table=None):
    layout = ctx['prs'].slides[idx].slide_layout
    slide = ctx['prs'].slides.add_slide(layout)
    content = None
    for shape in slide.placeholders:
        if shape.placeholder_format.type == PP_PLACEHOLDER.TITLE:
            shape.text = title
        elif shape.placeholder_format.type == PP_PLACEHOLDER.BODY:
            content = shape
            break
    if content is None:
        return slide
    if text is not None:
        content.text = text
    elif image is not None:
        slide_add_image(slide, content, image)
    elif table is not None:
        slide_add_table(slide, content, table_size=table)
    return slide


def slide_clone(idx=1, title=""):
    source = ctx['prs'].slides[idx]
    slide = ctx['prs'].slides.add_slide(source.slide_layout)

    for shape in list(slide.shapes):
        shape.element.getparent().remove(shape.element)

    for shape in source.shapes:
        element = deepcopy(shape.element)
        slide.shapes._spTree.insert_element_before(
            element, 'p:extLst'
        )

    for shape in slide.placeholders:
        if shape.placeholder_format.type == PP_PLACEHOLDER.TITLE:
            shape.text = title
            break

    return slide


def pdf_page_get_images(doc, page, file_prefix="pdf-{}.png"):
    images = page.get_images(full=True)

    if not images:
        return []  # images is actually empty

    mask_xrefs = {image[1] for image in images if image[1] != 0}

    image_paths = []

    for i, image in enumerate(images):
        xref = image[0]

        if xref in mask_xrefs:
            continue

        pix = pymupdf.Pixmap(doc, xref)

        if cf['debug']:
            print(f"xref       : {xref}")
            print(f"smask      : {image[1]}")
            print(f"size       : {image[2]} x {image[3]}")
            print(f"bpc        : {image[4]}")
            print(f"colorspace : {image[5]}")
            print(f"filter     : {image[8]}")
            rects = page.get_image_rects(xref)
            for r in rects:
                print(f"image rect : {r}")
            print(f"pixmap     : {pix.width} x {pix.height}")
            print(f"channels   : {pix.n}")
            print(f"alpha      : {pix.alpha}")

        image_path = os.path.join(
            cf['report_dir'],
            f"{file_prefix.format(i)}.png"
        )

        try:
            pix.save(image_path)
            print(f"pdf_page_get_images: image #{i} saved as '{image_path}'")
            image_paths.append(image_path)
        except Exception as e:
            print(f"pdf_page_get_images: image not saved: {e}")
            
    return image_paths


def pdf_page_find_line(page, text="", regex=None):
    blocks = page.get_text("dict")["blocks"]

    for block in blocks:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if cf['debug'] and line_text:
                print(
                    f"{line['bbox'][1]:6.1f}  "
                    f"{line['spans'][0]['size']:4.1f}  "
                    f"{line_text}"
                )
            if text and text in line_text:
                return line
            if regex is not None and regex.match(line_text):
                return line

    return None


def pdf_find_section(doc, section):
    toc = doc.get_toc()

    for level, text, page in toc:
        if section.lower() in text.lower():
            return page - 1      # PyMuPDF pages are 0-based

    return -1  # not found which may cause errors


def pdf_read(pdf):
    doc = pymupdf.open(pdf)

    section_re = re.compile(cf['bp_section_re'])

    data = {}

    for sect_key, section in cf['bp_sections'].items():
        page_num = pdf_find_section(doc, section)
        page = doc[page_num]

        data[section] = {}

        print(f"\n===== Section {section} @ Page {page_num + 1} =====")
        line = pdf_page_find_line(page, text=section)
        if line is not None:
            print(f"pdf_read: line_text '{line['spans'][0]['text']}'")

        file_prefix = f"{pdf.stem}-{page_num}-{{}}"
        image_paths = pdf_page_get_images(doc, page, file_prefix)
        data[section]['image_paths']= image_paths

        tables = page.find_tables()
        print(f"pdf_read: section '{section}' contains {len(tables.tables)} table(s)")

        if sect_key == 'super_flow_data_throughput':
            rows = []
            end_of_section = False
            while page_num < len(doc):
                for table in tables.tables:
                    rows.extend(table.extract())
                page_num += 1
                page = doc[page_num]

                line = pdf_page_find_line(page, regex=section_re)
                if line is not None:
                    end_of_section = True
                    print(f"pdf_read: end_of_section: text '{line['spans'][0]['text']}'")
                if end_of_section:
                    break

                tables = page.find_tables()
            data[section]['values'] = table_rows_summary(rows)
        elif sect_key in ("test_parameters", "test_device"):
            heading_bottom = line['bbox'][3]
            target = None
            for table in tables.tables:
                if table.bbox[1] > heading_bottom:
                    target = table
                    break
            if target is not None:
                table = target.extract()
                if sect_key == "test_parameters":
                    data[section]['params'] = {row[0]: row[-1] for row in table[1:]}
                elif sect_key == "test_device":
                    data[section]['bp_version'] = table[1][1]
                    print(f"pdf_read: bp_version {data[section]['bp_version']}")

    if ctx['verbose']:
        print("pdf_read: data:", data)

    return data


def table_rows_summary(rows):
    if ctx['verbose']:
        print(f"table_rows_summary: '{len(rows)}' rows")

    if ctx['debug']:
        for row in rows:
            print("\t", row)

    values = []
    for row in rows:
        value = row[-1]
        if value is None:
            continue
        try:
            values.append(float(value.replace(",", "").replace("~", "")))
        except (AttributeError, ValueError):
            pass

    n = len(values)
    trim_left, trim_right = cf['bp_table_values_trim']
    left, right = int(n * trim_left), int(n * trim_right)
    values = values[left:-right] if right else values  # remove first 5% and last 5%

    summary = {
        'cnt': len(values),
        'min': min(values),
        'avg': statistics.mean(values),
        'med': statistics.median(values),
        'max': max(values),
    }

    if ctx['verbose']:
        print(f"table_rows_summary: summary", summary)

    return summary


def pa_read(job):
    pa_info = {}

    log_file = next(job.glob(cf['cli_file']), None)
    if log_file is None:
        print("pa_read: CLI log not found.")

    with log_file.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for attr in cf['pa_attrs']:
        for line in lines:
            if attr in line:
                value = line.partition(":")[2].strip()
                pa_info[attr] = value
                break

    if ctx['verbose']:
        print("pa_read: pa_info")
        for key, value in pa_info.items():
            print(f"\t{key}: '{value}'")

    return pa_info


def sta_read(job):
    json_file = next(job.glob(cf['sta_file']))

    with json_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    result = {}
    for key in cf['sta_metrics'].keys():
        if key in data and "max" in data[key] and data[key]["max"]:
            result[key] = int(data[key]["max"][0])
        else:
            result[key] = None

    return result


def main():
    init()

    slide_cover()

    slide_clone(cf['sldId']['agenda'], title=cf['text']['agenda'])
    # slide = slide_add(1, title=cf['agenda'])
    # slide_add_bullets(slide.placeholders[1].text_frame, cf['agenda_items'])

    for folder in ctx['folders_case']:
        case = folder.name
        print(". " * 40)
        print(f"main: case '{case}'")

        slide_clone(cf['sldId']['section'], title=case)  # slide for section start
        slide_clone(cf['sldId']['case'], title=f"{cf['text']['case']} - {case}")  # slide for test case details

        ctx['cases'][case] = {}
        throughput, flow_rate = "", ""
        pdf_list = list(folder.glob(cf['bp_reports']))
        for pdf in pdf_list:
            print(f"main: case '{case}' pdf '{pdf.name}'")
            data = pdf_read(pdf)
            ctx['cases'][case][pdf.stem] = data
            if 'bp_version' not in ctx:
                ctx['bp_version'] = set()
            ctx['bp_version'].add(data[cf['bp_sections']['test_device']]['bp_version'])  # assume same for all cases
            throughput = data[cf['bp_sections']['super_flow_data_throughput']]['values']['avg']
            if 'flow_rate' not in ctx['cases'][case]:
                ctx['cases'][case]['flow_rate'] = []
            flow_rate = data[cf['bp_sections']['test_parameters']]['params']['Maximum Flow Creation Rate']
            ctx['cases'][case]['flow_rate'].append(flow_rate)
        for pdf in ctx['cases'][case]:
            data = ctx['cases'][case][pdf]
            for section in cf['bp_sections'].values():
                if section not in data:
                    continue
                for image in data[section]['image_paths']:
                    slide_add(cf['sldId']['new'], title=f"{case} - {section}", image=image)

        job_list = list(folder.glob(cf['job_dir']))
        for job in job_list:
            ctx['cases'][case][job.stem] = {}
            print(f"\nmain: case '{case}' job '{job.name}'")
            pa_info = pa_read(job)
            ctx['cases'][case][job.stem]['pa'] = pa_info
            if 'pa' not in ctx:
                ctx['pa'] = set()
            ctx['pa'].add((pa_info['model'], pa_info['sw-version']))
            stats = sta_read(job)
            stats.update({
                'case': case,
                'job': job.name,
                'throughput': throughput,
                'flow_rate': flow_rate,
                'supportedSessions': int(pa_info['sessions supported'])
            })
            throughput, flow_rate = "", ""  # used once
            ctx['results'].append(stats)
            slide_add_with_images(cf['sldId']['new'], job, cf['dp_files_list'], title=f"{case} - {cf['text']['dp']} ({{}})")
            slide_add_with_images(cf['sldId']['new'], job, cf['p_files_list'], title=f"{case} - {cf['text']['util']} ({{}})")

        slide_add_with_images(cf['sldId']['new'], folder, [cf['other_files']], title=f"{case} - {{}}")

    slide_clone(cf['sldId']['section'], title=cf['text']['others'])  # slide for section start
    for folder in ctx['folders_other']:
        slide_add_with_images(cf['sldId']['new'], folder, [cf['image_files']], title=f"{cf['text']['others']} - {folder.name} ({{}})")

    df = results_to_dataframe(ctx['results'])
    slide_fill_table(ctx['prs'].slides[cf['sldId']['results']], df)
    # slide = slide_clone(cf['sldId']['results'], title=cf['text']['results'])  # slide for the result table
    # slide_fill_table(slide, df)

    slides = ctx['prs'].slides._sldIdLst
    slides.remove(ctx['last_sldId'])
    slides.append(ctx['last_sldId'])  # move the previous last slide to the end of the presentation

    if 'removal' in cf['sldId']:
        left, right = cf['sldId']['removal']
        slides_removal = list(slides[left:right])
        for sldId in slides_removal:
            slides.remove(sldId)

    cleanup()

if __name__ == '__main__':
    main()
