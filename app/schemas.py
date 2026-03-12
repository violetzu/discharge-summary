from pydantic import BaseModel
from typing import Optional, List


class LabItem(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None
    flag: Optional[str] = None  # NORMAL | HIGH | LOW | CRITICAL | NULL


class LabReportGroup(BaseModel):
    date: str
    items: List[LabItem] = []


class NursingEvent(BaseModel):
    timestamp: str
    type: str  # VitalSign | Subjective | Objective | Intervention | Evaluation | NarrativeNote
    content: str
    vital_type: Optional[str] = None  # 僅 type=VitalSign 時使用


class Consultation(BaseModel):
    timestamp: str
    nurse_confirmation: str


class SummaryData(BaseModel):
    primary_diagnosis: Optional[str] = None
    secondary_diagnosis: Optional[str] = None
    past_medical_history: Optional[str] = None
    chief_complaint: Optional[str] = None
    present_illness: Optional[str] = None


class DischargeSummaryRequest(BaseModel):
    caseno: str
    hhisnum: str
    deviceId: str
    hnursta: Optional[str] = None
    hbed: Optional[str] = None
    summary: Optional[SummaryData] = None
    nursing_events: Optional[List[NursingEvent]] = []
    lab_reports: Optional[List[LabReportGroup]] = []
    consultations: Optional[List[Consultation]] = []


class DischargeValidationRequest(DischargeSummaryRequest):
    treatment_course: str
