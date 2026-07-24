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

import os
from pathlib import Path
from pptx import Presentation
from pptx.util import Cm
from pptx.enum.shapes import PP_PLACEHOLDER
from PIL import Image
import pymupdf

cf = {
    'template': 'data/pov_template.pptx',
    'target': 'data/poc12345.pptx',
    
    'poc_number': 'POC12345',
    'cust_name': 'Health & Co.',
    'subject': 'PA-5550 Performance Testing',
    'author': 'Terence <telee@>',

    'poc_dir': 'data/POC12345 (QLDH)',
    'test_case_prefixes': ['AP', 'AE', 'AVAM', 'URL', 'HA', 'TP', 'TC'],
    'bp_report': 'POC*.pdf',
    'job_dir': 'job-*',
    'report_dir': 'data',

    'bp_sections': [
        'Test Device',
        'Super Flow Data',
        'Super Flow Data Throughput',
        'Super Flow Iterations'
    ],

    'pa_fields': [
        'model',
        'sw-version',
        'app-version',
        'app-release-date',
    ],

    'agenda': 'Agenda',
    'agenda_items': [
        'Overview',
        'Lab Setup', [
            'Hardware Requirements',
            'Topology',
            'Test Case Summary',
            'Test Environment',
            'Traffic Details',
        ],
        'Test Result Summary',
        'Test Cases',
    ],
    'throughput': 'Throughput',
    'dp': 'DP Utilization',
    'util': 'Resources Utilization',

    'verbose': True,
    'debug': False,
}

ctx = {}

