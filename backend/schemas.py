"""schemas.py — all Pydantic request/response models for AuraGraph."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class AuthRequest(BaseModel):
    email:    Optional[str] = None
    username: Optional[str] = None
    password: str

    @property
    def identifier(self) -> str:
        return (self.email or self.username or "").strip()


class FusionResponse(BaseModel):
    fused_note:      str
    source:          str = "azure"
    fallback_reason: Optional[str] = None
    chunks_stored:   Optional[dict] = None


class DoubtRequest(BaseModel):
    notebook_id: str
    doubt:       str
    page_idx:    int = 0


class DoubtResponse(BaseModel):
    answer:              str
    source:              str = "azure"
    verification_status: str = "correct"
    correction:          str = ""
    footnote:            str = ""


class MutationRequest(BaseModel):
    notebook_id:        str
    doubt:              str
    page_idx:           int = 0
    original_paragraph: Optional[str] = None


class MutationResponse(BaseModel):
    mutated_paragraph: str
    concept_gap:       str
    answer:            str = ""
    page_idx:          int
    source:            str = "azure"
    can_mutate:        bool = True


class RegenerateSectionRequest(BaseModel):
    notebook_id: str
    page_idx:    int
    proficiency: str = "Practitioner"


class RegenerateSectionResponse(BaseModel):
    new_section: str
    page_idx:    int
    source:      str


class ExaminerRequest(BaseModel):
    concept_name:       str
    notebook_id:        Optional[str] = None
    custom_instruction: Optional[str] = None


class ExaminerResponse(BaseModel):
    practice_questions: str


class ConceptPracticeRequest(BaseModel):
    concept_name:       str
    level:              str = "partial"
    notebook_id:        Optional[str] = None
    custom_instruction: Optional[str] = None


class ConceptPracticeResponse(BaseModel):
    questions: list


class SniperExamRequest(BaseModel):
    notebook_id: Optional[str] = None


class SniperExamResponse(BaseModel):
    questions:       list
    concepts_tested: list


class NodeUpdateRequest(BaseModel):
    concept_name: str
    status:       str


class ConceptExtractRequest(BaseModel):
    note:        str
    notebook_id: Optional[str] = None


class NotebookCreateRequest(BaseModel):
    name:   str
    course: str


class NotebookUpdateRequest(BaseModel):
    note:        str
    proficiency: Optional[str] = None


class SectionCreateRequest(BaseModel):
    title:     str
    note_type: str = "topic"


class SectionUpdateRequest(BaseModel):
    title:     Optional[str] = None
    content:   Optional[str] = None
    note_type: Optional[str] = None
    order_idx: Optional[int] = None


class SectionReorderRequest(BaseModel):
    order: List[dict]


class SectionGenerateRequest(BaseModel):
    proficiency: Optional[str] = "Intermediate"


class FusionRequest(BaseModel):
    slide_summary:      str
    textbook_paragraph: str
    proficiency:        str = "Practitioner"
    notebook_id:        Optional[str] = None
