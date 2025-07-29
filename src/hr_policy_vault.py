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
    query, n_results=3, collection=None, extract_relevant=True, max_context_window=100
):
    """
    Search for policy information with enhanced relevance extraction.

    Args:
        query: The search query
        n_results: Number of chunks to retrieve
        collection: ChromaDB collection
        extract_relevant: Whether to extract only the most relevant section from each chunk
        max_context_window: Words around the query terms to extract (if extract_relevant=True)

    Returns:
        A list of relevant text sections with their metadata
    """
    if collection is None:
        collection = get_or_create_policy_collection()

    results = collection.query(query_texts=[query], n_results=n_results)

    # Return documents along with their metadata
    documents = results["documents"][0] if results["documents"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []

    if not extract_relevant:
        return list(zip(documents, metadatas))

    # Extract the most relevant parts based on query terms
    processed_results = []
    query_terms = set(term.lower() for term in query.split() if len(term) > 3)

    for doc, metadata in zip(documents, metadatas):
        # Find the most relevant paragraph
        paragraphs = [p for p in doc.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [doc]

        # Score paragraphs by query term occurrence
        scored_paragraphs = []
        for para in paragraphs:
            score = sum(1 for term in query_terms if term in para.lower())
            scored_paragraphs.append((para, score))

        # Get the most relevant paragraph
        most_relevant = (
            max(scored_paragraphs, key=lambda x: x[1])[0] if scored_paragraphs else doc
        )

        processed_results.append((most_relevant, metadata))

    return processed_results
