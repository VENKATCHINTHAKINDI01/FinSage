"""
Document loader and chunking - splits documents into searchable chunks.
Processes PDFs, text files, and web content.
"""

from typing import List, Dict, Any
from pydantic import BaseModel
import logging
import re

logger = logging.getLogger(__name__)


class Document(BaseModel):
    """Represents a document chunk"""
    document_id: str
    source: str  # File name, URL, etc.
    title: str
    content: str
    metadata: Dict[str, Any] = {}
    chunk_index: int = 0


class DocumentLoader:
    """
    Load and chunk documents for RAG.
    
    Supports:
    - Plain text
    - PDFs (via text extraction)
    - Web content
    - Markdown
    """
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize loader.
        
        Args:
            chunk_size: Characters per chunk
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        logger.info(f"DocumentLoader initialized (chunk_size={chunk_size})")
    
    async def load_text(
        self,
        text: str,
        source: str,
        title: str = "",
        metadata: Dict[str, Any] | None = None
    ) -> List[Document]:
        """
        Load and chunk plain text.
        
        Args:
            text: Document text
            source: Source identifier (filename, URL, etc.)
            title: Document title
            metadata: Additional metadata
        
        Returns:
            List of Document chunks
        
        Example:
            docs = await loader.load_text(
                "Tax deductions include...",
                source="tax_guide.txt",
                title="Tax Deductions Guide"
            )
        """
        
        if not text or len(text.strip()) == 0:
            logger.warning(f"Empty text from source: {source}")
            return []
        
        # Clean text
        text = self._clean_text(text)
        
        # Split into chunks
        chunks = self._chunk_text(text)
        
        # Create documents
        documents = []
        for i, chunk in enumerate(chunks):
            doc_id = f"{source}-{i}"
            doc = Document(
                document_id=doc_id,
                source=source,
                title=title,
                content=chunk,
                metadata=metadata or {},
                chunk_index=i
            )
            documents.append(doc)
        
        logger.info(f"Loaded {len(documents)} chunks from {source}")
        return documents
    
    async def load_pdf(
        self,
        pdf_path: str,
        title: str = "",
        metadata: Dict[str, Any] | None = None
    ) -> List[Document]:
        """
        Load and chunk PDF file.
        
        Args:
            pdf_path: Path to PDF file
            title: Document title
            metadata: Additional metadata
        
        Returns:
            List of Document chunks
        
        Note:
            Requires: pip install pypdf
        
        Example:
            docs = await loader.load_pdf(
                "tax_guide.pdf",
                title="Tax Deductions Guide"
            )
        """
        
        try:
            import PyPDF2
            
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num, page in enumerate(reader.pages):
                    text += f"\n--- Page {page_num + 1} ---\n"
                    text += page.extract_text()
            
            logger.info(f"Extracted text from PDF: {pdf_path}")
            
            return await self.load_text(
                text,
                source=pdf_path,
                title=title or pdf_path,
                metadata=metadata
            )
        
        except ImportError:
            logger.error("PyPDF2 not installed. Run: pip install PyPDF2")
            return []
        except Exception as e:
            logger.error(f"Error loading PDF {pdf_path}: {e}")
            return []
    
    async def load_markdown(
        self,
        md_path: str,
        title: str = "",
        metadata: Dict[str, Any] | None = None
    ) -> List[Document]:
        """
        Load and chunk Markdown file.
        Preserves heading structure for context.
        
        Args:
            md_path: Path to Markdown file
            title: Document title
            metadata: Additional metadata
        
        Returns:
            List of Document chunks
        """
        
        try:
            with open(md_path, 'r', encoding='utf-8') as file:
                text = file.read()
            
            # Split by headers for better context
            sections = self._split_by_headers(text)
            
            documents = []
            for i, (heading, content) in enumerate(sections):
                doc_id = f"{md_path}-{i}"
                doc = Document(
                    document_id=doc_id,
                    source=md_path,
                    title=heading or title or md_path,
                    content=content,
                    metadata={**(metadata or {}), "heading": heading},
                    chunk_index=i
                )
                documents.append(doc)
            
            logger.info(f"Loaded {len(documents)} sections from Markdown: {md_path}")
            return documents
        
        except Exception as e:
            logger.error(f"Error loading Markdown {md_path}: {e}")
            return []
    
    async def load_web_content(
        self,
        url: str,
        title: str = "",
        metadata: Dict[str, Any] | None = None
    ) -> List[Document]:
        """
        Load and chunk web content.
        
        Args:
            url: Web URL
            title: Document title
            metadata: Additional metadata
        
        Returns:
            List of Document chunks
        
        Note:
            Requires: pip install requests beautifulsoup4
        """
        
        try:
            import requests
            from bs4 import BeautifulSoup
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text from paragraphs
            text = ""
            for p in soup.find_all(['p', 'li', 'h1', 'h2', 'h3']):
                text += p.get_text() + "\n"
            
            logger.info(f"Extracted text from URL: {url}")
            
            return await self.load_text(
                text,
                source=url,
                title=title or soup.title.string if soup.title else url,
                metadata={**(metadata or {}), "url": url}
            )
        
        except ImportError:
            logger.error("requests/beautifulsoup4 not installed")
            return []
        except Exception as e:
            logger.error(f"Error loading web content {url}: {e}")
            return []
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters but keep essential ones
        text = re.sub(r'[^\w\s\.\,\:\;\-\!\?]', '', text)
        return text.strip()
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping chunks."""
        chunks = []
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) < self.chunk_size:
                current_chunk += " " + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Add overlap for context
        overlapped_chunks = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                # Add end of previous chunk for context
                prev_end = chunks[i-1][-self.chunk_overlap:]
                overlapped_chunks.append(prev_end + " " + chunk)
            else:
                overlapped_chunks.append(chunk)
        
        return overlapped_chunks
    
    def _split_by_headers(self, text: str) -> List[tuple[str, str]]:
        """Split markdown by headers."""
        sections = []
        current_heading = ""
        current_content = ""
        
        for line in text.split('\n'):
            if line.startswith('#'):
                # Found a header
                if current_content:
                    sections.append((current_heading, current_content.strip()))
                
                current_heading = line.replace('#', '').strip()
                current_content = ""
            else:
                current_content += line + "\n"
        
        if current_content:
            sections.append((current_heading, current_content.strip()))
        
        return sections


# Global document loader
document_loader = DocumentLoader()