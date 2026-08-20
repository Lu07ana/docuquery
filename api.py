import hashlib
import os
import tempfile

from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File
)

from fastapi.middleware.cors import (
    CORSMiddleware
)

from pydantic import BaseModel

from dotenv import load_dotenv

from google import genai

from retrieval import (
    connect_db,
    retrieve,
    initialize_database
)

from ingestion import (
    ensure_documents_table,
    ingest_pdf
)

from contextlib import asynccontextmanager

# =========================================================
# CONFIG
# =========================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

DOCUMENTS_DIR = (
    BASE_DIR
    / "documents"
)

DOCUMENTS_DIR.mkdir(
    exist_ok=True
)


MAX_PDF_SIZE = (
    50
    * 1024
    * 1024
)

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

# =========================================================
# ALLOWED FRONTEND ORIGINS
# =========================================================

allowed_origins_string = os.getenv(
    "ALLOWED_ORIGINS",
    ""
)


ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in allowed_origins_string.split(",")
    if origin.strip()
]


if not ALLOWED_ORIGINS:

    raise RuntimeError(
        "ALLOWED_ORIGINS was not found."
    )

# =========================================================
# APPLICATION LIFESPAN
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    initialize_database()

    yield



# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="DocuQuery API",
    description=(
        "Hybrid RAG document question answering API."
    ),
    version="1.0.0",
    lifespan=lifespan
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=[
        "GET",
        "POST",
        "DELETE"
    ],
    allow_headers=[
        "Content-Type"
    ]
)

# =========================================================
# GEMINI
# =========================================================
load_dotenv()


gemini_api_key = os.getenv("GEMINI_API_KEY")

if not gemini_api_key:
    raise RuntimeError(
        "GEMINI_API_KEY was not found."
    )


client = genai.Client(
    api_key=gemini_api_key
)


# =========================================================
# REQUEST MODEL
# =========================================================

class QuestionRequest(
    BaseModel
):

    question: str


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    conn = None

    try:

        conn = connect_db()

        conn.execute(
            "SELECT 1"
        )

        return {
            "status": "ok",
            "database": "connected"
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:

        if conn is not None:

            conn.close()


# =========================================================
# LIST DOCUMENTS
# =========================================================

@app.get("/documents")
def get_documents():

    conn = None

    try:

        conn = connect_db()

        ensure_documents_table(
            conn
        )


        rows = conn.execute(
            """
            SELECT
                filename,
                stored_name,
                page_count,
                chunk_count,
                uploaded_at
            FROM documents
            ORDER BY uploaded_at DESC
            """
        ).fetchall()


        documents = []

        for row in rows:

            documents.append(
                {
                    "filename": row[0],
                    "stored_name": row[1],
                    "page_count": row[2],
                    "chunk_count": row[3],
                    "uploaded_at": (
                        row[4].isoformat()
                        if row[4]
                        else None
                    )
                }
            )


        return {
            "documents": documents
        }


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


    finally:

        if conn is not None:

            conn.close()


# =========================================================
# DELETE DOCUMENT
# =========================================================

@app.delete("/documents/{stored_name}")
def delete_document(stored_name: str):

    conn = None

    try:

        # Prevent paths such as ../../something
        safe_name = Path(stored_name).name

        if safe_name != stored_name:

            raise HTTPException(
                status_code=400,
                detail="Invalid document name."
            )


        conn = connect_db()

        ensure_documents_table(
            conn
        )


        # =================================================
        # CHECK DOCUMENT EXISTS
        # =================================================

        document = conn.execute(
            """
            SELECT filename, stored_name
            FROM documents
            WHERE stored_name = %s
            """,
            (stored_name,)
        ).fetchone()


        if document is None:

            raise HTTPException(
                status_code=404,
                detail="Document not found."
            )


        filename = document[0]


        # =================================================
        # DELETE CHUNKS
        # =================================================

        conn.execute(
            """
            DELETE FROM chunks
            WHERE source = %s
            """,
            (stored_name,)
        )


        # =================================================
        # DELETE DOCUMENT RECORD
        # =================================================

        conn.execute(
            """
            DELETE FROM documents
            WHERE stored_name = %s
            """,
            (stored_name,)
        )


        conn.commit()


        # =================================================
        # OPTIONAL LOCAL FILE CLEANUP
        # =================================================

        pdf_path = (
            DOCUMENTS_DIR
            / stored_name
        )

        if pdf_path.exists():

            try:

                pdf_path.unlink()

            except OSError:

                pass    


        return {
            "message": "Document deleted.",
            "filename": filename,
            "stored_name": stored_name
        }


    except HTTPException:

        raise


    except Exception as error:

        if conn is not None:

            conn.rollback()


        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


    finally:

        if conn is not None:

            conn.close()


# =========================================================
# CREATE UNIQUE DOCUMENT NAME
# =========================================================

def create_storage_name(
    conn,
    filename,
    file_hash
):

    # Check whether this exact filename is already
    # being used by an indexed document.

    existing = conn.execute(
        """
        SELECT 1
        FROM documents
        WHERE stored_name = %s
        """,
        (filename,)
    ).fetchone()


    # If the name is free, keep the original name.

    if existing is None:

        return filename


    # Otherwise add part of the file hash.

    path = Path(
        filename
    )


    return (
        f"{path.stem}"
        f"-{file_hash[:8]}"
        f"{path.suffix.lower()}"
    )


# =========================================================
# UPLOAD PDF
# =========================================================

@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...)
):

    conn = None

    temporary_path = None


    try:

        # =================================================
        # SAFE FILE NAME
        # =================================================

        filename = Path(
            file.filename or ""
        ).name


        if not filename:

            raise HTTPException(
                status_code=400,
                detail="The file has no filename."
            )


        # =================================================
        # PDF ONLY
        # =================================================

        if not filename.lower().endswith(
            ".pdf"
        ):

            raise HTTPException(
                status_code=400,
                detail="Only PDF files are supported."
            )


        # =================================================
        # READ FILE
        # =================================================

        contents = await file.read(
            MAX_PDF_SIZE + 1
        )


        if len(contents) > MAX_PDF_SIZE:

            raise HTTPException(
                status_code=413,
                detail=(
                    "The PDF is too large. "
                    "Maximum size is 50 MB."
                )
            )


        # =================================================
        # VERIFY PDF SIGNATURE
        # =================================================

        if not contents.startswith(
            b"%PDF-"
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "The uploaded file does not "
                    "appear to be a valid PDF."
                )
            )


        # =================================================
        # CREATE SHA-256 HASH
        # =================================================

        file_hash = hashlib.sha256(
            contents
        ).hexdigest()


        # =================================================
        # DATABASE
        # =================================================

        conn = connect_db()

        ensure_documents_table(
            conn
        )


        # =================================================
        # DUPLICATE CHECK
        # =================================================

        existing = conn.execute(
            """
            SELECT filename
            FROM documents
            WHERE file_hash = %s
            """,
            (file_hash,)
        ).fetchone()


        if existing:

            raise HTTPException(
                status_code=409,
                detail=(
                    "This PDF has already been "
                    f"uploaded as '{existing[0]}'."
                )
            )


        # =================================================
        # CREATE INTERNAL DOCUMENT NAME
        # =================================================

        stored_name = create_storage_name(
            conn,
            filename,
            file_hash
        )


        # =================================================
        # TEMPORARILY SAVE PDF
        # =================================================

        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False
        ) as temporary_file:

            temporary_file.write(
                contents
            )

            temporary_path = Path(
                temporary_file.name
            )


        # =================================================
        # INDEX PDF
        # =================================================

        result = ingest_pdf(
            conn=conn,
            pdf_path=temporary_path,
            filename=filename,
            stored_name=stored_name,
            file_hash=file_hash
        )


        return {
            "message": (
                "PDF uploaded and indexed."
            ),
            **result
        }


    except HTTPException:

        raise


    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


    finally:

        # =================================================
        # DELETE TEMPORARY PDF
        # =================================================

        if (
            temporary_path is not None
            and
            temporary_path.exists()
        ):

            try:

                temporary_path.unlink()

            except OSError:

                pass


        if conn is not None:

            conn.close()


        await file.close()
        
