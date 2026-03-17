# backend/utils/pdf_writer.py
# Rewritten resume text → PDF file
#
# Why ReportLab?
# → Free, open source
# → Pure Python — no system dependencies
# → Good enough for clean resume PDF
# → python-docx alternative bhi hai
#   but PDF more universal hai

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph,
    Spacer, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
import os
from loguru import logger


def create_resume_pdf(
    resume_text : str,
    output_path : str,
    user_name   : str = ""
) -> str:
    """
    Resume text se clean PDF banao.

    Why SimpleDocTemplate?
    → Easy to use
    → Auto pagination
    → Style management built-in

    Returns output path.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize     = A4,
        rightMargin  = 0.75 * inch,
        leftMargin   = 0.75 * inch,
        topMargin    = 0.75 * inch,
        bottomMargin = 0.75 * inch
    )

    # Styles define karo
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "NameStyle",
        parent    = styles["Normal"],
        fontSize  = 18,
        fontName  = "Helvetica-Bold",
        alignment = TA_CENTER,
        spaceAfter= 4
    )

    section_style = ParagraphStyle(
        "SectionStyle",
        parent    = styles["Normal"],
        fontSize  = 11,
        fontName  = "Helvetica-Bold",
        spaceAfter= 4,
        spaceBefore=8,
        textColor = colors.HexColor("#2C3E50")
    )

    body_style = ParagraphStyle(
        "BodyStyle",
        parent    = styles["Normal"],
        fontSize  = 10,
        fontName  = "Helvetica",
        spaceAfter= 3,
        leading   = 14
    )

    bullet_style = ParagraphStyle(
        "BulletStyle",
        parent     = styles["Normal"],
        fontSize   = 10,
        fontName   = "Helvetica",
        spaceAfter = 2,
        leftIndent = 15,
        leading    = 13
    )

    story = []
    lines = resume_text.strip().split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        # Name — first non-empty line
        if story == [] or (
            len(story) == 1 and
            isinstance(story[0], Spacer)
        ):
            story.append(Paragraph(line, name_style))
            story.append(HRFlowable(
                width="100%",
                thickness=1,
                color=colors.HexColor("#2C3E50")
            ))
            continue

        # Section headers — ALL CAPS ya ends with :
        if (line.isupper() and len(line) > 3) or \
           (line.endswith(":") and len(line) < 30):
            story.append(Spacer(1, 6))
            story.append(Paragraph(line, section_style))
            story.append(HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.HexColor("#BDC3C7")
            ))
            continue

        # Bullet points
        if line.startswith(("•", "-", "*", "→")):
            clean = line.lstrip("•-*→ ").strip()
            story.append(Paragraph(f"• {clean}", bullet_style))
            continue

        # Normal text
        story.append(Paragraph(line, body_style))

    try:
        doc.build(story)
        logger.info(f"✅ PDF created: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"❌ PDF creation error: {e}")
        raise