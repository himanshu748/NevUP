"""POST /audit — verify hallucination rate of coaching responses."""

import re
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.memory.models import SessionMemory

router = APIRouter(tags=["Audit"])

class AuditRequest(BaseModel):
    coaching_response: str

class AuditReference(BaseModel):
    sessionId: str
    status: str

class AuditResponse(BaseModel):
    references: List[AuditReference]
    hallucination_rate: float

# Match standard UUID format
UUID_PATTERN = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", re.IGNORECASE)

@router.post("/audit", response_model=AuditResponse)
async def verify_hallucinations(
    payload: AuditRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Extracts all sessionId (UUID) references from a coaching response,
    checks if they exist in the memory store, and calculates hallucination rate.
    """
    text = payload.coaching_response
    
    # Extract unique UUIDs found in text
    extracted_uuids = set(UUID_PATTERN.findall(text))
    
    references = []
    
    if not extracted_uuids:
        return AuditResponse(references=[], hallucination_rate=0.0)
        
    found_count = 0
    not_found_count = 0
    
    for uuid_str in extracted_uuids:
        try:
            parsed_uuid = UUID(uuid_str)
            # Check if this session exists in DB
            stmt = select(SessionMemory.session_id).where(SessionMemory.session_id == parsed_uuid)
            result = await db.execute(stmt)
            exists = result.scalar_one_or_none() is not None
            
            if exists:
                found_count += 1
                status = "found"
            else:
                not_found_count += 1
                status = "notfound"
                
        except ValueError:
            # Should not happen given regex, but be safe
            not_found_count += 1
            status = "notfound"
            
        references.append(AuditReference(sessionId=uuid_str, status=status))
        
    total_refs = found_count + not_found_count
    hallucination_rate = (not_found_count / total_refs) if total_refs > 0 else 0.0
    
    return AuditResponse(
        references=references,
        hallucination_rate=round(hallucination_rate, 2)
    )
