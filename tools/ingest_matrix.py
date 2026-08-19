import json
import glob
import os
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# 1. Initialize persistent embedded Qdrant engine on local bare-metal disk
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
qdrant_storage_path = os.path.join(base_dir, "core_geometries", "qdrant_storage")
client = QdrantClient(path=qdrant_storage_path)

collection_name = "genesis_geometries"
vector_dimension = 768  # Corrected for nomic-embed-text

# 2. Recreate collection with Cosine similarity for HNSW indexing
print(f"[DIANA OS] Initializing HNSW collection '{collection_name}' with dimension {vector_dimension}...")
if client.collection_exists(collection_name):
    client.delete_collection(collection_name)
client.create_collection(
    collection_name=collection_name,
    vectors_config=VectorParams(size=vector_dimension, distance=Distance.COSINE),
)

# 3. Batch load sovereign geometries from clean_json
json_dir = os.path.join(base_dir, "core_geometries", "clean_json")
json_files = glob.glob(os.path.join(json_dir, "*.json"))

print(f"[DIANA OS] Loading {len(json_files)} files to generate embeddings...")

def process_file(idx, file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    text = data.get("text", "")
    if not text:
        return None
        
    try:
        resp = httpx.post(
            "http://127.0.0.1:11434/api/embeddings", 
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=30.0
        )
        embedding = resp.json().get("embedding")
        if not embedding:
            return None
            
        return PointStruct(
            id=idx,
            vector=embedding,
            payload={
                "logic_id": data.get("chunk_id", f"LOGIC_{idx}"),
                "domain_tag": data.get("domain_tag", "GENERAL"),
                "raw_text": text,
                "source_file": os.path.basename(file_path)
            }
        )
    except Exception as e:
        print(f"[ERROR] Failed to embed {file_path}: {e}")
        return None

points = []
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(process_file, idx, fp): fp for idx, fp in enumerate(json_files)}
    completed = 0
    
    for future in as_completed(futures):
        pt = future.result()
        if pt:
            points.append(pt)
        completed += 1
        if completed % 100 == 0:
            print(f"[DIANA OS] Embedded {completed}/{len(json_files)} geometries...")
            # Upload in batches of 100 to prevent memory exhaustion
            client.upsert(collection_name=collection_name, points=points[-100:])

# 4. Upload any remaining batch to embedded storage
if len(points) % 100 != 0 and points:
    client.upsert(
        collection_name=collection_name,
        points=points[-(len(points) % 100):]
    )

if points:
    print(f"[SUCCESS] Ingested {len(points)} sovereign geometries into embedded HNSW storage.")
else:
    print("[WARNING] No valid vector payloads generated.")
