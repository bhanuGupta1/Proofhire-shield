"""Client shortlist report PDF (platform Phase 4).

Renders a job's shortlisted candidates into a shareable one-page PDF a recruiter
can send to a client. Reuses the same reportlab conventions as the Trust Report.
Each candidate row carries its CV risk level, so the security posture that makes
ProofHire distinctive travels all the way to the client-facing artifact.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_RISK_COLOUR = {
    "GREEN": colors.HexColor("#16a34a"),
    "ORANGE": colors.HexColor("#ea580c"),
    "RED": colors.HexColor("#dc2626"),
}


@dataclass
class ReportCandidate:
    full_name: str
    headline: Optional[str]
    status: str
    risk_level: Optional[str]
    risk_score: Optional[int]


def build_client_report(
    job_title: str,
    client_name: Optional[str],
    candidates: list[ReportCandidate],
) -> bytes:
    """Return PDF bytes for a job's shortlist report."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, spaceAfter=6)
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey, spaceAfter=4
    )
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, spaceAfter=4)

    story = []
    story.append(Paragraph("ProofHire Shield — Candidate Shortlist", h1))
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = f"Role: {job_title}"
    if client_name:
        subtitle += f"  |  Client: {client_name}"
    story.append(Paragraph(subtitle, small))
    story.append(Paragraph(f"Generated: {ts}", small))
    story.append(Spacer(1, 0.4 * cm))

    if not candidates:
        story.append(Paragraph("No candidates have been shortlisted yet.", body))
    else:
        rows = [["Candidate", "Headline", "Status", "CV Risk"]]
        for c in candidates:
            risk = c.risk_level or "—"
            if c.risk_level and c.risk_score is not None:
                risk = f"{c.risk_level} ({c.risk_score}/100)"
            rows.append([c.full_name, c.headline or "—", c.status.title(), risk])

        tbl = Table(rows, colWidths=[4.5 * cm, 6 * cm, 2.5 * cm, 3 * cm])
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        # Colour the risk cell per candidate.
        for i, c in enumerate(candidates, start=1):
            if c.risk_level in _RISK_COLOUR:
                style.append(
                    ("TEXTCOLOR", (3, i), (3, i), _RISK_COLOUR[c.risk_level])
                )
        tbl.setStyle(TableStyle(style))
        story.append(tbl)

    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            "Each candidate's CV was scanned by ProofHire Shield for hidden "
            "instructions and personal data before inclusion. This report is a "
            "screening aid and does not constitute a final hiring decision.",
            small,
        )
    )
    doc.build(story)
    return buf.getvalue()
