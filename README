# DocuQuery

A full-stack Retrieval-Augmented Generation (RAG) application for asking questions about PDF documents.

Users can upload PDFs through the web interface, ask natural-language questions, and receive answers grounded in retrieved document passages. The system combines semantic vector search, PostgreSQL full-text search, CrossEncoder reranking, and Gemini answer generation.

## Live Demo

Frontend:

https://lu07ana.github.io/docuquery/

> **Note:** The frontend is permanently hosted on GitHub Pages, while the FastAPI backend currently runs in GitHub Codespaces for demonstration purposes. The backend must be running for document upload, retrieval, and question answering to work.

---

## Features

- Upload PDF documents directly through the browser
- Automatic text extraction and sentence-aware chunking
- Local document embeddings using `all-MiniLM-L6-v2`
- Semantic search using PostgreSQL + pgvector
- PostgreSQL full-text keyword retrieval
- Hybrid candidate retrieval
- CrossEncoder reranking using `ms-marco-MiniLM-L-6-v2`
- Gemini-based answer generation
- Source document and page references
- Retrieval-only developer mode for inspecting ranked chunks
- PDF duplicate detection using SHA-256 hashes
- Delete indexed documents and their associated chunks
- FastAPI REST API
- React + Vite frontend
- Retrieval evaluation with Hit@K and MRR

---

## Architecture

```mermaid
flowchart TD

    A[PDF Upload] --> B[PyMuPDF Text Extraction]
    B --> C[Text Cleaning]
    C --> D[Sentence-Aware Chunking]

    D --> E[MiniLM Embeddings]
    E --> F[(PostgreSQL + pgvector)]

    G[User Question] --> H[Semantic Retrieval]
    G --> I[Keyword Retrieval]

    F --> H
    F --> I

    H --> J[Candidate Merge]
    I --> J

    J --> K[CrossEncoder Reranking]
    K --> L[Top 3 Context Chunks]

    L --> M[Gemini]
    G --> M

    M --> N[Answer + Sources]
```

The deployed application currently uses:

```text
GitHub Pages
    ↓
React frontend
    ↓
GitHub Codespaces
    ↓
FastAPI
    ↓
Render PostgreSQL + pgvector
    ↓
Gemini API
```

---

## Retrieval Pipeline

### 1. PDF processing

PDF text is extracted using PyMuPDF.

The extracted text is cleaned and split into sentence-aware chunks of approximately 1000 characters with around 200 characters of overlap.

Each chunk stores:

- document source
- page number(s)
- chunk text
- embedding vector

Uploaded PDFs are processed temporarily. After indexing, the application stores the extracted chunks and embeddings rather than depending on the original PDF file.

### 2. Embeddings

Each chunk is embedded using:

```text
sentence-transformers/all-MiniLM-L6-v2
```

The model produces a:

```text
384-dimensional embedding
```

for every chunk.

These embeddings are stored in PostgreSQL using:

```sql
VECTOR(384)
```

provided by the pgvector extension.

### 3. Semantic retrieval

When the user asks a question, the question is embedded with the same MiniLM model.

PostgreSQL then performs cosine-distance search:

```sql
ORDER BY embedding <=> query_embedding
```

The semantic retriever returns the top candidate chunks.

### 4. Keyword retrieval

Semantic search can sometimes miss passages containing important exact terms.

To compensate for this, DocuQuery also performs PostgreSQL full-text search using:

```sql
to_tsvector(...)
to_tsquery(...)
```

Candidate terms are weighted based on their document frequency so rarer terms receive more importance.

### 5. Hybrid retrieval

Candidates from:

```text
semantic retrieval
+
keyword retrieval
```

are merged and deduplicated.

Instead of manually assigning semantic/keyword weighting, both retrieval methods are used primarily for candidate generation.

### 6. CrossEncoder reranking

The merged candidate set is reranked using:

```text
cross-encoder/ms-marco-MiniLM-L-6-v2
```

Unlike the embedding model, which encodes the question and passage independently, the CrossEncoder evaluates the pair jointly:

```text
(question, passage)
```

and assigns a relevance score.

The three highest-ranked passages are passed to the language model.

### 7. Answer generation

The final context and question are sent to Gemini.

The prompt instructs Gemini to answer using only the retrieved context and to state when the provided context is insufficient.

The frontend displays:

- generated answer
- source document
- source pages
- retrieval scores

---

## Retrieval Evaluation

Retrieval performance was evaluated on a manually labelled benchmark containing 50 questions.

Each question contains:

```json
{
  "question": "...",
  "expected_answer": "...",
  "expected_source": "...",
  "expected_pages": [...]
}
```

A retrieval result is considered relevant when the expected source matches and at least one expected page occurs in the retrieved chunk.

