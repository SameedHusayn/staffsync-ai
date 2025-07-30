import chromadb
import os
from dotenv import load_dotenv
import PyPDF2
from langchain_text_splitters import RecursiveCharacterTextSplitter
import tiktoken

load_dotenv()
policy_files = os.getenv("POLICIES")
if not policy_files:
    raise RuntimeError(
        "No policies are set. "
        "Copy .env.example → .env and put a comma-separated list of your policy files (PDF or TXT)."
    )

# Initialize ChromaDB client
chroma_client = chromadb.Client()


def get_or_create_policy_collection(collection_name="hr_policies"):
    # This will create the collection if it doesn't exist, or return it if it does
    return chroma_client.get_or_create_collection(name=collection_name)


def extract_text_from_file(file_path):
    if file_path.lower().endswith(".pdf"):
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(
                [page.extract_text() for page in reader.pages if page.extract_text()]
            )
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()


def get_token_count(text):
    """Count tokens using the cl100k tokenizer (used by GPT models)"""
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def chunk_text(text, source_file, chunk_size=100, chunk_overlap=20):
    """
    Smaller chunks with some overlap for this specific use case
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size * 4,  # Smaller chunks
        chunk_overlap=chunk_overlap * 4,  # Add some overlap
        length_function=get_token_count,
        # Add more specific separators for policy documents
        separators=["\n\n", "\n", ".", ":", ";", " ", ""],
    )

    chunks = text_splitter.split_text(text)

    # Create document objects with metadata
    documents = []
    for i, chunk in enumerate(chunks):
        # Skip very small chunks that might be headers
        if len(chunk.strip()) < 20:
            continue

        doc = {
            "text": chunk,
            "metadata": {
                "source": source_file,
                "chunk": i,
                "token_count": get_token_count(chunk),
            },
            "id": f"{os.path.basename(source_file)}_{i}",
        }
        documents.append(doc)

    return documents


def load_policies(collection=None):
    """
    Load policies from the specified files, chunk them efficiently,
    and add them to the ChromaDB collection.
    """
    if collection is None:
        collection = get_or_create_policy_collection()

    # Check if collection already has documents
    if collection.count() > 0:
        print("Policy collection already has documents; skipping load.")
        return

    all_chunks = []
    for file_path in policy_files.split(","):
        file_path = file_path.strip()
        text = extract_text_from_file(file_path)
        chunks = chunk_text(text, file_path)
        all_chunks.extend(chunks)

    # Prepare data for chromadb batch insert
    docs = [chunk["text"] for chunk in all_chunks]
    metadatas = [chunk["metadata"] for chunk in all_chunks]
    ids = [chunk["id"] for chunk in all_chunks]

    # Add chunks to collection
    collection.add(documents=docs, metadatas=metadatas, ids=ids)
    print(
        f"Loaded {len(docs)} chunks from {len(policy_files.split(','))} policy files into ChromaDB."
    )


def search_policy(
    query: str,
    n_results: int = 3,
    collection=None,
    similarity_cutoff: float = 1.0,
    extract_relevant: bool = True,
    max_context_window: int = 100,
):
    if collection is None:
        collection = get_or_create_policy_collection()

    query_terms = [t.lower() for t in query.split() if len(t) > 3]

    res = collection.query(
        query_texts=[query],
        n_results=max(n_results * 5, 10),  # fetch plenty first
        include=["documents", "metadatas", "distances"],
    )

    docs, metas, dists = res["documents"][0], res["metadatas"][0], res["distances"][0]

    # keep only hits under the cutoff, then sort by distance ↑
    keep = [
        (doc, meta, dist)
        for doc, meta, dist in zip(docs, metas, dists)
        if dist <= similarity_cutoff
    ]
    keep.sort(key=lambda x: x[2])  # nearest first
    keep = keep[:n_results]  # top‑k after filtering

    if not keep:
        return []  # or raise / return “no match”

    results = []
    for doc, meta, _dist in keep:
        paragraphs = [p for p in doc.split("\n\n") if p.strip()] or [doc]
        para_scores = [
            (p, sum(word in p.lower() for word in query_terms)) for p in paragraphs
        ]
        best_para = max(para_scores, key=lambda x: x[1])[0]
        results.append((best_para.strip(), meta))

    return results
