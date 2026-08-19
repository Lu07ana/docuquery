import re

import fitz

from pgvector import Vector

from retrieval import embedding_model


CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    text = text.replace("\x00", " ")

    text = re.sub(
        r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]",
        " ",
        text
    )

    text = (
        text
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# DOCUMENT TABLE
# =========================================================

def ensure_documents_table(conn):

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id BIGSERIAL PRIMARY KEY,
            filename TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            file_hash TEXT UNIQUE,
            page_count INTEGER,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Add documents that were already in the old chunks table.
    #
    # For example, your existing oldmansea.pdf chunks existed
    # before we added the documents table.
    old_documents = conn.execute(
        """
        SELECT source, COUNT(*)
        FROM chunks
        GROUP BY source
        """
    ).fetchall()

    for source, chunk_count in old_documents:

        conn.execute(
            """
            INSERT INTO documents (
                filename,
                stored_name,
                file_hash,
                page_count,
                chunk_count
            )
            VALUES (%s, %s, NULL, NULL, %s)
            ON CONFLICT (stored_name)
            DO UPDATE SET
                chunk_count = EXCLUDED.chunk_count
            """,
            (
                source,
                source,
                chunk_count
            )
        )

    conn.commit()


# =========================================================
# EXTRACT PDF TEXT
# =========================================================

def extract_pdf(pdf_path):

    full_text = ""

    page_ranges = []

    with fitz.open(pdf_path) as document:

        if document.needs_pass:

            raise ValueError(
                "Password-protected PDFs are not supported."
            )

        page_count = len(document)

        for page_number, page in enumerate(
            document,
            start=1
        ):

            page_text = clean_text(
                page.get_text("text")
            )

            if not page_text:
                continue

            start = len(full_text)

            full_text += page_text + " "

            end = len(full_text)

            page_ranges.append(
                (
                    page_number,
                    start,
                    end
                )
            )

    return (
        full_text.strip(),
        page_ranges,
        page_count
    )


# =========================================================
# FIND PAGES USED BY A CHUNK
# =========================================================

def get_chunk_pages(
    chunk_start,
    chunk_end,
    page_ranges
):

    pages = []

    for (
        page_number,
        page_start,
        page_end
    ) in page_ranges:

        overlaps = (
            chunk_start < page_end
            and
            chunk_end > page_start
        )

        if overlaps:

            pages.append(
                page_number
            )

    return pages


# =========================================================
# CREATE SENTENCE-AWARE CHUNKS
# =========================================================

def create_chunks(
    text,
    page_ranges,
    chunk_size=CHUNK_SIZE,
    overlap=CHUNK_OVERLAP
):

    sentence_matches = list(
        re.finditer(
            r"[^.!?]+(?:[.!?]+(?=\s|$)|$)",
            text
        )
    )

    sentences = []

    for match in sentence_matches:

        sentence = match.group().strip()

        if not sentence:
            continue

        sentences.append(
            {
                "text": sentence,
                "start": match.start(),
                "end": match.end()
            }
        )

    chunks = []

    current_sentences = []

    current_length = 0


    for sentence in sentences:

        sentence_length = (
            len(sentence["text"]) + 1
        )


        # -----------------------------------------
        # Current chunk is full
        # -----------------------------------------

        if (
            current_sentences
            and
            current_length + sentence_length
            > chunk_size
        ):

            chunk_text = " ".join(
                item["text"]
                for item in current_sentences
            )

            chunk_start = (
                current_sentences[0]["start"]
            )

            chunk_end = (
                current_sentences[-1]["end"]
            )

            pages = get_chunk_pages(
                chunk_start,
                chunk_end,
                page_ranges
            )


            if len(chunk_text) >= 50:

                chunks.append(
                    {
                        "text": chunk_text,
                        "pages": pages
                    }
                )


            # -------------------------------------
            # Keep approximately 200 characters
            # for overlap
            # -------------------------------------

            overlap_sentences = []

            overlap_length = 0

            for old_sentence in reversed(
                current_sentences
            ):

                old_length = (
                    len(old_sentence["text"])
                    + 1
                )

                if (
                    overlap_sentences
                    and
                    overlap_length + old_length
                    > overlap
                ):

                    break

                overlap_sentences.append(
                    old_sentence
                )

                overlap_length += (
                    old_length
                )


            current_sentences = list(
                reversed(
                    overlap_sentences
                )
            )

            current_length = sum(
                len(item["text"]) + 1
                for item
                in current_sentences
            )


        current_sentences.append(
            sentence
        )

        current_length += (
            sentence_length
        )


    # =====================================================
    # FINAL CHUNK
    # =====================================================

    if current_sentences:

        chunk_text = " ".join(
            item["text"]
            for item
            in current_sentences
        )

        chunk_start = (
            current_sentences[0]["start"]
        )

        chunk_end = (
            current_sentences[-1]["end"]
        )

        pages = get_chunk_pages(
            chunk_start,
            chunk_end,
            page_ranges
        )


        if len(chunk_text) >= 50:

            chunks.append(
                {
                    "text": chunk_text,
                    "pages": pages
                }
            )


    return chunks


# =========================================================
# INGEST ONE PDF
# =========================================================

def ingest_pdf(
    conn,
    pdf_path,
    filename,
    stored_name,
    file_hash
):

    ensure_documents_table(
        conn
    )


    # =====================================================
    # DUPLICATE CHECK
    # =====================================================

    existing = conn.execute(
        """
        SELECT filename
        FROM documents
        WHERE file_hash = %s
        """,
        (file_hash,)
    ).fetchone()


    if existing:

        raise ValueError(
            f"This PDF has already been uploaded as "
            f"'{existing[0]}'."
        )


    # =====================================================
    # EXTRACT
    # =====================================================

    (
        full_text,
        page_ranges,
        page_count
    ) = extract_pdf(
        pdf_path
    )


    if not full_text:

        raise ValueError(
            "No readable text could be extracted "
            "from this PDF."
        )


    # =====================================================
    # CHUNK
    # =====================================================

    chunks = create_chunks(
        full_text,
        page_ranges
    )


    if not chunks:

        raise ValueError(
            "The PDF did not contain enough "
            "readable text to create chunks."
        )


    # =====================================================
    # EMBEDDINGS
    # =====================================================

    chunk_texts = [
        chunk["text"]
        for chunk in chunks
    ]


    embeddings = (
        embedding_model.encode(
            chunk_texts,
            show_progress_bar=False
        )
    )


    # =====================================================
    # DATABASE INSERT
    # =====================================================

    try:

        for chunk, embedding in zip(
            chunks,
            embeddings
        ):

            pages = ",".join(
                str(page)
                for page
                in chunk["pages"]
            )


            conn.execute(
                """
                INSERT INTO chunks (
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
                    stored_name,
                    pages,
                    Vector(
                        embedding.tolist()
                    )
                )
            )


        conn.execute(
            """
            INSERT INTO documents (
                filename,
                stored_name,
                file_hash,
                page_count,
                chunk_count
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                filename,
                stored_name,
                file_hash,
                page_count,
                len(chunks)
            )
        )


        conn.commit()


    except Exception:

        conn.rollback()

        raise


    return {
        "filename": filename,
        "stored_name": stored_name,
        "page_count": page_count,
        "chunk_count": len(chunks)
    }