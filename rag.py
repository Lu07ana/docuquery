import re
from pathlib import Path

import fitz

from google import genai
from pgvector import Vector

from retrieval import (
    connect_db,
    retrieve,
    embedding_model
)


# =========================================================
# GEMINI
# =========================================================

client = genai.Client()


# =========================================================
# DATABASE CONNECTION
# =========================================================

conn = connect_db()


# =========================================================
# CREATE TABLE
# =========================================================

conn.execute(
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id BIGSERIAL PRIMARY KEY,
        text TEXT NOT NULL,
        source TEXT NOT NULL,
        pages TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL
    )
    """
)

conn.commit()


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    # Remove NUL characters
    text = text.replace(
        "\x00",
        " "
    )

    # Remove control characters
    text = re.sub(
        r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text
    )

    # Remove invisible Unicode characters
    text = (
        text
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# SENTENCE-AWARE CHUNKING
# =========================================================

def split_text(
    text,
    chunk_size=1000,
    overlap=200
):

    # Find sentences while preserving their
    # character positions inside the document.
    sentence_matches = list(
        re.finditer(
            r"[^.!?]+(?:[.!?]+(?=\s|$)|$)",
            text
        )
    )

    sentences = [
        {
            "text": match.group().strip(),
            "start": match.start(),
            "end": match.end()
        }
        for match in sentence_matches
        if match.group().strip()
    ]

    chunks = []

    i = 0

    while i < len(sentences):

        chunk_start = sentences[i]["start"]

        j = i
        chunk_end = sentences[i]["end"]

        # Add complete sentences until we reach
        # approximately chunk_size characters.
        while j < len(sentences):

            possible_end = sentences[j]["end"]

            if (
                possible_end - chunk_start
                > chunk_size
                and j > i
            ):
                break

            chunk_end = possible_end
            j += 1

        chunk_text = text[
            chunk_start:chunk_end
        ].strip()

        # Ignore very small chunks
        if len(chunk_text) >= 50:

            chunks.append(
                {
                    "text": chunk_text,
                    "start": chunk_start,
                    "end": chunk_end
                }
            )

        # -------------------------------------------------
        # Create overlap with next chunk
        # -------------------------------------------------

        target_position = (
            chunk_end - overlap
        )

        next_i = None

        for k in range(
            i + 1,
            j
        ):

            if (
                sentences[k]["start"]
                >= target_position
            ):
                next_i = k
                break

        if next_i is None:
            next_i = j

        # Prevent infinite loop
        if next_i <= i:
            next_i = i + 1

        i = next_i

    return chunks


# =========================================================
# PROCESS ONE PDF
# =========================================================

def process_pdf(pdf_path):

    print(
        "\nProcessing:",
        pdf_path.name
    )

    try:

        fitz.TOOLS.reset_mupdf_warnings()

        document = fitz.open(
            pdf_path
        )

        full_text = ""

        page_ranges = []

        # -----------------------------------------
        # Read every page
        # -----------------------------------------

        for page_number, page in enumerate(
            document,
            start=1
        ):

            page_text = page.get_text()

            page_text = clean_text(
                page_text
            )

            if not page_text:
                continue

            start_position = len(
                full_text
            )

            full_text += (
                page_text + " "
            )

            end_position = len(
                full_text
            )

            page_ranges.append(
                {
                    "page": page_number,
                    "start": start_position,
                    "end": end_position
                }
            )

        warnings = (
            fitz.TOOLS.mupdf_warnings()
        )

        document.close()

        # -----------------------------------------
        # Skip damaged PDFs
        # -----------------------------------------

        if warnings:

            print(
                "MuPDF warning detected:"
            )

            print(
                warnings
            )

            print(
                "Skipping:",
                pdf_path.name
            )

            return []

        if not full_text.strip():

            print(
                "No text found in:",
                pdf_path.name
            )

            return []

        # -----------------------------------------
        # Create chunks
        # -----------------------------------------

        raw_chunks = split_text(
            full_text
        )

        chunks = []

        for chunk in raw_chunks:

            chunk_start = (
                chunk["start"]
            )

            chunk_end = (
                chunk["end"]
            )

            pages = []

            # Find pages that overlap this chunk
            for page_info in page_ranges:

                if (
                    chunk_start
                    < page_info["end"]
                    and
                    chunk_end
                    > page_info["start"]
                ):

                    pages.append(
                        page_info["page"]
                    )

            page_string = ", ".join(
                str(page)
                for page in pages
            )

            chunks.append(
                {
                    "text": chunk["text"],
                    "source": pdf_path.name,
                    "pages": page_string
                }
            )

        print(
            "Created",
            len(chunks),
            "chunks."
        )

        return chunks

    except Exception as error:

        print(
            "Error processing",
            pdf_path.name
        )

        print(
            error
        )

        return []


# =========================================================
# CHECK DATABASE
# =========================================================

chunk_count = conn.execute(
    """
    SELECT COUNT(*)
    FROM chunks
    """
).fetchone()[0]


# =========================================================
# INGEST PDFs IF DATABASE IS EMPTY
# =========================================================

if chunk_count == 0:

    print(
        "Database is empty."
    )

    print(
        "Processing PDFs..."
    )

    pdf_files = list(
        Path("documents").glob(
            "*.pdf"
        )
    )

    if not pdf_files:

        print(
            "No PDF files found "
            "inside documents/."
        )

    else:

        all_chunks = []

        for pdf_path in pdf_files:

            pdf_chunks = process_pdf(
                pdf_path
            )

            all_chunks.extend(
                pdf_chunks
            )


        # -----------------------------------------
        # Create embeddings
        # -----------------------------------------

        if all_chunks:

            print(
                "\nCreating embeddings..."
            )

            chunk_texts = [
                chunk["text"]
                for chunk in all_chunks
            ]

            embeddings = (
                embedding_model.encode(
                    chunk_texts,
                    show_progress_bar=True
                )
            )


            # -----------------------------------------
            # Store chunks in PostgreSQL
            # -----------------------------------------

            print(
                "Saving chunks to PostgreSQL..."
            )

            for chunk, embedding in zip(
                all_chunks,
                embeddings
            ):

                conn.execute(
                    """
                    INSERT INTO chunks
                    (
                        text,
                        source,
                        pages,
                        embedding
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        chunk["text"],
                        chunk["source"],
                        chunk["pages"],
                        Vector(embedding)
                    )
                )

            conn.commit()

            print(
                "Stored",
                len(all_chunks),
                "chunks."
            )