### Current results

| Metric | Result |
|---|---:|
| Hit@1 | 34% |
| Hit@3 | 58% |
| Hit@5 | 76% |
| MRR | 0.491 |
| Average retrieval latency | ~1.65 s |

An earlier vector-only baseline on a smaller 10-question test achieved:

| Metric | Vector-only baseline | Hybrid + reranker |
|---|---:|---:|
| Hit@1 | 30% | 30% |
| Hit@3 | 40% | 70% |
| Hit@5 | 60% | 90% |
| MRR | 0.383 | 0.512 |

The results showed that adding keyword candidate retrieval and CrossEncoder reranking substantially improved the ability to recover relevant evidence in the top results.

One motivating failure case was the question:

> What object does Santiago place under the fishing line across his shoulders to cushion it?

Vector-only retrieval failed to rank the correct passage highly, while keyword retrieval recovered the relevant passage and the CrossEncoder promoted it to the top result.

---

## Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- PyMuPDF
- SentenceTransformers
- PyTorch
- Google Gemini API

### Retrieval and Storage

- PostgreSQL
- pgvector
- PostgreSQL Full-Text Search
- MiniLM embeddings
- CrossEncoder reranking

### Frontend

- React
- Vite
- JavaScript
- CSS

### Development / Deployment

- Docker Compose
- GitHub
- GitHub Actions
- GitHub Pages
- GitHub Codespaces
- Render PostgreSQL

---

## Project Structure

```text
docuquery/
│
├── api.py
│   FastAPI endpoints
│
├── retrieval.py
│   Hybrid retrieval and CrossEncoder reranking
│
├── ingestion.py
│   PDF extraction, chunking and database ingestion
│
├── rag.py
│   Original command-line RAG application
│
├── evaluation.py
│   Retrieval evaluation
│
├── generation_evaluation.py
│   Answer generation experiments
│
├── evaluation_questions.json
│   Retrieval benchmark
│
├── generation_questions_10.json
│   Generation evaluation questions
│
├── requirements.txt
│
├── docker-compose.yml
│
├── documents/
│
└── frontend/
    ├── src/
    │   ├── App.jsx
    │   └── App.css
    │
    ├── package.json
    └── vite.config.js
```

---

## Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/Lu07ana/docuquery.git
cd docuquery
```

### 2. Create a Python environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create:

```text
.env
```

using `.env.example` as a template:

```env
GEMINI_API_KEY=your_gemini_api_key

DATABASE_URL=postgresql://raguser:ragpassword@localhost:5432/ragdb

ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Never commit the real `.env` file.

### 5. Start PostgreSQL

```bash
docker compose up -d
```

### 6. Start FastAPI

```bash
uvicorn api:app --host 127.0.0.1 --port 8000
```

The API is available at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

### 7. Start React

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

---

## API

Main endpoints:

```text
GET     /health
GET     /documents

POST    /upload
POST    /retrieve
POST    /ask

DELETE  /documents/{stored_name}
```

### `/ask`

Performs:

```text
Question
→ hybrid retrieval
→ CrossEncoder reranking
→ top 3 chunks
→ Gemini
→ answer + sources
```

### `/retrieve`

Runs the complete retrieval pipeline without calling Gemini.

This endpoint is also exposed through the frontend's Developer Mode and is useful for debugging retrieval independently of generation.

---

## Current Limitations

- Scanned/image-only PDFs require OCR and are not currently supported.
- Retrieval currently searches across all indexed documents.
- The Codespaces backend is intended for temporary demonstrations rather than permanent production hosting.
- Transformer models introduce higher memory usage and cold-start time.
- Retrieval quality depends on PDF text extraction quality and chunk boundaries.
- The application currently stores indexed text and embeddings rather than retaining uploaded PDFs permanently.

---

## Planned Improvements

- Select individual documents before asking questions
- Add persistent production backend hosting
- Add vector indexes for faster large-scale retrieval
- Add PostgreSQL full-text indexes
- Add database connection pooling
- Support incremental document versioning
- Improve evaluation dataset size
- Add automated backend tests
- Add OCR support for scanned PDFs
- Improve retrieval latency
- Add document preview and source navigation

---

## Why I Built This

This project was built to explore the complete RAG pipeline rather than relying on a prebuilt retrieval framework.

The implementation covers the individual stages explicitly:

```text
document extraction
→ chunking
→ embeddings
→ vector storage
→ semantic retrieval
→ lexical retrieval
→ candidate fusion
→ reranking
→ context construction
→ answer generation
→ retrieval evaluation
```

This made it possible to inspect retrieval failures, compare different retrieval strategies, and quantitatively evaluate improvements instead of treating the RAG pipeline as a black box.

---

## License

This project is intended for educational and portfolio purposes.