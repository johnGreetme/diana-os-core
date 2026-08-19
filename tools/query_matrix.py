import httpx
import os
import sqlite3
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Resolve paths dynamically for Linux
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
qdrant_storage_path = os.path.join(base_dir, "core_geometries", "qdrant_storage")
sqlite_fallback_path = os.path.join(base_dir, "diana_matrix.db")
collection_name = "genesis_geometries"

OLLAMA_EMBEDDINGS_URL = "http://127.0.0.1:11434/api/embeddings"
EMBEDDING_MODEL = "nomic-embed-text"

def query_sovereign_matrix(query_vector: list, domain_filter: str = None, top_k: int = 5):
    """
    Executes an HNSW semantic search against embedded Qdrant storage.
    Supports strict symbolic domain filtering via payload checks.
    """
    # Instantiate locally to prevent module-level import crashes on file-lock
    client = QdrantClient(path=qdrant_storage_path)
    
    query_filter = None
    if domain_filter:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="domain_tag",
                    match=MatchValue(value=domain_filter)
                )
            ]
        )
    
    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k
    )
    
    formatted_results = []
    for hit in results.points:
        formatted_results.append({
            "score": hit.score,
            "logic_id": hit.payload.get("logic_id"),
            "domain_tag": hit.payload.get("domain_tag"),
            "raw_text": hit.payload.get("raw_text"),
            "source_file": hit.payload.get("source_file")
        })
        
    return formatted_results


def retrieve_relevant_geometries(query_text: str, domain_filter: str = None, top_k: int = 5) -> list:
    """Pre-migration compatibility wrapper for diana_mediator.

    Embeds the raw query text through the local Ollama daemon
    and runs it through query_sovereign_matrix.
    
    *LOCK CONTENTION GUARD*: If openclaw_daemon.py holds the Qdrant lock,
    this seamlessly falls back to the read-only SQLite rung (diana_matrix.db)
    to prevent file-lock crashes.
    """
    # 1. Try Qdrant Primary Path
    try:
        resp = httpx.post(
            OLLAMA_EMBEDDINGS_URL,
            json={"model": EMBEDDING_MODEL, "prompt": query_text},
            timeout=10.0
        )
        embedding = resp.json().get("embedding")
        if embedding:
            hits = query_sovereign_matrix(embedding, domain_filter=domain_filter, top_k=top_k)
            return [
                {
                    "logic_id": hit.get("logic_id"),
                    "domain_tag": hit.get("domain_tag"),
                    "source_url": hit.get("source_file") or "",
                    "raw_text": hit.get("raw_text"),
                    "similarity_score": hit.get("score")
                }
                for hit in hits
            ]
    except Exception as e:
        print(f"[DIANA MEMORY] Qdrant HNSW retrieval locked or unavailable ({e}). Falling back to Read-Only SQLite.")

    # 2. Fallback to SQLite (Read-Only Rung)
    fallback_results = []
    try:
        # Use exact match or simple LIKE based on keywords for fallback
        # In a real scenario, SQLite might use FTS5. For now, we return a degraded heuristic search.
        keywords = query_text.split()[:5]  # Take top 5 words
        conn = sqlite3.connect(sqlite_fallback_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='genesis_geometries'")
        if not cursor.fetchone():
            conn.close()
            return []
            
        sql = "SELECT logic_id, domain_tag, source_url, raw_text FROM genesis_geometries WHERE 1=1"
        params = []
        
        if domain_filter:
            sql += " AND domain_tag = ?"
            params.append(domain_filter)
            
        if keywords:
            sql += " AND (" + " OR ".join(["raw_text LIKE ?" for _ in keywords]) + ")"
            for k in keywords:
                params.append(f"%{k}%")
                
        sql += f" LIMIT {top_k}"
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        for row in rows:
            fallback_results.append({
                "logic_id": row[0],
                "domain_tag": row[1],
                "source_url": row[2],
                "raw_text": row[3],
                "similarity_score": 0.7  # Static degraded score for fallback
            })
        conn.close()
    except Exception as e:
        print(f"[DIANA MEMORY] SQLite Fallback also failed: {e}")
        
    return fallback_results

if __name__ == "__main__":
    print("[DIANA OS] Executing verification query against embedded Qdrant (with SQLite Fallback)...")
    hits = retrieve_relevant_geometries("test logic", top_k=2)
    print(f"[RESULTS] Retrieved {len(hits)} geometries successfully.")
