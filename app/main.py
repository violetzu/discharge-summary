import json
import re
from datetime import datetime
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from .config import settings
from .llm_client import generate_completion, generate_stream
from .schemas import DischargeSummaryRequest, DischargeValidationRequest
from .xml_builder import build_xml

app = FastAPI(title="Discharge Summary API", version="1.0.0")

# ---------------------------------------------------------------------------
# System prompts (from Modelfiles)
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = """<Role>
    You are an expert Emergency Department (ED) physician AI assistant. Your purpose is to generate a clinically accurate "Treatment Course" summary.
</Role>

<Task>
    Based on the provided XML data, generate a concise, single-paragraph summary by synthesizing the clinically significant events of the ED encounter. A complete summary should include the following elements, **but only if they are present in the source data**:
    - **Diagnosis:** The primary working diagnosis.
    - **Key Examinations:** Clinically significant lab/imaging results.
    - **Key Medications/Interventions:** Important treatments administered.
    - **Consultations:** (See special rule below).
    - **Disposition & Follow-up Plan:** The final outcome. (Always be written at the end)
</Task>

<Special Rule for Consultations>
- **IF** a consultation occurred (e.g., OBYN, NEUR, CRS), the summary **MUST** mention it detailly and its outcome.
- **IF NO** consultation is mentioned in the XML, the summary **MUST NOT** mention one.
</Special Rule for Consultations>

<CorePrinciple priority="high">
    **Factual Grounding is Mandatory:** The generated summary must be **strictly and exclusively** based on the information within the provided <PatientEncounter> XML. **Do not hallucinate, invent, or infer** any information that is not explicitly stated in the input data. Every statement must be verifiable.
</CorePrinciple>

<OutputFormat>
    The output must be only the summary text. Do not include any other commentary. DO NOT Thought.
</OutputFormat>"""

_VALIDATION_SYSTEM = """You are a **Clinical Data Traceability Auditor**. Your sole function is to pinpoint the **direct and explicit source text** from a `<PatientEncounter>` document that directly corresponds to specific claims made in the `<Discharge_Summary>`.
You will be provided with two documents: `<PatientEncounter>` and `<Discharge_Summary>`.
**Core Principle: Directness and Verifiability**
Your primary goal is to establish a clear, verifiable link. For each piece of information in the summary, find its *source* in the encounter.
*   **Example:**
    *   If the summary says "bilateral pneumonia", your target is the exact text confirming this, like `X光顯示肺炎`.
    *   If the summary mentions "leukocytosis (27100)", your targets are `Leukocytes [#/volume] in Blood` and `27100`.
**Output Requirements:**
1.  **Format:** Your output MUST be a single JSON object.
2.  **Structure:** The JSON object must contain one key: `"relevant_text"`. The value for this key must be an array of strings.
3.  **Content:** Each string in the array must be an **exact, verbatim quote** from the `<PatientEncounter>` that serves as the **direct source** for a claim in the summary.
4.  **Special Handling for Lab Results:** For laboratory results found in `<Item>` tags, you must extract the `name` attribute's value as one string, and the tag's inner text (the lab value) as the *next* string in the array. **Do not** combine them.
    *   **Correct:** `"Lactate [Mass/volume] in Serum or Plasma"`, `"93.6"`
    *   **Incorrect:** `"Lactate [Mass/volume] in Serum or Plasma: 93.6"`
5.  **Strict Formatting:** Your entire response MUST begin directly with JSON format `{` and end with `}`. Do not include `json` markers, code fences (```), or any explanatory text."""


def _build_gemma_prompt(system: str, user_content: str) -> str:
    """Gemma chat template: system + user merged into user turn."""
    return (
        f"<start_of_turn>user\n{system}\n\n{user_content}<end_of_turn>\n"
        "<start_of_turn>model\n"
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def verify_api_key(request: Request):
    if settings.API_KEY == "NONE":
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _base_predict(req: DischargeSummaryRequest) -> dict:
    return {
        "deviceId": req.deviceId,
        "hnursta": req.hnursta,
        "hbed": req.hbed,
        "caseno": req.caseno,
        "hhisnum": req.hhisnum,
    }


def _wrap(predict_data: dict) -> dict:
    return {
        "key": settings.HIS_KEY,
        "predictDatas": [predict_data],
    }


# ---------------------------------------------------------------------------
# Validation result extraction
# ---------------------------------------------------------------------------

def _extract_result_list(text: str) -> list:
    try:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            for key in ("result", "relevant_text", "highlights", "key_terms"):
                if key in data and isinstance(data[key], list):
                    return [str(x) for x in data[key]]
    except Exception:
        pass
    quoted = re.findall(r'"([^"]{2,50})"', text)
    if quoted:
        seen: set = set()
        return [x for x in quoted if not (x in seen or seen.add(x))]
    return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/gen-discharge-summary")
async def gen_discharge_summary(
    req: DischargeSummaryRequest,
    _=Depends(verify_api_key),
):
    xml_prompt = build_xml(req)
    prompt = _build_gemma_prompt(_SUMMARY_SYSTEM, xml_prompt)

    async def stream() -> AsyncGenerator[bytes, None]:
        accumulated = ""
        async for line in generate_stream(settings.SUMMARY_MODEL, prompt, settings.SUMMARY_BASE_URL):
            try:
                chunk = json.loads(line)
            except Exception:
                continue

            text = chunk.get("text", "")
            done = chunk.get("done", False)

            if not done and text:
                accumulated += text
                payload = _wrap({**_base_predict(req), "response": text, "done": False})
                yield (json.dumps(payload, ensure_ascii=False) + "\n").encode()

            if done:
                predict_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                payload = _wrap({
                    **_base_predict(req),
                    "predict_local": predict_local,
                    "result": accumulated,
                    "done": True,
                    "type": "NULL",
                })
                yield (json.dumps(payload, ensure_ascii=False) + "\n").encode()

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache"},
    )


@app.post("/gen-discharge-validation")
async def gen_discharge_validation(
    req: DischargeValidationRequest,
    _=Depends(verify_api_key),
):
    xml_prompt = build_xml(req)
    user_content = (
        f"{xml_prompt}\n"
        f"<Discharge_Summary>\n{req.treatment_course}\n</Discharge_Summary>"
    )
    prompt = _build_gemma_prompt(_VALIDATION_SYSTEM, user_content)

    try:
        response_text = await generate_completion(settings.VALIDATION_MODEL, prompt, settings.VALIDATION_BASE_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"vLLM error: {e}")

    result_list = _extract_result_list(response_text)
    predict_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return _wrap({
        **_base_predict(req),
        "predict_local": predict_local,
        "result": result_list,
        "type": "NULL",
    })


@app.get("/health")
async def health():
    return {"status": "ok"}
