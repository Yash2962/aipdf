import React, { useState } from "react";
import axios from "axios";
import BACKEND_URL from "./config";

function App() {
  const [files, setFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isAsking, setIsAsking] = useState(false);

  const handleFileChange = (e) => {
    setFiles(Array.from(e.target.files));
  };

  const handleUpload = async () => {
    if (!files.length) {
      setUploadStatus("Please select at least one PDF.");
      return;
    }

    try{
      setIsUploading(true);
      setUploadStatus("Uploading and processing PDFs...");

      const formData = new FormData();
      files.forEach((file) => formData.append("files", file));

      const res = await axios.post(`${BACKEND_URL}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      if (res.data.status === "ok") {
        setUploadStatus(
          `Uploaded ${res.data.uploaded.length} file(s) successfully.`
        );
      } else {
        setUploadStatus("Upload finished, but unexpected response.");
      }
    } catch (err) {
      console.error(err);
      setUploadStatus("Error during upload. Check console.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleAsk = async () => {
    if (!question.trim()) return;

    try {
      setIsAsking(true);
      setAnswer("Thinking...");

      const res = await axios.post(`${BACKEND_URL}/ask`, {
        question,
      });

      setAnswer(res.data.answer);
    } catch (err) {
      console.error(err);
      setAnswer("Error while getting answer. Check console.");
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div
      style={{
        fontFamily: "sans-serif",
        padding: "20px",
        maxWidth: "800px",
        margin: "0 auto",
      }}
    >
      <h1>AI PDF Assistant</h1>

      {/* Upload Section */}
      <section
        style={{
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
        }}
      >
        <h2>1. Upload PDFs</h2>
        <input
          type="file"
          accept="application/pdf"
          multiple
          onChange={handleFileChange}
        />
        <br />
        <button
          onClick={handleUpload}
          disabled={isUploading || !files.length}
          style={{ marginTop: "10px" }}
        >
          {isUploading ? "Uploading..." : "Upload & Process"}
        </button>
        {uploadStatus && <p style={{ marginTop: "10px" }}>{uploadStatus}</p>}
      </section>

      {/* Q&A Section */}
      <section
        style={{
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <h2>2. Ask Questions</h2>
        <textarea
          rows="3"
          style={{ width: "100%", padding: "8px" }}
          placeholder="Ask something based on the uploaded PDFs..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <br />
        <button
          onClick={handleAsk}
          disabled={isAsking || !question.trim()}
          style={{ marginTop: "10px" }}
        >
          {isAsking ? "Getting answer..." : "Ask"}
        </button>

        {answer && (
          <div
            style={{
              marginTop: "16px",
              background: "#f9f9f9",
              padding: "12px",
              borderRadius: "4px",
              whiteSpace: "pre-wrap",
            }}
          >
            <strong>Answer:</strong>
            <br />
            {answer}
          </div>
        )}
      </section>
    </div>
  );
}

export default App;
