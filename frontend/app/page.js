"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import "./globals.css";

export default function Home() {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [visualSummary, setVisualSummary] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [health, setHealth] = useState("checking");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => setHealth(d.ollama === "connected" ? "ok" : "bad"))
      .catch(() => setHealth("bad"));
  }, []);

  const handleFile = useCallback((f) => {
    if (f && f.type.startsWith("video/")) {
      setFile(f);
      setError("");
      setResult("");
      setVisualSummary("");
    } else if (f) {
      setError("Please upload a video file.");
    }
  }, []);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      handleFile(e.dataTransfer.files[0]);
    },
    [handleFile]
  );

  const analyze = async () => {
    if (!file) return;
    setLoading(true);
    setStatus("Uploading video...");
    setResult("");
    setVisualSummary("");
    setError("");

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("/api/analyze", { method: "POST", body: form });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const clean = line.replace(/^data:\s*/, "").trim();
          if (!clean) continue;
          try {
            const msg = JSON.parse(clean);
            switch (msg.type) {
              case "status":
                setStatus(msg.content);
                break;
              case "visual_summary":
                setVisualSummary(msg.content);
                break;
              case "result":
                setResult(msg.content);
                break;
              case "error":
                setError(msg.content);
                break;
            }
          } catch {
            // ignore parse errors on partial chunks
          }
        }
      }
    } catch (e) {
      setError("Failed to connect to the backend. Is it running?");
    } finally {
      setLoading(false);
    }
  };

  const copyText = (text) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="container">
      <h1>#HashtagCity</h1>
      <p className="subtitle">
        Upload a short video and get AI-generated titles & hashtags
      </p>

      <div className="health">
        <span className={`health-dot ${health}`} />
        {health === "ok" && "Ollama connected"}
        {health === "bad" && "Ollama not reachable — make sure it's running"}
        {health === "checking" && "Checking Ollama..."}
      </div>

      <div
        className={`upload-area ${dragOver ? "drag-over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/*"
          onChange={(e) => handleFile(e.target.files[0])}
        />
        <div className="upload-icon">&#x1F3AC;</div>
        <p className="upload-text">
          <strong>Click to upload</strong> or drag & drop a video
        </p>
        <p className="upload-text" style={{ fontSize: "0.85rem", marginTop: 4 }}>
          MP4, MOV, WebM — Shorts, Reels, TikToks
        </p>
        {file && <div className="file-name">{file.name}</div>}
      </div>

      <button
        className="analyze-btn"
        disabled={!file || loading}
        onClick={analyze}
      >
        {loading ? "Analyzing..." : "Analyze Video"}
      </button>

      {(loading || status) && (
        <div className="status-bar">
          {loading && <div className="spinner" />}
          {status}
        </div>
      )}

      {error && (
        <div className="result-section error" style={{ marginTop: 20 }}>
          <pre>{error}</pre>
        </div>
      )}

      <div className="results">
        {visualSummary && (
          <div className="result-section">
            <h3>Visual Analysis</h3>
            <pre>{visualSummary}</pre>
            <button className="copy-btn" onClick={() => copyText(visualSummary)}>
              Copy
            </button>
          </div>
        )}

        {result && (
          <div className="result-section">
            <h3>Titles & Hashtags</h3>
            <pre>{result}</pre>
            <button className="copy-btn" onClick={() => copyText(result)}>
              Copy
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