def init():
    ctx['verbose'] = cf['verbose']
    ctx['debug'] = cf['debug']

    ctx['prs'] = Presentation(cf['template'])
    # ctx['last_slide'] = ctx['prs'].slides[-1]
    ctx['last_sldId'] = ctx['prs'].slides._sldIdLst[22]  # [-1]
    ctx['cases'] = {}

    top_dir = Path(cf['poc_dir'])

    subdirs = sorted(
        (p for p in top_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name.lower()
    )

    folders = []

    for prefix in cf['test_case_prefixes']:
        prefix = prefix.casefold()

        folders.extend(
            d for d in subdirs
            if d.name.casefold().startswith(prefix)
        )

    if cf['debug']:
        for folder in folders:
            print(folder.name)
        print()

    ctx['folders'] = folders


def cleanup():
    ctx['prs'].save(cf['target'])


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


def slide_add_image(slide, placeholder, image_path):
    left = placeholder.left
    top = placeholder.top
    box_w = placeholder.width
    box_h = placeholder.height + Cm(1.5)

    if ctx['verbose']:
        print(f"slide_add_image: left {left}, top {top}, box_w {box_w}, box_h {box_h}")

    with Image.open(image_path) as img:
        img_w, img_h = img.size

    aspect = img_w / img_h

    if box_w / box_h > aspect:
        new_h = box_h  # limited by height
        new_w = int(new_h * aspect)
    else:
        new_w = box_w  # limited by width
        new_h = int(new_w / aspect)

    left += int((box_w - new_w) / 2)  # center image
    top += int((box_h - new_h) / 2)

    element = placeholder._element
    element.getparent().remove(element)  # remove placeholder

    if ctx['verbose']:
        print(f"slide_add_image: img_w {img_w}, img_h {img_h}, aspec {aspect}")
        print(f"slide_add_image: image_path {str(image_path)}")
        print(f"slide_add_image: left {left}, top {top}, new_w {new_w}, new_h {new_h}\n")

    slide.shapes.add_picture(
        image_path,
        left,
        top,
        width=new_w,
        height=new_h
    )


def slide_add(idx=1, title=None, text=None, image=None):
    layout = ctx['prs'].slides[idx].slide_layout
    slide = ctx['prs'].slides.add_slide(layout)
    content = None
    for shape in slide.placeholders:
        # print("idx {0}, type {1}".format(idx, shape.placeholder_format.type))
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
    return slide


def pdf_find_line(page, text):
    blocks = page.get_text("dict")["blocks"]

    for block in blocks:
        if block["type"] != 0:
            continue

        for line in block["lines"]:
            line_text = "".join(span["text"] for span in line["spans"])

            if text in line_text:
                return line

    return None


def pdf_find_section(doc, section):
    toc = doc.get_toc()

    for level, text, page in toc:
        if section.lower() in text.lower():
            return page - 1      # PyMuPDF pages are 0-based

    return None


def pdf_read(pdf):
    doc = pymupdf.open(pdf)

    data = {}

    for section in cf['bp_sections']:
        page_num = pdf_find_section(doc, section)

        page = doc[page_num]

        print(f"\n===== Section {section} @ Page {page_num + 1} =====")
        line = pdf_find_line(page, section)
        if line is not None:
            print(line['spans'][0]['text'], "\n")

        heading_bottom = line['bbox'][3]
        tables = page.find_tables()
        target = None

        print(f"Found {len(tables.tables)} table(s)")

        for table in tables.tables:
            if table.bbox[1] > heading_bottom:
                target = table
                break

        if section == "Test Device" and 'bp_version' not in ctx and target:
            table = target.extract()
            ctx["bp_version"] = table[1][1]
            print(f"version {table[1][1]}")
            for row in table:
                pass  # print(row)

        images = page.get_images(full=True)

        mask_xrefs = {image[1] for image in images if image[1] != 0}

        if images:
            for i, image in enumerate(images):
                xref = image[0]

                if xref in mask_xrefs:
                    continue

                smask = image[1]

                if cf['debug']:
                    print("=" * 70)
                    print(f"Image {i}")
                    print(f"xref      : {xref}")
                    print(f"smask     : {smask}")
                    print(f"size      : {image[2]} x {image[3]}")
                    print(f"bpc       : {image[4]}")
                    print(f"colorspace: {image[5]}")
                    print(f"filter    : {image[8]}")

                rects = page.get_image_rects(xref)

                for r in rects:
                    print(f"page rect  : {r}")

                pix = pymupdf.Pixmap(doc, xref)

                if cf['verbose']:
                    print(f"pixmap     : {pix.width} x {pix.height}")
                    print(f"channels   : {pix.n}")
                    print(f"alpha      : {pix.alpha}")

                image_path = os.path.join(
                    cf['report_dir'],
                    f"{pdf.stem}-{page_num}-{i}.png"
                )

                try:
                    pix.save(image_path)
                    print(f"saved      : {image_path}\n")
                except Exception as e:
                    print(f"save failed: {e}\n")

                if section not in data:
                    data[section] = []
                data[section].append(image_path)

    return data


def pa_read(job):
    ctx['pa'] = {}

    log_file = next(job.glob('cli*.log'), None)
    if log_file is None:
        print("No CLI log found.")

    with log_file.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    for field in cf['pa_fields']:
        for line in lines:
            if field in line:
                value = line.partition(":")[2].strip()
                ctx['pa'][field] = value
                break

    print(ctx['pa'])


def go():
    init()
    slide_cover()

    slide = slide_add(1, title=cf['agenda'])
    slide_add_bullets(slide.placeholders[1].text_frame, cf['agenda_items'])

    for folder in ctx['folders']:
        print(folder.name)
        case = folder.name
        ctx['cases'][case] = {}
        pdf_list = list(folder.glob(cf['bp_report']))
        for pdf in pdf_list:
            print(pdf.name)
            data = pdf_read(pdf)
            ctx['cases'][case][pdf.stem] = data
        for pdf in ctx['cases'][case]:
            data = ctx['cases'][case][pdf]
            for section in cf['bp_sections']:
                if section not in data:
                    continue
                for image in data[section]:
                    slide_add(1, title=f"{case} - {section}", image=image)
        job_list = list(folder.glob(cf['job_dir']))
        for job in job_list:
            print(job.name)
            if 'pa' not in ctx:
                pa_read(job)
            slide_add(1, title=f"{case} - {cf['dp']}", image=str(job / "dp-0.png"))
            slide_add(1, title=f"{case} - {cf['util']}", image=str(job / "p-0.png"))

    # move the previous last slide to the end
    #
    slides = ctx['prs'].slides._sldIdLst
    slides.remove(ctx['last_sldId'])
    slides.append(ctx['last_sldId'])

    cleanup()

if __name__ == '__main__':
    go()

exit()
