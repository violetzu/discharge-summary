import re
from typing import Optional
from .schemas import DischargeSummaryRequest, SummaryData


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r'<p[^>]*>', '', text)
    text = re.sub(r'</p>', '', text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text.strip()


def get_length_hint(total_chars: int) -> str:
    if total_chars < 1200:
        return "short"
    elif total_chars < 2100:
        return "medium"
    return "long"


def build_xml(req: DischargeSummaryRequest) -> str:
    s = req.summary or SummaryData()

    primary  = clean_text(getattr(s, 'primary_diagnosis',    None))
    secondary = clean_text(getattr(s, 'secondary_diagnosis',  None))
    past     = clean_text(getattr(s, 'past_medical_history',  None))
    cc       = clean_text(getattr(s, 'chief_complaint',       None))
    pi       = clean_text(getattr(s, 'present_illness',       None))

    summary_lines = [
        "    <Summary>",
        f"        <CaseNo>{clean_text(req.caseno)}</CaseNo>",
        f"        <HhisNum>{clean_text(req.hhisnum)}</HhisNum>",
    ]
    if primary:   summary_lines.append(f"        <PrimaryDiagnosis>{primary}</PrimaryDiagnosis>")
    if secondary: summary_lines.append(f"        <SecondaryDiagnosis>{secondary}</SecondaryDiagnosis>")
    if past:      summary_lines.append(f"        <PastMedicalHistory>{past}</PastMedicalHistory>")
    if cc:        summary_lines.append(f"        <ChiefComplaint>{cc}</ChiefComplaint>")
    if pi:        summary_lines.append(f"        <PresentIllness>{pi}</PresentIllness>")
    summary_lines.append("    </Summary>")

    events = []

    for ne in (req.nursing_events or []):
        ts = clean_text(ne.timestamp)
        content = clean_text(ne.content)
        if ne.type == "VitalSign":
            vt = clean_text(ne.vital_type or "")
            events.append(
                f'        <NursingEvent timestamp="{ts}">\n'
                f'            <VitalSign type="{vt}" value="{content}" />\n'
                f'        </NursingEvent>'
            )
        else:
            tag = ne.type if ne.type in (
                "Subjective", "Objective", "Intervention", "Evaluation", "NarrativeNote"
            ) else "NarrativeNote"
            events.append(
                f'        <NursingEvent timestamp="{ts}">\n'
                f'            <SOAPNote>\n'
                f'                <{tag}>{content}</{tag}>\n'
                f'            </SOAPNote>\n'
                f'        </NursingEvent>'
            )

    for lr in (req.lab_reports or []):
        items_xml = ""
        for item in lr.items:
            val = clean_text(item.value)
            unit = clean_text(item.unit or "")
            result_str = f"{val} {unit}".strip()
            if item.flag and item.flag not in ("NORMAL", "NULL"):
                result_str += f" ({item.flag})"
            items_xml += f'\n            <Item name="{clean_text(item.name)}">{result_str}</Item>'
        events.append(
            f'        <LabReportGroup date="{clean_text(lr.date)}">'
            f'{items_xml}\n        </LabReportGroup>'
        )

    for c in (req.consultations or []):
        if not c.nurse_confirmation:
            continue
        ts = clean_text(c.timestamp)
        content = clean_text(c.nurse_confirmation)
        events.append(
            f'        <Consultation timestamp="{ts}">\n'
            f'            <Content>\n'
            f'            {content}\n'
            f'            </Content>\n'
            f'        </Consultation>'
        )

    events_xml = "\n".join(events)
    total_chars = len(primary + secondary + past + cc + pi + events_xml)
    length_hint = get_length_hint(total_chars)

    return (
        f'<PatientEncounter summary_length_style="{length_hint}">\n'
        + "\n".join(summary_lines) + "\n"
        + "    <ChronologicalEvents>\n"
        + events_xml + "\n"
        + "    </ChronologicalEvents>\n"
        + "</PatientEncounter>"
    )


