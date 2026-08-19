import math
import re
import os
import psycopg

from sentence_transformers import SentenceTransformer, CrossEncoder
from pgvector.psycopg import register_vector
from pgvector import Vector
from pathlib import Path
from dotenv import load_dotenv 

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    BASE_DIR / ".env"
)


DATABASE_URL = os.getenv(
    "DATABASE_URL"
)


if not DATABASE_URL:

    raise RuntimeError(
        "DATABASE_URL was not found in .env"
    )

# =========================================================
# DATABASE
# =========================================================

def connect_db():

    conn = psycopg.connect(
        DATABASE_URL
    )

    register_vector(
        conn
    )

    return conn

# =========================================================
# MODELS
# =========================================================

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

reranker = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2"
)


# =========================================================
# KEYWORD EXTRACTION
# =========================================================

def extract_keywords(question):

    words = re.findall(
        r"\b[a-zA-Z]+\b",
        question.lower()
    )

    stop_words = {
        "what", "who", "where", "when",
        "why", "how",

        "does", "do", "did",
        "is", "are", "was", "were",

        "the", "a", "an",
        "to", "of", "in", "on",
        "for", "with", "and",

        "use", "using"
    }

    return [
        word
        for word in words
        if word not in stop_words
    ]


# =========================================================
# KEYWORD WEIGHTS
# =========================================================

def get_keyword_weights(conn, keywords):

    total_chunks = conn.execute(
        "SELECT COUNT(*) FROM chunks"
    ).fetchone()[0]

    weights = {}

    for word in keywords:

        document_frequency = conn.execute(
            """
            SELECT COUNT(*)
            FROM chunks
            WHERE
                to_tsvector('english', text)
                @@ plainto_tsquery('english', %s)
            """,
            (word,)
        ).fetchone()[0]

        weight = math.log(
            (total_chunks + 1)
            / (document_frequency + 1)
        ) + 1

        weights[word] = weight

    return weights


# =========================================================
# RETRIEVAL
# =========================================================

def retrieve(conn, question, top_k=3):

    # -----------------------------------------------------
    # 1. Semantic search
    # -----------------------------------------------------

    question_embedding = embedding_model.encode(
        question
    )

    semantic_results = conn.execute(
        """
        SELECT
            id,
            text,
            source,
            pages,
            embedding <=> %s AS distance
        FROM chunks
        ORDER BY embedding <=> %s
        LIMIT 20
        """,
        (
            Vector(question_embedding),
            Vector(question_embedding)
        )
    ).fetchall()


    # -----------------------------------------------------
    # 2. Keyword search
    # -----------------------------------------------------

    keywords = extract_keywords(question)

    keyword_results = []

    if keywords:

        keyword_weights = get_keyword_weights(
            conn,
            keywords
        )

        score_parts = []
        parameters = []

        for word, weight in keyword_weights.items():

            score_parts.append(
                """
                CASE
                    WHEN
                        to_tsvector('english', text)
                        @@ plainto_tsquery(
                            'english',
                            %s
                        )
                    THEN %s
                    ELSE 0
                END
                """
            )

            parameters.extend([
                word,
                weight
            ])

        keyword_score_sql = " + ".join(
            score_parts
        )

        keyword_query = " | ".join(
            keywords
        )

        parameters.append(
            keyword_query
        )

        keyword_results = conn.execute(
            f"""
            SELECT
                id,
                text,
                source,
                pages,
                ({keyword_score_sql}) AS keyword_score
            FROM chunks
            WHERE
                to_tsvector('english', text)
                @@ to_tsquery(
                    'english',
                    %s
                )
            ORDER BY keyword_score DESC
            LIMIT 20
            """,
            parameters
        ).fetchall()


    # -----------------------------------------------------
    # 3. Merge candidates
    # -----------------------------------------------------

    candidates = {}

    for result in semantic_results:

        (
            chunk_id,
            text,
            source,
            pages,
            distance
        ) = result

        candidates[chunk_id] = {
            "text": text,
            "source": source,
            "pages": pages
        }


    for result in keyword_results:

        (
            chunk_id,
            text,
            source,
            pages,
            keyword_score
        ) = result

        if chunk_id not in candidates:

            candidates[chunk_id] = {
                "text": text,
                "source": source,
                "pages": pages
            }


    candidate_list = list(
        candidates.values()
    )

    if not candidate_list:
        return []


    # -----------------------------------------------------
    # 4. CrossEncoder reranking
    # -----------------------------------------------------

    pairs = [
        (
            question,
            candidate["text"]
        )
        for candidate in candidate_list
    ]

    rerank_scores = reranker.predict(
        pairs
    )

    for candidate, score in zip(
        candidate_list,
        rerank_scores
    ):

        candidate["score"] = float(
            score
        )


    # -----------------------------------------------------
    # 5. Final ranking
    # -----------------------------------------------------

    ranked_results = sorted(
        candidate_list,
        key=lambda item: item["score"],
        reverse=True
    )

    final_results = []

    for item in ranked_results[:top_k]:

        final_results.append(
            (
                item["text"],
                item["source"],
                item["pages"],
                item["score"]
            )
        )

    return final_results