"""
Knowledge base management API endpoint.
Upload documents, view knowledge base stats, manage documents.
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import uuid

from backend.db.postgres import get_session
from backend.security.dependencies import get_current_user
from backend.middleware.ratelimit import MAX_UPLOAD_BYTES, UploadRejected, check_upload
from backend.models import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])

# PDF magic bytes are read from the leading chunk, well inside one read.
_SNIFF_WINDOW = 64


async def _read_capped(file: UploadFile, *, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """PRD-003: refuse an oversized upload DURING the read, not after.

    Reading the whole body first and measuring it afterward is the attack —
    by then the bytes are already resident. `UploadFile.read(n)` supports
    bounded reads, so the cap is enforced chunk by chunk.
    """
    chunk_size = 1024 * 1024
    out = bytearray()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        out.extend(chunk)
        if len(out) > limit:
            raise UploadRejected(
                f"the upload exceeds {limit // (1024 * 1024)} MB. It was "
                f"refused part-way through rather than after being read into "
                f"memory."
            )
    return bytes(out)


class DocumentUploadRequest(BaseModel):
    """Request to upload document"""
    title: str
    category: str  # "tax", "investment", "benefits", etc.
    source: str


class DocumentResponse(BaseModel):
    """Response from document operations"""
    document_id: str
    title: str
    category: str
    source: str
    status: str
    message: str


class KnowledgeBaseStats(BaseModel):
    """Knowledge base statistics"""
    total_documents: int
    categories: dict
    last_updated: str
    vector_store_size: int


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: str = "",
    category: str = "general",
    user: UserResponse = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    """
    Upload a document to knowledge base.
    
    Supports: .txt, .pdf, .md
    
    Example:
        POST /api/v1/knowledge/upload
        Authorization: Bearer token
        
        Form data:
        - file: <file>
        - title: "Tax Deductions Guide"
        - category: "tax"
    """
    
    try:
        from backend.rag.document_loader import document_loader
        from backend.rag.retriever import rag_retriever

        # PRD-003: the extension is a claim by the uploader; size is capped
        # while streaming, and for PDF the magic bytes are checked too — a
        # `.pdf` that starts with "PK" is a zip, and a zip handed to a PDF
        # parser is at best an error and at worst an unpacking bomb.
        try:
            content = await _read_capped(file)
        except UploadRejected as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
            ) from None

        if file.filename.endswith('.txt'):
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="the file is named .txt but its contents are not valid UTF-8 text.",
                ) from None
            file_type = 'text'
        elif file.filename.endswith('.pdf'):
            try:
                check_upload(content[:_SNIFF_WINDOW], declared_type="application/pdf")
            except UploadRejected as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
                ) from None
            # For PDF, save temporarily and load
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            file_type = 'pdf'
            text = None
        elif file.filename.endswith('.md'):
            try:
                text = content.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="the file is named .md but its contents are not valid UTF-8 text.",
                ) from None
            file_type = 'markdown'
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Use .txt, .pdf, or .md"
            )
        
        # Generate document ID
        doc_id = str(uuid.uuid4())
        
        # Load document
        if file_type == 'text':
            documents = await document_loader.load_text(
                text,
                source=file.filename,
                title=title or file.filename,
                metadata={"category": category, "uploaded_by": user.id}
            )
        elif file_type == 'pdf':
            documents = await document_loader.load_pdf(
                tmp_path,
                title=title or file.filename,
                metadata={"category": category, "uploaded_by": user.id}
            )
        elif file_type == 'markdown':
            documents = await document_loader.load_markdown(
                tmp_path if file_type == 'pdf' else file.filename,
                title=title or file.filename,
                metadata={"category": category, "uploaded_by": user.id}
            )
        else:
            documents = []
        
        if not documents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to process document"
            )
        
        # Store in knowledge base
        doc_dicts = [
            {
                "document_id": f"{doc_id}-{i}",
                "text": doc.content,
                "metadata": {**doc.metadata, "chunk": i}
            }
            for i, doc in enumerate(documents)
        ]
        
        count = await rag_retriever.add_documents_batch(doc_dicts)
        
        logger.info(f"Uploaded document {doc_id} with {count} chunks")
        
        return DocumentResponse(
            document_id=doc_id,
            title=title or file.filename,
            category=category,
            source=file.filename,
            status="success",
            message=f"Document stored as {count} chunks"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {e}")
        raise  # DEM-008: handled globally; str(e) must not reach the client


@router.get("/stats", response_model=KnowledgeBaseStats)
async def get_knowledge_base_stats(
    user: UserResponse = Depends(get_current_user),
) -> KnowledgeBaseStats:
    """
    Get knowledge base statistics.
    
    Example:
        GET /api/v1/knowledge/stats
        Authorization: Bearer token
    """
    
    try:
        from backend.rag.vector_store import qdrant_store
        
        stats = await qdrant_store.get_stats()
        
        return KnowledgeBaseStats(
            total_documents=stats.get("points_count", 0),
            categories={
                "tax": 0,  # TODO: Count by category
                "investment": 0,
                "benefits": 0,
                "general": 0
            },
            last_updated="2025-06-07T00:00:00Z",  # TODO: Track actual updates
            vector_store_size=stats.get("vector_size", 768)
        )
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise  # DEM-008: handled globally; str(e) must not reach the client


@router.get("/health")
async def knowledge_base_health():
    """Check if knowledge base is healthy."""
    try:
        from backend.rag.vector_store import qdrant_store
        
        stats = await qdrant_store.get_stats()
        
        return {
            "status": "ok",
            "service": "knowledge_base",
            "documents": stats.get("points_count", 0)
        }
    except Exception as e:
        logger.error(f"Knowledge base health check failed: {e}")
        return {
            "status": "error",
            "service": "knowledge_base",
            "error": str(e)
        }