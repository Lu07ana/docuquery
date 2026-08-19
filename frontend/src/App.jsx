import { useEffect, useState } from "react";
import "./App.css";


const API_URL =
  import.meta.env.VITE_API_URL
  || "http://127.0.0.1:8000";

const MAX_PDF_SIZE = 50 * 1024 * 1024;


function App() {

  // =====================================================
  // STATE
  // =====================================================

  const [question, setQuestion] = useState("");

  const [answer, setAnswer] = useState("");

  const [sources, setSources] = useState([]);

  const [retrievedChunks, setRetrievedChunks] = useState([]);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState("");

  const [apiOnline, setApiOnline] = useState(false);

  const [developerMode, setDeveloperMode] = useState(false);

  const [showDetails, setShowDetails] = useState(false);


  // Document upload state

  const [documents, setDocuments] = useState([]);

  const [uploading, setUploading] = useState(false);

  const [uploadError, setUploadError] = useState("");

  const [uploadSuccess, setUploadSuccess] = useState("");

  const [dragActive, setDragActive] = useState(false);

  const [deletingDocument, setDeletingDocument] = useState("");


  // =====================================================
  // INITIAL PAGE LOAD
  // =====================================================

  useEffect(() => {

    async function initialize() {

      await checkHealth();

      await loadDocuments();

    }

    initialize();

  }, []);


  // =====================================================
  // CHECK BACKEND
  // =====================================================

  async function checkHealth() {

    try {

      const response = await fetch(
        `${API_URL}/health`
      );

      setApiOnline(
        response.ok
      );

    } catch {

      setApiOnline(false);

    }

  }


  // =====================================================
  // LOAD INDEXED DOCUMENTS
  // =====================================================

  async function loadDocuments() {

    try {

      const response = await fetch(
        `${API_URL}/documents`
      );


      if (!response.ok) {
        return;
      }


      const data =
        await response.json();


      setDocuments(
        data.documents || []
      );

    } catch {

      // The API status indicator already shows
      // whether the backend is reachable.

    }

  }

  // =====================================================
  // DELETE DOCUMENT
  // =====================================================

  async function deleteDocument(document) {

    const confirmed = window.confirm(
      `Delete "${document.filename}"?\n\n`
      + "This will remove the PDF and all of its indexed chunks."
    );


    if (!confirmed) {
      return;
    }


    setDeletingDocument(
      document.stored_name
    );

    setUploadError("");

    setUploadSuccess("");


    try {

      const response = await fetch(
        `${API_URL}/documents/${encodeURIComponent(document.stored_name)}`,
        {
          method: "DELETE"
        }
      );


      const data =
        await response.json();


      if (!response.ok) {

        throw new Error(
          data.detail
          || "Could not delete document."
        );

      }


      setUploadSuccess(
        `${document.filename} deleted successfully.`
      );


      // Remove the deleted document from the
      // sidebar immediately.
      await loadDocuments();


      // Remove old displayed results that may
      // refer to the deleted PDF.

      setAnswer("");

      setSources([]);

      setRetrievedChunks([]);


    } catch (error) {

      setUploadError(
        createFriendlyError(
          error.message
        )
      );


    } finally {

      setDeletingDocument("");

    }

  }

  // =====================================================
  // FRIENDLY ERROR MESSAGES
  // =====================================================

  function createFriendlyError(message) {

    const lowerMessage =
      message.toLowerCase();


    if (
      lowerMessage.includes("quota")
      ||
      lowerMessage.includes("resource_exhausted")
      ||
      lowerMessage.includes("429")
    ) {

      return (
        "Answer generation is temporarily unavailable "
        + "because the Gemini usage limit has been reached. "
        + "Document retrieval is still available in Developer mode."
      );

    }


    if (
      lowerMessage.includes("failed to fetch")
    ) {

      return (
        "The backend is not reachable. "
        + "Make sure FastAPI is running."
      );

    }


    return message;

  }


  // =====================================================
  // UPLOAD PDF
  // =====================================================

  async function uploadPdf(file) {

    if (!file) {
      return;
    }


    // Check extension

    if (
      !file.name
        .toLowerCase()
        .endsWith(".pdf")
    ) {

      setUploadError(
        "Please choose a PDF file."
      );

      return;

    }


    // Check size

    if (
      file.size > MAX_PDF_SIZE
    ) {

      setUploadError(
        "The PDF is too large. Maximum size is 50 MB."
      );

      return;

    }


    setUploading(true);

    setUploadError("");

    setUploadSuccess("");


    try {

      const formData =
        new FormData();


      formData.append(
        "file",
        file
      );


      const response = await fetch(
        `${API_URL}/upload`,
        {
          method: "POST",
          body: formData
        }
      );


      const data =
        await response.json();


      if (!response.ok) {

        throw new Error(
          data.detail
          || "Upload failed."
        );

      }


      setUploadSuccess(
        `${data.filename} indexed successfully `
        + `(${data.chunk_count} chunks).`
      );


      await loadDocuments();


    } catch (error) {

      setUploadError(
        createFriendlyError(
          error.message
        )
      );


    } finally {

      setUploading(false);

    }

  }


  // =====================================================
  // FILE INPUT
  // =====================================================

  function handleFileChange(event) {

    const file =
      event.target.files[0];


    uploadPdf(
      file
    );


    // Allows selecting the same file again later

    event.target.value = "";

  }


  // =====================================================
  // DRAG AND DROP
  // =====================================================

  function handleDragOver(event) {

    event.preventDefault();

    setDragActive(true);

  }


  function handleDragLeave(event) {

    event.preventDefault();

    setDragActive(false);

  }


  function handleDrop(event) {

    event.preventDefault();

    setDragActive(false);


    const file =
      event.dataTransfer.files[0];


    uploadPdf(
      file
    );

  }


  // =====================================================
  // ASK — RETRIEVAL + GEMINI
  // =====================================================

  async function askQuestion() {

    if (!question.trim()) {
      return;
    }


    setLoading(true);

    setError("");

    setAnswer("");

    setSources([]);

    setRetrievedChunks([]);

    setShowDetails(false);


    try {

      const response = await fetch(
        `${API_URL}/ask`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            question: question
          })
        }
      );


      const data =
        await response.json();


      if (!response.ok) {

        throw new Error(
          data.detail
          || "Something went wrong."
        );

      }


      setAnswer(
        data.answer
      );

      setSources(
        data.sources || []
      );


    } catch (error) {

      setError(
        createFriendlyError(
          error.message
        )
      );


    } finally {

      setLoading(false);

    }

  }


  // =====================================================
  // RETRIEVAL ONLY — NO GEMINI
  // =====================================================

  async function retrieveOnly() {

    if (!question.trim()) {
      return;
    }


    setLoading(true);

    setError("");

    setAnswer("");

    setSources([]);

    setRetrievedChunks([]);

    setShowDetails(true);


    try {

      const response = await fetch(
        `${API_URL}/retrieve`,
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            question: question
          })
        }
      );


      const data =
        await response.json();


      if (!response.ok) {

        throw new Error(
          data.detail
          || "Something went wrong."
        );

      }


      setRetrievedChunks(
        data.results || []
      );


    } catch (error) {

      setError(
        createFriendlyError(
          error.message
        )
      );


    } finally {

      setLoading(false);

    }

  }


  // =====================================================
  // ENTER TO ASK
  // SHIFT + ENTER FOR NEW LINE
  // =====================================================

  function handleKeyDown(event) {

    if (
      event.key === "Enter"
      &&
      !event.shiftKey
    ) {

      event.preventDefault();

      askQuestion();

    }

  }


  // =====================================================
  // EXAMPLE QUESTION
  // =====================================================

  function useExampleQuestion() {

    setQuestion(
      "At what four depths does Santiago set his fishing baits?"
    );

  }


  // =====================================================
  // PAGE
  // =====================================================

  return (

    <div className="app-shell">


      {/* =================================================
          HEADER
      ================================================= */}

      <header className="topbar">

        <div className="brand">

          <div className="brand-icon">
            D
          </div>

          <div>

            <h1>
              DocuQuery
            </h1>

            <p>
              Hybrid RAG document assistant
            </p>

          </div>

        </div>


        <div
          className={
            apiOnline
              ? "status online"
              : "status offline"
          }
        >

          <span className="status-dot" />

          {
            apiOnline
              ? "API online"
              : "API offline"
          }

        </div>

      </header>


      {/* =================================================
          MAIN LAYOUT
      ================================================= */}

      <div className="layout">


        {/* ===============================================
            MAIN CONTENT
        =============================================== */}

        <main className="main-content">


          {/* =============================================
              QUESTION AREA
          ============================================= */}

          <section className="hero-card">

            <div className="hero-heading">

              <span className="eyebrow">
                DOCUMENT QUESTION ANSWERING
              </span>

              <h2>
                Ask your documents
              </h2>

              <p>
                Upload PDFs and ask questions using semantic
                retrieval, keyword search, cross-encoder
                reranking and Gemini.
              </p>

            </div>


            <div className="question-input-wrapper">

              <textarea
                value={question}

                onChange={
                  (event) =>
                    setQuestion(
                      event.target.value
                    )
                }

                onKeyDown={
                  handleKeyDown
                }

                placeholder={
                  documents.length > 0
                    ? "Ask something about your documents..."
                    : "Upload a PDF, then ask a question..."
                }

                rows="4"
              />


              <div className="question-footer">

                <button
                  className="example-button"
                  onClick={
                    useExampleQuestion
                  }
                >

                  Try an example

                </button>


                <button
                  className="ask-button"
                  onClick={
                    askQuestion
                  }
                  disabled={
                    loading
                    ||
                    !question.trim()
                  }
                >

                  {
                    loading
                      ? (
                        <>
                          <span className="spinner" />
                          Working...
                        </>
                      )
                      : (
                        <>
                          Ask
                          <span>
                            →
                          </span>
                        </>
                      )
                  }

                </button>

              </div>

            </div>

          </section>


          {/* =============================================
              LOADING
          ============================================= */}

          {
            loading && (

              <div className="loading-card">

                <span className="spinner dark" />

                <div>

                  <strong>
                    Searching documents
                  </strong>

                  <p>
                    Retrieving and ranking the most
                    relevant passages...
                  </p>

                </div>

              </div>

            )
          }


          {/* =============================================
              ERROR
          ============================================= */}

          {
            error && (

              <div className="error-card">

                <div className="error-icon">
                  !
                </div>

                <div>

                  <strong>
                    Request could not be completed
                  </strong>

                  <p>
                    {error}
                  </p>

                </div>

              </div>

            )
          }


          {/* =============================================
              ANSWER
          ============================================= */}

          {
            answer && (

              <section className="result-card">

                <div className="section-heading">

                  <span className="section-icon">
                    ✦
                  </span>

                  <h3>
                    Answer
                  </h3>

                </div>


                <p className="answer-text">
                  {answer}
                </p>


                {/* SOURCES */}

                {
                  sources.length > 0 && (

                    <div className="sources">

                      <span className="sources-label">
                        Sources
                      </span>


                      <div className="source-pills">

                        {
                          sources.map(
                            (
                              source,
                              index
                            ) => (

                              <div
                                className="source-pill"
                                key={index}
                              >

                                <span>
                                  ▣
                                </span>

                                {
                                  source.source
                                }

                                <span className="source-page">
                                  p. {source.pages}
                                </span>

                              </div>

                            )
                          )
                        }

                      </div>

                    </div>

                  )
                }


                {/* RETRIEVAL DETAILS */}

                {
                  sources.length > 0 && (

                    <div className="details-container">

                      <button
                        className="details-toggle"
                        onClick={
                          () =>
                            setShowDetails(
                              !showDetails
                            )
                        }
                      >

                        Retrieval details

                        <span>
                          {
                            showDetails
                              ? "▲"
                              : "▼"
                          }
                        </span>

                      </button>


                      {
                        showDetails && (

                          <div className="source-details">

                            {
                              sources.map(
                                (
                                  source,
                                  index
                                ) => (

                                  <div
                                    className="detail-row"
                                    key={index}
                                  >

                                    <div>

                                      <strong>
                                        Rank {index + 1}
                                      </strong>

                                      <span>
                                        {
                                          source.source
                                        }
                                        {" · "}
                                        page {
                                          source.pages
                                        }
                                      </span>

                                    </div>


                                    <span className="score">
                                      Score {
                                        source.reranker_score
                                      }
                                    </span>

                                  </div>

                                )
                              )
                            }

                          </div>

                        )
                      }

                    </div>

                  )
                }

              </section>

            )
          }


          {/* =============================================
              RETRIEVAL-ONLY RESULTS
          ============================================= */}

          {
            retrievedChunks.length > 0 && (

              <section className="result-card">

                <div className="section-heading">

                  <span className="section-icon">
                    ◇
                  </span>

                  <div>

                    <h3>
                      Retrieved context
                    </h3>

                    <p>
                      Gemini was not called.
                    </p>

                  </div>

                </div>


                <div className="chunk-list">

                  {
                    retrievedChunks.map(
                      (
                        chunk,
                        index
                      ) => (

                        <article
                          className="chunk-card"
                          key={index}
                        >

                          <div className="chunk-header">

                            <div>

                              <strong>
                                Rank {index + 1}
                              </strong>

                              <span>
                                {
                                  chunk.source
                                }
                                {" · "}
                                page {
                                  chunk.pages
                                }
                              </span>

                            </div>


                            <span className="score">
                              {
                                chunk.reranker_score
                              }
                            </span>

                          </div>


                          <p>
                            {chunk.text}
                          </p>

                        </article>

                      )
                    )
                  }

                </div>

              </section>

            )
          }

        </main>


        {/* ===============================================
            SIDEBAR
        =============================================== */}

        <aside className="sidebar">


          {/* =============================================
              DOCUMENT UPLOAD
          ============================================= */}

          <div className="sidebar-card document-card">

            <div className="documents-heading">

              <div>

                <span className="sidebar-label">
                  DOCUMENTS
                </span>

                <h3>
                  Document index
                </h3>

              </div>


              <span className="document-count">
                {documents.length}
              </span>

            </div>


            {/* UPLOAD ZONE */}

            <label
              className={
                dragActive
                  ? "upload-zone dragging"
                  : "upload-zone"
              }

              onDragOver={
                handleDragOver
              }

              onDragLeave={
                handleDragLeave
              }

              onDrop={
                handleDrop
              }
            >

              <input
                type="file"

                accept=".pdf,application/pdf"

                onChange={
                  handleFileChange
                }

                disabled={
                  uploading
                }
              />


              {
                uploading
                  ? (
                    <span className="upload-spinner" />
                  )
                  : (
                    <span className="upload-icon">
                      +
                    </span>
                  )
              }


              <strong>

                {
                  uploading
                    ? "Indexing PDF..."
                    : "Upload PDF"
                }

              </strong>


              <span className="upload-description">

                {
                  uploading
                    ? "Extracting text and creating embeddings"
                    : "Click or drag a PDF here"
                }

              </span>


              {
                !uploading && (

                  <span className="upload-limit">
                    Maximum 50 MB
                  </span>

                )
              }

            </label>


            {/* UPLOAD SUCCESS */}

            {
              uploadSuccess && (

                <div className="upload-message success">

                  <span>
                    ✓
                  </span>

                  <p>
                    {uploadSuccess}
                  </p>

                </div>

              )
            }


            {/* UPLOAD ERROR */}

            {
              uploadError && (

                <div className="upload-message failure">

                  <span>
                    !
                  </span>

                  <p>
                    {uploadError}
                  </p>

                </div>

              )
            }


            {/* DOCUMENT LIST */}

            <div className="document-list">

              {
                documents.length === 0
                  ? (

                    <div className="empty-documents">

                      <div className="empty-document-icon">
                        PDF
                      </div>

                      <p>
                        No PDFs indexed yet.
                      </p>

                    </div>

                  )
                  : (

                    documents.map(
                      (
                        document,
                        index
                      ) => (

                        <div
                          className="document-item"
                          key={
                            document.stored_name
                            || index
                          }
                        >

                          <div className="document-icon">
                            PDF
                          </div>


                          <div className="document-info">

                            <strong
                              title={
                                document.filename
                              }
                            >
                              {
                                document.filename
                              }
                            </strong>


                            <span>

                              {
                                document.page_count
                                  ? `${document.page_count} pages · `
                                  : ""
                              }

                              {
                                document.chunk_count
                              } chunks

                            </span>

                          </div>


                          <div className="document-actions">
                            <span className="indexed-check">
                              ✓
                            </span>
                            <button 
                              className="delete-document-button"
                              
                              onClick={
                                () =>
                                  deleteDocument(
                                    document
                                  )
                              }
                              disabled={
                                deletingDocument
                                === document.stored_name
                              }
                              
                              title={
                                `Delete ${document.filename}`
                              }
                            >
                              {
                                deletingDocument
                                === document.stored_name
                                ? "..."
                                : "Delete"
                              }

                            </button>
                       

                          </div>
                        
                    

                        </div>

                      )
                    )

                  )
              }

            </div>

          </div>


          {/* =============================================
              PIPELINE
          ============================================= */}

          <div className="sidebar-card">

            <span className="sidebar-label">
              SYSTEM
            </span>

            <h3>
              RAG pipeline
            </h3>


            <div className="pipeline">

              <div className="pipeline-item">

                <span>
                  1
                </span>

                <div>

                  <strong>
                    Hybrid retrieval
                  </strong>

                  <p>
                    Semantic + keyword
                  </p>

                </div>

              </div>


              <div className="pipeline-line" />


              <div className="pipeline-item">

                <span>
                  2
                </span>

                <div>

                  <strong>
                    CrossEncoder
                  </strong>

                  <p>
                    Candidate reranking
                  </p>

                </div>

              </div>


              <div className="pipeline-line" />


              <div className="pipeline-item">

                <span>
                  3
                </span>

                <div>

                  <strong>
                    Gemini
                  </strong>

                  <p>
                    Answer generation
                  </p>

                </div>

              </div>

            </div>

          </div>


          {/* =============================================
              DEVELOPER MODE
          ============================================= */}

          <div className="sidebar-card developer-card">

            <div className="developer-header">

              <div>

                <span className="sidebar-label">
                  DEVELOPER
                </span>

                <h3>
                  Debug tools
                </h3>

              </div>


              <label className="switch">

                <input
                  type="checkbox"

                  checked={
                    developerMode
                  }

                  onChange={
                    () =>
                      setDeveloperMode(
                        !developerMode
                      )
                  }
                />

                <span className="slider" />

              </label>

            </div>


            {
              developerMode && (

                <div className="developer-options">

                  <p>
                    Inspect retrieval results without
                    making a Gemini API request.
                  </p>


                  <button
                    className="retrieve-button"

                    onClick={
                      retrieveOnly
                    }

                    disabled={
                      loading
                      ||
                      !question.trim()
                    }
                  >

                    Retrieve only

                  </button>

                </div>

              )
            }

          </div>

        </aside>

      </div>


      {/* =================================================
          FOOTER
      ================================================= */}

      <footer>

        Built with React · FastAPI · PostgreSQL · pgvector

      </footer>

    </div>

  );

}


export default App;