# =========================================================
# RETRIEVE ONLY
# =========================================================

@app.post("/retrieve")
def retrieve_question(
    request: QuestionRequest
):

    question = (
        request.question.strip()
    )


    if not question:

        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )


    conn = None


    try:

        conn = connect_db()


        results = retrieve(
            conn,
            question,
            top_k=3
        )


        retrieved_chunks = []


        for (
            text,
            source,
            pages,
            score
        ) in results:

            retrieved_chunks.append(
                {
                    "text": text,
                    "source": source,
                    "pages": pages,
                    "reranker_score":
                        round(
                            float(score),
                            3
                        )
                }
            )


        return {
            "question": question,
            "results": retrieved_chunks
        }


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


    finally:

        if conn is not None:

            conn.close()


# =========================================================
# ASK
# =========================================================

@app.post("/ask")
def ask_question(
    request: QuestionRequest
):

    question = (
        request.question.strip()
    )


    if not question:

        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )


    conn = None


    try:

        conn = connect_db()


        results = retrieve(
            conn,
            question,
            top_k=3
        )


        if not results:

            return {
                "question": question,
                "answer": (
                    "I could not find enough "
                    "information in the documents."
                ),
                "sources": []
            }


        # =================================================
        # BUILD GEMINI CONTEXT
        # =================================================

        context_parts = []


        for (
            text,
            source,
            pages,
            score
        ) in results:

            context_parts.append(
                f"""
Source: {source}
Pages: {pages}

{text}
"""
            )


        context = "\n\n".join(
            context_parts
        )


        # =================================================
        # PROMPT
        # =================================================

        prompt = f"""
Answer the question using only the provided context.

If the answer cannot be found in the context,
say that there is not enough information.

Context:

{context}

Question:

{question}
"""


        # =================================================
        # GEMINI
        # =================================================

        try:

            response = (
                client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt
                )
            )


        except Exception as error:

            raise HTTPException(
                status_code=503,
                detail=(
                    "Gemini could not generate "
                    f"an answer: {error}"
                )
            )


        # =================================================
        # SOURCES
        # =================================================

        sources = []


        for (
            text,
            source,
            pages,
            score
        ) in results:

            sources.append(
                {
                    "source": source,
                    "pages": pages,
                    "reranker_score":
                        round(
                            float(score),
                            3
                        )
                }
            )


        return {
            "question": question,
            "answer": response.text,
            "sources": sources
        }


    except HTTPException:

        raise


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


    finally:

        if conn is not None:

            conn.close()