else:

    print(
        "Loaded",
        chunk_count,
        "chunks from PostgreSQL."
    )


# =========================================================
# QUESTION LOOP
# =========================================================

while True:

    print()

    question = input(
        "Ask a question "
        "(or type 'exit' to quit): "
    )

    if (
        question.lower().strip()
        == "exit"
    ):

        break

    if not question.strip():
        continue


    # =====================================================
    # RETRIEVAL
    # =====================================================

    results = retrieve(
        conn,
        question,
        top_k=3
    )


    if not results:

        print(
            "\nNo relevant chunks found."
        )

        continue


    # =====================================================
    # SHOW RETRIEVED SOURCES
    # =====================================================

    print(
        "\nRETRIEVED SOURCES:\n"
    )

    for (
        text,
        source,
        pages,
        score
    ) in results:

        print(
            "Source:",
            source,
            "| Pages:",
            pages,
            "| Reranker score:",
            round(score, 3)
        )


    # =====================================================
    # BUILD CONTEXT
    # =====================================================

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


    # =====================================================
    # BUILD GEMINI PROMPT
    # =====================================================

    prompt = f"""
You are answering a question using only the supplied
document context.

Do not use outside knowledge.

If the context does not contain enough information to
answer the question, say:

"I could not find enough information in the provided documents."

When possible, mention the source document and page number.

CONTEXT:

{context}


QUESTION:

{question}


ANSWER:
"""


    # =====================================================
    # GEMINI
    # =====================================================

    try:

        response = (
            client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
        )

        print(
            "\nANSWER:\n"
        )

        print(
            response.text
        )

    except Exception as error:

        # Retrieval still works even when Gemini
        # quota/API is unavailable.
        print(
            "\nGemini could not generate "
            "an answer."
        )

        print(
            "Retrieval completed successfully."
        )

        print(
            "\nGemini error:"
        )

        print(
            error
        )


# =========================================================
# CLOSE DATABASE
# =========================================================

conn.close()