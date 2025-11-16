import os
import uuid
from typing import List

from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from PyPDF2 import PdfReader

from supabase import create_client, Client
from pinecone import Pinecone
from openai import OpenAI  # ✅ new OpenAI client import

# -------------------------
# Load environment variables
# -------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "pdfs")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

# ✅ Initialize OpenAI client (v1 style)
client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------------
# Initialize Supabase
# -------------------------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------
# Initialize Pinecone
# -------------------------
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)

# -------------------------
# FastAPI app + CORS
# -------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev; tighten later in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------
# Models
# -------------------------
class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


# -------------------------
# Helper functions
# -------------------------
def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    """
    Read PDF from raw bytes and extract text.
    """
    from io import BytesIO

    pdf_stream = BytesIO(file_bytes)
    reader = PdfReader(pdf_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def chunk_text(text: str, max_chars: int = 1000) -> List[str]:
    """
    Simple chunking by characters.
    """
    chunks = []
    for i in range(0, len(text), max_chars):
        chunks.append(text[i: i + max_chars])
    return chunks


def get_embedding(text: str) -> List[float]:
    """
    Get embedding using OpenAI embeddings API (v1 client).
    """
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def generate_answer(question: str, context: str) -> str:
    """
    Call OpenAI Chat API with context + user question (v1 client).
    """
    messages = [
        {
            "role": "system",
            "content": "You are an AI assistant that answers questions based on the provided PDF context.",
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion: {question}",
        },
    ]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.2,
    )

    return response.choices[0].message.content


# -------------------------
# API Endpoints
# -------------------------


@app.get("/")
def root():
    return {"message": "AI PDF Assistant backend is running"}


@app.post("/upload")
async def upload_pdfs(files: List[UploadFile] = File(...)):
    """
    1. Upload PDFs to Supabase Storage
    2. Extract text
    3. Chunk text
    4. Create embeddings and store in Pinecone
    5. Store metadata in Supabase DB (optional, simple insert)
    """
    uploaded_docs = []

    for file in files:
        file_id = str(uuid.uuid4())
        file_bytes = await file.read()

        # 1. Upload to Supabase Storage
        path_on_bucket = f"{file_id}/{file.filename}"
        res = supabase.storage.from_(SUPABASE_BUCKET).upload(
            path_on_bucket, file_bytes
        )
        print("Supabase upload response:", res)

        # 2. Extract text from PDF
        text = extract_text_from_pdf_bytes(file_bytes)

        # 3. Chunk text
        chunks = chunk_text(text, max_chars=1000)

        # 4. For each chunk, create embedding and upsert to Pinecone
        vectors = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            emb = get_embedding(chunk)
            vec_id = f"{file_id}_{i}"
            vectors.append(
                {
                    "id": vec_id,
                    "values": emb,
                    "metadata": {
                        "file_id": file_id,
                        "file_name": file.filename,
                        "chunk_index": i,
                        "text": chunk,
                    },
                }
            )

        if vectors:
            index.upsert(vectors=vectors)

        # 5. Store simple metadata in Supabase table "documents" (optional)
        try:
            supabase.table("documents").insert(
                {
                    "id": file_id,
                    "file_name": file.filename,
                    "storage_path": path_on_bucket,
                }
            ).execute()
        except Exception as e:
            print("Error inserting into Supabase documents table:", e)

        uploaded_docs.append(
            {"file_id": file_id, "file_name": file.filename, "chunks": len(chunks)}
        )

    return {"status": "ok", "uploaded": uploaded_docs}


@app.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest):
    """
    1. Create embedding of the question
    2. Query Pinecone for top similar chunks
    3. Build context from those chunks
    4. Ask OpenAI to generate an answer
    """
    question = payload.question

    # 1. Question embedding
    q_emb = get_embedding(question)

    # 2. Query Pinecone
    query_res = index.query(
        vector=q_emb,
        top_k=5,
        include_metadata=True,
    )

    # 3. Build context from retrieved chunks
    context_parts = []
    for match in query_res["matches"]:
        md = match.get("metadata", {})
        text = md.get("text", "")
        context_parts.append(text)

    context = "\n\n---\n\n".join(context_parts)

    if not context.strip():
        return AskResponse(
            answer="I could not find relevant information in the uploaded PDFs."
        )

    # 4. Call OpenAI to generate answer
    answer = generate_answer(question, context)
    return AskResponse(answer=answer)
